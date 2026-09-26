from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

import pandas as pd

from core.config import Settings, load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import FALLBACK_JUDGE_REASONING, evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import PaperRecord, fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex

# Stage cua quality gate -> quyet dinh file report trong data/quality/.
BASELINE_STAGE = "baseline"

# So cau hoi lay tu test set de demo agent (chi minh hoa, khong tinh vao metrics).
DEMO_QUESTION_COUNT = 2


@dataclass(frozen=True)
class Phase1Result:
    """Ket qua baseline phase, dung lai duoc o CP4/CP5 ma khong phai doc lai file."""

    clean_df: pd.DataFrame
    index: LocalEmbeddingIndex
    test_set: list[dict[str, Any]]
    metrics: dict[str, Any]
    quality: dict[str, Any]
    freshness: dict[str, Any]
    source_summary: dict[str, Any]


def _relative(path: Path, root: Path) -> str:
    """In duong dan tuong doi so voi project dir (khong ro ri path tuyet doi)."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _load_records(settings: Settings) -> tuple[list[PaperRecord], str]:
    """Buoc 1 - Ingest: uu tien raw records da luu, chi goi lai nguon khi can.

    `REFRESH_SOURCE=1` hoac thieu `crossref_records.json` -> chay
    `fetch_source_records` (goi API that, tu fallback ve snapshot khi loi mang).
    """
    records_path = settings.paths.raw_records_json
    if not settings.refresh_source and records_path.exists():
        records = load_raw_records(records_path)
        if records:
            print(
                f"[phase1] 1/6 ingest: reuse {_relative(records_path, settings.paths.project_dir)} "
                f"records={len(records)}"
            )
            return records, "raw_records_snapshot"

    return fetch_source_records(settings), "crossref_fetch"


def _save_clean_dataset(settings: Settings, clean_df: pd.DataFrame) -> None:
    """Buoc 2 - Clean: luu song song CSV + JSON de hai dinh dang round-trip giong nhau."""
    write_csv(clean_df, settings.paths.clean_csv)
    write_json(settings.paths.clean_json, clean_df.to_dict(orient="records"))


def _load_or_build_test_set(settings: Settings, clean_df: pd.DataFrame) -> tuple[list[dict[str, Any]], str]:
    """Buoc 4 - Testset: giu nguyen bo de cu de so sanh cong bang giua cac lan chay.

    Dat `REFRESH_TEST_SET=1` khi muon sinh lai ground truth tu dataset moi.
    """
    testset_path = settings.paths.eval_testset
    if not settings.refresh_test_set and testset_path.exists():
        test_set = read_json(testset_path)
        if test_set:
            return test_set, "reused"
    return build_test_set(clean_df, testset_path), "rebuilt"


def _breakdown_by_question_type(answers: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Tong hop metric theo tung dang cau hoi de report chi ra diem yeu cu the."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in answers:
        groups.setdefault(str(item.get("question_type") or "unknown"), []).append(item)

    breakdown: dict[str, dict[str, Any]] = {}
    for question_type, items in groups.items():
        breakdown[question_type] = {
            "samples": len(items),
            "retrieval_hit_rate": round(mean(1.0 if item["retrieval_hit"] else 0.0 for item in items), 4),
            "mean_token_f1": round(mean(item["token_f1"] for item in items), 4),
            "judge_accuracy": round(mean(1.0 if item["judge"]["correct"] else 0.0 for item in items), 4),
            "mean_judge_score": round(mean(item["judge"]["score"] for item in items), 4),
        }
    return breakdown


def _answer_text(answer: Any) -> str:
    """Gom cau tra loi cua agent ve text phang.

    Model moi (vi du Gemini 3) tra `content` duoi dang list content block nen
    `run_agent_question` co the tra ve list thay vi str.
    """
    if isinstance(answer, str):
        return answer.strip()
    if isinstance(answer, list):
        parts = [
            str(block.get("text") or "") if isinstance(block, dict) else str(block) for block in answer
        ]
        return "".join(parts).strip()
    return str(answer).strip()


def _judge_mode(answers: list[dict[str, Any]]) -> dict[str, Any]:
    """Xac dinh judge_accuracy den tu LLM that hay heuristic du phong.

    `_judge_answer` im lang fallback khi LLM loi (het quota, sai model, mat mang),
    nen phai ghi ro vao metrics/report de khong doc sai con so.
    """
    fallback = sum(1 for item in answers if item["judge"]["reasoning"] == FALLBACK_JUDGE_REASONING)
    if not answers or fallback == len(answers):
        mode = "fallback_heuristic"
    elif fallback:
        mode = "mixed"
    else:
        mode = "llm"
    return {"judge_mode": mode, "judge_fallback_count": fallback}


def _demo_agent(settings: Settings, index: LocalEmbeddingIndex, test_set: list[dict[str, Any]]) -> None:
    """Demo tool-calling agent tren vai cau hoi (tuy chon, khong lam gay pipeline).

    Agent can LLM that nen buoc nay duoc bao ve: mat mang / thieu API key chi ghi
    loi vao artifact thay vi dung toan tuyen.
    """
    questions = [item["question"] for item in test_set[:DEMO_QUESTION_COUNT]]
    if not questions:
        return

    payload: dict[str, Any] = {
        "llm_provider": settings.llm_provider,
        "model_name": settings.model_name,
        "generated_at": now_utc().isoformat(),
        "answers": [],
    }
    try:
        from retrieval.agent import build_agent, run_agent_question

        agent = build_agent(settings=settings, index=index)
        for question in questions:
            answer = _answer_text(run_agent_question(agent, question))
            payload["answers"].append({"question": question, "answer": answer})
        print(f"[phase1] agent demo: {len(payload['answers'])} cau hoi")
    except Exception as error:  # noqa: BLE001 - demo khong duoc lam gay pipeline
        payload["error"] = f"{type(error).__name__}: {error}"
        print(f"[phase1] agent demo skipped: {payload['error']}")

    write_json(settings.paths.demo_answers, payload)


def run_phase1_pipeline(settings: Settings) -> Phase1Result:
    """Chay toan tuyen du lieu sach (CP3).

    1. Ingest raw records tu Crossref (hoac snapshot da luu).
    2. Clean + chuan hoa, luu `papers_clean.csv` / `papers_clean.json`.
    3. Index ChromaDB collection `papers-baseline` bang MiniLM embeddings.
    4. Sinh (hoac dung lai) benchmark test set 10 cau.
    5. Danh gia baseline: Retrieval Hit Rate, Token F1, LLM judge.
    6. Great Expectations quality gate + Freshness SLA, roi xuat
       `data/reports/phase1_report.md`.
    """
    paths = settings.paths
    root = paths.project_dir

    records, source_mode = _load_records(settings)

    clean_df = build_clean_dataframe(records, now_utc())
    _save_clean_dataset(settings, clean_df)
    print(
        f"[phase1] 2/6 clean: rows={len(clean_df)} dropped={len(records) - len(clean_df)} "
        f"-> {_relative(paths.clean_csv, root)}"
    )

    index = LocalEmbeddingIndex.build(clean_df, settings=settings, embeddings_output_path=paths.embeddings_json)
    print(
        f"[phase1] 3/6 index: collection={index.collection_name} docs={len(index.documents)} "
        f"-> {_relative(paths.chroma_dir, root)}"
    )

    test_set, testset_mode = _load_or_build_test_set(settings, clean_df)
    print(
        f"[phase1] 4/6 testset: {testset_mode} questions={len(test_set)} "
        f"-> {_relative(paths.eval_testset, root)}"
    )

    bundle = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=paths.eval_testset,
        metrics_output_path=paths.baseline_metrics,
        answers_output_path=paths.baseline_answers,
    )
    # Bo sung breakdown theo dang cau hoi roi ghi lai de artifact khop voi report.
    metrics = dict(bundle.summary)
    metrics.update(_judge_mode(bundle.answers))
    metrics["by_question_type"] = _breakdown_by_question_type(bundle.answers)
    write_json(paths.baseline_metrics, metrics)
    print(
        f"[phase1] 5/6 evaluate: hit_rate={metrics['retrieval_hit_rate']:.4f} "
        f"token_f1={metrics['mean_token_f1']:.4f} judge_accuracy={metrics['judge_accuracy']:.4f} "
        f"judge_mode={metrics['judge_mode']}"
    )

    quality = run_data_quality_checks(clean_df, settings, BASELINE_STAGE)
    freshness = build_freshness_report(clean_df, settings, paths.freshness_report)
    if not quality["success"]:
        # Baseline truot quality gate la tin hieu bat thuong -> canh bao nhung van
        # xuat report de co bang chung dieu tra.
        print(
            f"[phase1] WARNING quality gate FAILED: {quality['failed_expectations']} "
            f"is_fresh={freshness['is_fresh']}"
        )

    source_summary = {
        "source_api": settings.source_api,
        "source_mode": source_mode,
        "source_query": settings.source_query,
        "source_filter": settings.source_filter,
        "max_results": settings.max_results,
        "raw_records": len(records),
        "clean_rows": int(len(clean_df)),
        "dropped_rows": len(records) - int(len(clean_df)),
        "embedding_model": settings.embedding_model,
        "collection_name": index.collection_name,
        "indexed_documents": len(index.documents),
        "llm_provider": settings.llm_provider,
        "llm_model": settings.model_name,
        "top_k": settings.top_k,
        "test_set_mode": testset_mode,
        "test_set_size": len(test_set),
        "artifacts": {
            "Raw API response": _relative(paths.raw_api_response, root),
            "Raw records": _relative(paths.raw_records_json, root),
            "Clean CSV": _relative(paths.clean_csv, root),
            "Clean JSON": _relative(paths.clean_json, root),
            "ChromaDB": _relative(paths.chroma_dir, root),
            "Embeddings manifest": _relative(paths.embeddings_json, root),
            "Test set": _relative(paths.eval_testset, root),
            "Baseline metrics": _relative(paths.baseline_metrics, root),
            "Baseline answers": _relative(paths.baseline_answers, root),
            "Quality report": _relative(Path(quality["report_path"]), root),
            "Freshness report": _relative(paths.freshness_report, root),
            "Phase 1 report": _relative(paths.baseline_report, root),
        },
    }

    generate_phase1_report(
        report_path=paths.baseline_report,
        source_summary=source_summary,
        metrics=metrics,
        quality=quality,
        freshness=freshness,
    )
    print(
        f"[phase1] 6/6 quality gate: success={quality['success']} is_fresh={freshness['is_fresh']} "
        f"-> {_relative(paths.baseline_report, root)}"
    )

    _demo_agent(settings, index, test_set)

    return Phase1Result(
        clean_df=clean_df,
        index=index,
        test_set=test_set,
        metrics=metrics,
        quality=quality,
        freshness=freshness,
        source_summary=source_summary,
    )


def main() -> None:
    """Entrypoint cua `script/run_phase1.py`."""
    settings = load_settings()
    result = run_phase1_pipeline(settings)
    print(
        "[phase1] DONE clean_rows={rows} questions={questions} hit_rate={hit:.4f} "
        "token_f1={f1:.4f} quality_gate={gate} is_fresh={fresh}".format(
            rows=len(result.clean_df),
            questions=len(result.test_set),
            hit=result.metrics["retrieval_hit_rate"],
            f1=result.metrics["mean_token_f1"],
            gate=result.quality["success"],
            fresh=result.freshness["is_fresh"],
        )
    )
