# Phase 1 — Baseline Pipeline Report

- **Thời điểm sinh báo cáo:** 2026-09-26T04:04:05.993004+00:00
- **Nguồn dữ liệu:** Crossref REST API
- **Quality Gate:** PASS (Great Expectations 1.23.2)
- **Freshness SLA:** PASS

## 1. Nguồn dữ liệu & Lineage

| Trường | Giá trị |
| --- | --- |
| `source_api` | Crossref REST API |
| `source_mode` | raw_records_snapshot |
| `source_query` | agentic retrieval augmented generation large language model |
| `source_filter` | from-pub-date:2026-03-30,has-abstract:true |
| `max_results` | 24 |
| `raw_records` | 24 |
| `clean_rows` | 24 |
| `dropped_rows` | 0 |
| `embedding_model` | sentence-transformers/all-MiniLM-L6-v2 |
| `collection_name` | papers-baseline |
| `indexed_documents` | 24 |
| `llm_provider` | gemini |
| `llm_model` | gemini-3.8-flash |
| `top_k` | 4 |
| `test_set_mode` | reused |
| `test_set_size` | 10 |

## 2. Baseline RAG Metrics

| Chỉ số | Giá trị |
| --- | --- |
| Số câu hỏi đánh giá (samples) | 10 |
| Retrieval Hit Rate | 1.0000 (100.00%) |
| Mean Token F1 | 1.0000 |
| LLM Judge Accuracy | 1.0000 (100.00%) |
| Mean LLM Judge Score (1-5) | 5 |
| Chế độ judge (`llm` / `fallback_heuristic`) | fallback_heuristic |
| Số câu dùng judge dự phòng | 10 |

- **Ragas:** skipped=Set RUN_RAGAS=1 to enable the slower Ragas pass.

### 2.1. Chi tiết theo dạng câu hỏi

| question_type | samples | retrieval_hit_rate | mean_token_f1 | judge_accuracy | mean_judge_score |
| --- | --- | --- | --- | --- | --- |
| `summary` | 3 | 1.0000 (100.00%) | 1.0000 | 1.0000 (100.00%) | 5 |
| `authors` | 3 | 1.0000 (100.00%) | 1.0000 | 1.0000 (100.00%) | 5 |
| `date` | 2 | 1.0000 (100.00%) | 1.0000 | 1.0000 (100.00%) | 5 |
| `categories` | 2 | 1.0000 (100.00%) | 1.0000 | 1.0000 (100.00%) | 5 |

## 3. Data Quality Gate (Great Expectations 1.x)

| Hạng mục | Giá trị |
| --- | --- |
| Kết quả tổng (gate) | PASS |
| Great Expectations suite | PASS |
| Suite name | papers_quality_suite |
| Số bản ghi kiểm định | 24 |
| Expectations thất bại | không có |

| Expectation | Cột | Kết quả | observed_value | unexpected_count |
| --- | --- | --- | --- | --- |
| expect_table_row_count_to_be_between | - | PASS | 24 | n/a |
| expect_column_values_to_not_be_null | paper_id | PASS | n/a | 0 |
| expect_column_values_to_be_unique | paper_id | PASS | n/a | 0 |
| expect_column_values_to_not_be_null | title | PASS | n/a | 0 |
| expect_column_values_to_not_be_null | text_for_embedding | PASS | n/a | 0 |
| expect_column_value_lengths_to_be_between | summary | PASS | n/a | 0 |

## 4. Freshness SLA

| Hạng mục | Giá trị |
| --- | --- |
| Đạt Freshness SLA (is_fresh) | PASS |
| Tổng số bản ghi | 24 |
| Số bản ghi quá hạn (stale) | 1 |
| Tỷ lệ stale | 0.0417 (4.17%) |
| Ngưỡng stale tối đa | 0.2500 (25.00%) |
| Ngưỡng tuổi bài báo (ngày) | 180 |
| Tuổi lớn nhất (ngày) | 182 |
| Bài mới nhất | 2026-07-22 |
| Bài cũ nhất | 2026-03-28 |

## 5. Artifacts sinh ra

| Artifact | Đường dẫn |
| --- | --- |
| Raw API response | `data/raw/crossref_response.json` |
| Raw records | `data/raw/crossref_records.json` |
| Clean CSV | `data/clean/papers_clean.csv` |
| Clean JSON | `data/clean/papers_clean.json` |
| ChromaDB | `data/chroma` |
| Embeddings manifest | `data/embeddings/papers_embeddings.json` |
| Test set | `data/eval/test_set.json` |
| Baseline metrics | `data/results/baseline_metrics.json` |
| Baseline answers | `data/results/baseline_answers.json` |
| Quality report | `data/quality/baseline_quality_report.json` |
| Freshness report | `data/quality/freshness_report.json` |
| Phase 1 report | `data/reports/phase1_report.md` |
