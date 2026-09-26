# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Bùi Lê Gia Huy |
| MSSV | 2A202602607 |
| Khóa/Lớp | K4 — L3B |
| Tên nhóm | DoraEthanol |
| Vai trò chính | Data Observability & Benchmark Evaluation (GX 1.x, Freshness SLA, metrics, reporting) |
| Repository | `K4-L3B-DAY10-DoraEthanol-DataPipelineDataObservability` (nhánh `main`) |
| Ngày hoàn thành | 2026-09-26 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Quality Gate GX 1.x | `src/observability/quality.py` (`run_data_quality_checks`, `_build_suite`) | dataframe của một stage | `data/quality/{stage}_quality_report.json` + cờ `success` | Hoàn thành |
| Freshness SLA | `quality.py` (`evaluate_freshness_sla`, `build_freshness_report`) | cột `age_days`, `published` | `freshness_report.json`, `corrupted_freshness_report.json`, `repaired_freshness_report.json` | Hoàn thành |
| Benchmark test set | `src/evaluation/testset.py` (`build_test_set`, `QUESTION_SPECS`) | dataframe sạch | `data/eval/test_set.json` — 10 câu, 4 dạng | Hoàn thành |
| Bộ đo RAG | `src/evaluation/metrics.py` (`evaluate_pipeline`, `_token_f1`, `_judge_answer`) | test set + index | `*_metrics.json`, `*_answers.json` cho 3 trạng thái | Hoàn thành (judge chạy ở chế độ heuristic dự phòng) |
| Sinh báo cáo markdown | `src/observability/reporting.py` (`generate_phase1_report`, `generate_corruption_report`, `build_comparison_rows`) | metrics + quality + freshness | `data/reports/phase1_report.md`, `data/reports/corruption_report.md` | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Chốt ngưỡng để corruption chắc chắn bị bắt | Trần Anh Đăng (`corruption.py`) | GX đặt `summary` ≥ 30 ký tự (thấp hơn ngưỡng cleaning 40) và kịch bản `stale_date` đặt tỷ lệ 0.30 > `MAX_STALE_RATIO` 0.25 → gate FAIL có chủ đích, không do may mắn |
| Cung cấp hàm dựng bảng đối chiếu dùng chung | Nguyễn Minh Quân (`corruption_flow.py`) | `build_comparison_rows()` phục vụ cả markdown report và bảng ASCII in console, nên hai nơi không bao giờ lệch số |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Dựng suite 4 expectations trên GX 1.23.2 Ephemeral Context | `quality.py::_build_suite` | Suite `papers_quality_suite`, baseline 6/6 expectation PASS | `data/quality/baseline_quality_report.json` |
| Đo Freshness SLA cho 3 trạng thái | `evaluate_freshness_sla` | `stale_ratio` 0.0417 → 0.4286 → 0.0417 | 3 file `*freshness_report.json` |
| Sinh 10 câu benchmark phủ 4 dạng | `testset.py` | `summary` 3, `authors` 3, `date` 2, `categories` 2 | `data/eval/test_set.json` |
| Đo Hit Rate / Token F1 / judge cho 3 trạng thái | `metrics.py::evaluate_pipeline` | 3 file metrics + 3 file answers, đều `samples=10` | `data/results/` |
| Viết bảng đối chiếu 3 trạng thái kèm Δ và mức phục hồi | `reporting.py::generate_corruption_report` | `corruption_report.md` 7 mục | Mở `data/reports/corruption_report.md` |

Một output cụ thể mà phần việc của tôi tạo ra:

`data/quality/corrupted_quality_report.json`: gate `success=False` với `failed_expectations = ["expect_column_values_to_be_unique", "expect_column_value_lengths_to_be_between"]`, `unexpected_count` lần lượt 4 và 3, kèm `freshness.is_fresh=False` với `stale_ratio=0.4286`. Đây là **tín hiệu chủ động duy nhất** trong toàn pipeline báo rằng dữ liệu đã hỏng — mọi thứ khác (exit code, số lượng artifact, số câu trả lời) đều trông bình thường.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Pipeline cần một chốt kiểm soát đứng **trước** vector store, tự động phát hiện dữ liệu không đủ điều kiện phục vụ, và một bộ đo định lượng được mức suy giảm chất lượng trả lời. Thách thức phụ: Great Expectations 1.x đổi hoàn toàn API so với 0.x (không còn `DataContext` kiểu cũ, không còn `expect_*` gọi trực tiếp trên dataframe), nên phải viết đúng chuẩn mới để không crash.

### Cách triển khai

Quality gate dùng `gx.get_context(mode="ephemeral")` — không ghi project file, phù hợp chạy trong pipeline — rồi `data_sources.add_pandas` → `add_dataframe_asset` → `add_batch_definition_whole_dataframe` → `get_batch(batch_parameters={"dataframe": df})`. Suite gồm 4 loại expectation: `ExpectTableRowCountToBeBetween(5, 5000)`, `ExpectColumnValuesToNotBeNull` cho 3 cột bắt buộc, `ExpectColumnValuesToBeUnique(paper_id)`, `ExpectColumnValueLengthsToBeBetween(summary, min=30)`. Kết quả `validation.describe_dict()` được làm phẳng thành từng dòng có `observed_value` và `unexpected_count` để báo cáo chỉ ra được *bao nhiêu* dòng vi phạm, không chỉ pass/fail.

Điểm thiết kế quan trọng: `success` của gate là **hợp** của GX suite **và** Freshness SLA (`gx_success and freshness["is_fresh"]`). Freshness tính riêng: stale = `age_days > 180`, và dòng có `age_days` không đọc được cũng bị tính là stale (dữ liệu không đo được là dấu hiệu xấu, không phải trung tính); cảnh báo khi `stale_ratio > 0.25`.

Về đo lường: Token F1 so tập token của câu trả lời với ground truth (harmonic mean của precision/recall). LLM judge trả về `JudgeVerdict` có cấu trúc; khi LLM lỗi, hàm rơi về heuristic dựa trên Token F1 và **đánh dấu** bằng `FALLBACK_JUDGE_REASONING`, để `_judge_mode()` đếm được và ghi `judge_mode`/`judge_fallback_count` vào metrics.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | Dataframe một stage (`baseline`/`corrupted`/`repaired`); `test_set.json`; index đã nạp |
| Output | Dict quality (gate, expectations, freshness) + JSON report; `EvaluationBundle` (summary + answers); 2 file markdown report |
| Module phụ thuộc | `great_expectations` 1.23.2, `core.config`, `retrieval.qa`, `retrieval.llm` |
| Module sử dụng output | `pipelines.phase1`, `pipelines.corruption_flow`, báo cáo nhóm |
| Điều kiện lỗi cần xử lý | Thiếu cột `age_days` → coi toàn bộ là stale; dataset rỗng → `is_fresh=False`; LLM judge lỗi/hết quota → heuristic + ghi cờ; stage lạ → tự sinh tên file report bằng `safe_slug` |

### Cách xác minh

```bash
python -c "from core.config import load_settings; from observability.quality import run_data_quality_checks; import pandas as pd; s=load_settings(); df=pd.read_json(s.paths.clean_json); print(run_data_quality_checks(df, s, 'test')['success'])"
python script/run_corruption_flow.py
```

- **Kết quả mong đợi:** gate PASS trên dữ liệu sạch; FAIL trên dữ liệu bẩn với đúng 2 expectation; PASS trở lại sau repair.
- **Kết quả thực tế:** `True` cho dữ liệu sạch; corrupted `success=False` (2 expectation FAIL, `is_fresh=False`); repaired `success=True`, `failed_expectations=[]`.
- **Artifact/log:** `data/quality/baseline_quality_report.json`, `corrupted_quality_report.json`, `repaired_quality_report.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Định nghĩa thế nào là "gate PASS" khi có hai loại tín hiệu khác bản chất: schema/validity (GX) và timeliness (Freshness).
- **Các phương án đã cân nhắc:** (1) Gate chỉ là kết quả GX suite, freshness chỉ báo cáo tham khảo; (2) Gate là hợp của GX **và** Freshness SLA; (3) Cho freshness thành một expectation trong suite GX.
- **Phương án đã chọn:** Phương án 2 — `success = gx_success and freshness["is_fresh"]`, nhưng vẫn giữ `gx_success` riêng trong report để phân biệt được lỗi thuộc loại nào.
- **Lý do:** Nếu chọn (1), kịch bản `stale_date` sẽ lọt hoàn toàn: dữ liệu lùi 365 ngày vẫn không null, không trùng, summary vẫn đủ dài — GX PASS trong khi 42.86% corpus đã quá hạn. Chọn (3) thì mất khả năng đọc tách bạch: báo cáo chỉ thấy "một expectation fail" mà không nói được đây là lỗi cấu trúc hay lỗi độ mới, trong khi hai loại này cần hai hành động khắc phục khác nhau (làm sạch vs re-fetch).
- **Bằng chứng quyết định phù hợp:** Ở trạng thái corrupted, `corruption_report.md` §2 cho thấy đồng thời `Great Expectations suite = FAIL` và `Freshness SLA = FAIL` với `stale_ratio 0.4286` — hai dòng riêng biệt. Ngược lại, kịch bản `drop_latest_records` (mất 5 bài mới nhất) **không** làm GX fail dòng nào, chứng minh nếu thiếu tín hiệu freshness thì mất hẳn một vùng quan sát.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** `judge_accuracy = 1.0` và `mean_judge_score = 5` ở baseline — điểm tuyệt đối đáng ngờ; kiểm tra thì thấy mọi verdict đều có `reasoning = "Fallback heuristic judge used because the LLM evaluator was unavailable."`, còn artifact agent ghi `GoogleRateLimitError ... 429 RESOURCE_EXHAUSTED ... limit: 20` (đã che key).
- **Lệnh hoặc bước tái hiện:** `python script/run_phase1.py` rồi đọc `data/results/baseline_answers.json`, trường `judge.reasoning`.
- **Nguyên nhân gốc:** Hạn mức Gemini free-tier là 20 request/ngày cho mỗi model, đã cạn sau các lần chạy trước. `_judge_answer` bắt mọi `Exception` và im lặng rơi về heuristic (score theo Token F1: ≥0.95 → 5, ≥0.5 → 3, còn lại → 1), nên nhìn từ ngoài, một điểm heuristic không phân biệt được với phán quyết thật của LLM.
- **Cách xử lý:** Không xóa cơ chế fallback (nó giữ cho pipeline chạy được offline), nhưng làm cho nó **không thể bị đọc nhầm**: đánh dấu verdict dự phòng bằng hằng `FALLBACK_JUDGE_REASONING`, đếm trong `_judge_mode()` và ghi `judge_mode` + `judge_fallback_count` vào cả 3 file metrics; thêm dòng "Chế độ judge" vào `phase1_report.md` §2 và `corruption_report.md` §1.
- **Cách xác minh sau khi sửa:** `baseline_metrics.json`, `corrupted_metrics.json`, `repaired_metrics.json` đều có `"judge_mode": "fallback_heuristic"` và `"judge_fallback_count": 10`; hai báo cáo markdown đều ghi rõ chế độ judge của cả 3 trạng thái.
- **Điều học được:** Một chỉ số không có metadata về nguồn gốc là một chỉ số dễ gây hiểu sai. `judge_accuracy=1.0` trông như bằng chứng hệ thống hoàn hảo, nhưng thực chất chỉ là hệ quả của Token F1 = 1.0 — nếu không ghi cờ, báo cáo sẽ vô tình khai gian.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

1. Crossref → 24 `PaperRecord` → `build_clean_dataframe()` chuẩn hóa thành 24 dòng × 13 cột, trong đó `text_for_embedding` ghép 5 phần. Dataframe đi qua quality gate của tôi trước, rồi mới được MiniLM mã hóa và nạp vào ChromaDB.
2. `build_test_set()` chọn các bài đủ metadata (không thiếu trường, tiêu đề không chứa dấu nháy đơn để không phá regex trong `qa.py`), rồi ghép (bài, dạng câu hỏi) sao cho 4 dạng phân bố đều thành 10 câu. Mỗi câu lưu `ground_truth` (giá trị đúng lấy từ cột tương ứng) và `ground_truth_doc_ids` (`paper_id`). Hit Rate đo truy hồi, Token F1 đo nội dung trả lời, LLM judge (khi có quota) đo tính đúng về ngữ nghĩa.
3. Quality checks là ảnh chụp tĩnh về hình dạng dữ liệu: đủ dòng, không null, `paper_id` duy nhất, `summary` đủ dài — lỗi ở đây là lỗi cấu trúc, khắc phục bằng làm sạch. Freshness monitoring là tín hiệu theo thời gian: tỷ lệ bài `age_days > 180` vượt 25% — khắc phục bằng re-fetch dữ liệu mới. Một dataset có thể PASS cái này mà FAIL cái kia, và bài lab này chứng minh đúng điều đó.
4. Vì test set là thước đo. Sinh lại nó từ dataset corrupted thì thước đo bị uốn theo dữ liệu hỏng: câu hỏi trích tiêu đề đã bị cắt, ground truth là summary đã rỗng — hệ thống trả lời rỗng vẫn được tính đúng. Giữ nguyên `test_set.json` (`test_set_mode=reused`) thì chênh lệch metric chỉ còn một nguyên nhân duy nhất là chất lượng dữ liệu.
5. Từ góc độ đo lường: repair thành công khi `repaired_quality_report.json` có `success=True` và `failed_expectations=[]`, `repaired_freshness_report.json` có `is_fresh=True` với `stale_ratio` về đúng 0.0417, và `repaired_metrics.json` cho 4 metric trở lại mức baseline — tương ứng cột "Mức phục hồi" = 100% trong báo cáo đối chiếu.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| --- | --: | --: | --: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.7000 | 1.0000 | −30%: 3/10 câu mất bài nguồn; chỉ số này không hề báo lỗi, nó chỉ thấp đi |
| `mean_token_f1` | 1.0000 | 0.6741 | 1.0000 | Nhạy hơn Hit Rate vì bắt cả trường hợp hit mà nội dung sai (`eval_007`, `eval_009`) |
| `judge_accuracy` | 1.0000 | 0.7000 | 1.0000 | Heuristic — phải đọc kèm `judge_mode`, tuyệt đối không trình bày như phán quyết LLM |
| `mean_judge_score` | 5.0000 | 3.6000 | 5.0000 | Phân bố ở corrupted: 6 câu score 5, 1 câu score 3 (`eval_001`), 3 câu score 1 |
| Quality checks | PASS 0 fail | FAIL 2 (`unique` 4 dòng, `summary length` 3 dòng) | PASS 0 fail | Tín hiệu duy nhất chủ động báo động |
| Freshness status | 0.0417 Fresh | 0.4286 Stale, `max_age_days` 512 | 0.0417 Fresh | Bắt được loại lỗi mà GX hoàn toàn không thấy |

### Kết luận từ số liệu

1. `blank_summary` (3 dòng) và `duplicate_rows` (2 dòng → 4 bản trùng) → GX FAIL ở `expect_column_value_lengths_to_be_between` và `expect_column_values_to_be_unique`, đồng thời `stale_date` đẩy `stale_ratio` lên 0.4286 → `mean_token_f1` giảm về 0.6741 và `mean_judge_score` về 3.6000.
2. Repair dựng lại dataset từ raw snapshot → `repaired_quality_report.json` `failed_expectations=[]` và `stale_ratio` về 0.0417 → cả 4 metric RAG về đúng mức baseline, mức phục hồi 100%.

Corruption nào ảnh hưởng rõ nhất và vì sao?

Xét theo tín hiệu quan sát được: `duplicate_rows` gây `unexpected_count` lớn nhất trong GX (4 dòng), còn `stale_date` gây biến động lớn nhất về độ lớn tương đối — `stale_ratio` tăng hơn 10 lần (0.0417 → 0.4286) và `max_age_days` từ 182 lên 512. Nhưng đáng lo nhất là phát hiện ngược: `drop_latest_records`, kịch bản phá hoại metric mạnh nhất (một mình nó làm mất 3/10 câu), lại **không kích hoạt expectation nào** — 21 dòng vẫn nằm trong ngưỡng 5–5000. Đây là vùng mù của quality gate hiện tại và là bài học lớn nhất của phần việc tôi phụ trách.

Kết quả nào khác với kỳ vọng ban đầu?

Tôi kỳ vọng `expect_table_row_count_to_be_between` sẽ bắt được việc mất 20% bản ghi. Thực tế không, vì ngưỡng đặt tuyệt đối (5–5000) chứ không so với số dòng kỳ vọng của lần chạy trước. Tôi đã kiểm chứng bằng `corrupted_quality_report.json`: expectation này `success=True` với `observed_value=21`. Giả thuyết đúng: cần một expectation so sánh tương đối (ví dụ row count không được giảm quá 10% so với snapshot trước) mới bắt được loại lỗi mất dữ liệu.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Great Expectations 1.x phải viết theo luồng context → data source → asset → batch definition → batch; dùng lại cú pháp 0.x sẽ crash. Ephemeral context là lựa chọn đúng cho pipeline vì không để lại project file.
2. Quality gate cần nhiều lớp tín hiệu: schema check bắt lỗi hình dạng, freshness bắt lỗi độ mới, và vẫn còn vùng mù (mất bản ghi) mà chỉ metric đánh giá mới thấy. Không có lớp nào thay thế được lớp nào.
3. Chỉ số phải mang theo ngữ cảnh về cách nó được tạo ra. `judge_accuracy=1.0` từ heuristic và từ LLM là hai thứ hoàn toàn khác nhau; thiếu `judge_mode` là báo cáo đang nói quá.

### Nếu có thêm thời gian

Thêm expectation kiểu volume drift: lưu row count của lần chạy trước vào `data/quality/` và FAIL nếu số dòng giảm hơn 10%. Đo cải thiện bằng cách chạy lại Phase 2: kỳ vọng `corrupted_quality_report.json` xuất hiện expectation thứ 5 FAIL do 24 → 21 dòng (giảm 12.5%), tức là gate bắt được `drop_latest_records` — vùng mù hiện tại được bịt lại, và lần này gate báo động trước khi metric tụt.

## 10. Cam kết của thành viên

*(Tự đánh dấu sau khi đọc lại toàn bộ báo cáo và artifact liên quan.)*

- [ ] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [ ] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [ ] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [ ] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [ ] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [ ] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Bùi Lê Gia Huy
**Ngày xác nhận:** 2026-09-26
