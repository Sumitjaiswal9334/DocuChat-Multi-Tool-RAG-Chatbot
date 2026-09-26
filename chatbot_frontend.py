import uuid

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from chatbot_backend import (
    chatbot,
    ingest_pdf,
    retrieve_all_threads,
    thread_document_metadata,
)

# =========================== Page Config ===========================
st.set_page_config(
    page_title="DocuChat — PDF Chatbot",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =========================== Custom Styling ===========================
st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
        }

        /* Hide default streamlit chrome */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}

        /* App header */
        .app-header {
            padding: 1.4rem 1.8rem;
            border-radius: 16px;
            background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #a855f7 100%);
            margin-bottom: 1.5rem;
            box-shadow: 0 8px 24px rgba(99, 102, 241, 0.25);
        }
        .app-header h1 {
            color: white;
            font-size: 1.6rem;
            font-weight: 700;
            margin: 0;
        }
        .app-header p {
            color: rgba(255,255,255,0.9);
            margin: 0.3rem 0 0 0;
            font-size: 0.92rem;
        }

        /* Sidebar */
        section[data-testid="stSidebar"] {
            background: #f8f9fc;
            border-right: 1px solid #eaeaf2;
        }
        .sidebar-card {
            background: white;
            border: 1px solid #eaeaf2;
            border-radius: 12px;
            padding: 0.9rem 1rem;
            margin-bottom: 0.8rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        }
        .sidebar-title {
            font-weight: 600;
            font-size: 0.95rem;
            color: #1f2130;
            margin-bottom: 0.2rem;
        }
        .doc-badge {
            display: inline-block;
            background: #ecfdf5;
            color: #059669;
            border: 1px solid #a7f3d0;
            padding: 2px 10px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
            margin-top: 0.4rem;
        }
        .empty-state {
            color: #8b8d98;
            font-size: 0.85rem;
            text-align: center;
            padding: 1rem 0.5rem;
        }

        /* Thread list buttons */
        div[data-testid="stSidebar"] button {
            border-radius: 10px !important;
            text-align: left;
        }

        /* Chat bubbles */
        div[data-testid="stChatMessage"] {
            border-radius: 14px;
            padding: 0.3rem 0.2rem;
        }

        /* Chat input */
        .stChatInput textarea {
            border-radius: 12px !important;
        }

        .footer-caption {
            text-align: center;
            color: #a0a2ad;
            font-size: 0.78rem;
            margin-top: 1rem;
        }

        /* Feature cards on welcome screen */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 14px !important;
            transition: box-shadow 0.2s ease, transform 0.2s ease;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:hover {
            box-shadow: 0 6px 18px rgba(99, 102, 241, 0.12);
            transform: translateY(-2px);
        }

        /* Force accent color to match the purple theme everywhere,
           overriding Streamlit's default red/orange primaryColor */
        button[kind="primary"] {
            background: linear-gradient(135deg, #6366f1, #8b5cf6) !important;
            border-color: #6366f1 !important;
            color: white !important;
        }
        button[kind="primary"]:hover {
            background: linear-gradient(135deg, #5457e0, #7c4fe0) !important;
            border-color: #5457e0 !important;
        }
        div[data-testid="stChatInput"] textarea:focus,
        div[data-testid="stChatInput"]:focus-within {
            border-color: #8b5cf6 !important;
            border-radius:18px !important;
            
            box-shadow: 0 0 0 2px rgba(139, 92, 246, 0.25) !important;
        }
        input:focus, textarea:focus {
            box-shadow: 0 0 0 2px rgba(139, 92, 246, 0.25) !important;
            border-color: #8b5cf6 !important;
            
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================== Utilities ===========================
def generate_thread_id():
    return uuid.uuid4()


def reset_chat():
    thread_id = generate_thread_id()
    st.session_state["thread_id"] = thread_id
    add_thread(thread_id)
    st.session_state["message_history"] = []


def add_thread(thread_id):
    if thread_id not in st.session_state["chat_threads"]:
        st.session_state["chat_threads"].append(thread_id)


def load_conversation(thread_id):
    state = chatbot.get_state(config={"configurable": {"thread_id": thread_id}})
    return state.values.get("messages", [])


def short_id(thread_id, length=8):
    return str(thread_id)[:length]


def get_thread_title(thread_id, max_len=30):
    """Return a human-friendly title for a thread, derived from its first
    user message. Falls back to 'New chat' if no messages exist yet.
    Result is cached in session_state so we don't hit the backend on every
    rerun for every thread in the sidebar. Icon prefix is applied by the
    caller so every row uses one consistent icon scheme.
    """
    cache = st.session_state.setdefault("thread_titles", {})
    key = str(thread_id)

    if key in cache:
        return cache[key]

    title = "New chat"  # fallback
    try:
        messages = load_conversation(thread_id)
        for msg in messages:
            if isinstance(msg, HumanMessage) and msg.content:
                text = str(msg.content).strip().replace("\n", " ")
                if len(text) > max_len:
                    text = text[:max_len].rstrip() + "…"
                title = text
                break
    except Exception:
        pass  # keep fallback title if backend lookup fails

    cache[key] = title
    return title


def refresh_thread_title(thread_id):
    """Drop the cached title for a thread so it's recomputed on next render
    (used right after a new message is sent so the sidebar updates live).
    """
    cache = st.session_state.setdefault("thread_titles", {})
    cache.pop(str(thread_id), None)


# ======================= Session Initialization ===================
if "message_history" not in st.session_state:
    st.session_state["message_history"] = []

if "thread_id" not in st.session_state:
    st.session_state["thread_id"] = generate_thread_id()

if "chat_threads" not in st.session_state:
    st.session_state["chat_threads"] = retrieve_all_threads()

if "ingested_docs" not in st.session_state:
    st.session_state["ingested_docs"] = {}

add_thread(st.session_state["thread_id"])

thread_key = str(st.session_state["thread_id"])
thread_docs = st.session_state["ingested_docs"].setdefault(thread_key, {})
threads = st.session_state["chat_threads"][::-1]
selected_thread = None

# ============================ Sidebar ============================
with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-card">
            <div class="sidebar-title">🤖 DocuChat PDF Chatbot</div>
            <div style="font-size:0.78rem; color:#8b8d98;">Chat with your documents, powered by LangGraph</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="sidebar-card">
            <div class="sidebar-title">🧵 Current Thread</div>
            <div style="font-size:0.8rem; color:#6b6d78;">ID: <code>{short_id(thread_key)}</code></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("➕ New Chat", use_container_width=True, type="primary"):
        reset_chat()
        st.rerun()

    st.markdown("#### 📎 Document")
    if thread_docs:
        latest_doc = list(thread_docs.values())[-1]
        st.markdown(
            f"""
            <div class="sidebar-card">
                <div class="sidebar-title">📄 {latest_doc.get('filename')}</div>
                <div style="font-size:0.8rem; color:#6b6d78;">
                    {latest_doc.get('chunks')} chunks &nbsp;•&nbsp; {latest_doc.get('documents')} pages
                </div>
                <span class="doc-badge">✓ Indexed</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="empty-state">📭 No PDF indexed yet.<br>Upload one below to get started.</div>',
            unsafe_allow_html=True,
        )

    uploaded_pdf = st.file_uploader("Upload a PDF for this chat", type=["pdf"], label_visibility="collapsed")
    if uploaded_pdf:
        if uploaded_pdf.name in thread_docs:
            st.info(f"`{uploaded_pdf.name}` already processed for this chat.")
        else:
            with st.status("📚 Indexing PDF…", expanded=True) as status_box:
                st.write("Reading pages and creating embeddings...")
                summary = ingest_pdf(
                    uploaded_pdf.getvalue(),
                    thread_id=thread_key,
                    filename=uploaded_pdf.name,
                )
                thread_docs[uploaded_pdf.name] = summary
                status_box.update(label="✅ PDF indexed successfully", state="complete", expanded=False)
            st.rerun()

    st.markdown("#### 🕘 Past Conversations")
    if not threads:
        st.markdown('<div class="empty-state">No past conversations yet.</div>', unsafe_allow_html=True)
    else:
        for tid in threads:
            is_active = str(tid) == thread_key
            icon = "🟢" if is_active else "💬"
            label = f"{icon} {get_thread_title(tid)}"
            if st.button(label, key=f"side-thread-{tid}", use_container_width=True):
                selected_thread = tid

# ============================ Main Layout ========================
st.markdown(
    """
    <div class="app-header">
        <h1>🤖 DocuChat PDF Chatbot</h1>
        <p>Ask questions about your uploaded PDF, or chat freely using the built-in tools.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Chat area
if not st.session_state["message_history"]:
    st.markdown(
        """
        <div style="text-align:center; padding: 2rem 1rem 1rem 1rem; color:#a0a2ad;">
            <div style="font-size:2.4rem;">🤖</div>
            <div style="font-size:1.05rem; font-weight:700; color:#2b2d3a; margin-top:0.4rem;">Welcome! Here's what I can do</div>
            <div style="font-size:0.85rem; margin-top:0.2rem;">Upload a PDF from the sidebar and ask anything about it — or just say hi!</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.write("")
    col1, col2, col3 = st.columns(3)

    with col1:
        with st.container(border=True):
            st.markdown("### 📚 Chat with PDF")
            st.caption(
                "Upload a PDF and ask questions "
                "using RAG-powered retrieval."
            )

    with col2:
        with st.container(border=True):
            st.markdown("### 🌐 Web Search")
            st.caption(
                "Search the web whenever you need "
                "up-to-date information."
            )

    with col3:
        with st.container(border=True):
            st.markdown("### 🧮 AI Tools")
            st.caption(
                "Calculate values and access useful "
                "external information."
            )

    st.write("")

for message in st.session_state["message_history"]:
    avatar = "🧑‍💻" if message["role"] == "user" else "🤖"
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])

user_input = st.chat_input("Ask about your document or use tools 💬")

if user_input:
    st.session_state["message_history"].append({"role": "user", "content": user_input})
    with st.chat_message("user", avatar="🧑‍💻"):
        st.markdown(user_input)

    CONFIG = {
        "configurable": {"thread_id": thread_key},
        "metadata": {"thread_id": thread_key},
        "run_name": "chat_turn",
    }

    with st.chat_message("assistant", avatar="🤖"):
        status_holder = {"box": None}

        def ai_only_stream():
            for message_chunk, _ in chatbot.stream(
                {"messages": [HumanMessage(content=user_input)]},
                config=CONFIG,
                stream_mode="messages",
            ):
                if isinstance(message_chunk, ToolMessage):
                    tool_name = getattr(message_chunk, "name", "tool")
                    if status_holder["box"] is None:
                        status_holder["box"] = st.status(
                            f"🔧 Using `{tool_name}` …", expanded=True
                        )
                    else:
                        status_holder["box"].update(
                            label=f"🔧 Using `{tool_name}` …",
                            state="running",
                            expanded=True,
                        )

                if isinstance(message_chunk, AIMessage):
                    yield message_chunk.content

        ai_message = st.write_stream(ai_only_stream())

        if status_holder["box"] is not None:
            status_holder["box"].update(
                label="✅ Tool finished", state="complete", expanded=False
            )

    st.session_state["message_history"].append(
        {"role": "assistant", "content": ai_message}
    )
    refresh_thread_title(st.session_state["thread_id"])

    doc_meta = thread_document_metadata(thread_key)
    if doc_meta:
        st.caption(
            f"📄 Document indexed: **{doc_meta.get('filename')}** "
            f"(chunks: {doc_meta.get('chunks')}, pages: {doc_meta.get('documents')})"
        )

if selected_thread:
    st.session_state["thread_id"] = selected_thread
    messages = load_conversation(selected_thread)

    temp_messages = []
    for msg in messages:
        role = "user" if isinstance(msg, HumanMessage) else "assistant"
        temp_messages.append({"role": role, "content": msg.content})
    st.session_state["message_history"] = temp_messages
    st.session_state["ingested_docs"].setdefault(str(selected_thread), {})
    st.rerun()