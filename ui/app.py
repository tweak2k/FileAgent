"""Giao diện Streamlit — demo hỏi đáp tài liệu.

Chỉ gọi HTTP qua `ui.api_client.ApiClient`, không import gì từ `api/app`.
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
    return ApiClient(base_url=API_BASE_URL)


def render_sidebar(client: ApiClient) -> int | None:
    st.sidebar.title("Tài liệu")

    uploaded = st.sidebar.file_uploader("Tải tài liệu lên", type=None)
    if uploaded is not None and st.sidebar.button("Bắt đầu bóc tách"):
        document = client.upload_document(
            uploaded.name, uploaded.getvalue(), uploaded.type or "application/octet-stream"
        )
        st.session_state["pending_document_id"] = document["id"]
        st.rerun()

    pending_id = st.session_state.get("pending_document_id")
    if pending_id:
        document = client.get_document(pending_id)
        if document["parse_status"] in {"pending", "parsing"}:
            st.sidebar.info(f"Đang bóc tách `{document['filename']}`...")
            time.sleep(POLL_INTERVAL_SECONDS)
            st.rerun()
        else:
            st.session_state.pop("pending_document_id")
            if document["parse_status"] == "failed":
                st.sidebar.error(f"Bóc tách thất bại: {document['parse_error']}")
            st.rerun()

    documents = [d for d in client.list_documents() if d["parse_status"] == "ready"]
    if not documents:
        st.sidebar.warning("Chưa có tài liệu nào sẵn sàng.")
        return None

    labels = {d["id"]: f"{d['filename']} ({d['char_count']} ký tự)" for d in documents}
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

    conversation_labels = {c["id"]: f"#{c['id']} — {c['title']}" for c in conversations}
    conversation_id = st.sidebar.selectbox(
        "Chọn hội thoại",
        options=list(conversation_labels),
        format_func=lambda i: conversation_labels[i],
    )

    if st.sidebar.button("Reset phiên phân tích"):
        client.reset_sandbox(conversation_id)
        st.sidebar.success("Đã reset sandbox cho hội thoại này.")

    return conversation_id


def render_steps(steps: list[dict]) -> None:
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
