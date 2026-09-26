# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Trần Anh Đăng |
| MSSV | 2A202602992 |
| Khóa/Lớp | K4 — L3B |
| Tên nhóm | DoraEthanol |
| Vai trò chính | Data Foundation & Recovery (ingestion, cleaning, corruption suite) |
| Repository | `K4-L3B-DAY10-DoraEthanol-DataPipelineDataObservability` (nhánh `main`) |
| Ngày hoàn thành | 2026-09-26 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Thu thập dữ liệu nguồn | `src/ingestion/crossref.py` (`fetch_source_records`, `parse_crossref_payload`, `load_raw_records`) | Crossref `/works` + `Settings` | `data/raw/crossref_response.json` (24 items), `data/raw/crossref_records.json` (24 records) | Hoàn thành |
| Bóc tách & làm sạch văn bản | `crossref.py::_strip_markup`, `_first_text` | Trường `title`, `abstract` dạng JATS | Chuỗi không còn thẻ `<jats:p>`, đã unescape HTML entity | Hoàn thành |
| Chuẩn hóa dataset | `src/ingestion/cleaning.py` (`build_clean_dataframe`, `build_embedding_text`) | 24 `PaperRecord` | `data/clean/papers_clean.csv|json` — 24 dòng × 13 cột | Hoàn thành |
| Bộ kịch bản làm bẩn | `src/ingestion/corruption.py` (`corrupt_clean_dataframe` + 6 kịch bản) | dataframe sạch | `data/clean/papers_clean_corrupted.csv|json`, `data/results/corruption_log.json` | Hoàn thành |
| Nguồn dữ liệu cho repair | `load_raw_records()` chấp nhận cả 2 định dạng snapshot | `crossref_records.json` hoặc `crossref_response.json` | 24 `PaperRecord` để `repair_from_raw_snapshot()` dựng lại dataset | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Kiểm tra dữ liệu sau repair | Nguyễn Minh Quân (`corruption_flow.py`) | Đối chiếu `papers_clean_repaired.csv` với `papers_clean.csv`: khớp 24/24 dòng trên cả 13 cột (`matches_baseline=True`) |
| Giải thích ngữ nghĩa cột cho quality gate | Bùi Lê Gia Huy (`quality.py`) | Thống nhất ngưỡng `summary` ≥ 30 ký tự ở GX thấp hơn ngưỡng cleaning (40) để kịch bản `blank_summary` chắc chắn bị bắt |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Gọi Crossref có retry/backoff + fallback snapshot | `crossref.py::fetch_source_records` | 24 record, `source_mode=raw_records_snapshot` ở lần chạy gần nhất | `phase1_report.md` §1 |
| Bóc thẻ JATS khỏi abstract | `_strip_markup` | Cột `summary` sạch markup trong `papers_clean.csv` | Mở CSV, không còn chuỗi `<jats:p>` |
| Chuẩn hóa 13 cột + `age_days` + dedupe | `build_clean_dataframe` | 24/24 record hợp lệ, `dropped_rows=0` | `phase1_report.md` §1 |
| Tiêm đủ 6 kịch bản corruption có seed | `corrupt_clean_dataframe` | 24 → 21 dòng, 22 bản ghi thay đổi | `data/results/corruption_log.json` |
| Ghi nhật ký before/after từng dòng | `_record`, `_scenario` | Log có `baseline_row`, `paper_id`, `before`, `after`, `note` | `corruption_log.json` §scenarios |

Một output cụ thể mà phần việc của tôi tạo ra:

`data/results/corruption_log.json`: 6 block kịch bản, `seed=20261010`, tổng `total_change_records=22` (xóa 5, thêm 2, sửa 13), và mỗi bản ghi đều có `baseline_row` trỏ về chỉ số dòng của dataset sạch. Nhờ trường này, nhóm truy nguyên được từng câu hỏi bị hỏng về đúng kịch bản gây ra nó — ví dụ `eval_009` lần về `truncate_title` trên bài `10.1145/3637528.3671811`.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Abstract của Crossref không phải văn bản thuần: nó bọc trong thẻ JATS (`<jats:p>`), có HTML entity, có tiền tố "Abstract:" và khoảng trắng lộn xộn. Nếu đưa nguyên chuỗi đó vào embedding thì vector mang theo rác markup. Ngoài ra, dữ liệu nguồn phải được bảo toàn nguyên trạng để bước repair ở CP5 còn chỗ dựa — nếu snapshot thô bị ghi đè bởi dữ liệu đã biến đổi thì không còn gì phục hồi.

### Cách triển khai

Về ingestion: `fetch_source_records` thử tối đa 3 lần, retry khi gặp 429/500/502/503/504, timeout 30s; nếu vẫn lỗi mạng thì đọc snapshot local. Điểm quan trọng là `crossref_response.json` **chỉ** được ghi đè khi thực sự nhận payload mới từ API (`if source == "api"`), còn khi fallback thì chỉ đọc — nhờ vậy snapshot gốc bất biến. Về cleaning: mỗi record đi qua chuỗi normalize → parse ISO date → kiểm tra ngưỡng (`title` ≥ 10, `summary` ≥ 40) → tính `age_days` → sinh `text_for_embedding`; sau đó sort theo `published` giảm dần rồi `drop_duplicates(subset="paper_id", keep="first")` để mỗi DOI chỉ giữ bản mới nhất. Về corruption: cả 6 kịch bản dùng một `random.Random(CORRUPTION_SEED)` duy nhất, các kịch bản sau chọn dòng trên phần còn lại của kịch bản trước (`inject_noise` còn loại trừ các dòng vừa bị `blank_summary`) để mỗi hiện tượng quan sát được độc lập. Cuối cùng `summary_chars`, `age_days` và `text_for_embedding` được tính lại cho toàn dataset theo đúng công thức của cleaning — nếu không, dữ liệu bẩn sẽ "tố giác" chính nó bằng các cột dẫn xuất không khớp.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | Crossref payload JSON; hoặc snapshot `crossref_response.json` / `crossref_records.json`; với corruption là dataframe sạch 24 dòng |
| Output | `list[PaperRecord]`; dataframe 13 cột theo `CLEAN_COLUMNS`; dataframe corrupted 21 dòng + `corruption_log.json` |
| Module phụ thuộc | `core.utils` (normalize, I/O), `requests` |
| Module sử dụng output | `retrieval.index` (embedding), `observability.quality` (gate), `pipelines.phase1` và `pipelines.corruption_flow` |
| Điều kiện lỗi cần xử lý | API 429/5xx → retry rồi fallback snapshot; không có snapshot → `RuntimeError`; record thiếu trường bắt buộc → loại bỏ; payload không sinh được record nào → `RuntimeError` |

### Cách xác minh

```bash
python -c "from core.config import load_settings; from ingestion.crossref import load_raw_records; s=load_settings(); print(len(load_raw_records(s.paths.raw_records_json)))"
python script/run_phase1.py
python script/run_corruption_flow.py
```

- **Kết quả mong đợi:** 24 record từ snapshot; clean 24 dòng, `dropped_rows=0`; corruption tạo đúng 6 kịch bản và còn 21 dòng.
- **Kết quả thực tế:** đúng như mong đợi — log Phase 2 in `scenarios=6 rows 24 -> 21 (removed=5 added=2 modified=13)`.
- **Artifact/log:** `data/raw/`, `data/clean/papers_clean.csv`, `data/results/corruption_log.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Chọn cách phục hồi dữ liệu sau khi dataset đã bị tiêm 6 loại lỗi khác nhau.
- **Các phương án đã cân nhắc:** (1) Viết hàm sửa từng loại lỗi: điền lại summary rỗng, khôi phục title bị cắt, dedupe, cộng bù ngày bị lùi; (2) Bỏ hẳn dataset hỏng, đọc lại raw snapshot và dựng lại toàn bộ bằng chính `build_clean_dataframe()` của baseline.
- **Phương án đã chọn:** Phương án 2.
- **Lý do:** Phương án 1 phải viết 6 hàm nghịch đảo, mà có kịch bản **không** nghịch đảo được: `truncate_title` cắt mất ký tự, `blank_summary` xóa trắng nội dung — thông tin đã biến mất khỏi dataset, không thể suy ra từ dữ liệu hỏng. Vá từng ô chỉ che được triệu chứng ở những cột còn manh mối, và mỗi lần chạy lại sẽ cho kết quả khác nhau (không idempotent). Dựng lại từ nguồn thì mọi cột đều sinh lại từ dữ liệu gốc, và chi phí chỉ là một lần đọc file 24 record.
- **Bằng chứng quyết định phù hợp:** `corruption_report.md` §5 ghi `matches_baseline=True` và `idempotent_rerun_identical=True`; §3 cho thấy `blank_summaries` 3 → 0, `titles_below_min` 3 → 0, `duplicate_paper_ids` 2 → 0, `noisy_summaries` 3 → 0 — tất cả dấu hiệu hỏng đều về 0, không còn sót.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Sau khi tiêm corruption, quality gate ban đầu **không** FAIL ở expectation về độ dài `summary` như kỳ vọng, dù đã có 3 dòng bị xóa trắng.
- **Lệnh hoặc bước tái hiện:** `python script/run_corruption_flow.py` rồi đọc `data/quality/corrupted_quality_report.json`, xem `failed_expectations`.
- **Nguyên nhân gốc:** Gate kiểm tra trên cột `summary`, nhưng các cột dẫn xuất (`summary_chars`, `text_for_embedding`) vẫn còn giá trị cũ của dữ liệu sạch vì tôi chưa tính lại sau khi biến đổi. Dataset ở trạng thái "nửa hỏng": ô nội dung đã rỗng mà siêu dữ liệu vẫn báo dài — không phản ánh đúng một sự cố thật ngoài sản xuất, nơi mọi cột dẫn xuất được tính lại theo dữ liệu bẩn.
- **Cách xử lý:** Thêm bước 7 trong `corrupt_clean_dataframe`: sau khi tiêm đủ 6 kịch bản, tính lại `summary_chars = summary.str.len()`, ép `age_days` về int64 và sinh lại `text_for_embedding` cho **toàn bộ** dataset bằng đúng `build_embedding_text()` mà cleaning dùng.
- **Cách xác minh sau khi sửa:** `corrupted_quality_report.json` có `expect_column_value_lengths_to_be_between` FAIL với `unexpected_count=3` (đúng 3 dòng bị blank) và `expect_column_values_to_be_unique` FAIL với `unexpected_count=4`; `corruption_report.md` §3 hiển thị `summaries_below_min=3`.
- **Điều học được:** Làm bẩn dữ liệu cũng phải tôn trọng hợp đồng dữ liệu. Nếu chỉ sửa cột hiển thị mà bỏ cột dẫn xuất thì bài thực nghiệm đo một trạng thái không tồn tại trong thực tế, và quality gate sẽ im lặng vì lý do sai.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

1. Crossref trả về danh sách `items`; mỗi item được bóc DOI, title, abstract (gỡ thẻ JATS), tác giả, subject, ngày `published`/`created` thành `PaperRecord`. Hai file raw được lưu để giữ lineage. `build_clean_dataframe()` chuẩn hóa, loại record không đủ điều kiện, khử trùng `paper_id`, rồi ghép `text_for_embedding` 5 phần — đây chính là chuỗi được MiniLM mã hóa thành vector và nạp vào ChromaDB kèm metadata.
2. Mỗi câu hỏi trong test set gắn với một bài cụ thể: `ground_truth_doc_ids` là `paper_id` của bài đó, `ground_truth` là giá trị đúng lấy từ cột tương ứng (summary/authors/published/categories). Hit Rate đo top-4 có chứa bài đó không; Token F1 so câu trả lời với chuỗi đúng.
3. Quality check kiểm tra hình dạng dữ liệu tại một thời điểm (đủ dòng, không null, không trùng, summary đủ dài). Freshness monitoring kiểm tra độ mới theo thời gian (`age_days > 180`, cảnh báo khi vượt 25% tổng số bài). Dữ liệu có thể sạch hoàn hảo nhưng toàn bộ đã cũ 2 năm — GX sẽ PASS, Freshness sẽ FAIL.
4. Vì test set được sinh **từ** dataset. Nếu sinh lại trên dữ liệu bẩn thì câu hỏi sẽ trích tiêu đề đã bị cắt và ground truth sẽ là summary đã rỗng — hệ thống trả lời "rỗng" lại được tính là đúng. So sánh chỉ có nghĩa khi thước đo không thay đổi.
5. Thành công khi dataset sau repair khớp baseline trên cả 24 dòng × 13 cột (`matches_baseline=True`), mọi dấu hiệu hỏng trong §3 của báo cáo về 0, GX 0 fail, `is_fresh=True`, và metric RAG trở lại mức baseline.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| --- | --: | --: | --: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.7000 | 1.0000 | 3 câu hỏng đều trỏ vào 3 trong 5 bài tôi xóa ở kịch bản 1 — quan hệ nhân quả trực tiếp |
| `mean_token_f1` | 1.0000 | 0.6741 | 1.0000 | Phần giảm thêm ngoài retrieval đến từ `stale_date` và `blank_summary` làm nội dung trả lời sai |
| `judge_accuracy` | 1.0000 | 0.7000 | 1.0000 | Đang là heuristic nên chỉ dùng để tham chiếu xu hướng |
| `mean_judge_score` | 5.0000 | 3.6000 | 5.0000 | 3 câu Token F1 = 0 bị hạ về score 1 |
| Quality checks | PASS | FAIL: `unique paper_id` (4), `summary length` (3) | PASS | Đúng 2 kịch bản tôi thiết kế để đánh vào GX |
| Freshness status | 0.0417 Fresh | 0.4286 Stale | 0.0417 Fresh | Kịch bản `stale_date` đặt ratio 0.30 > ngưỡng 0.25 nên FAIL là tất yếu |

### Kết luận từ số liệu

1. `blank_summary` xóa trắng 3 summary và `duplicate_rows` nhân bản 2 dòng → GX FAIL đồng thời ở `expect_column_value_lengths_to_be_between` (`unexpected_count=3`) và `expect_column_values_to_be_unique` (`unexpected_count=4`) → câu `eval_009` nhận top-1 là bài có summary rỗng nên trả về chuỗi trống, Token F1 = 0.
2. Repair đọc lại 24 record từ `crossref_records.json` và dựng lại dataset → `blank_summaries`, `noisy_summaries`, `titles_below_min`, `duplicate_paper_ids` đều về 0 và `stale_ratio` về 0.0417 → Token F1 trở lại 1.0000.

Corruption nào ảnh hưởng rõ nhất và vì sao?

Với tư cách người thiết kế bộ kịch bản, tôi thấy `stale_date` là loại nguy hiểm nhất về bản chất, dù nó không làm Hit Rate giảm dòng nào. Lý do: nó không xóa, không làm rỗng, không làm trùng — dữ liệu vẫn "hợp lệ" hoàn toàn với GX (cả 4 expectation vẫn PASS ở phần liên quan), nhưng agent trả lời sai một cách trông rất thuyết phục: `eval_007` trả về `2025-06-04` thay vì `2026-06-04`. Một câu trả lời sai đúng định dạng, đúng ngữ cảnh, lệch đúng 365 ngày — người dùng không có cách nào phát hiện. Chỉ Freshness SLA bắt được (`stale_ratio` 0.4286 > 0.25).

Kết quả nào khác với kỳ vọng ban đầu?

Tôi kỳ vọng `inject_noise` sẽ kéo Token F1 xuống mạnh vì chuỗi rác làm lệch embedding. Thực tế 3 dòng bị chèn rác không đánh sập câu nào trực tiếp: `mean_token_f1` của nhóm `summary` còn 0.5802 nhưng phần lớn là do bài bị xóa và bài bị bỏ trắng summary. Tôi đã kiểm tra bằng cách đối chiếu `paper_id` của 3 dòng noise với `retrieved_doc_ids` trong `corrupted_answers.json` — chúng không nằm ở top-1 của câu nào. Giả thuyết: với corpus chỉ 24 bài và `top_k=4`, phần văn bản sạch còn lại trong summary vẫn đủ giữ vector gần đúng vị trí cũ; muốn thấy rõ tác động của noise cần tăng tỷ lệ chèn hoặc chèn vào cả `title`.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Bảo toàn dữ liệu thô là điều kiện tiên quyết của mọi cơ chế phục hồi: chỉ ghi đè snapshot khi thật sự có payload mới, còn lại chỉ đọc. Không có nguyên tắc này thì repair không có nguồn nào để dựng lại.
2. Làm bẩn dữ liệu phải giữ tính nhất quán nội bộ (tính lại mọi cột dẫn xuất) và phải có seed cố định, nếu không thì mỗi lần chạy là một thí nghiệm khác nhau và không ai kiểm chứng được kết luận.
3. Có loại lỗi dữ liệu mà không expectation nào bắt được: xóa bớt bản ghi mới và lùi ngày đều tạo ra dataset "hợp lệ". Vì thế cần cả Freshness SLA và bộ metric đánh giá, không chỉ schema check.

### Nếu có thêm thời gian

Thêm kịch bản thứ 7 — hoán đổi `authors_joined` giữa các bài (identity swap). Đây là lỗi mà cả GX (không null, không trùng, đủ dài) và Freshness (ngày không đổi) đều PASS, chỉ Token F1 ở nhóm câu hỏi `authors` phát hiện được. Đo cải thiện bằng cách xác nhận `by_question_type.authors.mean_token_f1` giảm trong khi `quality gate` vẫn PASS — chứng minh thêm một vùng mù của quality gate.

## 10. Cam kết của thành viên

*(Tự đánh dấu sau khi đọc lại toàn bộ báo cáo và artifact liên quan.)*

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Trần Anh Đăng
**Ngày xác nhận:** 2026-09-26
