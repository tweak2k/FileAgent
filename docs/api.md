# HTTP API

Base URL `http://localhost:8000`. Interactive docs at `/docs`.

No authentication — this is a local demo. Error bodies are always
`{"detail": "..."}`, with Vietnamese text since it is shown to end users.

## Health

### `GET /health`

```json
{"status": "ok", "service": "file-understanding-api"}
```

Does not touch the database. Used by the compose healthcheck and by the UI on
startup.

## Documents

### `POST /documents`

Upload a file. Multipart, field name `file`.

Returns **201** immediately, before parsing has run:

```json
{
  "id": 1,
  "filename": "hsmt.pdf",
  "mime_type": "application/pdf",
  "parse_status": "pending",
  "parse_error": null,
  "char_count": 0
}
```

The filename is normalised to its last path component, so `../../evil.pdf` is
stored as `evil.pdf`.

Parsing then runs in the background: status moves to `parsing`, then `ready` or
`failed`. Poll `GET /documents/{id}` to follow it.

### `GET /documents`

Every document, newest first, whatever its status. `char_count` is 0 until
parsing succeeds.

### `GET /documents/{id}`

One document. **404** when it does not exist.

When `parse_status` is `failed`, `parse_error` carries the reason (truncated at
2000 characters).

## Conversations

### `POST /conversations`

```json
{"document_id": 1, "title": "optional"}
```

**201:**

```json
{"id": 1, "document_id": 1, "title": "Hỏi đáp — hsmt.pdf", "sandbox_session_id": null}
```

- **404** — the document does not exist
- **409** — the document is not `ready` yet

`sandbox_session_id` stays null until the first turn that runs code.

### `GET /conversations?document_id={id}`

Conversations, newest first. The `document_id` filter is optional.

### `GET /conversations/{id}/messages`

The full history in `(created_at, id)` order. Each assistant message carries the
steps that produced it:

```json
[
  {"id": 1, "role": "user", "content": "Gói thầu số mấy?", "created_at": "...", "steps": []},
  {
    "id": 2,
    "role": "assistant",
    "content": "Gói thầu số 33.",
    "created_at": "...",
    "steps": [
      {
        "step_index": 0,
        "code": "print(open('document.md').read()[:500])",
        "stdout": "# Gói thầu 33\n...",
        "stderr": "",
        "status": "completed",
        "duration_ms": 42
      }
    ]
  }
]
```

**404** when the conversation does not exist.

### `POST /conversations/{id}/messages`

Ask a question.

```json
{"content": "Giá gói thầu là bao nhiêu?"}
```

Returns the assistant's `MessageOut` once the agent has finished. This is
**synchronous and can take a while** — one turn may run up to
`AGENT_MAX_STEPS` code executions. The UI's HTTP client uses a 600-second
timeout. There is no streaming.

| Status | Meaning |
|---|---|
| 200 | Answered |
| 404 | No such conversation |
| 409 | The document has no markdown artifact |
| 502 | The LLM failed after its retries |
| 503 | The sandbox is unreachable or out of session slots |

The user's question is stored before the agent runs, so a 502 or 503 never
loses it. Steps that executed before the failure are stored too, attached to an
assistant message recording the error.

### `POST /conversations/{id}/reset-sandbox`

Closes the conversation's sandbox session and clears its id. The next turn
starts from a clean interpreter with the markdown re-uploaded. Use it when the
sandbox state has become confusing.

**204** on success, **404** if the conversation does not exist, **503** if the
sandbox could not be reached.

### `DELETE /conversations/{id}`

Deletes the conversation and, by cascade, its messages and agent steps.

**204** on success, **404** if it does not exist. A sandbox that is down does
**not** block the delete: the session is left for python-vm's reaper.

## Adding a route

1. Add the schema to `api/app/api/schemas.py`.
2. Add the handler to the relevant router. Keep it thin: load the row, call a
   service, map exceptions.
3. Reuse `_raise_for_service_error` for anything the chat layer can raise —
   the order of the `isinstance` checks matters, because
   `SandboxCapacityError` is a subclass of `SandboxError`.
4. Write the test first, then update this document.
