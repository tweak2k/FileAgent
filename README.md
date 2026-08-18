# file-understanding

Bộ khung agent hỏi đáp tài liệu: upload file → chuyển sang markdown bằng LlamaParse →
hỏi đáp nhiều lượt qua agent CodeAct chạy code trong sandbox `python-vm`.

## Yêu cầu

- Docker + Docker Compose
- `python-vm` đang chạy sẵn ở port 8081 (repo riêng, không nằm trong compose này)
- Key LlamaParse và key của một provider LLM OpenAI-compatible (OpenRouter, Cerebras...)

## Chạy

```bash
cp .env.example .env
# điền LLM_API_KEY và LLAMA_CLOUD_API_KEY vào .env
docker compose up --build
```

- UI: http://localhost:8501
- API docs: http://localhost:8000/docs

## Kiến trúc

| Thành phần | Vai trò |
|---|---|
| `postgres` | conversation, message, document, artifact, agent step |
| `api` | FastAPI, chứa core agent |
| `ui` | Streamlit, chỉ gọi HTTP |
| `python-vm` (ngoài compose) | sandbox chạy code, giữ state theo session |

Sandbox session là cache chứ không phải nguồn sự thật: nếu session bị `python-vm`
dọn do idle, hệ thống tự tạo lại và upload lại markdown.

## Test

```bash
/Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest -m "not integration"
```

Smoke test cần compose và `python-vm` đang chạy:

```bash
/Users/macpro24/miniconda3/envs/minhln/bin/python -m pytest -m integration
```

## Thiết kế và kế hoạch

- Spec: `docs/superpowers/specs/2026-08-18-file-understanding-framework-design.md`
- Plan: `docs/superpowers/plans/2026-08-18-file-understanding-framework.md`
