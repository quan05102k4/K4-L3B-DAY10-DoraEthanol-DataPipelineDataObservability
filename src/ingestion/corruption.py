from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import random
from typing import Any, Iterable

import pandas as pd

from core.utils import now_utc, write_json
from ingestion.cleaning import build_embedding_text

# Seed co dinh -> moi lan chay tiem dung mot bo row, nho do CP4/CP5 so sanh
# baseline vs corrupted vs repaired tren cung mot kich ban loi.
CORRUPTION_SEED = 20261010

# Ti le row bi tac dong cho tung kich ban. Rieng DROP_LATEST_RATIO tinh tren
# dataset goc, cac ti le con lai tinh tren phan con lai sau khi drop.
DROP_LATEST_RATIO = 0.20
BLANK_SUMMARY_RATIO = 0.15
INJECT_NOISE_RATIO = 0.20
TRUNCATE_TITLE_RATIO = 0.15
# Lon hon MAX_STALE_RATIO (0.25) cua quality gate -> Freshness SLA chac chan FAIL.
STALE_DATE_RATIO = 0.30
DUPLICATE_ROWS_RATIO = 0.10

# Title sau khi cat con duoi 8 ky tu (va duoi MIN_TITLE_CHARS = 10 cua cleaning).
TRUNCATED_TITLE_CHARS = 7

# Lui published 365 ngay -> vuot xa freshness_threshold_days (180).
STALE_SHIFT_DAYS = 365

# Chuoi rac chen vao summary: gia lap loi encoding, HTML escape sot lai, control char.
NOISE_SNIPPETS = (
    "[[&#xFFFD;&#xFFFD;]]",
    "<<<NULL>>>",
    "@@@###$$$%%%",
    "\\x00\\x01\\x02 ?????",
    "0xDEADBEEF ||| ###",
)

# Cat bot before/after khi ghi log de file log khong phinh to.
PREVIEW_CHARS = 160


def _preview(value: object) -> str:
    """Rut gon mot gia tri text truoc khi dua vao log."""
    text = "" if value is None else str(value)
    if len(text) <= PREVIEW_CHARS:
        return text
    return f"{text[:PREVIEW_CHARS]}... (+{len(text) - PREVIEW_CHARS} chars)"


def _pick_rows(rng: random.Random, labels: Iterable[Any], ratio: float) -> list[Any]:
    """Chon ngau nhien (co seed) mot ti le row; luon tiem it nhat 1 row."""
    pool = list(labels)
    if not pool:
        return []
    count = min(len(pool), max(1, round(len(pool) * ratio)))
    return sorted(rng.sample(pool, count))


def _shift_date(value: object, days: int) -> str:
    """Lui mot chuoi ngay ISO ve qua khu; gia tri khong parse duoc thi giu nguyen."""
    text = str(value or "").strip()
    try:
        parsed = date.fromisoformat(text[:10])
    except ValueError:
        fallback = pd.to_datetime(text, errors="coerce")
        if pd.isna(fallback):
            return text
        parsed = fallback.date()
    return (parsed - timedelta(days=days)).isoformat()


def _record(
    action: str,
    baseline_row: Any,
    paper_id: object,
    column: str | None = None,
    before: object = None,
    after: object = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Mot dong nhat ky: row nao, cot nao, gia tri truoc/sau khi tiem loi."""
    return {
        "action": action,
        "baseline_row": int(baseline_row),
        "paper_id": str(paper_id),
        "column": column,
        "before": None if before is None else _preview(before),
        "after": None if after is None else _preview(after),
        "note": note,
    }


def _scenario(
    scenario_id: int,
    name: str,
    label: str,
    params: dict[str, Any],
    gate_impact: str,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Gom ket qua cua mot kich ban corruption thanh mot block trong log."""
    return {
        "id": scenario_id,
        "name": name,
        "label": label,
        "params": params,
        "expected_gate_impact": gate_impact,
        "rows_affected": len(records),
        "paper_ids": sorted({item["paper_id"] for item in records}),
        "records": records,
    }


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path) -> pd.DataFrame:
    """Tiem 6 dang su co du lieu thuc te vao dataset sach (CP4).

    1. Drop latest records: bo 20% bai bao moi nhat (mat tri thuc moi).
    2. Blank summary: xoa trang tom tat o mot so dong.
    3. Inject noise: chen chuoi ky tu rac vao tom tat.
    4. Truncate title: cat tieu de xuong duoi 8 ky tu.
    5. Stale date: lui published/updated ve 365 ngay truoc.
    6. Duplicate rows: nhan doi mot so dong de tao trung lap paper_id.
    7. Rebuild `summary_chars` + `text_for_embedding` cho toan bo dataset.
    8. Ghi nhat ky chi tiet (before/after tung dong) vao `output_log_path`.

    `baseline_row` trong log la chi so row cua dataset sach dau vao, nho do
    buoc repair o CP5 doi chieu nguoc lai duoc. Dataframe tra ve da reset_index
    nen dung thang duoc cho index va quality gate.
    """
    rng = random.Random(CORRUPTION_SEED)
    # Giu nguyen nhan index goc trong suot qua trinh tiem loi -> log truy nguoc duoc.
    corrupted = df.copy().reset_index(drop=True)
    source_rows = int(len(corrupted))
    scenarios: list[dict[str, Any]] = []

    # --- 1. Drop latest records: mat 20% bai bao moi nhat --------------------
    ordered = corrupted.sort_values(["published", "paper_id"], ascending=[False, True], kind="stable")
    drop_count = min(source_rows, max(1, round(source_rows * DROP_LATEST_RATIO)))
    drop_labels = sorted(ordered.index[:drop_count])
    drop_records = [
        _record(
            "removed",
            label,
            corrupted.at[label, "paper_id"],
            column=None,
            before=corrupted.at[label, "title"],
            after=None,
            note=f"published={corrupted.at[label, 'published']} (nam trong nhom moi nhat)",
        )
        for label in drop_labels
    ]
    corrupted = corrupted.drop(index=drop_labels)
    scenarios.append(
        _scenario(
            1,
            "drop_latest_records",
            "Bo 20% bai bao moi nhat",
            {"ratio": DROP_LATEST_RATIO, "rows_selected": len(drop_labels)},
            "Row count giam va mat tri thuc moi nhat -> retrieval hit rate tut.",
            drop_records,
        )
    )

    # --- 2. Blank summary: xoa trang tom tat ---------------------------------
    blank_labels = _pick_rows(rng, corrupted.index, BLANK_SUMMARY_RATIO)
    blank_records: list[dict[str, Any]] = []
    for label in blank_labels:
        before = str(corrupted.at[label, "summary"])
        corrupted.at[label, "summary"] = ""
        blank_records.append(
            _record(
                "modified",
                label,
                corrupted.at[label, "paper_id"],
                column="summary",
                before=before,
                after="",
                note=f"summary_chars {len(before)} -> 0",
            )
        )
    scenarios.append(
        _scenario(
            2,
            "blank_summary",
            "Xoa trang summary",
            {"ratio": BLANK_SUMMARY_RATIO, "rows_selected": len(blank_labels)},
            "ExpectColumnValueLengthsToBeBetween(summary, min=30) FAIL.",
            blank_records,
        )
    )

    # --- 3. Inject noise: chen ky tu rac vao summary --------------------------
    # Bo qua row vua bi blank de moi kich ban van quan sat duoc doc lap.
    blanked = set(blank_labels)
    noise_labels = _pick_rows(rng, [label for label in corrupted.index if label not in blanked], INJECT_NOISE_RATIO)
    noise_records: list[dict[str, Any]] = []
    for label in noise_labels:
        before = str(corrupted.at[label, "summary"])
        middle = len(before) // 2
        inner = rng.choice(NOISE_SNIPPETS)
        tail = rng.choice(NOISE_SNIPPETS)
        after = f"{before[:middle]} {inner} {before[middle:]} {tail}"
        corrupted.at[label, "summary"] = after
        noise_records.append(
            _record(
                "modified",
                label,
                corrupted.at[label, "paper_id"],
                column="summary",
                before=before,
                after=after,
                note=f"chen {inner} o giua va {tail} o cuoi",
            )
        )
    scenarios.append(
        _scenario(
            3,
            "inject_noise",
            "Chen chuoi rac vao summary",
            {
                "ratio": INJECT_NOISE_RATIO,
                "rows_selected": len(noise_labels),
                "snippets": list(NOISE_SNIPPETS),
            },
            "Summary ban -> embedding lech ngu nghia, token F1 va judge score giam.",
            noise_records,
        )
    )

    # --- 4. Truncate title: cat tieu de xuong duoi 8 ky tu --------------------
    truncate_labels = _pick_rows(rng, corrupted.index, TRUNCATE_TITLE_RATIO)
    truncate_records: list[dict[str, Any]] = []
    for label in truncate_labels:
        before = str(corrupted.at[label, "title"])
        after = before[:TRUNCATED_TITLE_CHARS].strip() or "???"
        corrupted.at[label, "title"] = after
        truncate_records.append(
            _record(
                "modified",
                label,
                corrupted.at[label, "paper_id"],
                column="title",
                before=before,
                after=after,
                note=f"title_chars {len(before)} -> {len(after)} (duoi nguong 8)",
            )
        )
    scenarios.append(
        _scenario(
            4,
            "truncate_title",
            "Cat title con duoi 8 ky tu",
            {
                "ratio": TRUNCATE_TITLE_RATIO,
                "rows_selected": len(truncate_labels),
                "max_chars": TRUNCATED_TITLE_CHARS,
            },
            "Title cut -> ground truth theo title khong match, retrieval hit rate giam.",
            truncate_records,
        )
    )

    # --- 5. Stale date: lui published/updated 365 ngay ------------------------
    stale_labels = _pick_rows(rng, corrupted.index, STALE_DATE_RATIO)
    stale_records: list[dict[str, Any]] = []
    for label in stale_labels:
        before_published = str(corrupted.at[label, "published"])
        before_updated = str(corrupted.at[label, "updated"])
        before_age = int(corrupted.at[label, "age_days"])

        after_published = _shift_date(before_published, STALE_SHIFT_DAYS)
        after_updated = _shift_date(before_updated, STALE_SHIFT_DAYS)
        after_age = before_age + STALE_SHIFT_DAYS

        corrupted.at[label, "published"] = after_published
        corrupted.at[label, "updated"] = after_updated
        corrupted.at[label, "age_days"] = after_age
        stale_records.append(
            _record(
                "modified",
                label,
                corrupted.at[label, "paper_id"],
                column="published",
                before=before_published,
                after=after_published,
                note=(
                    f"updated {before_updated} -> {after_updated}; "
                    f"age_days {before_age} -> {after_age}"
                ),
            )
        )
    scenarios.append(
        _scenario(
            5,
            "stale_date",
            "Lui published ve 365 ngay truoc",
            {
                "ratio": STALE_DATE_RATIO,
                "rows_selected": len(stale_labels),
                "shift_days": STALE_SHIFT_DAYS,
            },
            "Stale ratio vuot 0.25 -> Freshness SLA is_fresh = False.",
            stale_records,
        )
    )

    # --- 6. Duplicate rows: nhan doi dong de tao trung paper_id ---------------
    duplicate_labels = _pick_rows(rng, corrupted.index, DUPLICATE_ROWS_RATIO)
    duplicate_records: list[dict[str, Any]] = []
    if duplicate_labels:
        clones = corrupted.loc[duplicate_labels].copy()
        # Nhan moi noi tiep index goc -> index van unique, chi paper_id bi trung.
        next_label = int(max(corrupted.index)) + 1
        clones.index = list(range(next_label, next_label + len(clones)))
        corrupted = pd.concat([corrupted, clones])
        for source_label, clone_label in zip(duplicate_labels, clones.index):
            duplicate_records.append(
                _record(
                    "added",
                    clone_label,
                    corrupted.at[clone_label, "paper_id"],
                    column=None,
                    before=None,
                    after=corrupted.at[clone_label, "title"],
                    note=f"nhan ban tu baseline row {int(source_label)} -> paper_id bi trung lap",
                )
            )
    scenarios.append(
        _scenario(
            6,
            "duplicate_rows",
            "Nhan doi row de tao trung lap",
            {"ratio": DUPLICATE_ROWS_RATIO, "rows_selected": len(duplicate_records)},
            "ExpectColumnValuesToBeUnique(paper_id) FAIL.",
            duplicate_records,
        )
    )

    # --- 7. Rebuild cot dan xuat theo dung cong thuc cua cleaning -------------
    corrupted["title"] = corrupted["title"].fillna("").astype(str)
    corrupted["summary"] = corrupted["summary"].fillna("").astype(str)
    corrupted["summary_chars"] = corrupted["summary"].str.len().astype("int64")
    corrupted["age_days"] = pd.to_numeric(corrupted["age_days"], errors="coerce").fillna(0).astype("int64")
    corrupted["text_for_embedding"] = [
        build_embedding_text(
            title=str(row["title"]),
            authors_joined=str(row["authors_joined"]),
            published=str(row["published"]),
            categories_joined=str(row["categories_joined"]),
            summary=str(row["summary"]),
        )
        for _, row in corrupted.iterrows()
    ]

    # --- 8. Ghi nhat ky corruption -------------------------------------------
    modified_rows = sorted(
        {
            item["baseline_row"]
            for scenario in scenarios
            for item in scenario["records"]
            if item["action"] == "modified"
        }
    )
    affected_paper_ids = sorted(
        {item["paper_id"] for scenario in scenarios for item in scenario["records"]}
    )
    payload: dict[str, Any] = {
        "generated_at": now_utc().isoformat(),
        "seed": CORRUPTION_SEED,
        "row_index_reference": "baseline_row = chi so row trong dataset sach dau vao (papers_clean).",
        "source_rows": source_rows,
        "corrupted_rows": int(len(corrupted)),
        "rows_removed": len(drop_records),
        "rows_added": len(duplicate_records),
        "rows_modified": len(modified_rows),
        "modified_rows": modified_rows,
        "scenarios_applied": len(scenarios),
        "scenario_names": [scenario["name"] for scenario in scenarios],
        "total_change_records": sum(scenario["rows_affected"] for scenario in scenarios),
        "affected_paper_ids": affected_paper_ids,
        "scenarios": scenarios,
    }
    write_json(Path(output_log_path), payload)

    return corrupted.reset_index(drop=True)
