# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Nguyễn Minh Quân |
| MSSV | 2A202602490 |
| Khóa/Lớp | K4 — L3B |
| Tên nhóm | DoraEthanol |
| Vai trò chính | Trưởng nhóm / Pipeline Integrator (orchestration + repair flow) |
| Repository | `K4-L3B-DAY10-DoraEthanol-DataPipelineDataObservability` (nhánh `main`) |
| Ngày hoàn thành | 2026-09-26 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Cấu hình & đường dẫn artifact | `src/core/config.py` (`Paths`, `Settings`, `load_settings`, `normalized_provider`) | biến môi trường `.env` | Một `Settings` bất biến chứa 30 đường dẫn artifact cho cả 3 trạng thái | Hoàn thành |
| Tiện ích I/O dùng chung | `src/core/utils.py` (`write_json`, `write_csv`, `read_json`, `now_utc`, `safe_slug`) | path + payload | Ghi file UTF-8 tự tạo thư mục cha | Hoàn thành |
| Orchestration Phase 1 | `src/pipelines/phase1.py` (`run_phase1_pipeline`, `_load_records`, `_judge_mode`, `_demo_agent`) | `Settings` | `data/reports/phase1_report.md`, `baseline_metrics.json` | Hoàn thành |
| Orchestration Phase 2 | `src/pipelines/corruption_flow.py` (`run_corruption_flow_pipeline`, `_evaluate_stage`, `_load_baseline`, `_print_comparison`) | `Settings` + artifact Phase 1 | Bảng đối chiếu 3 trạng thái trên console + `corruption_report.md` | Hoàn thành |
| Cơ chế phục hồi | `src/pipelines/corruption_flow.py::repair_from_raw_snapshot()` | `data/raw/crossref_records.json` | `papers_clean_repaired.csv|json` + summary repair | Hoàn thành |
| Entrypoint | `script/run_phase1.py`, `script/run_corruption_flow.py` | CLI | 2 lệnh chạy exit code 0 | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Rà soát bảo mật trước khi nộp | Cả nhóm | `.env` đã nằm trong `.gitignore`, không có trong git history; `grep` xác nhận không hardcode path tuyệt đối trong `src/` và `script/` |
| Chốt hợp đồng dữ liệu giữa các module | Trần Anh Đăng, Nguyễn Khánh Đô | Thống nhất `build_clean_dataframe` là điểm vào duy nhất tạo dataframe (baseline và repaired dùng chung), nhờ đó `matches_baseline=True` |
| Phân chia file commit theo vai trò | Cả nhóm | Bảng phân công file trong `docs/TEAM.md` để 4 người đều có commit riêng trên `main` |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Nối 6 bước Phase 1 và in log từng bước | `pipelines/phase1.py` | `phase1_report.md` sinh 2026-09-26T04:04:05Z, Hit Rate 1.0000 | `python script/run_phase1.py` |
| Nối 6 bước Phase 2: corrupt → đo → repair → đo → đối chiếu | `pipelines/corruption_flow.py` | `corruption_report.md`, `corrupted_metrics.json`, `repaired_metrics.json` | `python script/run_corruption_flow.py` |
| Bảo đảm 3 trạng thái dùng chung một test set | `_evaluate_stage()` truyền `settings.paths.eval_testset` | 3 file metrics đều `samples=10` | So `samples` trong 3 file `*_metrics.json` |
| Viết cơ chế repair idempotent | `repair_from_raw_snapshot()` | `rows_restored=3`, `idempotent_rerun_identical=True`, `matches_baseline=True` | `corruption_report.md` §5 |
| In bảng so sánh 3 cột ra console | `_console_table()`, `_print_comparison()` | Bảng ASCII 6 cột (kèm Delta và Recovery) | Log cuối của `run_corruption_flow.py` |

Một output cụ thể mà phần việc của tôi tạo ra:

Bảng đối chiếu 3 trạng thái trong `data/reports/corruption_report.md` §1 và bản in ASCII trên console: Retrieval Hit Rate 1.0000 → 0.7000 → 1.0000, Mean Token F1 1.0000 → 0.6741 → 1.0000, kèm cột "Mức phục hồi" = 100% cho cả 4 metric. Cột này do tôi định nghĩa theo công thức `(repaired − corrupted) / (baseline − corrupted)`, để báo cáo trả lời được câu "phục hồi bao nhiêu phần trăm" thay vì chỉ liệt kê ba con số rời.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Ba module dữ liệu (ingestion/cleaning, retrieval/index, observability/evaluation) do ba người khác nhau viết. Phần của tôi là làm cho chúng chạy đúng thứ tự, dùng đúng một bộ cấu hình, và bảo đảm phép so sánh 3 trạng thái là công bằng — tức là cùng test set, cùng cách tính metric, cùng công thức `text_for_embedding`, chỉ khác dữ liệu.

### Cách triển khai

Phase 2 được viết thành 6 bước rõ ràng. Bước 1 lấy mốc baseline: nếu `papers_clean.json`, `baseline_metrics.json` và `test_set.json` đều còn thì dùng lại (`mode=reuse_phase1_artifacts`), thiếu bất kỳ file nào thì tự gọi `run_phase1_pipeline()` để Phase 2 không bao giờ so sánh với một mốc không tồn tại. Bước 3 và 5 dùng chung một hàm `_evaluate_stage()` — cùng một đường code nạp Chroma, gọi `evaluate_pipeline`, bổ sung `by_question_type` và `judge_mode`, rồi chạy quality gate — nên corrupted và repaired không thể bị đo bằng hai cách khác nhau. Bước 4 gọi `repair_from_raw_snapshot()`: đọc raw snapshot, gọi lại `build_clean_dataframe()` của baseline, ghi đè artifact repaired, và dựng lại dataframe **lần thứ hai** từ cùng snapshot để so khớp — đó là bằng chứng idempotent chứ không phải lời khẳng định suông.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | `Settings` (từ `load_settings()`), artifact Phase 1 (`papers_clean.json`, `baseline_metrics.json`, `test_set.json`), raw snapshot `crossref_records.json` |
| Output | `CorruptionFlowResult` (baseline/corrupted/repaired + log + repair summary) và 13 artifact trong `data/` |
| Module phụ thuộc | `ingestion.cleaning`, `ingestion.corruption`, `ingestion.crossref`, `retrieval.index`, `evaluation.metrics`, `observability.quality`, `observability.reporting` |
| Module sử dụng output | `script/run_corruption_flow.py`; báo cáo nhóm và phần demo CP6 |
| Điều kiện lỗi cần xử lý | Thiếu artifact baseline → chạy lại Phase 1; thiếu cả hai raw snapshot → `RuntimeError` có chỉ rõ đường dẫn; LLM judge lỗi → `evaluate_pipeline` tự fallback và tôi ghi `judge_mode` vào metrics để số liệu không bị đọc sai |

### Cách xác minh

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
```

- **Kết quả mong đợi:** cả hai exit code 0; console in bảng 3 trạng thái; sinh `corruption_report.md`.
- **Kết quả thực tế:** đúng như mong đợi. Log cuối: `DONE hit_rate baseline=1.0000 -> corrupted=0.7000 -> repaired=1.0000 | quality_gate corrupted=False repaired=True | matches_baseline=True`.
- **Artifact/log:** `data/reports/corruption_report.md`, `data/results/corrupted_metrics.json`, `data/results/repaired_metrics.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Cần chỗ để nạp dữ liệu corrupted và repaired vào vector store mà vẫn giữ được bằng chứng của trạng thái trước đó.
- **Các phương án đã cân nhắc:** (1) Dùng lại một collection `papers-baseline` và ghi đè ở mỗi bước; (2) Tạo 3 collection riêng `papers-baseline` / `papers-corrupted` / `papers-repaired` cùng 3 manifest embedding riêng.
- **Phương án đã chọn:** Phương án 2, đồng thời cho mỗi stage một file quality report và freshness report riêng (`corrupted_freshness_report.json`, `repaired_freshness_report.json`) thay vì ghi đè `freshness_report.json` của baseline.
- **Lý do:** Ghi đè một collection sẽ khiến bảng đối chiếu không thể kiểm chứng lại — sau khi repair xong thì không còn gì chứng minh trạng thái corrupted từng tồn tại, và giám khảo không thể truy vấn lại. Ba collection tách biệt đắt hơn về dung lượng nhưng cho phép mở Chroma ra đếm trực tiếp.
- **Bằng chứng quyết định phù hợp:** `chromadb.PersistentClient('data/chroma').list_collections()` trả về `papers-baseline 24`, `papers-corrupted 21`, `papers-repaired 24` — đúng số dòng của từng dataset, và cả 3 vẫn dùng để kiểm tra lại sau khi pipeline kết thúc.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** `GoogleRateLimitError: Error calling model 'gemini-3.8-flash' (RESOURCE_EXHAUSTED): 429 ... Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20` (ghi trong `data/results/agent_demo_answers.json`, đã che key).
- **Lệnh hoặc bước tái hiện:** `python script/run_phase1.py` — bước demo agent và bước LLM judge.
- **Nguyên nhân gốc:** Hạn mức free-tier của Gemini là 20 request/ngày cho mỗi model; Phase 1 tiêu 10 request cho judge, Phase 2 tiêu thêm 20 request cho 2 lần đánh giá, nên quota cạn. Đây **không** phải lỗi sai tên model — model tồn tại, chỉ hết hạn mức.
- **Cách xử lý:** Không bịa số: giữ nguyên cơ chế fallback heuristic của `_judge_answer`, nhưng bắt buộc ghi `judge_mode` và `judge_fallback_count` vào cả 3 file metrics và in ra mọi báo cáo, để người đọc biết `judge_accuracy=1.0` đến từ heuristic chứ không phải LLM. Bước demo agent được bọc `try/except` ghi lỗi vào artifact thay vì làm sập pipeline.
- **Cách xác minh sau khi sửa:** `judge_mode=fallback_heuristic` và `judge_fallback_count=10` xuất hiện trong `baseline_metrics.json`, `corrupted_metrics.json`, `repaired_metrics.json`; dòng "Chế độ judge" có trong cả `phase1_report.md` và `corruption_report.md`; hai pipeline vẫn exit code 0.
- **Điều học được:** Một chỉ số phụ thuộc dịch vụ ngoài phải mang theo metadata về nguồn gốc của nó. Nếu chỉ ghi `judge_accuracy=1.0` thì báo cáo trông đẹp nhưng sai bản chất; ghi kèm `judge_mode` mới là số liệu trung thực.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

1. Crossref `/works` trả JSON (query về agentic RAG, filter `has-abstract:true`); payload gốc được lưu `crossref_response.json`, bóc tách thành 24 `PaperRecord` lưu `crossref_records.json`. `build_clean_dataframe()` chuẩn hóa thành 24 dòng × 13 cột, ghép `text_for_embedding` gồm 5 phần Title/Authors/Published/Categories/Summary. MiniLM-L6-v2 biến chuỗi đó thành vector, nạp vào collection Chroma kèm metadata để truy vấn.
2. `test_set.json` gồm 10 câu, mỗi câu có `ground_truth` (chuỗi trả lời đúng lấy từ dataset) và `ground_truth_doc_ids` (`paper_id` của bài nguồn). Retrieval Hit Rate kiểm tra top-4 trả về có chứa `paper_id` đó hay không — đo chất lượng **truy hồi**; Token F1 so câu trả lời với `ground_truth` — đo chất lượng **trả lời**. Hai chỉ số này có thể lệch nhau, và chính chỗ lệch mới lộ ra lỗi (ca `eval_002` và `eval_009`).
3. Quality check (GX) trả lời "dữ liệu có đúng hình dạng không": đủ dòng, không null, `paper_id` duy nhất, summary đủ dài — lỗi tĩnh, phát hiện ngay. Freshness monitoring trả lời "dữ liệu có còn mới không": tỷ lệ bài `age_days > 180` vượt 25% hay chưa — dữ liệu có thể hoàn toàn hợp lệ về cấu trúc mà vẫn quá cũ để dùng.
4. Vì nếu sinh lại test set trên dữ liệu bẩn thì cả câu hỏi và ground truth đều bẩn theo, metric sẽ vẫn cao trong khi hệ thống đang trả lời sai — mất luôn hiện tượng cần đo. Giữ nguyên test set thì mọi chênh lệch chỉ còn một nguyên nhân: chất lượng dữ liệu.
5. Repair được coi là thành công khi hội đủ: `matches_baseline=True` (dataset khớp baseline), `idempotent_rerun_identical=True` (dựng lại lần hai cho kết quả y hệt), GX suite 0 expectation FAIL, `is_fresh=True` với `stale_ratio` về 0.0417, và 4 metric RAG trở lại mức baseline (mức phục hồi 100%).

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| --- | --: | --: | --: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.7000 | 1.0000 | Đúng 3 câu bị mất bài nguồn — khớp chính xác 5 dòng bị xóa ở kịch bản 1 |
| `mean_token_f1` | 1.0000 | 0.6741 | 1.0000 | Giảm sâu hơn Hit Rate (−32.59% so với −30%) vì có câu retrieval đúng mà trả lời vẫn sai |
| `judge_accuracy` | 1.0000 | 0.7000 | 1.0000 | Bám theo Token F1 vì judge đang là heuristic; không đọc như phán quyết LLM |
| `mean_judge_score` | 5.0000 | 3.6000 | 5.0000 | 3 câu bị hạ thẳng về score 1 — tương ứng 3 câu Token F1 = 0 |
| Quality checks | PASS (0 fail) | FAIL (2 fail) | PASS (0 fail) | Gate là chốt duy nhất *chủ động* báo lỗi; metric chỉ "tụt" trong im lặng |
| Freshness status | Fresh 0.0417 | Stale 0.4286 | Fresh 0.0417 | Trở về đúng con số cũ, không phải "xấp xỉ" — bằng chứng repair dựng lại từ nguồn |

### Kết luận từ số liệu

1. `drop_latest_records` xóa 5 bài mới nhất và `duplicate_rows` nhân bản 2 dòng → row count 24 → 21 và GX FAIL ở `expect_column_values_to_be_unique` (`unexpected_count=4`) → `retrieval_hit_rate` tụt 1.0000 → 0.7000 vì 3 câu hỏi không còn bài nguồn trong index.
2. `repair_from_raw_snapshot()` dựng lại 24 dòng từ `crossref_records.json` → GX về 0 fail và `stale_ratio` về 0.0417 → cả 4 metric RAG trở lại đúng mức baseline, mức phục hồi 100%.

Corruption nào ảnh hưởng rõ nhất và vì sao?

Ở góc độ orchestration, `drop_latest_records` là nặng nhất với metric: nó không làm bẩn ô nào, chỉ **xóa** bài — và retrieval không thể truy hồi thứ không tồn tại, nên 3/10 câu mất hẳn cơ hội đúng. Đáng chú ý là kịch bản này lại **không** làm GX FAIL (21 dòng vẫn nằm trong ngưỡng 5–5000, không null, không trùng): mất 20% tri thức mới mà quality gate vẫn im lặng, chỉ Freshness và metric mới thấy. Đó là lý do nhóm không dựa vào GX một mình.

Kết quả nào khác với kỳ vọng ban đầu?

Tôi kỳ vọng `mean_token_f1` giảm cùng nhịp với Hit Rate, nhưng thực tế nó giảm sâu hơn và có 2 ca trái chiều: `eval_002` retrieval sai mà Token F1 = 1.0 (bài thay thế tình cờ cùng danh sách tác giả), còn `eval_009` retrieval tính là đúng mà câu trả lời rỗng. Tôi đã kiểm tra bằng cách đối chiếu `retrieved_doc_ids` với `corruption_log.json`: `eval_009` có bài nguồn ở hạng 4 nên hit vẫn True, nhưng top-1 là bài bị bỏ trắng summary. Kết luận: hai chỉ số phải đọc cùng nhau, không thay thế được nhau.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Pipeline phải idempotent theo nghĩa kiểm chứng được: mỗi bước nạp lại đều xóa collection cũ trước khi tạo, và repair phải dựng lại từ nguồn bất biến — bằng chứng là chạy hai lần cho kết quả giống nhau, không phải vì code "trông có vẻ đúng".
2. Observability là hai lớp tín hiệu khác nhau: GX bắt lỗi hình dạng, Freshness bắt lỗi thời gian. Có loại corruption chỉ một trong hai lớp phát hiện được, và có loại (`drop_latest_records`) chỉ metric mới thấy.
3. Dữ liệu hỏng không làm chương trình báo lỗi. Pipeline vẫn exit code 0, vẫn ghi đủ artifact, agent vẫn trả lời 10/10 câu — trong khi 30% câu trả lời đã sai. Không có bộ đo, không ai biết.

### Nếu có thêm thời gian

Nối self-healing thật: thay vì gọi repair vô điều kiện, để `run_corruption_flow_pipeline` kiểm tra `corrupted.quality["success"]`, nếu `False` thì tự kích hoạt `repair_from_raw_snapshot()` và ghi lý do rollback vào log. Đo cải thiện bằng cách chèn một corruption mới chưa từng chạy và xác nhận pipeline tự phục hồi mà không cần sửa code — đúng tiêu chí bonus B2.

## 10. Cam kết của thành viên

*(Tự đánh dấu sau khi đọc lại toàn bộ báo cáo và artifact liên quan.)*

- [ ] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [ ] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [ ] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [ ] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [ ] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [ ] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Minh Quân
**Ngày xác nhận:** 2026-09-26
