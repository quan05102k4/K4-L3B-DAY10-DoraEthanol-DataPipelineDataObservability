from __future__ import annotations

from pathlib import Path
from pathlib import Path
from typing import Any

from core.utils import now_utc, write_text

# Nhan hien thi + key trong metrics summary cua `evaluate_pipeline`.
_METRIC_ROWS = [
    ("Số câu hỏi đánh giá (samples)", "samples"),
    ("Retrieval Hit Rate", "retrieval_hit_rate"),
    ("Mean Token F1", "mean_token_f1"),
    ("LLM Judge Accuracy", "judge_accuracy"),
    ("Mean LLM Judge Score (1-5)", "mean_judge_score"),
    ("Chế độ judge (`llm` / `fallback_heuristic`)", "judge_mode"),
    ("Số câu dùng judge dự phòng", "judge_fallback_count"),
]

# Metric dang ti le -> in kem phan tram cho de doc.
_RATIO_KEYS = frozenset({"retrieval_hit_rate", "judge_accuracy", "stale_ratio", "max_stale_ratio"})

# Cot cua bang breakdown theo dang cau hoi (summary / authors / date / categories).
_BREAKDOWN_COLUMNS = ["samples", "retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"]

# Nhan hien thi + key trong freshness report.
_FRESHNESS_ROWS = [
    ("Đạt Freshness SLA (is_fresh)", "is_fresh"),
    ("Tổng số bản ghi", "total_rows"),
    ("Số bản ghi quá hạn (stale)", "stale_rows"),
    ("Tỷ lệ stale", "stale_ratio"),
    ("Ngưỡng stale tối đa", "max_stale_ratio"),
    ("Ngưỡng tuổi bài báo (ngày)", "freshness_threshold_days"),
    ("Tuổi lớn nhất (ngày)", "max_age_days"),
    ("Bài mới nhất", "latest_published"),
    ("Bài cũ nhất", "oldest_published"),
]

# Nhan hien thi + key cho bang doi chieu 3 trang thai (CP5).
COMPARISON_METRICS: tuple[tuple[str, str], ...] = (
    ("Số câu hỏi đánh giá (samples)", "samples"),
    ("Retrieval Hit Rate", "retrieval_hit_rate"),
    ("Mean Token F1", "mean_token_f1"),
    ("LLM Judge Accuracy", "judge_accuracy"),
    ("Mean LLM Judge Score (1-5)", "mean_judge_score"),
)

COMPARISON_HEADERS: tuple[str, ...] = (
    "Chỉ số",
    "Baseline",
    "Corrupted",
    "Repaired",
    "Δ Corrupted",
    "Mức phục hồi",
)

# (nhan, key, nguon) cua bang Quality Gate 3 trang thai; nguon = quality | freshness.
_GATE_ROWS = [
    ("Quality Gate (tổng)", "success", "quality"),
    ("Great Expectations suite", "gx_success", "quality"),
    ("Số bản ghi kiểm định", "row_count", "quality"),
    ("Expectations thất bại", "failed_expectations", "quality"),
    ("Freshness SLA (is_fresh)", "is_fresh", "freshness"),
    ("Số bản ghi quá hạn (stale)", "stale_rows", "freshness"),
    ("Tỷ lệ stale", "stale_ratio", "freshness"),
    ("Ngưỡng stale tối đa", "max_stale_ratio", "freshness"),
    ("Tuổi lớn nhất (ngày)", "max_age_days", "freshness"),
    ("Bài mới nhất", "latest_published", "freshness"),
]


def _cell(value: Any) -> str:
    """Ep mot gia tri ve text an toan cho o trong bang markdown."""
    if value is None or value == "":
        return "n/a"
    if isinstance(value, bool):
        return "PASS" if value else "FAIL"
    if isinstance(value, float):
        text = f"{value:.4f}"
    elif isinstance(value, (list, tuple, set)):
        text = ", ".join(str(item) for item in value) or "n/a"
    elif isinstance(value, dict):
        text = "; ".join(f"{key}={val}" for key, val in value.items()) or "n/a"
    else:
        text = str(value)
    # Ky tu "|" va newline se pha vo bang markdown.
    return text.replace("|", r"\|").replace("\n", " ").strip() or "n/a"


def _ratio_cell(value: Any) -> str:
    """In metric ti le duoi dang `0.9000 (90.00%)`."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _cell(value)
    return f"{float(value):.4f} ({float(value) * 100:.2f}%)"


def _value_cell(key: str, value: Any) -> str:
    return _ratio_cell(value) if key in _RATIO_KEYS else _cell(value)


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    """Dung bang markdown; rong thi ghi ro de report khong bi hut noi dung."""
    if not rows:
        return "_Không có dữ liệu._"
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def _kv_section(title: str, payload: dict[str, Any], skip: set[str] | None = None) -> list[str]:
    """Bang hai cot Truong / Gia tri cho mot dict phang."""
    skipped = skip or set()
    rows = [[f"`{key}`", _value_cell(key, value)] for key, value in payload.items() if key not in skipped]
    return [title, "", _markdown_table(["Trường", "Giá trị"], rows), ""]


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Viet markdown report cho baseline phase (CP3).

    1. Tom tat nguon du lieu / lineage tu `source_summary`.
    2. In bang metrics retrieval + evaluation, kem breakdown theo dang cau hoi
       khi `metrics["by_question_type"]` co san.
    3. In ket qua Great Expectations suite va Freshness SLA.
    4. Ghi markdown vao `report_path`.

    `source_summary` co the kem key `artifacts` (ten -> duong dan) de liet ke san
    pham cua pipeline; moi key con lai duoc in nhu mot dong Truong / Gia tri.
    """
    artifacts = dict(source_summary.get("artifacts") or {})
    by_question_type = dict(metrics.get("by_question_type") or {})
    quality_pass = bool(quality.get("success"))

    lines: list[str] = [
        "# Phase 1 — Baseline Pipeline Report",
        "",
        f"- **Thời điểm sinh báo cáo:** {now_utc().isoformat()}",
        f"- **Nguồn dữ liệu:** {_cell(source_summary.get('source_api'))}",
        f"- **Quality Gate:** {'PASS' if quality_pass else 'FAIL'}"
        f" (Great Expectations {_cell(quality.get('gx_version'))})",
        f"- **Freshness SLA:** {'PASS' if freshness.get('is_fresh') else 'FAIL'}",
        "",
    ]

    lines += _kv_section("## 1. Nguồn dữ liệu & Lineage", source_summary, skip={"artifacts"})

    lines += ["## 2. Baseline RAG Metrics", ""]
    metric_rows = [[label, _value_cell(key, metrics.get(key))] for label, key in _METRIC_ROWS]
    lines += [_markdown_table(["Chỉ số", "Giá trị"], metric_rows), ""]
    if metrics.get("ragas"):
        lines += [f"- **Ragas:** {_cell(metrics['ragas'])}", ""]

    if by_question_type:
        lines += ["### 2.1. Chi tiết theo dạng câu hỏi", ""]
        breakdown_rows = [
            [f"`{question_type}`"] + [_value_cell(column, stats.get(column)) for column in _BREAKDOWN_COLUMNS]
            for question_type, stats in by_question_type.items()
        ]
        lines += [_markdown_table(["question_type"] + _BREAKDOWN_COLUMNS, breakdown_rows), ""]

    lines += ["## 3. Data Quality Gate (Great Expectations 1.x)", ""]
    gate_rows = [
        ["Kết quả tổng (gate)", _cell(quality_pass)],
        ["Great Expectations suite", _cell(quality.get("gx_success"))],
        ["Suite name", _cell(quality.get("suite_name"))],
        ["Số bản ghi kiểm định", _cell(quality.get("row_count"))],
        ["Expectations thất bại", _cell(quality.get("failed_expectations") or "không có")],
    ]
    lines += [_markdown_table(["Hạng mục", "Giá trị"], gate_rows), ""]

    expectation_rows = [
        [
            _cell(item.get("expectation")),
            _cell(item.get("column") or "-"),
            _cell(item.get("success")),
            _cell(item.get("observed_value")),
            _cell(item.get("unexpected_count")),
        ]
        for item in quality.get("expectations") or []
    ]
    lines += [
        _markdown_table(["Expectation", "Cột", "Kết quả", "observed_value", "unexpected_count"], expectation_rows),
        "",
    ]

    lines += ["## 4. Freshness SLA", ""]
    freshness_rows = [
        [label, _value_cell(key, freshness.get(key))] for label, key in _FRESHNESS_ROWS if key in freshness
    ]
    lines += [_markdown_table(["Hạng mục", "Giá trị"], freshness_rows), ""]

    if artifacts:
        lines += ["## 5. Artifacts sinh ra", ""]
        artifact_rows = [[name, f"`{_cell(path)}`"] for name, path in artifacts.items()]
        lines += [_markdown_table(["Artifact", "Đường dẫn"], artifact_rows), ""]

    write_text(Path(report_path), "\n".join(lines).rstrip() + "\n")


def _number(value: Any) -> float | None:
    """Ep ve float de tinh delta; tra None khi gia tri khong phai so."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _delta_cell(baseline: Any, other: Any) -> str:
    """Muc chenh lech (co dau) cua mot trang thai so voi baseline."""
    base = _number(baseline)
    current = _number(other)
    if base is None or current is None:
        return "n/a"
    diff = current - base
    if base:
        return f"{diff:+.4f} ({diff / base * 100:+.2f}%)"
    return f"{diff:+.4f}"


def _recovery_cell(baseline: Any, corrupted: Any, repaired: Any) -> str:
    """Phan khoang cach `baseline - corrupted` ma repair lay lai duoc.

    100% = repaired bang dung baseline. `n/a` khi chi so khong suy giam (khong co
    khoang cach nao de phuc hoi) hoac gia tri khong phai so.
    """
    base = _number(baseline)
    broken = _number(corrupted)
    fixed = _number(repaired)
    if base is None or broken is None or fixed is None:
        return "n/a"
    gap = base - broken
    if abs(gap) < 1e-9:
        return "n/a"
    return f"{(fixed - broken) / gap * 100:.2f}%"


def _metric_cell(key: str, value: Any) -> str:
    """O gia tri cua bang doi chieu; ep so nguyen ve float de 3 cot cung dinh dang."""
    if key == "samples" or isinstance(value, bool) or not isinstance(value, (int, float)):
        return _value_cell(key, value)
    return _value_cell(key, float(value))


def build_comparison_rows(
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    metric_rows: tuple[tuple[str, str], ...] = COMPARISON_METRICS,
) -> list[list[str]]:
    """Dung cac dong cua bang doi chieu 3 trang thai (Baseline/Corrupted/Repaired).

    Gia tri trong o luon la ASCII nen dung chung duoc cho ca markdown report lan
    bang in ra console; chi phan nhan (`metric_rows`) doi theo noi hien thi.
    """
    rows: list[list[str]] = []
    for label, key in metric_rows:
        baseline = baseline_metrics.get(key)
        corrupted = corrupted_metrics.get(key)
        repaired = repaired_metrics.get(key)
        rows.append(
            [
                label,
                _metric_cell(key, baseline),
                _metric_cell(key, corrupted),
                _metric_cell(key, repaired),
                _delta_cell(baseline, corrupted),
                _recovery_cell(baseline, corrupted, repaired),
            ]
        )
    return rows


def _breakdown_rows(
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
) -> list[list[str]]:
    """So sanh hit rate / token F1 theo tung dang cau hoi tren ca 3 trang thai."""
    states = [
        dict(baseline_metrics.get("by_question_type") or {}),
        dict(corrupted_metrics.get("by_question_type") or {}),
        dict(repaired_metrics.get("by_question_type") or {}),
    ]
    question_types: list[str] = []
    for state in states:
        question_types.extend(key for key in state if key not in question_types)

    rows: list[list[str]] = []
    for question_type in question_types:
        stats = [state.get(question_type) or {} for state in states]
        samples = next((item.get("samples") for item in stats if item.get("samples") is not None), None)
        row = [f"`{question_type}`", _cell(samples)]
        for key in ("retrieval_hit_rate", "mean_token_f1"):
            row.extend(_value_cell(key, item.get(key)) for item in stats)
        rows.append(row)
    return rows


def _gate_rows(states: list[tuple[dict[str, Any], dict[str, Any]]]) -> list[list[str]]:
    """Bang Quality Gate + Freshness SLA cho 3 trang thai.

    `states` theo dung thu tu Baseline, Corrupted, Repaired; trang thai thieu
    artifact thi truyen dict rong -> o tuong ung in `n/a`.
    """
    rows: list[list[str]] = []
    for label, key, source in _GATE_ROWS:
        row = [label]
        for quality, freshness in states:
            payload = quality if source == "quality" else (freshness or quality.get("freshness") or {})
            row.append(_value_cell(key, payload.get(key)))
        rows.append(row)
    return rows


def _scenario_rows(corruption_log: dict[str, Any]) -> list[list[str]]:
    """Liet ke cac kich ban corruption da tiem, doc tu `corruption_log.json`."""
    return [
        [
            _cell(scenario.get("id")),
            f"`{_cell(scenario.get('name'))}`",
            _cell(scenario.get("label")),
            _cell(scenario.get("rows_affected")),
            _cell(scenario.get("expected_gate_impact")),
        ]
        for scenario in corruption_log.get("scenarios") or []
    ]


def _silent_failure_lines(
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> list[str]:
    """Dien giai so lieu thanh nhan xet Silent Failure va muc do phuc hoi."""
    samples = _cell(corrupted_metrics.get("samples"))
    hit = (
        baseline_metrics.get("retrieval_hit_rate"),
        corrupted_metrics.get("retrieval_hit_rate"),
        repaired_metrics.get("retrieval_hit_rate"),
    )
    f1 = (
        baseline_metrics.get("mean_token_f1"),
        corrupted_metrics.get("mean_token_f1"),
        repaired_metrics.get("mean_token_f1"),
    )
    failed = corrupted_quality.get("failed_expectations") or []

    return [
        "- **Silent Failure:** pipeline chạy trên dữ liệu bẩn **không phát sinh exception** — agent vẫn "
        f"trả lời đủ {samples}/{samples} câu hỏi và vẫn ghi ra artifact như bình thường. Nhưng Retrieval "
        f"Hit Rate rơi {_ratio_cell(hit[0])} → {_ratio_cell(hit[1])} ({_delta_cell(hit[0], hit[1])}) và "
        f"Mean Token F1 rơi {_cell(f1[0])} → {_cell(f1[1])} ({_delta_cell(f1[0], f1[1])}): hệ thống sai "
        "trong im lặng, chỉ có chỉ số mới phát hiện được.",
        "- **Tín hiệu phát hiện:** chốt kiểm soát chất lượng là thứ duy nhất báo động — Great Expectations "
        f"FAIL ở {_cell(failed) if failed else 'không có expectation nào'} và Freshness SLA "
        f"`is_fresh = {_cell(corrupted_freshness.get('is_fresh'))}` với stale_ratio "
        f"{_ratio_cell(corrupted_freshness.get('stale_ratio'))} "
        f"(ngưỡng {_ratio_cell(corrupted_freshness.get('max_stale_ratio'))}).",
        "- **Phục hồi:** sau khi ghi đè dữ liệu hỏng bằng bản dựng lại từ snapshot thô, Retrieval Hit Rate "
        f"trở lại {_ratio_cell(hit[2])} (lấy lại {_recovery_cell(*hit)} khoảng suy giảm) và Mean Token F1 "
        f"trở lại {_cell(f1[2])} (lấy lại {_recovery_cell(*f1)}); Quality Gate "
        f"`success = {_cell(repaired_quality.get('success'))}`, Freshness SLA "
        f"`is_fresh = {_cell(repaired_freshness.get('is_fresh'))}`.",
        "- **Bài học:** không thể lấy việc pipeline chạy hết mà không lỗi làm bằng chứng dữ liệu tốt. Phải "
        "đặt Data Quality Gate trước khi nạp vector store, và phải giữ snapshot thô bất biến để luôn dựng "
        "lại được trạng thái sạch.",
    ]


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
    corruption_log: dict[str, Any] | None = None,
    repair_summary: dict[str, Any] | None = None,
    baseline_quality: dict[str, Any] | None = None,
    baseline_freshness: dict[str, Any] | None = None,
    dataset_stats: dict[str, dict[str, Any]] | None = None,
    artifacts: dict[str, str] | None = None,
) -> None:
    """Viet markdown report so sanh baseline / corrupted / repaired (CP5).

    1. Bang doi chieu 3 trang thai cho metrics RAG, kem delta va muc phuc hoi.
    2. Breakdown theo dang cau hoi de chi ra dang nao hong nang nhat.
    3. Quality Gate + Freshness SLA cua ca 3 trang thai canh nhau.
    4. Thong ke dataset (row count, trung lap, summary rong, stale...).
    5. Kich ban corruption da tiem va co che repair tu snapshot tho.
    6. Phan tich Silent Failure + danh sach artifact.

    Cac tham so tu `corruption_log` tro di la tuy chon: thieu du lieu nao thi
    report bo qua section tuong ung thay vi vo.
    """
    log = dict(corruption_log or {})
    repair = dict(repair_summary or {})
    gate_states = [
        (dict(baseline_quality or {}), dict(baseline_freshness or {})),
        (dict(corrupted_quality or {}), dict(corrupted_freshness or {})),
        (dict(repaired_quality or {}), dict(repaired_freshness or {})),
    ]

    lines: list[str] = [
        "# Phase 2 — Corruption, Repair & Đối Chiếu 3 Trạng Thái",
        "",
        f"- **Thời điểm sinh báo cáo:** {now_utc().isoformat()}",
        f"- **Evaluation set dùng chung cho 3 trạng thái:** {_cell(baseline_metrics.get('samples'))} câu hỏi"
        " (không sinh lại test set để phép so sánh có nghĩa)",
        f"- **Số bản ghi:** baseline {_cell(log.get('source_rows'))}"
        f" → corrupted {_cell(log.get('corrupted_rows'))}"
        f" → repaired {_cell(repair.get('repaired_rows'))}",
        f"- **Quality Gate:** baseline {_cell(gate_states[0][0].get('success'))}"
        f" → corrupted {_cell(corrupted_quality.get('success'))}"
        f" → repaired {_cell(repaired_quality.get('success'))}",
        f"- **Dữ liệu sau repair khớp baseline:** {_cell(repair.get('matches_baseline'))}",
        "",
    ]

    lines += [
        "## 1. Bảng đối chiếu hiệu năng 3 trạng thái",
        "",
        _markdown_table(
            list(COMPARISON_HEADERS),
            build_comparison_rows(baseline_metrics, corrupted_metrics, repaired_metrics),
        ),
        "",
        "> `Δ Corrupted` = corrupted − baseline. `Mức phục hồi` = phần khoảng cách"
        " `baseline − corrupted` mà repair lấy lại được (100% = trở lại đúng baseline,"
        " `n/a` = chỉ số không suy giảm nên không có gì để phục hồi).",
        "",
        f"- Chế độ judge: baseline `{_cell(baseline_metrics.get('judge_mode'))}`,"
        f" corrupted `{_cell(corrupted_metrics.get('judge_mode'))}`,"
        f" repaired `{_cell(repaired_metrics.get('judge_mode'))}`.",
        "",
    ]

    breakdown_rows = _breakdown_rows(baseline_metrics, corrupted_metrics, repaired_metrics)
    if breakdown_rows:
        lines += [
            "### 1.1. Chi tiết theo dạng câu hỏi",
            "",
            _markdown_table(
                [
                    "question_type",
                    "samples",
                    "HitRate Baseline",
                    "HitRate Corrupted",
                    "HitRate Repaired",
                    "TokenF1 Baseline",
                    "TokenF1 Corrupted",
                    "TokenF1 Repaired",
                ],
                breakdown_rows,
            ),
            "",
        ]

    lines += [
        "## 2. Quality Gate & Freshness SLA",
        "",
        _markdown_table(["Hạng mục", "Baseline", "Corrupted", "Repaired"], _gate_rows(gate_states)),
        "",
    ]

    if dataset_stats:
        states = [dict(dataset_stats.get(name) or {}) for name in ("baseline", "corrupted", "repaired")]
        stat_keys: list[str] = []
        for state in states:
            stat_keys.extend(key for key in state if key not in stat_keys)
        lines += [
            "## 3. Thống kê dataset 3 trạng thái",
            "",
            _markdown_table(
                ["Chỉ tiêu", "Baseline", "Corrupted", "Repaired"],
                [[f"`{key}`"] + [_value_cell(key, state.get(key)) for state in states] for key in stat_keys],
            ),
            "",
        ]

    scenario_rows = _scenario_rows(log)
    if scenario_rows:
        lines += [
            "## 4. Kịch bản corruption đã tiêm",
            "",
            f"- Seed: `{_cell(log.get('seed'))}` (cố định để mọi lần chạy tiêm đúng một bộ bản ghi).",
            f"- Tổng số thay đổi: {_cell(log.get('total_change_records'))} bản ghi"
            f" (xóa {_cell(log.get('rows_removed'))}, thêm {_cell(log.get('rows_added'))},"
            f" sửa {_cell(log.get('rows_modified'))}).",
            "",
            _markdown_table(["#", "Kịch bản", "Mô tả", "Rows", "Tác động kỳ vọng lên gate"], scenario_rows),
            "",
        ]

    if repair:
        lines += [
            "## 5. Cơ chế phục hồi (Idempotent Repair)",
            "",
            _markdown_table(
                ["Trường", "Giá trị"],
                [[f"`{key}`", _value_cell(key, value)] for key, value in repair.items() if not isinstance(value, dict)],
            ),
            "",
            "- Repair **không vá từng ô dữ liệu hỏng** mà dựng lại toàn bộ dataset từ snapshot thô bất biến"
            " rồi ghi đè: cùng một snapshot luôn cho ra cùng một kết quả (idempotent), chạy lại nhiều lần"
            " không tích lũy thêm sai lệch.",
            "",
        ]

    lines += ["## 6. Phân tích Silent Failure & Kết luận", ""]
    lines += _silent_failure_lines(
        baseline_metrics,
        corrupted_metrics,
        repaired_metrics,
        corrupted_quality,
        repaired_quality,
        corrupted_freshness,
        repaired_freshness,
    )
    lines += [""]

    if artifacts:
        lines += [
            "## 7. Artifacts sinh ra",
            "",
            _markdown_table(["Artifact", "Đường dẫn"], [[name, f"`{_cell(path)}`"] for name, path in artifacts.items()]),
            "",
        ]

    write_text(Path(report_path), "\n".join(lines).rstrip() + "\n")
