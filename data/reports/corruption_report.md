# Phase 2 — Corruption, Repair & Đối Chiếu 3 Trạng Thái

- **Thời điểm sinh báo cáo:** 2026-09-26T04:43:13.875037+00:00
- **Evaluation set dùng chung cho 3 trạng thái:** 10 câu hỏi (không sinh lại test set để phép so sánh có nghĩa)
- **Số bản ghi:** baseline 24 → corrupted 21 → repaired 24
- **Quality Gate:** baseline PASS → corrupted FAIL → repaired PASS
- **Dữ liệu sau repair khớp baseline:** PASS

## 1. Bảng đối chiếu hiệu năng 3 trạng thái

| Chỉ số | Baseline | Corrupted | Repaired | Δ Corrupted | Mức phục hồi |
| --- | --- | --- | --- | --- | --- |
| Số câu hỏi đánh giá (samples) | 10 | 10 | 10 | +0.0000 (+0.00%) | n/a |
| Retrieval Hit Rate | 1.0000 (100.00%) | 0.7000 (70.00%) | 1.0000 (100.00%) | -0.3000 (-30.00%) | 100.00% |
| Mean Token F1 | 1.0000 | 0.6741 | 1.0000 | -0.3259 (-32.59%) | 100.00% |
| LLM Judge Accuracy | 1.0000 (100.00%) | 0.7000 (70.00%) | 1.0000 (100.00%) | -0.3000 (-30.00%) | 100.00% |
| Mean LLM Judge Score (1-5) | 5.0000 | 3.6000 | 5.0000 | -1.4000 (-28.00%) | 100.00% |

> `Δ Corrupted` = corrupted − baseline. `Mức phục hồi` = phần khoảng cách `baseline − corrupted` mà repair lấy lại được (100% = trở lại đúng baseline, `n/a` = chỉ số không suy giảm nên không có gì để phục hồi).

- Chế độ judge: baseline `fallback_heuristic`, corrupted `fallback_heuristic`, repaired `fallback_heuristic`.

### 1.1. Chi tiết theo dạng câu hỏi

| question_type | samples | HitRate Baseline | HitRate Corrupted | HitRate Repaired | TokenF1 Baseline | TokenF1 Corrupted | TokenF1 Repaired |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `summary` | 3 | 1.0000 (100.00%) | 0.6667 (66.67%) | 1.0000 (100.00%) | 1.0000 | 0.5802 | 1.0000 |
| `authors` | 3 | 1.0000 (100.00%) | 0.6667 (66.67%) | 1.0000 (100.00%) | 1.0000 | 1.0000 | 1.0000 |
| `date` | 2 | 1.0000 (100.00%) | 0.5000 (50.00%) | 1.0000 (100.00%) | 1.0000 | 0.0000 | 1.0000 |
| `categories` | 2 | 1.0000 (100.00%) | 1.0000 (100.00%) | 1.0000 (100.00%) | 1.0000 | 1.0000 | 1.0000 |

## 2. Quality Gate & Freshness SLA

| Hạng mục | Baseline | Corrupted | Repaired |
| --- | --- | --- | --- |
| Quality Gate (tổng) | PASS | FAIL | PASS |
| Great Expectations suite | PASS | FAIL | PASS |
| Số bản ghi kiểm định | 24 | 21 | 24 |
| Expectations thất bại | n/a | expect_column_values_to_be_unique, expect_column_value_lengths_to_be_between | n/a |
| Freshness SLA (is_fresh) | PASS | FAIL | PASS |
| Số bản ghi quá hạn (stale) | 1 | 9 | 1 |
| Tỷ lệ stale | 0.0417 (4.17%) | 0.4286 (42.86%) | 0.0417 (4.17%) |
| Ngưỡng stale tối đa | 0.2500 (25.00%) | 0.2500 (25.00%) | 0.2500 (25.00%) |
| Tuổi lớn nhất (ngày) | 182 | 512 | 182 |
| Bài mới nhất | 2026-07-22 | 2026-06-12 | 2026-07-22 |

## 3. Thống kê dataset 3 trạng thái

| Chỉ tiêu | Baseline | Corrupted | Repaired |
| --- | --- | --- | --- |
| `rows` | 24 | 21 | 24 |
| `unique_paper_ids` | 24 | 19 | 24 |
| `duplicate_paper_ids` | 0 | 2 | 0 |
| `blank_summaries` | 0 | 3 | 0 |
| `summaries_below_min` | 0 | 3 | 0 |
| `noisy_summaries` | 0 | 3 | 0 |
| `titles_below_min` | 0 | 3 | 0 |
| `stale_rows` | 1 | 9 | 1 |
| `latest_published` | 2026-07-22 | 2026-06-12 | 2026-07-22 |

## 4. Kịch bản corruption đã tiêm

- Seed: `20261010` (cố định để mọi lần chạy tiêm đúng một bộ bản ghi).
- Tổng số thay đổi: 22 bản ghi (xóa 5, thêm 2, sửa 13).

| # | Kịch bản | Mô tả | Rows | Tác động kỳ vọng lên gate |
| --- | --- | --- | --- | --- |
| 1 | `drop_latest_records` | Bo 20% bai bao moi nhat | 5 | Row count giam va mat tri thuc moi nhat -> retrieval hit rate tut. |
| 2 | `blank_summary` | Xoa trang summary | 3 | ExpectColumnValueLengthsToBeBetween(summary, min=30) FAIL. |
| 3 | `inject_noise` | Chen chuoi rac vao summary | 3 | Summary ban -> embedding lech ngu nghia, token F1 va judge score giam. |
| 4 | `truncate_title` | Cat title con duoi 8 ky tu | 3 | Title cut -> ground truth theo title khong match, retrieval hit rate giam. |
| 5 | `stale_date` | Lui published ve 365 ngay truoc | 6 | Stale ratio vuot 0.25 -> Freshness SLA is_fresh = False. |
| 6 | `duplicate_rows` | Nhan doi row de tao trung lap | 2 | ExpectColumnValuesToBeUnique(paper_id) FAIL. |

## 5. Cơ chế phục hồi (Idempotent Repair)

| Trường | Giá trị |
| --- | --- |
| `repair_strategy` | rebuild_from_raw_snapshot |
| `source_snapshot` | data/raw/crossref_records.json |
| `raw_records` | 24 |
| `repaired_rows` | 24 |
| `idempotent_rerun_identical` | PASS |
| `repaired_collection` | papers-repaired |
| `repaired_csv` | data/clean/papers_clean_repaired.csv |
| `repaired_json` | data/clean/papers_clean_repaired.json |
| `repaired_at` | 2026-09-26T04:37:04.802411+00:00 |
| `corrupted_rows` | 21 |
| `rows_restored` | 3 |
| `baseline_rows` | 24 |
| `matches_baseline` | PASS |

- Repair **không vá từng ô dữ liệu hỏng** mà dựng lại toàn bộ dataset từ snapshot thô bất biến rồi ghi đè: cùng một snapshot luôn cho ra cùng một kết quả (idempotent), chạy lại nhiều lần không tích lũy thêm sai lệch.

## 6. Phân tích Silent Failure & Kết luận

- **Silent Failure:** pipeline chạy trên dữ liệu bẩn **không phát sinh exception** — agent vẫn trả lời đủ 10/10 câu hỏi và vẫn ghi ra artifact như bình thường. Nhưng Retrieval Hit Rate rơi 1.0000 (100.00%) → 0.7000 (70.00%) (-0.3000 (-30.00%)) và Mean Token F1 rơi 1.0000 → 0.6741 (-0.3259 (-32.59%)): hệ thống sai trong im lặng, chỉ có chỉ số mới phát hiện được.
- **Tín hiệu phát hiện:** chốt kiểm soát chất lượng là thứ duy nhất báo động — Great Expectations FAIL ở expect_column_values_to_be_unique, expect_column_value_lengths_to_be_between và Freshness SLA `is_fresh = FAIL` với stale_ratio 0.4286 (42.86%) (ngưỡng 0.2500 (25.00%)).
- **Phục hồi:** sau khi ghi đè dữ liệu hỏng bằng bản dựng lại từ snapshot thô, Retrieval Hit Rate trở lại 1.0000 (100.00%) (lấy lại 100.00% khoảng suy giảm) và Mean Token F1 trở lại 1.0000 (lấy lại 100.00%); Quality Gate `success = PASS`, Freshness SLA `is_fresh = PASS`.
- **Bài học:** không thể lấy việc pipeline chạy hết mà không lỗi làm bằng chứng dữ liệu tốt. Phải đặt Data Quality Gate trước khi nạp vector store, và phải giữ snapshot thô bất biến để luôn dựng lại được trạng thái sạch.

## 7. Artifacts sinh ra

| Artifact | Đường dẫn |
| --- | --- |
| Raw snapshot (nguon repair) | `data/raw/crossref_records.json` |
| Clean baseline CSV | `data/clean/papers_clean.csv` |
| Corrupted CSV | `data/clean/papers_clean_corrupted.csv` |
| Corrupted JSON | `data/clean/papers_clean_corrupted.json` |
| Repaired CSV | `data/clean/papers_clean_repaired.csv` |
| Repaired JSON | `data/clean/papers_clean_repaired.json` |
| Corruption log | `data/results/corruption_log.json` |
| Baseline metrics | `data/results/baseline_metrics.json` |
| Corrupted metrics | `data/results/corrupted_metrics.json` |
| Repaired metrics | `data/results/repaired_metrics.json` |
| Corrupted answers | `data/results/corrupted_answers.json` |
| Repaired answers | `data/results/repaired_answers.json` |
| Corrupted quality report | `data/quality/corrupted_quality_report.json` |
| Repaired quality report | `data/quality/repaired_quality_report.json` |
| Corrupted freshness report | `data/quality/corrupted_freshness_report.json` |
| Repaired freshness report | `data/quality/repaired_freshness_report.json` |
| Comparison report | `data/reports/corruption_report.md` |
