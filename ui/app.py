"""Streamlit UI — the document Q&A demo.

Talks HTTP through `ui.api_client.ApiClient` only, importing nothing from
`api/app`. All on-screen text is Vietnamese because that is the audience;
comments and docstrings are English.
"""

from __future__ import annotations

import os
import time

import streamlit as st

from ui.api_client import ApiClient, ApiError

API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
POLL_INTERVAL_SECONDS = 3


@st.cache_resource
def get_client() -> ApiClient:
    """Return the process-wide API client, cached across Streamlit reruns."""
    return ApiClient(base_url=API_BASE_URL)


def render_sidebar(client: ApiClient) -> int | None:
    """Render the sidebar: upload, document picker, conversation picker.

    The whole body is wrapped in try/except ApiError. Every call in here would
    otherwise be unguarded, so a backend error (say a 503 when python-vm is
    down) would make Streamlit render a traceback instead of the page.
    Returning None on failure lets main() show the "not ready" screen instead
    of crashing.
    """
    st.sidebar.title("Tài liệu")

    try:
        return _render_sidebar_body(client)
    except ApiError as exc:
        if exc.status_code == 503:
            st.sidebar.error(
                f"{exc}\n\nKiểm tra xem sandbox (python-vm) đã chạy ở cổng 8081 chưa."
            )
        else:
            st.sidebar.error(f"Lỗi gọi API: {exc}")
        return None


def _render_sidebar_body(client: ApiClient) -> int | None:
    """Sidebar body; may raise ApiError, which render_sidebar turns into a message."""
    uploaded = st.sidebar.file_uploader("Tải tài liệu lên", type=None)
    if uploaded is not None and st.sidebar.button("Bắt đầu bóc tách"):
        document = client.upload_document(
            uploaded.name, uploaded.getvalue(), uploaded.type or "application/octet-stream"
        )
        st.session_state["pending_document_id"] = document["id"]
        st.rerun()

    pending_id = st.session_state.get("pending_document_id")
    if pending_id:
        try:
            document = client.get_document(pending_id)
        except ApiError:
            # Pop even when the call failed: otherwise every later rerun dies
            # on this same line and the UI is stuck for good.
            st.session_state.pop("pending_document_id", None)
            raise

        if document["parse_status"] in {"pending", "parsing"}:
            st.sidebar.info(f"Đang bóc tách `{document['filename']}`...")
            time.sleep(POLL_INTERVAL_SECONDS)
            st.rerun()
        else:
            st.session_state.pop("pending_document_id", None)
            if document["parse_status"] == "failed":
                st.sidebar.error(f"Bóc tách thất bại: {document['parse_error']}")
            # No st.rerun() here: a rerun restarts the script with
            # pending_document_id already popped, so the error just rendered
            # above disappears before anyone can read it. Let the script fall
            # through to the document list below instead.

    documents = client.list_documents()
    if not documents:
        st.sidebar.warning("Chưa có tài liệu nào.")
        return None

    st.sidebar.caption("Trạng thái các tài liệu:")
    for d in documents:
        status = d["parse_status"]
        if status == "ready":
            st.sidebar.caption(f"- {d['filename']}: sẵn sàng ({d['char_count']} ký tự)")
        elif status == "failed":
            st.sidebar.caption(
                f"- {d['filename']}: bóc tách thất bại — {d.get('parse_error') or 'không rõ lỗi'}"
            )
        else:
            st.sidebar.caption(f"- {d['filename']}: đang {status}")

    ready_documents = [d for d in documents if d["parse_status"] == "ready"]
    if not ready_documents:
        st.sidebar.warning("Chưa có tài liệu nào sẵn sàng.")
        return None

    labels = {d["id"]: f"{d['filename']} ({d['char_count']} ký tự)" for d in ready_documents}
    document_id = st.sidebar.selectbox(
        "Chọn tài liệu", options=list(labels), format_func=lambda i: labels[i]
    )

    st.sidebar.divider()
    st.sidebar.subheader("Hội thoại")

    conversations = client.list_conversations(document_id)
    if st.sidebar.button("Tạo hội thoại mới"):
        conversation = client.create_conversation(document_id)
        st.session_state["conversation_id"] = conversation["id"]
        st.rerun()

    if not conversations:
        st.sidebar.caption("Chưa có hội thoại nào cho tài liệu này.")
        return None

    conversation_ids = [c["id"] for c in conversations]
    conversation_labels = {c["id"]: f"#{c['id']} — {c['title']}" for c in conversations}
    # Preselect the conversation just created rather than always the first one.
    just_created_id = st.session_state.get("conversation_id")
    default_index = (
        conversation_ids.index(just_created_id) if just_created_id in conversation_ids else 0
    )
    conversation_id = st.sidebar.selectbox(
        "Chọn hội thoại",
        options=conversation_ids,
        format_func=lambda i: conversation_labels[i],
        index=default_index,
    )

    if st.sidebar.button("Reset phiên phân tích"):
        client.reset_sandbox(conversation_id)
        st.sidebar.success("Đã reset sandbox cho hội thoại này.")

    return conversation_id


def render_steps(steps: list[dict]) -> None:
    """Render the agent's code steps under a reply, collapsed into an expander."""
    if not steps:
        return
    with st.expander(f"Các bước agent đã chạy ({len(steps)})"):
        for step in steps:
            st.markdown(f"**Bước {step['step_index'] + 1}** — {step['status']}, {step['duration_ms']}ms")
            st.code(step["code"], language="python")
            if step["stdout"]:
                st.text(step["stdout"])
            if step["stderr"]:
                st.error(step["stderr"])


def main() -> None:
    """Entry point: health check, sidebar, conversation history, chat input."""
    st.set_page_config(page_title="Hỏi đáp tài liệu", layout="wide")
    client = get_client()

    if not client.health():
        st.error(f"Không kết nối được tới API tại {API_BASE_URL}")
        return

    conversation_id = render_sidebar(client)
    st.title("Hỏi đáp tài liệu")

    if conversation_id is None:
        st.info("Tải tài liệu lên và tạo một hội thoại ở thanh bên để bắt đầu.")
        return

    for message in client.list_messages(conversation_id):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            render_steps(message.get("steps", []))

    question = st.chat_input("Hỏi gì về tài liệu này?")
    if question:
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"), st.spinner("Agent đang đọc tài liệu..."):
            try:
                answer = client.send_message(conversation_id, question)
            except ApiError as exc:
                st.error(str(exc))
                return
            st.markdown(answer["content"])
            render_steps(answer.get("steps", []))


if __name__ == "__main__":
    main()
