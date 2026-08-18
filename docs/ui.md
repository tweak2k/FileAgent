# UI

Streamlit, in two files:

- `ui/api_client.py` — every HTTP call to the backend
- `ui/app.py` — the page itself

`ui/app.py` imports nothing from `api/app`. The only contract between them is
HTTP, which is what keeps the backend free to be used by something other than
this page.

On-screen text is Vietnamese, since that is the audience. Comments and
docstrings are English, like the rest of the repo.

## Layout

```
┌─ sidebar ──────────────┬─ main ───────────────────────┐
│ Tài liệu               │ Hỏi đáp tài liệu             │
│  [ upload ]            │                              │
│  [ Bắt đầu bóc tách ]  │  user:      Gói thầu số mấy? │
│                        │  assistant: Gói thầu số 33.  │
│  Trạng thái tài liệu:  │   ▸ Các bước agent đã chạy(1)│
│  - a.pdf: sẵn sàng     │                              │
│  - b.pdf: thất bại — … │  [ Hỏi gì về tài liệu này? ] │
│                        │                              │
│  [ chọn tài liệu ▾ ]   │                              │
│  Hội thoại             │                              │
│  [ Tạo hội thoại mới ] │                              │
│  [ chọn hội thoại ▾ ]  │                              │
│  [ Reset phiên phân tích ]                            │
└────────────────────────┴──────────────────────────────┘
```

Every assistant reply carries an expander listing the agent's steps: the code,
its stdout, and its stderr in red. That panel is the point of the demo — it
shows what the agent actually did rather than asking anyone to trust it.

## Parse polling

Upload is asynchronous, so the sidebar polls:

1. After upload, the document id goes into `st.session_state["pending_document_id"]`.
2. Each run calls `get_document(pending_id)`. While the status is `pending` or
   `parsing`, the sidebar shows a message, sleeps `POLL_INTERVAL_SECONDS` (3),
   and reruns.
3. Once the status settles the key is popped. On `failed`, the error is shown.

Two details in that flow are easy to get wrong, and both have a comment in the
code:

**No `st.rerun()` after rendering the error.** A rerun restarts the script with
the key already popped, so the error disappears before anyone reads it. The
script falls through to the document list instead.

**Pop the key even when the call raises.** Otherwise every later rerun dies on
the same line and the UI is stuck for good.

The document list shows *all* documents with their status, not just the ready
ones — a failed parse has to be visible. Only ready documents can be selected
for a conversation, because the API returns 409 for anything else.

## Error handling

`ApiClient` raises `ApiError` carrying the backend's `detail` and the HTTP
status. The status is what lets the UI say something useful about a 503:

```
Sandbox không dùng được: ...

Kiểm tra xem sandbox (python-vm) đã chạy ở cổng 8081 chưa.
```

`render_sidebar` wraps its whole body in `try/except ApiError` and returns
`None` on failure, so a backend problem shows a message instead of a Streamlit
traceback. The chat input has its own handler.

`health()` is the one method that never raises: it returns `False` when the API
is unreachable, and the page shows a connection message rather than crashing.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `API_BASE_URL` | `http://api:8000` | Backend base URL; compose sets it for the service network |

Running the UI outside compose against a local API means
`API_BASE_URL=http://localhost:8000`.

The HTTP client uses a 600-second timeout because one chat turn can run several
sandbox executions.

## Tests

`ui/tests/test_api_client.py` covers the client with `httpx.MockTransport`, so
no network is involved. `ui/app.py` has no automated tests — the project has no
Streamlit test harness. Check it by hand after changing it:

```bash
docker compose up -d --build ui
open http://localhost:8501
```
