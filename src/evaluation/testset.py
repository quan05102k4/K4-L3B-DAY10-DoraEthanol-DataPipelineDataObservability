from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from core.utils import first_sentence, normalize_whitespace, write_json
from ingestion.cleaning import UNKNOWN_AUTHORS, UNKNOWN_CATEGORY

# So cau hoi ground truth cua benchmark (CP2 yeu cau dung 10 cau).
TEST_SET_SIZE = 10

# Template cau hoi + cach lay ground truth cho tung dang bai toan.
# Chu y: cau hoi phai chua tu khoa ma `retrieval/qa.py::_extract_answer` dung de
# chon dung field metadata ("who authored", "when was", "what categories"), va
# title phai nam trong dau nhay don de `answer_question` lookup duoc exact doc.
QUESTION_SPECS: dict[str, tuple[str, Callable[[dict[str, Any]], str]]] = {
    "summary": (
        "What is the summary of the paper '{title}'?",
        lambda row: first_sentence(_text(row, "summary")),
    ),
    "authors": (
        "Who authored the paper '{title}'?",
        lambda row: _text(row, "authors_joined"),
    ),
    "date": (
        "When was the paper '{title}' published?",
        lambda row: _text(row, "published"),
    ),
    "categories": (
        "What categories does the paper '{title}' belong to?",
        lambda row: _text(row, "categories_joined"),
    ),
}
QUESTION_TYPES = tuple(QUESTION_SPECS)

# Moi paper tra loi duoc toi da 4 dang cau hoi -> can it nhat 3 paper de du 10 cau.
MIN_DOCUMENTS = math.ceil(TEST_SET_SIZE / len(QUESTION_TYPES))

# Cac cot phai co gia tri o moi row duoc chon lam ground truth.
GROUND_TRUTH_COLUMNS = ["paper_id", "title", "summary", "authors_joined", "categories_joined", "published"]


def _text(row: dict[str, Any], column: str) -> str:
    """Doc mot cot ve dang chuoi da gop khoang trang."""
    return normalize_whitespace(str(row.get(column) or ""))


def _is_usable(row: dict[str, Any]) -> bool:
    """Row chi dung lam ground truth khi day metadata va title khong pha regex."""
    if any(not _text(row, column) for column in GROUND_TRUTH_COLUMNS):
        return False
    # Title chua dau nhay don se lam regex r"'([^']+)'" trong qa.py cat sai ten bai.
    return "'" not in _text(row, "title")


def _has_placeholder(row: dict[str, Any]) -> bool:
    """Nhan biet row dung placeholder cua cleaning (ground truth kem gia tri)."""
    return _text(row, "authors_joined") == UNKNOWN_AUTHORS or _text(row, "categories_joined") == UNKNOWN_CATEGORY


def _spread_indices(total: int, size: int) -> list[int]:
    """Lay `size` vi tri rai deu tren `total` row (giu thu tu, khong random)."""
    if total <= size:
        return list(range(total))
    step = total / size
    return list(dict.fromkeys(min(total - 1, int(position * step)) for position in range(size)))


def _select_papers(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Chon cac paper dai dien: day metadata truoc, rai deu tu moi den cu."""
    usable = [row for row in df.to_dict(orient="records") if _is_usable(row)]
    # Paper co metadata thuc len dau, paper dung placeholder chi lay khi con thieu.
    ranked = [row for row in usable if not _has_placeholder(row)] + [row for row in usable if _has_placeholder(row)]

    if len(ranked) < MIN_DOCUMENTS:
        raise ValueError(
            f"Can it nhat {MIN_DOCUMENTS} paper day metadata de sinh {TEST_SET_SIZE} cau hoi, "
            f"chi tim thay {len(ranked)}."
        )
    return [ranked[index] for index in _spread_indices(len(ranked), TEST_SET_SIZE)]


def _pair_questions(papers: list[dict[str, Any]], size: int) -> list[tuple[dict[str, Any], str]]:
    """Ghep (paper, question_type) sao cho 4 dang phan bo deu va khong trung cap.

    Vong offset dau moi paper mot dang cau hoi; chi khi corpus it hon `size` paper
    thi moi quay lai paper cu nhung voi dang cau hoi khac.
    """
    pairs: list[tuple[dict[str, Any], str]] = []
    for offset in range(len(QUESTION_TYPES)):
        for position, paper in enumerate(papers):
            pairs.append((paper, QUESTION_TYPES[(position + offset) % len(QUESTION_TYPES)]))
            if len(pairs) == size:
                return pairs
    return pairs


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Sinh benchmark test set (ground truth) tu dataframe da lam sach.

    1. Kiem tra corpus con du paper day metadata (>= MIN_DOCUMENTS).
    2. Chon paper dai dien, rai deu tu bai moi nhat den bai cu nhat.
    3. Tao cau hoi phu deu 4 dang: summary / authors / date / categories.
    4. Moi row gom id, question_type, question, ground_truth, ground_truth_doc_ids.
    5. Ghi JSON vao `output_path` va tra ve list cau hoi.
    """
    if df is None or df.empty:
        raise ValueError("Dataframe rong, khong the sinh evaluation set.")

    papers = _select_papers(df)
    test_set: list[dict[str, Any]] = []

    for order, (paper, question_type) in enumerate(_pair_questions(papers, TEST_SET_SIZE), start=1):
        template, ground_truth_of = QUESTION_SPECS[question_type]
        test_set.append(
            {
                "id": f"eval_{order:03d}",
                "question_type": question_type,
                "question": template.format(title=_text(paper, "title")),
                "ground_truth": ground_truth_of(paper),
                "ground_truth_doc_ids": [_text(paper, "paper_id")],
            }
        )

    write_json(Path(output_path), test_set)
    return test_set
