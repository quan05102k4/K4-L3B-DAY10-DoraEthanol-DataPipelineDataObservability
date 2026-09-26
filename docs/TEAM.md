# Danh Sách Thành Viên & Báo Cáo Phân Công Nhóm

- **Tên Nhóm:** `DoraEthanol`
- **Mã Nhóm / Lớp:** `K4-L3B-DAY10`
- **Tên Repository Nộp Bài:** `K4-L3B-DAY10-DoraEthanol-DataPipelineDataObservability`
- **Ngày hoàn thành:** 2026-09-26
- **Nhánh nộp bài:** `main`

---

## # Thành viên

| STT | Họ và tên | MSSV | Email | Vai trò & Phân công công việc | Báo cáo cá nhân |
|---:|---|---|---|---|---|
| 1 | Nguyễn Minh Quân | 2A202602490 | quan05102k4@gmail.com | Trưởng nhóm / Pipeline Integrator (`core/`, `phase1.py`, `corruption_flow.py`) | `report/individual_2A202602490_NguyenMinhQuan.md` |
| 2 | Trần Anh Đăng | 2A202602992 | trananhdang2004@gmail.com | Data Foundation & Recovery (`crossref.py`, `cleaning.py`, `corruption.py`, raw data) | `report/individual_2A202602992_TranAnhDang.md` |
| 3 | Nguyễn Khánh Đô | 2A202602687 | nguyenkhanhdo27@gmail.com | RAG & Vector Index (`retrieval/index.py`, `embeddings.py`, `qa.py`, `agent.py`, ChromaDB) | `report/individual_2A202602687_NguyenKhanhDo.md` |
| 4 | Bùi Lê Gia Huy | 2A202602607 | builegiahuywork@gmail.com | Observability & Evaluation (`quality.py` GX 1.x, `testset.py`, `metrics.py`, `reporting.py`) | `report/individual_2A202602607_BuiLeGiaHuy.md` |

---

## # Bảng tự chấm tỷ lệ đóng góp (% Contribution)

Tỷ lệ dưới đây do cả 4 thành viên thống nhất, đối chiếu theo khối lượng module sở hữu và lịch sử commit trên nhánh `main`.

| STT | Thành viên | Checkpoint phụ trách chính | Deliverable chính | % Contribution |
|---:|---|---|---|---:|
| 1 | Nguyễn Minh Quân | CP0 (môi trường), CP3, CP5, CP6 | `core/config.py`, `core/utils.py`, `pipelines/phase1.py`, `pipelines/corruption_flow.py`, `script/`, `data/reports/`, điều phối demo | 25% |
| 2 | Trần Anh Đăng | CP0 (ingestion), CP1 (cleaning), CP4 | `ingestion/crossref.py`, `ingestion/cleaning.py`, `ingestion/corruption.py`, `data/raw/`, `data/clean/` | 25% |
| 3 | Nguyễn Khánh Đô | CP2 (indexing), CP4/CP5 (re-index) | `retrieval/embeddings.py`, `retrieval/index.py`, `retrieval/qa.py`, `retrieval/agent.py`, `retrieval/llm.py`, `data/chroma/`, `data/embeddings/` | 25% |
| 4 | Bùi Lê Gia Huy | CP1 (GX 1.x), CP2 (test set), CP3/CP5 (đo lường & báo cáo) | `observability/quality.py`, `observability/reporting.py`, `evaluation/testset.py`, `evaluation/metrics.py`, `data/quality/`, `data/eval/`, `data/results/` | 25% |
| | **TỔNG** | | | **100%** |

---

## # Phân công file & commit trên nhánh `main`

Mỗi thành viên tự commit đúng nhóm file thuộc phạm vi của mình bằng tài khoản GitHub cá nhân (không dùng co-author, không commit hộ nhau) để tab **Insights → Contributors** ghi nhận đủ 4 người.

| Thứ tự | Thành viên | File / thư mục thuộc phạm vi commit | Thông điệp commit gợi ý |
|---:|---|---|---|
| 1 | Trần Anh Đăng | `src/ingestion/crossref.py`, `src/ingestion/cleaning.py`, `src/ingestion/corruption.py`, `src/ingestion/__init__.py`, `data/raw/`, `data/clean/` | `feat(ingestion): crossref fetch + cleaning + 6 corruption scenarios` |
| 2 | Nguyễn Khánh Đô | `src/retrieval/`, `data/embeddings/`, `data/chroma/` | `feat(retrieval): MiniLM embeddings + 3 ChromaDB collections + QA agent` |
| 3 | Bùi Lê Gia Huy | `src/observability/`, `src/evaluation/`, `data/quality/`, `data/eval/`, `data/results/` | `feat(observability): GX 1.x quality gate, freshness SLA, testset & metrics` |
| 4 | Nguyễn Minh Quân | `src/core/`, `src/pipelines/`, `script/`, `data/reports/`, `docs/TEAM.md`, `report/group_report.md`, `README.md` | `feat(pipelines): phase1 + corruption/repair flow & báo cáo đối chiếu 3 trạng thái` |
| 5 | Mỗi thành viên | `report/individual_<MSSV>_<HoTen>.md` của chính mình | `docs(report): báo cáo cá nhân <Họ tên>` |

Ràng buộc kỹ thuật: commit theo thứ tự trên (ingestion → retrieval → observability → pipelines) để mỗi commit đều là trạng thái import được; tuyệt đối không commit `.env` (đã chặn trong `.gitignore`).

---

## # Cá nhân

### ## Nguyễn Minh Quân - 2A202602490
- **Vai trò:** Trưởng nhóm & Điều phối Pipeline.
- **Công việc chi tiết đã hoàn thành:**
  - Thiết lập cấu hình hệ thống `core/config.py` (toàn bộ `Paths` cho 3 trạng thái dữ liệu) và tiện ích I/O `core/utils.py`.
  - Kết nối luồng thực thi trong `src/pipelines/phase1.py` (6 bước) và `src/pipelines/corruption_flow.py` (6 bước, gồm `repair_from_raw_snapshot()`).
  - Chạy nghiệm thu toàn tuyến: `run_phase1.py` và `run_corruption_flow.py` đều exit code 0; kiểm tra tính nhất quán giữa artifact và số liệu trong báo cáo.
- **Điều học được / Đóng góp chính:**
  - Hiểu sâu về Idempotent Pipeline: repair dựng lại dataset từ snapshot thô thay vì vá từng ô hỏng, xác minh bằng `idempotent_rerun_identical` và `matches_baseline` đều `True`.

### ## Trần Anh Đăng - 2A202602992
- **Vai trò:** Phụ trách Ingestion, Làm sạch, Làm bẩn & Phục hồi dữ liệu.
- **Công việc chi tiết đã hoàn thành:**
  - Xây dựng module thu thập Crossref API với retry/backoff và fallback offline trong `src/ingestion/crossref.py`; bảo toàn 2 raw artifact (24 record).
  - Chuẩn hóa schema 13 cột, tính `age_days`, ghép `text_for_embedding` 5 phần trong `src/ingestion/cleaning.py` (24/24 record hợp lệ, `dropped_rows=0`).
  - Triển khai đủ 6 kịch bản corruption trong `src/ingestion/corruption.py` với seed cố định `20261010` và nhật ký before/after từng dòng.
- **Điều học được / Đóng góp chính:**
  - Kỹ thuật Data Lineage: chỉ ghi đè `crossref_response.json` khi thực sự có payload mới từ API, nhờ đó snapshot thô luôn đủ tin cậy để phục hồi.

### ## Nguyễn Khánh Đô - 2A202602687
- **Vai trò:** Phụ trách RAG, Vector Database & Embedding.
- **Công việc chi tiết đã hoàn thành:**
  - Quản lý mô hình embedding `sentence-transformers/all-MiniLM-L6-v2` (`retrieval/embeddings.py`, cache model bằng `lru_cache`).
  - Nạp và quản lý 3 collection riêng biệt trong ChromaDB: `papers-baseline` (24 docs), `papers-corrupted` (21 docs), `papers-repaired` (24 docs), khoảng cách cosine.
  - Xây dựng QA pipeline `retrieval/qa.py` và tool-calling agent `retrieval/agent.py` (2 tool: `semantic_search_papers`, `lookup_paper`).
- **Điều học được / Đóng góp chính:**
  - Cách cô lập không gian vector theo từng trạng thái để so sánh khách quan, và phát hiện điểm yếu của cơ chế tra cứu theo tiêu đề khi title bị cắt (ca `eval_009`).

### ## Bùi Lê Gia Huy - 2A202602607
- **Vai trò:** Phụ trách Data Observability & Benchmark Evaluation.
- **Công việc chi tiết đã hoàn thành:**
  - Thiết lập Quality Gate chuẩn **Great Expectations 1.23.2** (Ephemeral Context, 4 expectations) và Freshness SLA trong `src/observability/quality.py`.
  - Xây dựng bộ 10 câu hỏi benchmark phủ 4 dạng nghiệp vụ trong `src/evaluation/testset.py` và bộ đo Hit Rate / Token F1 / LLM judge trong `src/evaluation/metrics.py`.
  - Viết `src/observability/reporting.py` sinh `phase1_report.md` và bảng đối chiếu 3 trạng thái trong `corruption_report.md`.
- **Điều học được / Đóng góp chính:**
  - Quality Gate phải là hợp của GX suite **và** Freshness SLA: ở trạng thái corrupted, GX bắt được trùng `paper_id` (4 dòng) và summary quá ngắn (3 dòng), còn Freshness bắt được `stale_ratio` 42.86% — hai loại tín hiệu không thay thế được nhau.
