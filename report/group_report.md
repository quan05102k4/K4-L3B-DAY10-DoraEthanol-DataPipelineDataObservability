# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin | Nội dung |
| --- | --- |
| Khóa/Lớp | K4 — L3B |
| Tên nhóm | DoraEthanol (`K4-L3B-DAY10`) |
| Repository | `K4-L3B-DAY10-DoraEthanol-DataPipelineDataObservability` (nhánh `main`) |
| Ngày hoàn thành | 2026-09-26 |

### Thành viên và phân công

| STT | Họ và tên | MSSV | Vai trò chính | Module/deliverable sở hữu |
| --: | --- | --- | --- | --- |
| 1 | Nguyễn Minh Quân | 2A202602490 | Trưởng nhóm / Pipeline Integrator | `core/config.py`, `core/utils.py`, `pipelines/phase1.py`, `pipelines/corruption_flow.py`, `script/`, `data/reports/` |
| 2 | Trần Anh Đăng | 2A202602992 | Data Foundation & Recovery Source (nguồn dữ liệu phục hồi) | `ingestion/crossref.py`, `ingestion/cleaning.py`, `ingestion/corruption.py`, `data/raw/`, `data/clean/` |
| 3 | Nguyễn Khánh Đô | 2A202602687 | RAG & Vector Index | `retrieval/embeddings.py`, `retrieval/index.py`, `retrieval/qa.py`, `retrieval/agent.py`, `data/chroma/`, `data/embeddings/` |
| 4 | Bùi Lê Gia Huy | 2A202602607 | Observability & Evaluation | `observability/quality.py`, `observability/reporting.py`, `evaluation/testset.py`, `evaluation/metrics.py`, `data/quality/`, `data/eval/`, `data/results/` |

## 2. Tóm tắt kết quả

**Tóm tắt của nhóm:**

Nhóm hoàn thành trọn 6 checkpoint: ingestion từ Crossref REST API (24 record, có fallback snapshot), cleaning thành 24 dòng × 13 cột với `text_for_embedding` 5 phần, index ChromaDB bằng `all-MiniLM-L6-v2`, sinh benchmark 10 câu phủ 4 dạng nghiệp vụ, dựng Quality Gate Great Expectations 1.23.2 + Freshness SLA, tiêm 6 kịch bản corruption, phục hồi idempotent từ snapshot thô và xuất báo cáo đối chiếu 3 trạng thái.

Baseline sinh đầy đủ artifact: `data/raw/` (2 file), `data/clean/papers_clean.csv|json`, `data/embeddings/papers_embeddings.json`, `data/eval/test_set.json`, `data/results/baseline_metrics.json`, `data/quality/baseline_quality_report.json` + `freshness_report.json`, `data/reports/phase1_report.md`. Baseline đạt Hit Rate 1.0000, Token F1 1.0000, Quality Gate PASS, Freshness PASS (stale 4.17%).

Corruption ảnh hưởng rõ nhất là **drop_latest_records** (mất 5/24 bài mới nhất): một mình kịch bản này đánh sập 3/10 câu hỏi về retrieval. Về phía quality signal, **duplicate_rows** và **blank_summary** là hai kịch bản làm GX FAIL (4 dòng trùng `paper_id`, 3 dòng summary dưới 30 ký tự), còn **stale_date** đẩy `stale_ratio` từ 4.17% lên 42.86% khiến Freshness SLA FAIL.

Repair dựng lại dataset từ `data/raw/crossref_records.json` đã phục hồi **100%** khoảng suy giảm của cả 4 metric (Hit Rate, Token F1, Judge Accuracy, Judge Score) và đưa Quality Gate + Freshness về PASS; dataframe sau repair khớp tuyệt đối baseline (`matches_baseline=True`).

Giới hạn quan trọng nhất còn lại: LLM judge không gọi được do quota Gemini free-tier cạn (429 RESOURCE_EXHAUSTED), nên cả 3 trạng thái đều dùng judge heuristic dự phòng (`judge_mode=fallback_heuristic`); Ragas cũng chưa bật.

## 3. Kiến trúc và luồng dữ liệu

### Luồng end-to-end

```text
Crossref REST API (fallback: data/raw/crossref_response.json)
    -> raw response + raw records (24)
    -> cleaning & data modeling (24 dòng, 13 cột, text_for_embedding 5 phần)
    -> MiniLM embedding + ChromaDB collection papers-baseline (24 docs)
    -> evaluation baseline trên test_set.json (10 câu)
    -> GX 1.x quality gate + freshness SLA -> phase1_report.md
    -> corruption 6 kịch bản (seed 20261010) -> corruption_log.json
    -> re-index papers-corrupted (21 docs) + re-evaluate cùng test set
    -> repair_from_raw_snapshot() dựng lại từ raw records -> ghi đè dữ liệu hỏng
    -> re-index papers-repaired (24 docs) + re-evaluate
    -> corruption_report.md (bảng đối chiếu 3 trạng thái)
```

### Trách nhiệm của từng khối

| Khối | Input | Xử lý chính | Output/artifact | Owner |
| --- | --- | --- | --- | --- |
| Ingestion | Crossref `/works` + query/filter | Fetch 3 lần thử, retry theo status 429/5xx, parse JATS, fallback snapshot | `data/raw/crossref_response.json`, `data/raw/crossref_records.json` | Trần Anh Đăng |
| Cleaning | 24 `PaperRecord` | Normalize whitespace, parse ISO date, `age_days`, dedupe `paper_id`, ghép `text_for_embedding` | `data/clean/papers_clean.csv`, `papers_clean.json` | Trần Anh Đăng |
| Embedding/index | `text_for_embedding` | MiniLM-L6-v2 normalize, ChromaDB cosine, 3 collection tách biệt | `data/chroma/`, `data/embeddings/papers_embeddings*.json` | Nguyễn Khánh Đô |
| Evaluation | `test_set.json` + index | Retrieval Hit Rate, Token F1, LLM judge (có fallback heuristic) | `data/results/*_metrics.json`, `*_answers.json` | Bùi Lê Gia Huy |
| Observability | clean/corrupted/repaired dataframe | GX 1.x Ephemeral Context 4 expectations + Freshness SLA 25% | `data/quality/*_quality_report.json`, `*_freshness_report.json` | Bùi Lê Gia Huy |
| Corruption/repair | clean dataframe + raw snapshot | 6 kịch bản có seed; repair dựng lại từ raw records | `data/results/corruption_log.json`, `data/clean/papers_clean_corrupted|repaired.*` | Trần Anh Đăng (corruption + nguồn phục hồi: `load_raw_records`, `build_clean_dataframe`) + Nguyễn Minh Quân (repair flow: `repair_from_raw_snapshot`) |
| Orchestration | Settings + toàn bộ module | Thứ tự 6 bước mỗi phase, in log tiến trình, gọi sinh report | `data/reports/phase1_report.md`, `data/reports/corruption_report.md` | Nguyễn Minh Quân |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Biến/cấu hình | Giá trị sử dụng |
| --- | --- |
| `LLM_PROVIDER` | `gemini` |
| `LLM_MODEL` | `gemini-3.8-flash` |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Số lượng Crossref records | 24 (`max_results=24`) |
| Retrieval `top_k` | 4 |
| Freshness threshold | 180 ngày; `MAX_STALE_RATIO = 0.25` |
| Random seed | `CORRUPTION_SEED = 20261010` |

### Lệnh cài đặt

```bash
python -m pip install -e .
```

### Lệnh chạy

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
```

### Kết quả tái hiện

| Lệnh | Trạng thái | Thời điểm chạy gần nhất | Bằng chứng |
| --- | --- | --- | --- |
| Baseline pipeline | Thành công (exit code 0) | 2026-09-26T04:04:05Z | `data/reports/phase1_report.md`, `data/results/baseline_metrics.json` |
| Corruption flow | Thành công (exit code 0) | 2026-09-26T04:43:13Z | `data/reports/corruption_report.md`, `data/results/corrupted_metrics.json`, `repaired_metrics.json` |

Ghi chú trung thực: trong cả hai lần chạy, LLM judge và agent demo **không** gọi được model do quota free-tier cạn (429 RESOURCE_EXHAUSTED) — xem `data/results/agent_demo_answers.json` và `judge_mode` trong các file metrics. Hit Rate và Token F1 không phụ thuộc LLM nên vẫn hợp lệ.

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính | Giá trị |
| --- | --- |
| Source | Crossref REST API — `https://api.crossref.org/works` |
| Query/filter | `agentic retrieval augmented generation large language model`; filter `from-pub-date:2026-03-30,has-abstract:true` |
| Thời điểm lấy dữ liệu | Snapshot `data/raw/crossref_response.json`; lần chạy gần nhất dùng `source_mode=raw_records_snapshot` |
| Số record nhận được | 24 (payload 24 items → 24 `PaperRecord`) |
| Cơ chế retry/backoff | `MAX_ATTEMPTS=3`, retry khi gặp 429/500/502/503/504, timeout 30s; lỗi mạng → fallback snapshot local |

### Raw và clean schema

| Trường | Kiểu dữ liệu | Bắt buộc? | Ý nghĩa | Xử lý khi thiếu/sai |
| --- | --- | --- | --- | --- |
| `paper_id` | str (DOI, lowercase) | Có | Khóa định danh bài báo | Thiếu → loại bỏ record; trùng → giữ bản mới nhất |
| `title` | str | Có | Tiêu đề đã bỏ markup | Ngắn hơn `MIN_TITLE_CHARS=10` → loại bỏ record |
| `summary` | str | Có | Abstract đã bỏ thẻ JATS | Ngắn hơn `MIN_SUMMARY_CHARS=40` → loại bỏ record |
| `authors_joined` | str | Có | Danh sách tác giả ghép bằng `, ` | Rỗng → placeholder `Unknown authors` |
| `categories_joined` / `primary_category` | str | Có | Chủ đề Crossref `subject` | Rỗng → placeholder `uncategorized` |
| `published` / `updated` | str ISO `YYYY-MM-DD` | Có | Ngày xuất bản / cập nhật | Không parse được `published` → loại bỏ; `updated` rỗng → lấy theo `published` |
| `age_days` | int64 | Có | `(run_date - published).days` | Không parse được → record đã bị loại từ trước |
| `summary_chars` | int64 | Có | Độ dài summary, dùng cho quality gate | Tính lại sau mọi biến đổi |
| `abs_url` / `pdf_url` | str | Có | Link tài liệu | Rỗng → `https://doi.org/<paper_id>` |
| `text_for_embedding` | str | Có | Ngữ cảnh 5 phần đưa vào embedding | Sinh lại từ 5 trường nguồn, không nhận từ ngoài |

### Quy tắc cleaning

| Quy tắc | Quality dimension liên quan | Số record bị tác động | Cách xác minh |
| --- | --- | --: | --- |
| Loại record thiếu `paper_id` / `published` không parse được | Completeness / Validity | 0 | `dropped_rows=0` trong `phase1_report.md` §1 |
| Loại record có `title` < 10 ký tự hoặc `summary` < 40 ký tự | Validity | 0 | `clean_rows=24` so với `raw_records=24` |
| Khử trùng lặp theo `paper_id`, giữ bản mới nhất | Uniqueness | 0 (dữ liệu nguồn không trùng) | GX `expect_column_values_to_be_unique` PASS, `unexpected_count=0` |
| Bỏ thẻ JATS/HTML và gộp khoảng trắng ở `title`/`summary` | Validity / Consistency | 24 (toàn bộ) | Cột `summary` trong `papers_clean.csv` không còn `<jats:p>` |
| Placeholder cho `authors_joined` / `categories_joined` rỗng | Completeness | 0 | GX not-null PASS trên các cột bắt buộc |

Cách nhóm tạo `text_for_embedding`, document ID và `age_days`:

`text_for_embedding` được ghép cố định theo 5 dòng `Title / Authors / Published / Categories / Summary` bởi `build_embedding_text()`. Thứ tự cố định là điều kiện để bước corruption và repair dựng lại chuỗi này y hệt baseline, nhờ đó so sánh vector giữa 3 trạng thái mới công bằng. Document ID trong ChromaDB là `record_id = f"{paper_id}::{index}"` — ghép thêm chỉ số dòng để dataset corrupted (có `paper_id` trùng do nhân bản) vẫn nạp được vào Chroma mà không đụng ràng buộc ID duy nhất, trong khi `paper_id` gốc vẫn nằm trong metadata để đối chiếu ground truth. `age_days = (run_date - published).days` tính theo ngày UTC của lần chạy, và được tính lại sau corruption (`+365` ngày cho các dòng bị `stale_date`).

## 6. Evaluation setup

| Thành phần | Cấu hình thực tế |
| --- | --- |
| Số câu hỏi | 10 |
| Các `question_type` | `summary` (3), `authors` (3), `date` (2), `categories` (2) |
| Ground-truth document ID | `ground_truth_doc_ids` = `paper_id` của bài được chọn; ground truth text lấy trực tiếp từ cột tương ứng của dataset sạch |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` (vector normalize) |
| Vector store/collection | ChromaDB persistent `data/chroma/`; `papers-baseline` / `papers-corrupted` / `papers-repaired`, space cosine |
| Retrieval `top_k` | 4 |
| LLM provider/model | `gemini` / `gemini-3.8-flash` (judge rơi về heuristic do 429) |
| Test set dùng chung cho ba trạng thái | `data/eval/test_set.json`, `test_set_mode=reused` (không sinh lại giữa các lần chạy) |

Vì sao test set được giữ nguyên khi đánh giá baseline, corrupted và repaired:

Chỉ khi cả 3 lần đo dùng đúng 10 câu hỏi và đúng bộ `ground_truth_doc_ids` thì chênh lệch metric mới phản ánh **chất lượng dữ liệu**, chứ không phải độ khó khác nhau của câu hỏi. Nếu sinh lại test set từ dataset corrupted, câu hỏi sẽ được tạo từ chính dữ liệu đã hỏng (tiêu đề bị cắt, summary rỗng) và ground truth cũng hỏng theo — metric có thể vẫn cao trong khi hệ thống đang trả lời sai, tức là đo mất luôn hiện tượng cần quan sát. Vì vậy `run_corruption_flow.py` luôn truyền `settings.paths.eval_testset` cho cả 3 lần `evaluate_pipeline` và không đặt `REFRESH_TEST_SET=1`.

## 7. Kết quả baseline

### Artifact checklist

| Artifact | Đường dẫn thực tế | Trạng thái | Ghi chú |
| --- | --- | --- | --- |
| Raw response/records | `data/raw/crossref_response.json`, `crossref_records.json` | Có | 24 items / 24 records |
| Cleaned dataset | `data/clean/papers_clean.csv`, `papers_clean.json` | Có | 24 dòng × 13 cột |
| Embedding manifest/index | `data/embeddings/papers_embeddings.json`, `data/chroma/` | Có | `papers-baseline` 24 docs |
| Evaluation set | `data/eval/test_set.json` | Có | 10 câu, 4 dạng |
| Baseline metrics | `data/results/baseline_metrics.json` | Có | Kèm `by_question_type` |
| Quality/freshness | `data/quality/baseline_quality_report.json`, `freshness_report.json` | Có | GX 1.23.2, suite `papers_quality_suite` |
| Baseline report | `data/reports/phase1_report.md` | Có | Sinh 2026-09-26T04:04:05Z |

### Baseline metrics

| Metric | Giá trị | Diễn giải |
| --- | --: | --- |
| `retrieval_hit_rate` | 1.0000 | 10/10 câu truy hồi đúng bài chứa ground truth — corpus 24 bài, `top_k=4` và cơ chế tra cứu chính xác theo tiêu đề giúp đạt trần |
| `mean_token_f1` | 1.0000 | Câu trả lời được trích thẳng từ metadata của đúng bài, nên trùng khớp ground truth theo token |
| `judge_accuracy` | 1.0000 | Đạt trần, nhưng do judge heuristic dự phòng (F1 ≥ 0.95 → score 5), **không phải** phán quyết của LLM |
| `mean_judge_score` | 5 | Cùng lý do trên; `judge_fallback_count=10/10` |
| Ragas | N/A | Bỏ qua vì chưa bật `RUN_RAGAS=1` (vòng đánh giá chậm, cần LLM còn quota) |

## 8. Data quality và freshness

### Quality checks

| Check | Quality dimension | Ngưỡng/kỳ vọng | Kết quả baseline | Bằng chứng |
| --- | --- | --- | --- | --- |
| `expect_table_row_count_to_be_between` | Completeness / Volume | 5 ≤ rows ≤ 5000 | PASS — observed 24 | `data/quality/baseline_quality_report.json` |
| `expect_column_values_to_not_be_null` (`paper_id`, `title`, `text_for_embedding`) | Completeness | 0 null | PASS — `unexpected_count=0` cả 3 cột | cùng file trên |
| `expect_column_values_to_be_unique` (`paper_id`) | Uniqueness | 0 trùng | PASS — `unexpected_count=0` | cùng file trên |
| `expect_column_value_lengths_to_be_between` (`summary`) | Validity | độ dài ≥ 30 | PASS — `unexpected_count=0` | cùng file trên |
| Freshness SLA (ngoài GX suite) | Timeliness | `stale_ratio` ≤ 0.25 | PASS — 0.0417 | `data/quality/freshness_report.json` |

### Freshness

| Thuộc tính | Giá trị |
| --- | --- |
| Freshness được đo tại | Dataset đã clean, ngay trước khi nạp vector (`evaluate_freshness_sla` trên dataframe) |
| Timestamp mới nhất | `latest_published = 2026-07-22` (cũ nhất `2026-03-28`) |
| Ngưỡng freshness | `age_days > 180` là stale; cảnh báo khi tỷ lệ stale > 25% |
| Trạng thái baseline | Fresh (`is_fresh=True`) |
| Lý do | 1/24 bài quá hạn (`max_age_days=182`, chỉ vượt ngưỡng 2 ngày) → `stale_ratio=0.0417`, thấp hơn nhiều ngưỡng 0.25 |

## 9. Corruption scenarios và repair

| Corruption | Cách tạo | Record bị tác động | Quality signal kỳ vọng | Tác động thực tế | Cách repair |
| --- | --- | --: | --- | --- | --- |
| `drop_latest_records` | Xóa 20% bài có `published` mới nhất | 5 | Row count giảm, mất tri thức mới | 24 → 21 dòng; đánh sập retrieval của `eval_001`, `eval_002`, `eval_003` (Hit Rate 1.0 → 0.7) | Dựng lại toàn bộ 24 dòng từ raw snapshot |
| `blank_summary` | Gán `summary = ""` | 3 | `expect_column_value_lengths_to_be_between` FAIL | GX FAIL, `unexpected_count=3`; `eval_009` trả về chuỗi rỗng (F1 = 0) | Summary lấy lại từ abstract trong raw records |
| `inject_noise` | Chèn chuỗi rác (`<<<NULL>>>`, `0xDEADBEEF ||| ###`, …) vào giữa và cuối summary | 3 | Embedding lệch ngữ nghĩa, Token F1 và judge score giảm | 3 dòng summary bẩn; góp phần làm `mean_token_f1` nhóm `summary` còn 0.5802 | Ghi đè bằng summary sạch từ nguồn |
| `truncate_title` | Cắt `title` còn 7 ký tự | 3 | Ground truth theo title không match, Hit Rate giảm | Phá cơ chế tra cứu chính xác theo tiêu đề trong `qa.py`; `eval_009` mất top-1 đúng | Title lấy lại từ raw records |
| `stale_date` | Lùi `published`/`updated` 365 ngày, cộng `age_days` | 6 | `stale_ratio` vượt 0.25 → Freshness FAIL | `stale_ratio` 0.0417 → 0.4286, `max_age_days` 182 → 512, `is_fresh=False`; `eval_007` trả lời `2025-06-04` thay vì `2026-06-04` | `published` tính lại từ trường `published`/`created` của Crossref |
| `duplicate_rows` | Nhân bản dòng, `paper_id` bị trùng | 2 | `expect_column_values_to_be_unique` FAIL | GX FAIL, `unexpected_count=4` (2 cặp trùng) | Dedupe theo `paper_id` khi dựng lại dataset |

Corruption log:

- Đường dẫn: `data/results/corruption_log.json`
- Trạng thái: Có
- Nhận xét: Log ghi đủ 6 kịch bản kèm `seed=20261010`, tham số từng kịch bản (`ratio`, `shift_days`, `max_chars`, danh sách snippet rác), tổng 22 bản ghi thay đổi (xóa 5, thêm 2, sửa 13) và giá trị before/after của **từng dòng** kèm `baseline_row` để truy nguyên về dataset sạch.

Cách repair đảm bảo dữ liệu được phục hồi từ nguồn đáng tin cậy thay vì chỉ che kết quả lỗi:

`repair_from_raw_snapshot()` không sửa chữa từng ô đã hỏng trong dataset corrupted — nó đọc lại `data/raw/crossref_records.json` (file chỉ được ghi ở bước ingest, corruption không bao giờ chạm tới) rồi gọi **đúng** `build_clean_dataframe()` mà baseline đã dùng. Vì thế mọi cột dẫn xuất (`summary_chars`, `age_days`, `text_for_embedding`) đều được tính lại từ nguồn, không thể còn sót dấu vết của dữ liệu bẩn. Hai bằng chứng kèm trong `corruption_report.md` §5: `idempotent_rerun_identical=True` (dựng lại lần hai từ cùng snapshot cho dataframe y hệt → phép repair idempotent) và `matches_baseline=True` (dataset sau repair khớp tuyệt đối 24 dòng baseline, không phải "gần đúng"). Collection `papers-repaired` cũng được `delete_collection` trước khi tạo lại, nên không cộng dồn document cũ.

## 10. So sánh baseline, corrupted và repaired

| Metric/signal | Baseline | Corrupted | Repaired | Thay đổi do corruption | Mức phục hồi | Nhận xét |
| --- | --: | --: | --: | --: | --: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.7000 | 1.0000 | −0.3000 (−30.00%) | 100% | 3/10 câu mất bài nguồn vì `drop_latest_records` |
| `mean_token_f1` | 1.0000 | 0.6741 | 1.0000 | −0.3259 (−32.59%) | 100% | 4/10 câu trả lời sai/rỗng; giảm sâu hơn Hit Rate |
| `judge_accuracy` | 1.0000 | 0.7000 | 1.0000 | −0.3000 (−30.00%) | 100% | Judge heuristic, phản ánh gián tiếp Token F1 |
| `mean_judge_score` | 5.0000 | 3.6000 | 5.0000 | −1.4000 (−28.00%) | 100% | 3 câu bị hạ xuống score 1 |
| Quality checks pass/fail | PASS (0 fail) | **FAIL** (2 fail) | PASS (0 fail) | `unique paper_id`: 4 dòng; `summary length`: 3 dòng | Về 0 fail | GX là tín hiệu bắt lỗi cấu trúc |
| Freshness status | Fresh (0.0417) | **Stale** (0.4286) | Fresh (0.0417) | +0.3869 tỷ lệ stale | Về đúng 0.0417 | `max_age_days` 182 → 512 → 182 |

Hai chuỗi nguyên nhân–bằng chứng:

1. `drop_latest_records` xóa 5 bài mới nhất (`corruption_log.json` §scenario 1) → row count 24 → 21 (`corrupted_quality_report.json`) và `stale_date` đẩy `stale_ratio` lên 0.4286 (`corrupted_freshness_report.json`) → 3 câu hỏi `eval_001/002/003` không còn bài nguồn trong index nên `retrieval_hit_rate` tụt về 0.7000 và `mean_token_f1` về 0.6741 (`corrupted_metrics.json`, `corrupted_answers.json`).
2. `repair_from_raw_snapshot()` dựng lại 24 dòng từ raw snapshot (`corruption_report.md` §5: `rows_restored=3`, `matches_baseline=True`) → GX trở lại 0 expectation FAIL và `stale_ratio` về 0.0417 (`repaired_quality_report.json`, `repaired_freshness_report.json`) → cả 4 metric trở về đúng mức baseline, tương ứng mức phục hồi 100% khoảng suy giảm (`repaired_metrics.json`).

Ba quan sát Silent Failure đáng chú ý, đối chiếu trực tiếp từ `corrupted_answers.json`:

- **`eval_007` — retrieval đúng nhưng câu trả lời sai:** bài `10.1145/3637528.3671816` vẫn được truy hồi đúng (hit = True), nhưng `published` đã bị lùi 365 ngày nên agent trả lời `2025-06-04` thay vì `2026-06-04` (Token F1 = 0). Đây là lý do Freshness SLA phải là tín hiệu **riêng**, không suy ra được từ Hit Rate.
- **`eval_002` — metric trả lời "đẹp" che mất lỗi retrieval:** bài nguồn đã bị xóa (hit = False) nhưng bài được truy hồi thay thế tình cờ có cùng danh sách tác giả `Bao Do, Linh Ngo`, nên Token F1 vẫn = 1.0. Nếu chỉ nhìn Token F1 sẽ kết luận sai rằng hệ thống khỏe.
- **`eval_009` — Hit Rate = 1 nhưng câu trả lời rỗng:** `truncate_title` cắt tiêu đề còn 7 ký tự làm hỏng cơ chế tra cứu chính xác theo tiêu đề trong `qa.py`, thứ hạng bị xáo trộn nên top-1 rơi vào bài `…3671823` có summary bị bỏ trắng → câu trả lời là chuỗi rỗng, dù bài nguồn vẫn nằm ở hạng 4 (nên hit vẫn được tính True).

## 11. Vấn đề tích hợp quan trọng

- **Triệu chứng:** Dataset corrupted có `paper_id` bị nhân bản, nếu dùng `paper_id` làm ID document thì ChromaDB sẽ ghi đè bản trùng và dataset 21 dòng chỉ còn 19 document — bước đo suy giảm sẽ mất đúng phần lỗi cần quan sát.
- **Nguyên nhân:** ChromaDB yêu cầu ID document là duy nhất trong một collection, trong khi kịch bản `duplicate_rows` cố tình tạo trùng `paper_id`.
- **Cách xử lý:** `LocalEmbeddingIndex._build_documents()` dùng `record_id = f"{paper_id}::{index}"` làm ID và giữ `paper_id` gốc trong metadata, nên số document khớp đúng số dòng dataset; đồng thời mỗi trạng thái nạp vào một collection riêng (`papers-baseline` / `papers-corrupted` / `papers-repaired`) thay vì ghi đè chung một collection.
- **Cách xác minh:** `python script/run_corruption_flow.py` in `docs=21` cho collection corrupted và `docs=24` cho repaired; kiểm tra lại bằng `chromadb.PersistentClient('data/chroma').list_collections()` → `papers-baseline 24`, `papers-corrupted 21`, `papers-repaired 24`.

## 12. Giới hạn và hướng cải thiện

| Giới hạn hiện tại | Ảnh hưởng | Hướng cải thiện có thể kiểm chứng |
| --- | --- | --- |
| LLM judge không gọi được (429 RESOURCE_EXHAUSTED, quota free-tier 20 request/ngày) | `judge_accuracy` và `mean_judge_score` của cả 3 trạng thái đến từ heuristic dựa trên Token F1, không phải phán quyết ngữ nghĩa; agent demo rỗng | Chạy lại khi quota hồi hoặc đổi provider (`LLM_PROVIDER=mock` để kiểm thử luồng, hoặc key có quota); so `judge_mode=llm` với bản heuristic để đo độ lệch |
| Baseline đạt trần 1.0000 ở cả 4 metric | Không còn khoảng để quan sát các corruption nhẹ, mọi suy giảm chỉ thấy được khi lỗi đủ nặng | Mở rộng corpus (`max_results` > 24) và thêm câu hỏi nhiều bước/nhiều tài liệu để baseline nằm dưới trần |
| Ragas bị bỏ qua (`RUN_RAGAS` chưa bật) | Chưa có faithfulness / context precision–recall để đối chiếu với Token F1 | Bật `RUN_RAGAS=1` với LLM còn quota, so sánh xu hướng 3 trạng thái giữa Ragas và Token F1 |
| Repair chạy vô điều kiện trong luồng demo | Chưa phải self-healing thật: gate FAIL và hành động repair chưa được nối tự động | Nối điều kiện `quality["success"] is False` → tự kích hoạt `repair_from_raw_snapshot()`, ghi log lý do rollback rồi re-evaluate |
| Agent trả lời bằng trích xuất metadata theo từ khóa trong câu hỏi | Câu hỏi diễn đạt khác mẫu có thể lấy sai trường; chưa dùng LLM sinh câu trả lời | Thay `_extract_answer` bằng sinh câu trả lời từ context có trích dẫn, đo lại trên cùng test set |

## 13. Checklist trước khi nộp

- [x] Thông tin nhóm và repository chính xác.
- [x] Phân công khớp với module, artifact và kết quả thực tế.
- [x] Lệnh tái hiện đã được chạy lại trên phiên bản dùng để nộp (2026-09-26, cả hai script exit code 0).
- [x] Baseline, corrupted và repaired dùng cùng evaluation set (`data/eval/test_set.json`, `test_set_mode=reused`).
- [x] Bảng metrics khớp với các file trong `data/results/`.
- [x] Quality/freshness conclusions khớp với `data/quality/`.
- [x] Các đường dẫn báo cáo và artifact truy cập được.
- [x] Mỗi thành viên đã hoàn thành báo cáo vai trò riêng (`report/individual_<MSSV>_<HoTen>.md`).
- [x] Không có `.env`, API key, token hoặc secret trong source, report, log hay ảnh (`.env` đã nằm trong `.gitignore`).
