from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import pandas as pd

from core.config import Settings, load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import CLEAN_COLUMNS, MIN_TITLE_CHARS, build_clean_dataframe
from ingestion.corruption import NOISE_SNIPPETS, corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import MIN_SUMMARY_CHARS, build_freshness_report, run_data_quality_checks
from observability.reporting import COMPARISON_HEADERS, build_comparison_rows, generate_corruption_report

# Dung lai helper cua phase1 de metrics cua ca 3 trang thai co cung schema
# (breakdown theo dang cau hoi, judge_mode, duong dan tuong doi trong log).
from pipelines.phase1 import (
    _breakdown_by_question_type,
    _judge_mode,
    _relative,
    run_phase1_pipeline,
)
from retrieval.index import LocalEmbeddingIndex

# Stage cua quality gate -> quyet dinh ten file report trong data/quality/.
CORRUPTED_STAGE = "corrupted"
REPAIRED_STAGE = "repaired"

# Bang in ra console giu ASCII: stdout tren Windows khi bi pipe dung cp1252 va
# se vo neu gap dau tieng Viet (markdown report thi ghi UTF-8 nen khong sao).
CONSOLE_HEADERS = ("Metric", "Baseline", "Corrupted", "Repaired", "Delta vs Baseline", "Recovery")
CONSOLE_METRICS: tuple[tuple[str, str], ...] = (
    ("Samples", "samples"),
    ("Retrieval Hit Rate", "retrieval_hit_rate"),
    ("Mean Token F1", "mean_token_f1"),
    ("LLM Judge Accuracy", "judge_accuracy"),
    ("Mean Judge Score", "mean_judge_score"),
)

# Nhan dien summary da bi kich ban 3 (inject_noise) chen chuoi rac.
_NOISE_PATTERN = re.compile("|".join(re.escape(snippet) for snippet in NOISE_SNIPPETS))


@dataclass(frozen=True)
class BaselineState:
    """Anh baseline cua Phase 1 dung lam moc so sanh cho Phase 2."""

    clean_df: pd.DataFrame
    metrics: dict[str, Any]
    quality: dict[str, Any] | None
    freshness: dict[str, Any] | None
    mode: str


@dataclass(frozen=True)
class StageResult:
    """Ket qua do luong cua mot trang thai du lieu (corrupted hoac repaired)."""

    stage: str
    df: pd.DataFrame
    index: LocalEmbeddingIndex
    metrics: dict[str, Any]
    quality: dict[str, Any]
    freshness: dict[str, Any]


@dataclass(frozen=True)
class CorruptionFlowResult:
    """Ket qua toan tuyen Phase 2, dung lai duoc o CP6 khi demo truc tiep."""

    baseline: BaselineState
    corrupted: StageResult
    repaired: StageResult
    corruption_log: dict[str, Any]
    repair_summary: dict[str, Any]
    dataset_stats: dict[str, dict[str, Any]]
    report_path: Path


def _read_optional(path: Path) -> dict[str, Any] | None:
    """Doc JSON artifact neu co; thieu file thi tra None de report in `n/a`."""
    return read_json(path) if path.exists() else None


def _freshness_path(settings: Settings, stage: str) -> Path:
    """Freshness report rieng cho tung stage, khong ghi de ban cua baseline."""
    return settings.paths.quality_dir / f"{stage}_freshness_report.json"


def _dataset_stats(df: pd.DataFrame, settings: Settings) -> dict[str, Any]:
    """Do cac dau hieu hong o muc dataset de doi chieu 3 trang thai canh nhau."""
    titles = df["title"].fillna("").astype(str)
    summaries = df["summary"].fillna("").astype(str)
    ages = pd.to_numeric(df.get("age_days"), errors="coerce")
    published = pd.to_datetime(df.get("published"), errors="coerce")

    return {
        "rows": int(len(df)),
        "unique_paper_ids": int(df["paper_id"].nunique()),
        "duplicate_paper_ids": int(len(df) - df["paper_id"].nunique()),
        "blank_summaries": int((summaries.str.len() == 0).sum()),
        "summaries_below_min": int((summaries.str.len() < MIN_SUMMARY_CHARS).sum()),
        "noisy_summaries": int(summaries.str.contains(_NOISE_PATTERN).sum()),
        "titles_below_min": int((titles.str.len() < MIN_TITLE_CHARS).sum()),
        "stale_rows": int((ages > settings.freshness_threshold_days).sum()),
        "latest_published": published.max().date().isoformat() if published.notna().any() else None,
    }


def _console_table(headers: tuple[str, ...], rows: list[list[str]]) -> str:
    """Ve bang fixed-width de console in duoc 3 cot so sanh thang hang."""
    widths = [len(str(header)) for header in headers]
    for row in rows:
        for column, cell in enumerate(row):
            widths[column] = max(widths[column], len(str(cell)))

    border = "+" + "+".join("-" * (width + 2) for width in widths) + "+"

    def line(cells) -> str:
        return "| " + " | ".join(str(cell).ljust(widths[column]) for column, cell in enumerate(cells)) + " |"

    return "\n".join([border, line(headers), border, *(line(row) for row in rows), border])


def _print_comparison(
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
) -> list[list[str]]:
    """In bang doi chieu 3 trang thai ra console va tra lai cac dong da dung."""
    rows = build_comparison_rows(baseline_metrics, corrupted_metrics, repaired_metrics, CONSOLE_METRICS)
    print("")
    print("[corruption] BANG DOI CHIEU 3 TRANG THAI: Baseline vs Corrupted vs Repaired")
    print(_console_table(CONSOLE_HEADERS, rows))
    print(
        "[corruption] Delta = corrupted - baseline; Recovery = phan khoang cach baseline-corrupted "
        "ma repair lay lai duoc (n/a = chi so khong suy giam)."
    )
    print("")
    return rows


def _load_baseline(settings: Settings) -> BaselineState:
    """Buoc 1 - lay moc baseline: uu tien artifact cua Phase 1 da co san.

    Thieu `papers_clean.json` / `baseline_metrics.json` / test set -> chay lai
    `run_phase1_pipeline` de Phase 2 luon co moc so sanh hop le.
    """
    paths = settings.paths
    if paths.clean_json.exists() and paths.baseline_metrics.exists() and paths.eval_testset.exists():
        return BaselineState(
            clean_df=pd.DataFrame(read_json(paths.clean_json), columns=CLEAN_COLUMNS),
            metrics=read_json(paths.baseline_metrics),
            quality=_read_optional(paths.baseline_quality_report),
            freshness=_read_optional(paths.freshness_report),
            mode="reuse_phase1_artifacts",
        )

    print("[corruption] thieu artifact baseline -> chay lai phase 1 truoc khi corrupt.")
    result = run_phase1_pipeline(settings)
    return BaselineState(
        clean_df=result.clean_df,
        metrics=result.metrics,
        quality=result.quality,
        freshness=result.freshness,
        mode="rebuild_phase1",
    )


def _evaluate_stage(
    settings: Settings,
    stage: str,
    df: pd.DataFrame,
    embeddings_path: Path,
    metrics_path: Path,
    answers_path: Path,
) -> StageResult:
    """Nap mot dataset vao ChromaDB roi do lai metrics + quality gate cua no.

    Collection duoc suy ra tu `embeddings_path` (`papers-corrupted` /
    `papers-repaired`) va bi xoa truoc khi tao lai, nen moi lan chay la mot lan
    ghi de sach chu khong cong don document cu.
    """
    index = LocalEmbeddingIndex.build(df, settings=settings, embeddings_output_path=embeddings_path)
    bundle = evaluate_pipeline(
        settings=settings,
        index=index,
        # Dung dung test set cua baseline: chi co cung bo cau hoi thi so sanh moi co nghia.
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=metrics_path,
        answers_output_path=answers_path,
    )

    metrics = dict(bundle.summary)
    metrics.update(_judge_mode(bundle.answers))
    metrics["by_question_type"] = _breakdown_by_question_type(bundle.answers)
    metrics["stage"] = stage
    write_json(metrics_path, metrics)

    quality = run_data_quality_checks(df, settings, stage)
    freshness = build_freshness_report(df, settings, _freshness_path(settings, stage))
    return StageResult(stage=stage, df=df, index=index, metrics=metrics, quality=quality, freshness=freshness)


def _mismatched_columns(baseline_df: pd.DataFrame, repaired_df: pd.DataFrame) -> list[str]:
    """Liet ke cot con lech giua repaired va baseline khi chua khop tuyet doi."""
    if len(baseline_df) != len(repaired_df):
        return ["<row_count>"]
    left = baseline_df.reset_index(drop=True)
    right = repaired_df.reset_index(drop=True)
    return [
        column
        for column in left.columns
        if column in right.columns and not left[column].astype(str).equals(right[column].astype(str))
    ]


def repair_from_raw_snapshot(
    settings: Settings,
    corrupted_df: pd.DataFrame | None = None,
    baseline_df: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Phuc hoi an toan: dung lai dataset sach tu snapshot tho roi ghi de du lieu hong.

    1. Doc raw snapshot `crossref_records.json` (fallback `crossref_response.json`).
       Hai file nay chi duoc ghi o buoc ingest nen corruption khong cham vao ->
       day la nguon dang tin cay duy nhat con lai.
    2. Chay lai dung `build_clean_dataframe` cua baseline: khong va tay tung o du
       lieu hong (che loi) ma dung lai toan bo dataset tu nguon.
    3. Ghi de artifact repaired (CSV + JSON). Cung mot snapshot luon cho ra cung
       mot ket qua -> buoc nay idempotent, chay lai bao nhieu lan cung khong tich
       luy sai lech; `idempotent_rerun_identical` la bang chung kem theo.
    4. Tra ve dataframe da phuc hoi + summary de doi chieu voi baseline/corrupted.
    """
    paths = settings.paths
    snapshot_path = paths.raw_records_json if paths.raw_records_json.exists() else paths.raw_api_response
    if not snapshot_path.exists():
        raise RuntimeError(
            "Khong tim thay raw snapshot de repair: "
            f"{paths.raw_records_json} / {paths.raw_api_response}"
        )

    records = load_raw_records(snapshot_path)
    if not records:
        raise RuntimeError(f"Raw snapshot {snapshot_path.name} khong con record hop le nao de repair.")

    repaired = build_clean_dataframe(records, now_utc())
    # Dung lai lan hai tu cung snapshot -> chung minh repair la idempotent.
    rerun = build_clean_dataframe(records, now_utc())

    write_csv(repaired, paths.repaired_clean_csv)
    write_json(paths.repaired_clean_json, repaired.to_dict(orient="records"))

    summary: dict[str, Any] = {
        "repair_strategy": "rebuild_from_raw_snapshot",
        "source_snapshot": _relative(snapshot_path, paths.project_dir),
        "raw_records": len(records),
        "repaired_rows": int(len(repaired)),
        "idempotent_rerun_identical": bool(repaired.equals(rerun)),
        "repaired_collection": settings.repaired_collection_name,
        "repaired_csv": _relative(paths.repaired_clean_csv, paths.project_dir),
        "repaired_json": _relative(paths.repaired_clean_json, paths.project_dir),
        "repaired_at": now_utc().isoformat(),
    }

    if corrupted_df is not None:
        summary["corrupted_rows"] = int(len(corrupted_df))
        summary["rows_restored"] = int(len(repaired)) - int(len(corrupted_df))
    if baseline_df is not None:
        expected = baseline_df.reset_index(drop=True)
        summary["baseline_rows"] = int(len(expected))
        summary["matches_baseline"] = bool(
            list(expected.columns) == list(repaired.columns) and repaired.equals(expected)
        )
        if not summary["matches_baseline"]:
            summary["mismatched_columns"] = _mismatched_columns(expected, repaired)

    return repaired, summary


def run_corruption_flow_pipeline(settings: Settings) -> CorruptionFlowResult:
    """Chay toan tuyen Phase 2: corrupt -> do suy giam -> repair -> doi chieu (CP4 + CP5).

    1. Lay moc baseline tu Phase 1 (clean dataset + baseline metrics).
    2. Tiem 6 kich ban corruption, luu dataset ban + `corruption_log.json`.
    3. Nap du lieu ban vao collection `papers-corrupted` roi do lai metrics tren
       dung test set cu -> quan sat Silent Failure (pipeline khong loi, chi so tut).
    4. Goi `repair_from_raw_snapshot()` de ghi de du lieu hong bang ban dung lai
       tu snapshot tho ban dau.
    5. Nap lai collection `papers-repaired`, do lai metrics + quality gate.
    6. In bang so sanh 3 trang thai ra console va xuat `corruption_report.md`.
    """
    paths = settings.paths
    root = paths.project_dir

    baseline = _load_baseline(settings)
    print(
        f"[corruption] 1/6 baseline: {baseline.mode} rows={len(baseline.clean_df)} "
        f"hit_rate={baseline.metrics['retrieval_hit_rate']:.4f} "
        f"token_f1={baseline.metrics['mean_token_f1']:.4f}"
    )

    corrupted_df = corrupt_clean_dataframe(baseline.clean_df, paths.corruption_log)
    write_csv(corrupted_df, paths.corrupted_clean_csv)
    write_json(paths.corrupted_clean_json, corrupted_df.to_dict(orient="records"))
    corruption_log = read_json(paths.corruption_log)
    print(
        f"[corruption] 2/6 corrupt: scenarios={corruption_log['scenarios_applied']} "
        f"rows {corruption_log['source_rows']} -> {corruption_log['corrupted_rows']} "
        f"(removed={corruption_log['rows_removed']} added={corruption_log['rows_added']} "
        f"modified={corruption_log['rows_modified']}) -> {_relative(paths.corruption_log, root)}"
    )

    corrupted = _evaluate_stage(
        settings,
        CORRUPTED_STAGE,
        corrupted_df,
        paths.corrupted_embeddings_json,
        paths.corrupted_metrics,
        paths.corrupted_answers,
    )
    print(
        f"[corruption] 3/6 evaluate corrupted: collection={corrupted.index.collection_name} "
        f"docs={len(corrupted.index.documents)} hit_rate={corrupted.metrics['retrieval_hit_rate']:.4f} "
        f"token_f1={corrupted.metrics['mean_token_f1']:.4f} "
        f"judge_accuracy={corrupted.metrics['judge_accuracy']:.4f}"
    )
    print(
        f"[corruption]     quality gate={corrupted.quality['success']} "
        f"is_fresh={corrupted.freshness['is_fresh']} "
        f"stale_ratio={corrupted.freshness['stale_ratio']} "
        f"failed={corrupted.quality['failed_expectations']}"
    )
    print(
        "[corruption]     SILENT FAILURE: pipeline khong nem exception nao, "
        f"chi co metrics tut {corrupted.metrics['retrieval_hit_rate'] - baseline.metrics['retrieval_hit_rate']:+.4f} "
        "hit rate va quality gate bao dong."
    )

    repaired_df, repair_summary = repair_from_raw_snapshot(
        settings,
        corrupted_df=corrupted_df,
        baseline_df=baseline.clean_df,
    )
    print(
        f"[corruption] 4/6 repair: source={repair_summary['source_snapshot']} "
        f"rows {repair_summary.get('corrupted_rows')} -> {repair_summary['repaired_rows']} "
        f"matches_baseline={repair_summary.get('matches_baseline')} "
        f"idempotent={repair_summary['idempotent_rerun_identical']} "
        f"-> {repair_summary['repaired_csv']}"
    )

    repaired = _evaluate_stage(
        settings,
        REPAIRED_STAGE,
        repaired_df,
        paths.repaired_embeddings_json,
        paths.repaired_metrics,
        paths.repaired_answers,
    )
    print(
        f"[corruption] 5/6 evaluate repaired: collection={repaired.index.collection_name} "
        f"docs={len(repaired.index.documents)} hit_rate={repaired.metrics['retrieval_hit_rate']:.4f} "
        f"token_f1={repaired.metrics['mean_token_f1']:.4f} "
        f"judge_accuracy={repaired.metrics['judge_accuracy']:.4f}"
    )
    print(
        f"[corruption]     quality gate={repaired.quality['success']} "
        f"is_fresh={repaired.freshness['is_fresh']} "
        f"stale_ratio={repaired.freshness['stale_ratio']}"
    )

    _print_comparison(baseline.metrics, corrupted.metrics, repaired.metrics)

    dataset_stats = {
        "baseline": _dataset_stats(baseline.clean_df, settings),
        "corrupted": _dataset_stats(corrupted_df, settings),
        "repaired": _dataset_stats(repaired_df, settings),
    }

    artifacts = {
        "Raw snapshot (nguon repair)": repair_summary["source_snapshot"],
        "Clean baseline CSV": _relative(paths.clean_csv, root),
        "Corrupted CSV": _relative(paths.corrupted_clean_csv, root),
        "Corrupted JSON": _relative(paths.corrupted_clean_json, root),
        "Repaired CSV": _relative(paths.repaired_clean_csv, root),
        "Repaired JSON": _relative(paths.repaired_clean_json, root),
        "Corruption log": _relative(paths.corruption_log, root),
        "Baseline metrics": _relative(paths.baseline_metrics, root),
        "Corrupted metrics": _relative(paths.corrupted_metrics, root),
        "Repaired metrics": _relative(paths.repaired_metrics, root),
        "Corrupted answers": _relative(paths.corrupted_answers, root),
        "Repaired answers": _relative(paths.repaired_answers, root),
        "Corrupted quality report": _relative(Path(corrupted.quality["report_path"]), root),
        "Repaired quality report": _relative(Path(repaired.quality["report_path"]), root),
        "Corrupted freshness report": _relative(_freshness_path(settings, CORRUPTED_STAGE), root),
        "Repaired freshness report": _relative(_freshness_path(settings, REPAIRED_STAGE), root),
        "Comparison report": _relative(paths.comparison_report, root),
    }

    generate_corruption_report(
        report_path=paths.comparison_report,
        baseline_metrics=baseline.metrics,
        corrupted_metrics=corrupted.metrics,
        repaired_metrics=repaired.metrics,
        corrupted_quality=corrupted.quality,
        repaired_quality=repaired.quality,
        corrupted_freshness=corrupted.freshness,
        repaired_freshness=repaired.freshness,
        corruption_log=corruption_log,
        repair_summary=repair_summary,
        baseline_quality=baseline.quality,
        baseline_freshness=baseline.freshness,
        dataset_stats=dataset_stats,
        artifacts=artifacts,
    )
    print(f"[corruption] 6/6 report: {_relative(paths.comparison_report, root)}")

    return CorruptionFlowResult(
        baseline=baseline,
        corrupted=corrupted,
        repaired=repaired,
        corruption_log=corruption_log,
        repair_summary=repair_summary,
        dataset_stats=dataset_stats,
        report_path=paths.comparison_report,
    )


def main() -> None:
    """Entrypoint cua `script/run_corruption_flow.py`."""
    settings = load_settings()
    result = run_corruption_flow_pipeline(settings)
    print(
        "[corruption] DONE hit_rate baseline={base:.4f} -> corrupted={bad:.4f} -> repaired={fixed:.4f} "
        "| quality_gate corrupted={bad_gate} repaired={fixed_gate} | matches_baseline={matches} "
        "| report={report}".format(
            base=result.baseline.metrics["retrieval_hit_rate"],
            bad=result.corrupted.metrics["retrieval_hit_rate"],
            fixed=result.repaired.metrics["retrieval_hit_rate"],
            bad_gate=result.corrupted.quality["success"],
            fixed_gate=result.repaired.quality["success"],
            matches=result.repair_summary.get("matches_baseline"),
            report=result.report_path.name,
        )
    )
