"""Prompt strings and prompt builders for the CodeAct agent.

The prompt text itself stays in Vietnamese on purpose: it is runtime data
sent to the LLM, and the agent answers Vietnamese-speaking users. Only the
comments and docstrings around it are English.
"""

from __future__ import annotations

SYSTEM_PROMPT = """Bạn là trợ lý đọc hiểu tài liệu. Tài liệu đã được chuyển sang markdown và \
nằm tại `document.md` trong thư mục làm việc của một môi trường Python.

Bạn KHÔNG được nhìn thấy toàn bộ nội dung tài liệu. Cách làm việc của bạn là viết code Python \
để tự tìm phần mình cần: đọc file, tìm chuỗi, cắt đoạn, đếm, lọc bảng.

Quy tắc:
- Khi cần xem dữ liệu, trả lời bằng đúng một block ```python. Code sẽ được chạy và bạn nhận lại \
stdout/stderr ở lượt sau.
- Biến và import được giữ nguyên giữa các lần chạy, không cần đọc lại file mỗi lượt.
- In ra vừa đủ để suy luận. Đừng in cả tài liệu.
- Khi đã đủ thông tin, trả lời bằng tiếng Việt, KHÔNG kèm block code nào.
- Nếu code lỗi, đọc stderr rồi sửa ở lượt tiếp theo.
"""

STEP_LIMIT_NOTICE = (
    "\n\n(Lưu ý: agent đã chạm giới hạn số bước nên phần tìm hiểu chưa hoàn tất. "
    "Câu trả lời trên dựa vào những gì thu thập được cho tới lúc dừng.)"
)

# If the agent accidentally prints the whole document (e.g.
# print(open('document.md').read())), stdout can run to hundreds of thousands
# of characters. Without truncation all of it lands in the next prompt, the
# provider is likely to answer 400 (context limit), and the three retries then
# surface as a 502 with no way to recover — the agent cannot fix this itself
# because the failure is at the provider layer, not in the Python stderr.
OBSERVATION_MAX_CHARS = 6000


def build_system_prompt() -> str:
    """Return the fixed system prompt for the CodeAct agent."""
    return SYSTEM_PROMPT


def build_document_context(filename: str, char_count: int, head: str) -> str:
    """Describe the document under discussion, including its head as a starting point."""
    return (
        f"Tài liệu đang xét: `{filename}`, đã chuyển sang markdown, dài {char_count} ký tự, "
        f"đọc được tại `document.md`.\n\n"
        f"Phần đầu tài liệu:\n\n{head}"
    )


def _truncate(text: str, limit: int = OBSERVATION_MAX_CHARS) -> str:
    """Cut text down to `limit` characters, appending a note that it was truncated."""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n... (đã cắt bớt, còn {limit}/{len(text)} ký tự)"


def build_observation(stdout: str, stderr: str, timed_out: bool) -> str:
    """Build the observation message fed back to the LLM after a code run."""
    parts = [f"Kết quả chạy code:\n\nstdout:\n{_truncate(stdout) if stdout else '(rỗng)'}"]
    if stderr:
        parts.append(f"stderr:\n{_truncate(stderr)}")
    if timed_out:
        parts.append("Code đã chạy quá thời gian cho phép và bị dừng.")
    return "\n\n".join(parts)
