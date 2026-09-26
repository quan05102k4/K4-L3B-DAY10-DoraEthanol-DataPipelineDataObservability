from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from core.utils import compact_join, normalize_whitespace
from ingestion.crossref import PaperRecord

# Nguong toi thieu de mot record con dung duoc cho embedding / QA.
MIN_TITLE_CHARS = 10
MIN_SUMMARY_CHARS = 40

# Placeholder giu cot khong bao gio null -> expectation not-null o CP1 van pass.
UNKNOWN_AUTHORS = "Unknown authors"
UNKNOWN_CATEGORY = "uncategorized"

# Schema co dinh: chi giu cot scalar de CSV va JSON round-trip giong nhau
# (list authors/categories chi ton tai duoi dang *_joined).
CLEAN_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "authors_joined",
    "categories_joined",
    "primary_category",
    "published",
    "updated",
    "age_days",
    "summary_chars",
    "abs_url",
    "pdf_url",
    "text_for_embedding",
]


def build_embedding_text(
    title: str,
    authors_joined: str,
    published: str,
    categories_joined: str,
    summary: str,
) -> str:
    """Ghep 5 phan metadata thanh doan ngu canh dung de sinh vector.

    Giu nguyen thu tu Title / Authors / Published / Categories / Summary de
    buoc corruption (CP4) va repair (CP5) rebuild lai duoc y het baseline.
    """
    return "\n".join(
        [
            f"Title: {normalize_whitespace(title)}",
            f"Authors: {normalize_whitespace(authors_joined) or UNKNOWN_AUTHORS}",
            f"Published: {normalize_whitespace(published)}",
            f"Categories: {normalize_whitespace(categories_joined) or UNKNOWN_CATEGORY}",
            f"Summary: {normalize_whitespace(summary)}",
        ]
    )


def _parse_iso_date(value: object) -> date | None:
    """Doc chuoi ngay thanh `date`; tra ve None khi khong parse duoc."""
    text = normalize_whitespace(str(value or ""))
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    parsed = pd.to_datetime(text, errors="coerce", utc=True)
    return None if pd.isna(parsed) else parsed.date()


def _as_day(run_date: datetime | date) -> date:
    """Quy run_date ve ngay (UTC-naive) de tru ngay khong vuong tzinfo."""
    return run_date.date() if isinstance(run_date, datetime) else run_date


def _clean_list(values: list[str] | None) -> list[str]:
    return [text for text in (normalize_whitespace(str(item or "")) for item in values or []) if text]


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Chuan hoa `PaperRecord` thanh dataframe san sang de embed.

    1. Normalize title / summary / authors / categories (gop khoang trang).
    2. Parse published + updated ve chuoi ISO `YYYY-MM-DD`.
    3. Tinh `age_days = (run_date - published).days`.
    4. Tao cot helper: authors_joined, categories_joined, summary_chars,
       text_for_embedding.
    5. Bo row xau (thieu paper_id / title / summary / published) va khu trung
       lap theo `paper_id`.
    6. Sort moi nhat truoc roi reset index.
    """
    run_day = _as_day(run_date)
    rows: list[dict[str, object]] = []

    for record in records:
        paper_id = normalize_whitespace(str(record.paper_id or "")).lower()
        title = normalize_whitespace(record.title or "")
        summary = normalize_whitespace(record.summary or "")
        published_date = _parse_iso_date(record.published)

        # Thieu khoa, tieu de, abstract hoac ngay xuat ban -> khong dung duoc cho RAG.
        if (
            not paper_id
            or len(title) < MIN_TITLE_CHARS
            or len(summary) < MIN_SUMMARY_CHARS
            or published_date is None
        ):
            continue

        categories = _clean_list(record.categories)
        authors_joined = compact_join(_clean_list(record.authors)) or UNKNOWN_AUTHORS
        categories_joined = compact_join(categories) or UNKNOWN_CATEGORY
        primary_category = normalize_whitespace(record.primary_category or "") or (
            categories[0] if categories else UNKNOWN_CATEGORY
        )

        published = published_date.isoformat()
        updated = (_parse_iso_date(record.updated) or published_date).isoformat()
        abs_url = normalize_whitespace(record.abs_url or "") or f"https://doi.org/{paper_id}"

        rows.append(
            {
                "paper_id": paper_id,
                "title": title,
                "summary": summary,
                "authors_joined": authors_joined,
                "categories_joined": categories_joined,
                "primary_category": primary_category,
                "published": published,
                "updated": updated,
                "age_days": (run_day - published_date).days,
                "summary_chars": len(summary),
                "abs_url": abs_url,
                "pdf_url": normalize_whitespace(record.pdf_url or "") or abs_url,
                "text_for_embedding": build_embedding_text(
                    title=title,
                    authors_joined=authors_joined,
                    published=published,
                    categories_joined=categories_joined,
                    summary=summary,
                ),
            }
        )

    df = pd.DataFrame(rows, columns=CLEAN_COLUMNS)
    if df.empty:
        raise ValueError("Khong con record hop le nao sau buoc cleaning.")

    # Sort truoc khi dedupe: moi paper_id giu lai ban ghi moi nhat.
    df = df.sort_values(["published", "paper_id"], ascending=[False, True], kind="stable")
    df = df.drop_duplicates(subset="paper_id", keep="first").reset_index(drop=True)

    df["age_days"] = df["age_days"].astype("int64")
    df["summary_chars"] = df["summary_chars"].astype("int64")
    return df
