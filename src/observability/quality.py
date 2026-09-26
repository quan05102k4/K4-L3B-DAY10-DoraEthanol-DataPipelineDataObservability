from __future__ import annotations

from pathlib import Path
from typing import Any

import great_expectations as gx
import great_expectations.expectations as gxe
from great_expectations.core.expectation_suite import ExpectationSuite
import pandas as pd

from core.config import Settings
from core.utils import now_utc, safe_slug, write_json

# Nguong cua Quality Gate: it hon MIN_ROWS -> dataset rong nghi van, nhieu hon
# MAX_ROWS -> nghi ngo duplicate/ghi de nhieu lan.
MIN_ROWS = 5
MAX_ROWS = 5000

# Cot bat buoc phai co gia tri, neu null thi document khong the embed / tra cuu.
REQUIRED_COLUMNS = ["paper_id", "title", "text_for_embedding"]

# Summary ngan hon nguong nay coi nhu khong con noi dung de embed.
MIN_SUMMARY_CHARS = 30

# Freshness SLA: qua 25% bai bao cu hon `freshness_threshold_days` -> gan co stale.
MAX_STALE_RATIO = 0.25

# Stage -> artifact path da khai bao san trong config (stage khac se tu sinh ten).
_STAGE_REPORTS = {
    "baseline": "baseline_quality_report",
    "corrupted": "corrupted_quality_report",
}


def _report_path(settings: Settings, report_name: str) -> Path:
    """Tra ve duong dan JSON report cho mot stage."""
    attr = _STAGE_REPORTS.get(report_name.strip().lower())
    if attr:
        return getattr(settings.paths, attr)
    return settings.paths.quality_dir / f"{safe_slug(report_name)}_quality_report.json"


def _build_suite(context) -> ExpectationSuite:
    """Dinh nghia 4 hang rao kiem dinh bat buoc cua Quality Gate."""
    suite = context.suites.add(ExpectationSuite(name="papers_quality_suite"))

    # 1. So luong ban ghi nam trong nguong cho phep.
    suite.add_expectation(
        gxe.ExpectTableRowCountToBeBetween(min_value=MIN_ROWS, max_value=MAX_ROWS)
    )

    # 2. Cac cot quan trong khong duoc null.
    for column in REQUIRED_COLUMNS:
        suite.add_expectation(gxe.ExpectColumnValuesToNotBeNull(column=column))

    # 3. Moi paper_id chi xuat hien mot lan.
    suite.add_expectation(gxe.ExpectColumnValuesToBeUnique(column="paper_id"))

    # 4. Summary phai dai toi thieu MIN_SUMMARY_CHARS ky tu.
    suite.add_expectation(
        gxe.ExpectColumnValueLengthsToBeBetween(column="summary", min_value=MIN_SUMMARY_CHARS)
    )
    return suite


def _flatten_expectation(item: dict[str, Any]) -> dict[str, Any]:
    """Rut gon mot ket qua expectation thanh dong de doc trong report."""
    kwargs = dict(item.get("kwargs") or {})
    kwargs.pop("batch_id", None)
    result = item.get("result") or {}
    return {
        "expectation": item.get("expectation_type"),
        "column": kwargs.pop("column", None),
        "success": bool(item.get("success")),
        "kwargs": kwargs,
        "observed_value": result.get("observed_value"),
        "element_count": result.get("element_count"),
        "unexpected_count": result.get("unexpected_count"),
        "partial_unexpected_list": result.get("partial_unexpected_list"),
    }


def evaluate_freshness_sla(df: pd.DataFrame, settings: Settings) -> dict[str, Any]:
    """Do ti le bai bao cu de quyet dinh `is_fresh`.

    Stale = `age_days` > `settings.freshness_threshold_days` (180). Neu ti le
    stale vuot MAX_STALE_RATIO (25%) thi gan co `is_fresh = False`.
    """
    threshold_days = settings.freshness_threshold_days
    total_rows = int(len(df))

    ages = pd.to_numeric(df.get("age_days"), errors="coerce") if "age_days" in df else pd.Series(dtype="float64")
    known_ages = ages.dropna()
    stale_rows = int((known_ages > threshold_days).sum())
    # age_days khong doc duoc cung la tin hieu xau -> tinh nhu stale.
    unknown_age_rows = total_rows - int(len(known_ages))
    stale_rows += unknown_age_rows

    stale_ratio = round(stale_rows / total_rows, 4) if total_rows else 1.0
    # Dataset rong khong the coi la tuoi moi.
    is_fresh = bool(total_rows) and stale_ratio <= MAX_STALE_RATIO

    return {
        "is_fresh": is_fresh,
        "total_rows": total_rows,
        "stale_rows": stale_rows,
        "unknown_age_rows": unknown_age_rows,
        "stale_ratio": stale_ratio,
        "max_stale_ratio": MAX_STALE_RATIO,
        "freshness_threshold_days": threshold_days,
        "max_age_days": int(known_ages.max()) if not known_ages.empty else None,
        "min_age_days": int(known_ages.min()) if not known_ages.empty else None,
        "mean_age_days": round(float(known_ages.mean()), 2) if not known_ages.empty else None,
        "evaluated_at": now_utc().isoformat(),
    }


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Chot kiem soat du lieu truoc khi nap vao Vector Database.

    1. Dung Great Expectations 1.x Ephemeral Context de validate 4 hang rao:
       row count, not-null, unique `paper_id`, do dai `summary`.
    2. Do freshness SLA bang `evaluate_freshness_sla()`.
    3. Ghi JSON report vao `data/quality/` va tra ve dict ket qua.

    Gate chi `success = True` khi ca GX suite lan freshness SLA deu pass.
    """
    # Ephemeral context: khong ghi project file, phu hop chay trong pipeline.
    context = gx.get_context(mode="ephemeral")
    data_source = context.data_sources.add_pandas(name="papers_source")
    data_asset = data_source.add_dataframe_asset(name="papers_asset")
    batch_def = data_asset.add_batch_definition_whole_dataframe("papers_batch")
    batch = batch_def.get_batch(batch_parameters={"dataframe": df})

    suite = _build_suite(context)
    validation = batch.validate(suite)
    described = validation.describe_dict()

    statistics = dict(described.get("statistics") or {})
    expectations = [_flatten_expectation(item) for item in described.get("expectations") or []]
    failed = [item["expectation"] for item in expectations if not item["success"]]

    gx_success = bool(described.get("success"))
    freshness = evaluate_freshness_sla(df, settings)

    payload: dict[str, Any] = {
        "stage": report_name,
        "success": gx_success and freshness["is_fresh"],
        "gx_success": gx_success,
        "gx_version": gx.__version__,
        "suite_name": suite.name,
        "row_count": int(len(df)),
        "statistics": statistics,
        "failed_expectations": failed,
        "expectations": expectations,
        "freshness": freshness,
        "generated_at": now_utc().isoformat(),
    }

    report_path = _report_path(settings, report_name)
    write_json(report_path, payload)
    payload["report_path"] = str(report_path)
    return payload


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Tong hop freshness report (latest/oldest published + trang thai stale)."""
    published = pd.to_datetime(df.get("published"), errors="coerce") if "published" in df else pd.Series(dtype="datetime64[ns]")
    known_published = published.dropna()

    sla = evaluate_freshness_sla(df, settings)
    payload: dict[str, Any] = {
        "latest_published": known_published.max().date().isoformat() if not known_published.empty else None,
        "oldest_published": known_published.min().date().isoformat() if not known_published.empty else None,
        "stale_rows": sla["stale_rows"],
        "total_rows": sla["total_rows"],
        "is_fresh": sla["is_fresh"],
        "stale_ratio": sla["stale_ratio"],
        "max_stale_ratio": sla["max_stale_ratio"],
        "freshness_threshold_days": sla["freshness_threshold_days"],
        "max_age_days": sla["max_age_days"],
        "generated_at": sla["evaluated_at"],
    }

    write_json(Path(report_path), payload)
    return payload
