# Thiết kế: Bộ khung agent hỏi đáp tài liệu

Ngày: 2026-08-18

## Mục tiêu

Dựng một demo repo đủ sườn để kiểm chứng khả năng xây agent đọc hiểu tài liệu:
người dùng đính kèm file, hệ thống chuyển sang markdown, rồi hỏi đáp nhiều lượt
về nội dung file thông qua một agent CodeAct chạy code trong sandbox.

Đây là bộ khung, không phải sản phẩm. Tiêu chí thành công:

1. Luồng hội thoại multi-turn hoạt động đúng — lịch sử được nạp đủ và đúng thứ
   tự, agent nhớ ngữ cảnh các lượt trước, state trong sandbox giữ nguyên giữa
   các lượt.
2. Backend có ranh giới rõ ràng, thay được provider LLM / parser / sandbox mà
   không đụng tới logic agent.
3. UI Streamlit đủ để chạy demo: upload file, xem trạng thái parse, chat, xem
   agent đã chạy code gì.
4. Toàn bộ chạy bằng một `docker compose up`.

Không phải mục tiêu: chất lượng bóc tách, kỹ thuật prompt, độ chính xác câu trả
lời. Những thứ đó thuộc giai đoạn sau.

## Quyết định nền tảng

| Hạng mục | Lựa chọn | Lý do |
|---|---|---|
| LLM | Client OpenAI-compatible, `base_url` + `model` + `api_key` từ env | Dùng được OpenRouter, Cerebras, Groq... đổi provider bằng biến môi trường |
| Parser | LlamaParse (LlamaIndex Cloud) qua API | Dự án không tập trung vào xử lý file; mua ngoài |
| Sandbox | `python-vm` có sẵn, chạy độc lập ngoài compose tại port 8081 | Đã có session API stateful, giới hạn tài nguyên, chặn network, có test |
| DB | Postgres trong compose, SQLAlchemy + Alembic | Gần production, sau cắm pgvector dễ |
| Kiến trúc | FastAPI backend + Streamlit client tách service | Core agent không dính vòng đời rerun của Streamlit |
| Dữ liệu vào sandbox | Session-scoped upload, một session cho mỗi conversation | Đúng mô hình CodeAct: upload markdown một lần, giữ state giữa các lượt |

## Kiến trúc

### Service

| Service | Vai trò | Cổng |
|---|---|---|
| `postgres` | Lưu conversation, message, document, artifact, agent step | 5432 (nội bộ) |
| `api` | FastAPI: upload, parse, chat, CRUD. Chứa toàn bộ core agent | 8000 |
| `ui` | Streamlit, chỉ gọi HTTP tới `api` | 8501 |

`python-vm` **không** nằm trong compose. `api` gọi tới nó qua
`SANDBOX_BASE_URL`, từ trong container trên macOS là
`http://host.docker.internal:8081`, kèm `SANDBOX_API_KEY` gửi ở header
`Authorization: Bearer`.

File gốc và markdown lưu trên volume `./data` mount vào `api`. Không dùng MinIO
ở giai đoạn này.

`api` phụ thuộc `postgres` với `condition: service_healthy`, và chạy
`alembic upgrade head` ở entrypoint trước khi khởi động uvicorn. `ui` phụ thuộc
`api`.

### Cấu trúc code

```
api/
  app/
    api/
      documents.py      POST /documents, GET /documents, GET /documents/{id}
      conversations.py  CRUD conversation, GET messages
      chat.py           POST /conversations/{id}/messages
      health.py
    core/
      llm/
        base.py         LLMClient protocol
        openai_compat.py OpenAICompatibleClient
      parsing/
        base.py         Parser protocol
        llamaparse.py   LlamaParseParser
      sandbox/
        client.py       SandboxClient — wrap HTTP của python-vm
        resolver.py     SessionResolver — lazy re-attach
      agent/
        codeact.py      CodeActAgent — vòng lặp reason → code → exec → observe
        prompts.py
    db/
      models.py
      session.py
      migrations/       Alembic
    config.py           Settings (pydantic-settings)
  tests/
ui/
  app.py
  api_client.py
docker-compose.yml
```

Ba `Protocol` — `LLMClient`, `Parser`, `SandboxClient` — là ranh giới thật của
hệ thống: mỗi cái test được bằng fake, và thay hiện thực không đụng tới agent.

### Giao diện các Protocol

```python
class LLMClient(Protocol):
    def complete(self, messages: list[Message], *, max_tokens: int) -> LLMResponse: ...

class Parser(Protocol):
    def to_markdown(self, file_path: Path, *, mime_type: str) -> ParseResult: ...

class SandboxClient(Protocol):
    def create_session(self, files: list[SandboxFile]) -> str: ...
    def execute(self, session_id: str, code: str, *, timeout_seconds: int) -> ExecutionResult: ...
    def close_session(self, session_id: str) -> None: ...
```

`ExecutionResult` mang `status`, `stdout`, `stderr`, `timed_out`, `duration_ms`.

## Mô hình dữ liệu

- **documents** — `id`, `filename`, `mime_type`, `source_path`, `size_bytes`,
  `parse_status` (`pending` | `parsing` | `ready` | `failed`), `parse_error`,
  `created_at`
- **document_artifacts** — `id`, `document_id`, `kind` (`markdown`),
  `content_path`, `char_count`, `parser_name`, `created_at`. Tách bảng để sau
  này thêm `kind` khác (outline, chunk index) mà không đổi schema.
- **conversations** — `id`, `document_id`, `title`, `sandbox_session_id`
  (nullable), `sandbox_session_created_at`, `created_at`
- **messages** — `id`, `conversation_id`, `role` (`user` | `assistant`),
  `content`, `created_at`
- **agent_steps** — `id`, `message_id`, `step_index`, `code`, `stdout`,
  `stderr`, `status`, `duration_ms`. Đây là thứ khiến demo thuyết phục: xem
  được agent thực sự đã chạy code gì.

Thứ tự hội thoại lấy theo `created_at` kèm `id` làm khoá phụ để tie-break, tránh
lệch thứ tự khi hai bản ghi trùng timestamp.

## Luồng chạy

### Upload và parse

Parse chạy nền vì LlamaParse với tài liệu hàng trăm trang mất vài phút.

1. `POST /documents` (multipart) lưu file xuống `./data/uploads/{id}/`, tạo bản
   ghi `parse_status=pending`, đẩy job vào `BackgroundTasks`, trả `document_id`
   ngay.
2. Job đặt `parse_status=parsing`, gọi `LlamaParseParser`, ghi markdown xuống
   `./data/artifacts/{document_id}.md`, tạo `document_artifacts`, đặt
   `parse_status=ready`.
3. Lỗi thì đặt `parse_status=failed` kèm `parse_error`.
4. UI poll `GET /documents/{id}` cho tới khi `ready` hoặc `failed`.

Không dùng Celery/Redis. `BackgroundTasks` là đủ cho demo, và ranh giới đã đặt
đúng chỗ để sau này thay bằng queue thật.

### Vòng lặp CodeAct

`POST /conversations/{id}/messages` với body `{"content": "..."}`:

1. Ghi message của user vào DB ngay, trước khi gọi agent — để lượt hỏi không mất
   nếu agent lỗi giữa chừng.
2. `SessionResolver.ensure(conversation)` trả về một sandbox session sống, đảm
   bảo workspace đã có `/workspace/document.md`.
3. Dựng prompt gồm: system prompt CodeAct, mô tả tài liệu (tên file, số ký tự,
   khoảng 30 dòng đầu của markdown), và toàn bộ lịch sử hội thoại của
   conversation. **Không nhét toàn bộ markdown vào context** — đó chính là lý do
   dùng CodeAct: agent tự đọc từng phần bằng code.
4. Lặp tối đa `AGENT_MAX_STEPS` (mặc định 8):
   - Gọi LLM.
   - Nếu response có block ```python → chạy trong sandbox → ghi `agent_steps` →
     đưa stdout/stderr vào lượt kế tiếp dưới dạng observation → lặp tiếp.
   - Nếu không có block code → đó là câu trả lời cuối, thoát vòng lặp.
5. Ghi message `assistant` vào DB, trả về `{message, steps}`.

Response đồng bộ, không streaming. Streamlit hiện các bước trong `st.expander`
sau khi xong. SSE nằm ngoài phạm vi lần này.

### Vòng đời sandbox session

Nguyên tắc: **sandbox session là cache, không phải nguồn sự thật.** Nguồn sự
thật là Postgres (markdown artifact và lịch sử hội thoại). Vì vậy không cần biết
khi nào conversation "kết thúc".

`SessionResolver.ensure(conversation)`:

1. Nếu `conversation.sandbox_session_id` là null → tạo session mới, upload
   markdown, lưu id vào DB, trả về.
2. Nếu có id → dùng luôn. Khi `execute` trả 404 (session đã bị reap) → tạo mới,
   upload lại, cập nhật DB, retry **đúng một lần**. Thất bại lần hai thì báo
   lỗi.

python-vm tự dọn session idle quá `PYTHON_VM_SESSION_IDLE_TIMEOUT_SECONDS`
(mặc định 1800s) qua reaper chạy mỗi 60s, và giới hạn
`max_concurrent_sessions` (mặc định 10).

Đóng chủ động chỉ ở hai chỗ, cả hai gọi `DELETE /sessions/{id}`:

- Xoá conversation.
- Nút "Reset phiên phân tích" trong UI, dùng khi sandbox state bị bẩn.

## Xử lý lỗi

Nguyên tắc: **lỗi của code trong sandbox là dữ liệu cho agent; lỗi hạ tầng là
lỗi cho người dùng.**

| Tình huống | Xử lý |
|---|---|
| Code chạy sai (traceback, exit code khác 0) | Đưa stderr vào observation, agent tự sửa. Không phải lỗi HTTP |
| Code timeout | Như trên, kèm ghi chú đã timeout |
| Sandbox trả 404 | Tái tạo session, retry một lần |
| Sandbox trả 429 (hết session slot) | HTTP 503 kèm thông điệp rõ ràng lên UI |
| Sandbox không kết nối được | HTTP 503, UI gợi ý kiểm tra python-vm đang chạy chưa |
| LlamaParse lỗi | `parse_status=failed` + `parse_error`, UI cho bấm parse lại |
| LLM lỗi mạng / 5xx | Retry backoff 2 lần, sau đó HTTP 502 |
| Chạm `AGENT_MAX_STEPS` | Trả lời bằng những gì đã thu thập, kèm cảnh báo chưa hoàn tất |

## UI Streamlit

Một trang, hai cột:

- **Sidebar** — upload file, danh sách document kèm trạng thái parse, danh sách
  conversation, nút tạo conversation mới, nút reset phiên phân tích.
- **Chính** — khung chat: lịch sử message; mỗi câu trả lời của assistant kèm một
  `expander` "Các bước agent đã chạy" hiện code, stdout, stderr của từng
  `agent_step`.

Streamlit chỉ gọi HTTP qua `ui/api_client.py`, không import gì từ `api/app`.

## Cấu hình

Biến môi trường, đọc bằng pydantic-settings, khai báo trong `.env.example`:

```
DATABASE_URL=postgresql+psycopg://app:app@postgres:5432/file_understanding

LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=
LLM_MODEL=anthropic/claude-sonnet-4.5
LLM_MAX_TOKENS=4096

LLAMA_CLOUD_API_KEY=

SANDBOX_BASE_URL=http://host.docker.internal:8081
SANDBOX_API_KEY=dev-secret
SANDBOX_TIMEOUT_SECONDS=30

AGENT_MAX_STEPS=8
DATA_DIR=/data
```

## Kiểm thử

Viết theo TDD. Chạy bằng conda env `minhln`
(`/Users/macpro24/miniconda3/envs/minhln/bin/python`), không dựng venv mới.

Test đặt ở các ranh giới, dùng fake cho cả ba protocol:

- `FakeLLMClient` phát kịch bản dựng sẵn → test vòng lặp CodeAct: dừng đúng lúc
  khi không còn block code, đếm bước đúng, chạm `AGENT_MAX_STEPS` thì dừng, đưa
  stderr vào observation đúng định dạng.
- `FakeSandboxClient` → test `SessionResolver`: tạo mới khi chưa có id; tái tạo
  và upload lại đúng một lần khi gặp 404; không retry vô hạn.
- **Test multi-turn** (quan trọng nhất): hai lượt liên tiếp trong cùng
  conversation phải dùng lại đúng một `sandbox_session_id`, và prompt lượt hai
  phải chứa đủ lịch sử lượt một theo đúng thứ tự.
- Test DB dùng Postgres thật qua fixture, mỗi test một transaction rollback.
- Một smoke test end-to-end chạy compose thật, đánh dấu
  `@pytest.mark.integration` để tách khỏi vòng test nhanh.

## Ngoài phạm vi

Auth và multi-user. Retrieval bằng vector. Nhiều tài liệu trong một hội thoại.
Streaming SSE. Đo chi phí token. Xuất báo cáo. Chất lượng prompt và độ chính xác
câu trả lời.

Khung để sẵn chỗ cắm cho những thứ này nhưng không xây.
