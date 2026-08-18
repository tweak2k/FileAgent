"""Chuỗi prompt và hàm dựng prompt cho CodeActAgent."""

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


def build_system_prompt() -> str:
    """Trả về system prompt cố định cho CodeActAgent."""
    return SYSTEM_PROMPT


def build_document_context(filename: str, char_count: int, head: str) -> str:
    """Dựng message giới thiệu tài liệu đang xét, kèm phần đầu để agent có điểm khởi đầu."""
    return (
        f"Tài liệu đang xét: `{filename}`, đã chuyển sang markdown, dài {char_count} ký tự, "
        f"đọc được tại `document.md`.\n\n"
        f"Phần đầu tài liệu:\n\n{head}"
    )


def build_observation(stdout: str, stderr: str, timed_out: bool) -> str:
    """Dựng nội dung quan sát (observation) từ kết quả chạy code để đưa vào lượt kế tiếp."""
    parts = [f"Kết quả chạy code:\n\nstdout:\n{stdout or '(rỗng)'}"]
    if stderr:
        parts.append(f"stderr:\n{stderr}")
    if timed_out:
        parts.append("Code đã chạy quá thời gian cho phép và bị dừng.")
    return "\n\n".join(parts)
