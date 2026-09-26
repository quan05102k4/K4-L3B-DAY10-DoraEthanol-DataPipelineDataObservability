# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Nguyễn Khánh Đô |
| MSSV | 2A202602687 |
| Khóa/Lớp | K4 — L3B |
| Tên nhóm | DoraEthanol |
| Vai trò chính | RAG & Vector Index (embedding, ChromaDB, QA agent) |
| Repository | `K4-L3B-DAY10-DoraEthanol-DataPipelineDataObservability` (nhánh `main`) |
| Ngày hoàn thành | 2026-09-26 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Embedding backend | `src/retrieval/embeddings.py` (`MiniLMEmbeddings`, `_load_model` có `lru_cache`) | `text_for_embedding` | Vector 384 chiều đã normalize | Hoàn thành |
| Vector store | `src/retrieval/index.py` (`LocalEmbeddingIndex.build/load/search/lookup`) | dataframe của từng trạng thái | 3 collection ChromaDB + 3 manifest `data/embeddings/*.json` | Hoàn thành |
| Truy hồi & trả lời | `src/retrieval/qa.py` (`answer_question`, `_extract_answer`) | câu hỏi + index | `AnswerResult` (answer, `retrieved_doc_ids`, contexts) | Hoàn thành |
| Multi-provider router | `src/retrieval/llm.py` (`build_llm`) | `Settings` | Client cho 7 provider: gemini/openai/anthropic/openrouter/ollama/custom/mock | Hoàn thành |
| Tool-calling agent | `src/retrieval/agent.py` (`build_agent` với 2 tool) | `Settings` + index | Agent `paper_corpus_agent`; artifact `data/results/agent_demo_answers.json` | Một phần — code hoàn chỉnh nhưng lần chạy gần nhất không gọi được LLM do quota 429 |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Xác minh số document mỗi trạng thái | Nguyễn Minh Quân (`corruption_flow.py`) | `papers-baseline 24`, `papers-corrupted 21`, `papers-repaired 24` — khớp đúng số dòng dataset |
| Truy vết câu trả lời rỗng của `eval_009` | Bùi Lê Gia Huy (`metrics.py`) | Chỉ ra nguyên nhân là thứ hạng bị xáo trộn do `truncate_title`, không phải lỗi tính Token F1 |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Nạp 24 document sạch vào `papers-baseline` | `index.py::build` | Collection 24 docs, space cosine | `phase1_report.md` §1 (`indexed_documents=24`) |
| Nạp dataset corrupted 21 dòng vào collection riêng | `_derive_collection_name` theo manifest path | `papers-corrupted` 21 docs | Log Phase 2: `collection=papers-corrupted docs=21` |
| Nạp dataset repaired vào `papers-repaired` | `index.py::build` (xóa collection trước khi tạo) | `papers-repaired` 24 docs | Log Phase 2: `docs=24` |
| Truy hồi top-4 + trích câu trả lời theo dạng câu hỏi | `qa.py` | `retrieved_doc_ids`, `retrieved_contexts` trong `*_answers.json` | `data/results/baseline_answers.json` |
| Router đa provider | `llm.py` | Đổi provider chỉ bằng biến môi trường, có `mock` để chạy offline | `python -c "from core.config import load_settings; from retrieval.llm import build_llm; build_llm(load_settings())"` |

Một output cụ thể mà phần việc của tôi tạo ra:

Ba collection ChromaDB độc lập trong `data/chroma/` với số document khớp đúng số dòng của từng dataset (24 / 21 / 24). Đây là điều kiện để bảng đối chiếu 3 trạng thái có nghĩa: nếu ba trạng thái dùng chung một collection thì sau khi repair sẽ không còn cách nào kiểm chứng lại trạng thái corrupted. Kiểm tra lại bất cứ lúc nào bằng `chromadb.PersistentClient('data/chroma').list_collections()`.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Cần một vector store cục bộ cho phép nạp ba phiên bản khác nhau của cùng một corpus mà không đè lên nhau, và phải nạp được cả dataset có `paper_id` trùng lặp (do kịch bản `duplicate_rows` cố tình tạo ra) — trong khi ChromaDB yêu cầu ID document là duy nhất.

### Cách triển khai

ID document là `record_id = f"{paper_id}::{index}"`, còn `paper_id` gốc nằm trong metadata cùng title/published/authors/categories/summary/url. Cách này giữ được đúng số document bằng số dòng dataset kể cả khi có DOI trùng, mà ground truth vẫn đối chiếu được qua metadata. Tên collection được suy ra từ đường dẫn manifest embedding (`_derive_collection_name`): `papers_embeddings.json` → `papers-baseline`, `..._corrupted.json` → `papers-corrupted`, `..._repaired.json` → `papers-repaired`; đường dẫn lạ thì rơi về `safe_slug(stem)`. Trước khi tạo, collection cũ luôn bị `delete_collection` — nhờ đó mỗi lần chạy là một lần ghi đè sạch, không cộng dồn document của lần trước (điều kiện để pipeline idempotent). Embedding dùng `normalize_embeddings=True` với space cosine, và điểm số trả về là `max(0, 1 − distance)` để dễ đọc. Ở `qa.py`, câu hỏi có tiêu đề trong dấu nháy đơn sẽ được thử tra cứu chính xác trước (`index.lookup`), kết quả đó được ghim lên đầu danh sách rồi mới ghép với top-k từ tìm kiếm ngữ nghĩa.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | Dataframe có cột `paper_id`, `title`, `text_for_embedding` + metadata; đường dẫn manifest embedding quyết định tên collection |
| Output | `LocalEmbeddingIndex` (query được) + manifest JSON chứa `collection_name`, `persist_path`, danh sách document |
| Module phụ thuộc | `ingestion.cleaning` (cấu trúc cột), `core.utils`, `chromadb`, `sentence_transformers` |
| Module sử dụng output | `evaluation.metrics` (`evaluate_pipeline`), `retrieval.agent`, `pipelines.phase1` và `pipelines.corruption_flow` |
| Điều kiện lỗi cần xử lý | Collection đã tồn tại → xóa rồi tạo lại; kết quả truy vấn thiếu metadata/document → bỏ qua bản ghi đó; `lookup` không thấy → trả `None` để `qa.py` chỉ dùng kết quả ngữ nghĩa |

### Cách xác minh

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
python -c "import chromadb; c=chromadb.PersistentClient(path='data/chroma'); print([(x.name, x.count()) for x in c.list_collections()])"
```

- **Kết quả mong đợi:** 3 collection với 24 / 21 / 24 document.
- **Kết quả thực tế:** `[('papers-baseline', 24), ('papers-corrupted', 21), ('papers-repaired', 24)]`.
- **Artifact/log:** `data/chroma/`, `data/embeddings/papers_embeddings.json`, `..._corrupted.json`, `..._repaired.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Dataset corrupted có 2 cặp `paper_id` trùng lặp; cần quyết định dùng gì làm ID document trong ChromaDB.
- **Các phương án đã cân nhắc:** (1) Dùng thẳng `paper_id` làm ID; (2) Dùng ID tổng hợp `paper_id::row_index` và giữ `paper_id` trong metadata; (3) Dedupe trước khi nạp để ID luôn duy nhất.
- **Phương án đã chọn:** Phương án 2.
- **Lý do:** Phương án 1 làm ChromaDB ghi đè bản trùng, dataset 21 dòng sẽ chỉ còn 19 document — tức là vector store tự "sửa" mất đúng lỗi mà bài lab cần quan sát. Phương án 3 còn tệ hơn: nó biến tầng index thành một bước làm sạch ngầm, khiến quality gate và index nói hai câu chuyện khác nhau về cùng một dataset. Phương án 2 giữ vector store trung thực với dữ liệu đầu vào, còn việc phán xét dữ liệu bẩn là việc của quality gate.
- **Bằng chứng quyết định phù hợp:** Log Phase 2 in `docs=21` cho collection corrupted, khớp đúng `row_count=21` trong `corrupted_quality_report.json`; GX vẫn bắt được `expect_column_values_to_be_unique` FAIL với `unexpected_count=4` vì dữ liệu trùng không bị index che đi.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Câu `eval_009` ("What is the summary of the paper 'Hybrid Search Architectures: Combining BM25 with Dense Representations'?") ở trạng thái corrupted trả về **chuỗi rỗng**, Token F1 = 0, trong khi `retrieval_hit` vẫn được tính là `True`.
- **Lệnh hoặc bước tái hiện:** `python script/run_corruption_flow.py`, sau đó mở `data/results/corrupted_answers.json` tại `id = eval_009`.
- **Nguyên nhân gốc:** Chuỗi hai bước. (a) `truncate_title` cắt tiêu đề bài `10.1145/3637528.3671811` còn 7 ký tự, nên `index.lookup()` theo tiêu đề chính xác không còn khớp — mất đường ưu tiên ghim bài đúng lên top-1 trong `qa.py`. (b) Thứ hạng ngữ nghĩa vì thế đưa bài `10.1145/3637528.3671823` lên top-1, mà bài này nằm trong nhóm bị `blank_summary`, nên `_extract_answer` trả về `first_sentence("")` = chuỗi rỗng. Bài đúng vẫn nằm ở hạng 4 trong top-4 nên Hit Rate vẫn tính là hit.
- **Cách xử lý:** Đây là hành vi **đúng** của hệ thống trước dữ liệu bẩn, nên tôi không "sửa" để làm đẹp số liệu. Việc tôi làm là xác minh và ghi lại chuỗi nhân quả: đối chiếu `retrieved_doc_ids` của `eval_009` với `corruption_log.json` để chứng minh top-1 là bài bị bỏ trắng summary, và đưa phát hiện này vào báo cáo nhóm §10 như một ca Silent Failure điển hình.
- **Cách xác minh sau khi sửa:** Ở trạng thái repaired, cùng câu `eval_009` có Token F1 = 1.0000 và nhóm `summary` trở lại `retrieval_hit_rate=1.0`, `mean_token_f1=1.0` (`repaired_metrics.json`) — xác nhận nguyên nhân nằm ở dữ liệu, không nằm ở code truy hồi.
- **Điều học được:** Retrieval Hit Rate chỉ trả lời "bài đúng có nằm trong top-k không", nó không trả lời "câu trả lời có đúng không". Một hệ thống có thể đạt hit rate hoàn hảo mà vẫn trả lời rỗng, nếu top-1 là tài liệu đã hỏng. Muốn đọc đúng sức khỏe hệ thống phải xem Hit Rate cùng Token F1, và nên cân nhắc đo cả thứ hạng (MRR) chứ không chỉ "có/không".

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

1. Crossref → `PaperRecord` → dataframe sạch với cột `text_for_embedding` gồm 5 phần. Ở tầng của tôi, mỗi dòng thành một document: nội dung là `text_for_embedding`, ID là `paper_id::row_index`, metadata giữ đủ trường để trả lời (authors, published, categories, summary, url). MiniLM-L6-v2 mã hóa nội dung thành vector 384 chiều đã normalize, `collection.add()` nạp vào ChromaDB persistent tại `data/chroma/`.
2. Khi đánh giá, mỗi câu hỏi được embed rồi truy vấn cosine lấy `top_k=4`. `retrieved_doc_ids` (lấy từ metadata `paper_id`) đem so với `ground_truth_doc_ids` → Hit Rate. Câu trả lời do `_extract_answer` trích từ metadata của top-1 theo từ khóa trong câu hỏi, rồi so với `ground_truth` → Token F1.
3. Quality checks soi cấu trúc dataset trước khi nạp vector (null, trùng, độ dài, số dòng). Freshness soi độ mới theo `age_days`. Ở tầng vector store thì cả hai đều nằm **trước** tôi: nếu gate đã FAIL mà vẫn nạp thì index sẽ mang nguyên lỗi vào serving — đó chính là kịch bản Phase 2 dựng lại để chứng minh.
4. Vì test set sinh ra từ dataset. Sinh lại trên dữ liệu bẩn thì ground truth cũng bẩn (tiêu đề bị cắt, summary rỗng), và câu trả lời rỗng sẽ được tính là đúng. Giữ nguyên test set thì ba lần đo chỉ khác nhau ở dữ liệu được index.
5. Ở góc độ của tôi: collection `papers-repaired` có đúng 24 document, `matches_baseline=True`, và cùng bộ câu hỏi cho lại Hit Rate 1.0000 / Token F1 1.0000 — tức là không gian vector đã trở về đúng trạng thái sạch, không phải "gần giống".

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| --- | --: | --: | --: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.7000 | 1.0000 | 3 câu miss vì bài nguồn không còn trong collection — index không thể truy hồi thứ không tồn tại |
| `mean_token_f1` | 1.0000 | 0.6741 | 1.0000 | Có câu hit nhưng trả lời sai: lỗi nằm ở nội dung document, không ở khâu xếp hạng |
| `judge_accuracy` | 1.0000 | 0.7000 | 1.0000 | Heuristic, chỉ đọc như hệ quả của Token F1 |
| `mean_judge_score` | 5.0000 | 3.6000 | 5.0000 | Ba câu bị hạ về 1 đều là câu có Token F1 = 0 |
| Quality checks | PASS | FAIL (2) | PASS | Index vẫn nạp được dữ liệu FAIL gate — đúng lý do cần gate **trước** khi nạp |
| Freshness status | Fresh | Stale 0.4286 | Fresh | Metadata `published` trong vector store cũng bị lùi theo, nên câu trả lời về ngày sai |

### Kết luận từ số liệu

1. `drop_latest_records` khiến collection `papers-corrupted` chỉ còn 21 document → 3 câu hỏi có `ground_truth_doc_ids` không nằm trong collection → `retrieval_hit_rate` = 0.7000 (`corrupted_answers.json`: `eval_001`, `eval_002`, `eval_003` đều `hit=False`).
2. Repair nạp lại `papers-repaired` với đủ 24 document → mọi `ground_truth_doc_ids` trở lại nằm trong collection → Hit Rate và Token F1 đều về 1.0000 (`repaired_metrics.json`).

Corruption nào ảnh hưởng rõ nhất và vì sao?

Ở tầng retrieval, `drop_latest_records` là rõ nhất và không có cách nào chống: 5 bài bị xóa khỏi collection thì 3 câu hỏi liên quan mất hẳn khả năng hit, bất kể `top_k` bằng bao nhiêu. Nhưng loại tôi thấy nguy hiểm hơn về mặt thiết kế là `truncate_title`, vì nó không tấn công vector mà tấn công **đường đi phụ** của `qa.py`: cơ chế tra cứu chính xác theo tiêu đề. Khi lối đi đó vỡ, thứ hạng bị xáo trộn và top-1 có thể rơi vào một tài liệu hỏng khác — một lỗi lan truyền, khó đoán hơn là mất bản ghi.

Kết quả nào khác với kỳ vọng ban đầu?

Tôi kỳ vọng `inject_noise` làm điểm cosine tụt rõ và đẩy bài bẩn ra khỏi top-4. Thực tế 3 bài bị chèn rác vẫn không rơi khỏi top-4 ở câu nào và cũng không lên top-1 gây sai. Tôi kiểm tra bằng cách đối chiếu `paper_id` của 3 bài đó với `retrieved_doc_ids` trong `corrupted_answers.json`. Giả thuyết: chuỗi rác chỉ chiếm một phần nhỏ trong `text_for_embedding` (vốn có cả Title/Authors/Published/Categories), nên vector vẫn nằm gần vị trí cũ. Muốn thấy tác động cần chèn rác vào nhiều trường hơn hoặc tăng tỷ lệ chèn.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Vector store phải trung thực với dữ liệu đầu vào: chọn ID document sai (dùng `paper_id`) sẽ khiến index âm thầm dedupe và xóa mất bằng chứng lỗi. Việc phán xét dữ liệu là của quality gate, không phải của tầng index.
2. Nạp lại index phải là ghi đè sạch (`delete_collection` trước khi `create_collection`), nếu không thì số document cộng dồn qua các lần chạy và mọi so sánh đều vô nghĩa.
3. Chất lượng câu trả lời không tỷ lệ thuận với chất lượng truy hồi: `eval_009` hit mà trả lời rỗng, `eval_002` miss mà Token F1 = 1.0. Phải đọc hai chỉ số cùng nhau.

### Nếu có thêm thời gian

Thêm MRR / Recall@k cạnh Hit Rate và ghi lại thứ hạng của bài đúng trong `*_answers.json`. Với `eval_009`, Hit Rate hiện cho 1 điểm dù bài đúng chỉ ở hạng 4; MRR sẽ hạ xuống 0.25 và phản ánh đúng mức suy giảm. Đo cải thiện bằng cách so MRR ba trạng thái: kỳ vọng thấy khoảng cách baseline–corrupted rộng hơn Hit Rate, tức là chỉ số nhạy hơn với dữ liệu bẩn.

## 10. Cam kết của thành viên

*(Tự đánh dấu sau khi đọc lại toàn bộ báo cáo và artifact liên quan.)*

- [ ] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [ ] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [ ] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [ ] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [ ] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [ ] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Khánh Đô
**Ngày xác nhận:** 2026-09-26
