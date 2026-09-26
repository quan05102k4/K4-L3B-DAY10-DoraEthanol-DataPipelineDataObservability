from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from html import unescape
from pathlib import Path
import re
import time
from typing import Any

import requests

from core.config import Settings
from core.utils import compact_join, normalize_whitespace, read_json, write_json

CROSSREF_ENDPOINT = "https://api.crossref.org/works"
SELECT_FIELDS = "DOI,title,abstract,author,subject,published,created,URL"
USER_AGENT = "day10-data-observability-lab/0.1 (+https://api.crossref.org)"
REQUEST_TIMEOUT_SECONDS = 30
MAX_ATTEMPTS = 3
RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

_MARKUP_RE = re.compile(r"<[^>]+>")
_ABSTRACT_LABEL_RE = re.compile(r"^abstract\s*[:.\-]?\s+", re.IGNORECASE)


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def _strip_markup(value: Any) -> str:
    """Bo the XML/HTML (vi du <jats:p>) va chuan hoa khoang trang."""
    if not value:
        return ""
    text = _MARKUP_RE.sub(" ", str(value))
    text = normalize_whitespace(unescape(text))
    stripped = _ABSTRACT_LABEL_RE.sub("", text)
    return stripped or text


def _first_text(value: Any) -> str:
    """Crossref tra ve title duoi dang list, lay phan tu dau tien hop le."""
    if isinstance(value, list):
        for item in value:
            text = _strip_markup(item)
            if text:
                return text
        return ""
    return _strip_markup(value)


def _format_author(entry: Any) -> str:
    if isinstance(entry, str):
        return normalize_whitespace(entry)
    if not isinstance(entry, dict):
        return ""
    given = normalize_whitespace(str(entry.get("given") or ""))
    family = normalize_whitespace(str(entry.get("family") or ""))
    name = compact_join([given, family], " ")
    if name:
        return name
    return normalize_whitespace(str(entry.get("name") or ""))


def _date_from_parts(node: Any) -> str:
    """Doi {"date-parts": [[2026, 5, 20]]} thanh chuoi ISO "2026-05-20"."""
    if not isinstance(node, dict):
        return ""
    parts = node.get("date-parts") or []
    if not parts or not isinstance(parts[0], list):
        return ""
    values = [int(part) for part in parts[0] if str(part).isdigit()]
    if not values:
        return ""
    year = values[0]
    month = values[1] if len(values) > 1 else 1
    day = values[2] if len(values) > 2 else 1
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return f"{year:04d}-01-01"


def _date_from_timestamp(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    raw = str(node.get("date-time") or "")[:10]
    return raw if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw) else _date_from_parts(node)


def _pick_published(item: dict) -> str:
    for key in ("published", "published-online", "published-print", "issued"):
        value = _date_from_parts(item.get(key))
        if value:
            return value
    return _date_from_timestamp(item.get("created"))


def _pick_updated(item: dict, published: str) -> str:
    for key in ("created", "deposited", "indexed"):
        value = _date_from_timestamp(item.get(key))
        if value:
            return value
    return published


def _pick_pdf_url(item: dict, fallback: str) -> str:
    for link in item.get("link") or []:
        if not isinstance(link, dict):
            continue
        content_type = str(link.get("content-type") or "").lower()
        url = str(link.get("URL") or "").strip()
        if url and "pdf" in content_type:
            return url
    return fallback


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Boc tach payload Crossref thanh danh sach `PaperRecord`.

    1. Duyet `payload["message"]["items"]`.
    2. Lay DOI, title, abstract, authors, subject, dates, URLs.
    3. Chuan hoa text (bo the <jats:*>, gop khoang trang) va bo record khong hop le.
    4. Tra ve list `PaperRecord` da khu trung lap theo `paper_id`.
    """
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, dict):
            items = message.get("items") or []
        elif isinstance(message, list):
            items = message
        else:
            items = payload.get("items") or []
    else:
        items = []

    records: list[PaperRecord] = []
    seen: set[str] = set()

    for item in items:
        if not isinstance(item, dict):
            continue

        paper_id = normalize_whitespace(str(item.get("DOI") or "")).lower()
        title = _first_text(item.get("title"))
        summary = _strip_markup(item.get("abstract"))

        # Record thieu DOI / title / abstract khong dung duoc cho RAG -> bo qua.
        if not paper_id or not title or not summary or paper_id in seen:
            continue
        seen.add(paper_id)

        authors = [name for name in (_format_author(a) for a in item.get("author") or []) if name]
        categories = [text for text in (_strip_markup(s) for s in item.get("subject") or []) if text]
        if not categories:
            categories = ["uncategorized"]

        published = _pick_published(item)
        abs_url = normalize_whitespace(str(item.get("URL") or "")) or f"https://doi.org/{paper_id}"

        records.append(
            PaperRecord(
                paper_id=paper_id,
                title=title,
                summary=summary,
                authors=authors,
                categories=categories,
                primary_category=categories[0],
                published=published,
                updated=_pick_updated(item, published),
                abs_url=abs_url,
                pdf_url=_pick_pdf_url(item, abs_url),
                comment=f"Crossref record {paper_id}",
            )
        )

    return records


def _request_crossref(settings: Settings) -> dict:
    """Goi Crossref REST API, retry co backoff cho 429/5xx."""
    params = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
        "select": SELECT_FIELDS,
        "sort": "published",
        "order": "desc",
    }
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    last_error: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(
                CROSSREF_ENDPOINT, params=params, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
            )
            if response.status_code in RETRY_STATUS_CODES:
                raise requests.HTTPError(f"Crossref returned {response.status_code}", response=response)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as error:
            last_error = error
            if attempt == MAX_ATTEMPTS:
                break
            retry_after = 0.0
            response = getattr(error, "response", None)
            if response is not None:
                try:
                    retry_after = float(response.headers.get("Retry-After", 0))
                except (TypeError, ValueError):
                    retry_after = 0.0
            time.sleep(min(max(retry_after, 2.0**attempt), 10.0))

    raise RuntimeError(f"Crossref request failed after {MAX_ATTEMPTS} attempts: {last_error}")


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Thu thap metadata tu Crossref va cat giu ban tho phuc vu data lineage.

    1. Mac dinh doc snapshot `data/raw/crossref_response.json` de ket qua on dinh;
       dat `REFRESH_SOURCE=1` trong `.env` de goi lai API that.
    2. Khi goi API that bai (mat mang, 429 Too Many Requests, 5xx) -> fallback ve
       snapshot local thay vi lam gay pipeline.
    3. Luu raw response vao `settings.paths.raw_api_response` (chi khi tai moi tu API,
       de khong pha huy ban goc dang duoc dung lam diem tua phuc hoi).
    4. Parse bang `parse_crossref_payload` va luu records vao `settings.paths.raw_records_json`.
    """
    response_path = settings.paths.raw_api_response
    snapshot_available = response_path.exists() and response_path.stat().st_size > 0
    payload: dict | None = None
    source = "snapshot"

    if settings.refresh_source or not snapshot_available:
        try:
            payload = _request_crossref(settings)
            source = "api"
        except (RuntimeError, OSError) as error:
            if not snapshot_available:
                raise RuntimeError(
                    f"Khong goi duoc Crossref API va cung khong co snapshot tai {response_path}."
                ) from error
            print(f"[ingestion] Crossref API loi ({error}); fallback sang snapshot {response_path.name}.")

    if payload is None:
        payload = read_json(response_path)

    if source == "api":
        # Raw preservation: chi ghi de khi that su co payload moi tu API.
        write_json(response_path, payload)

    records = parse_crossref_payload(payload)
    if not records:
        raise RuntimeError("Crossref payload khong sinh duoc record hop le nao.")

    write_json(settings.paths.raw_records_json, [asdict(record) for record in records])
    print(f"[ingestion] source={source} records={len(records)} -> {settings.paths.raw_records_json.name}")
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Doc JSON snapshot va map thanh `PaperRecord`.

    Chap nhan ca `crossref_records.json` (list record da boc tach) lan
    `crossref_response.json` (payload goc tu API) de buoc repair o CP5 linh hoat.
    """
    payload = read_json(path)

    if isinstance(payload, dict) or (
        isinstance(payload, list) and payload and isinstance(payload[0], dict) and "DOI" in payload[0]
    ):
        return parse_crossref_payload(payload)

    records: list[PaperRecord] = []
    for entry in payload or []:
        if not isinstance(entry, dict):
            continue
        paper_id = str(entry.get("paper_id") or "")
        if not paper_id:
            continue
        categories = [str(c) for c in entry.get("categories") or []]
        published = str(entry.get("published") or "")
        abs_url = str(entry.get("abs_url") or "")
        records.append(
            PaperRecord(
                paper_id=paper_id,
                title=str(entry.get("title") or ""),
                summary=str(entry.get("summary") or ""),
                authors=[str(a) for a in entry.get("authors") or []],
                categories=categories,
                primary_category=str(entry.get("primary_category") or (categories[0] if categories else "")),
                published=published,
                updated=str(entry.get("updated") or published),
                abs_url=abs_url,
                pdf_url=str(entry.get("pdf_url") or abs_url),
                comment=str(entry.get("comment") or f"Crossref record {paper_id}"),
            )
        )
    return records
