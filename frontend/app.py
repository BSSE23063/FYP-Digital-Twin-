"""
Streamlit Web UI for Personal AI Digital Twin Platform (T2-RAG).

Features:
- Twin Management (create, view, select active twin)
- Knowledge Ingestion (upload PDF/DOCX/TXT/MD, or paste raw text)
- Interactive Chat (with Access Tier simulation, citation viewer, policy inspector)
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st
import json
from backend.db.session import SessionLocal
from backend.services.twin_service import TwinService
from backend.services.document_service import DocumentService
from backend.services.conversation_service import ConversationService
from backend.config import settings

# Page configuration
st.set_page_config(
    page_title="T2-RAG | Personal AI Digital Twin",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🤖 T2-RAG: Personal AI Digital Twin Platform")
st.caption("Grounded, multi-tenant conversational digital twins with LangGraph and ChromaDB.")


def get_services():
    db = SessionLocal()
    return TwinService(db), DocumentService(db), ConversationService(db), db


twin_svc, doc_svc, conv_svc, db = get_services()

# ─────────────────────────────────────────────────────────────
# Sidebar: Twin Selection & Creation
# ─────────────────────────────────────────────────────────────
st.sidebar.header("👤 Digital Twin Setup")

twins = twin_svc.list_twins()
twin_names = {t.id: t.name for t in twins}

if not twins:
    st.sidebar.warning("No twins created yet. Create one below!")
    selected_twin_id = None
else:
    selected_twin_id = st.sidebar.selectbox(
        "Select Active Twin",
        options=list(twin_names.keys()),
        format_func=lambda tid: twin_names[tid],
    )

with st.sidebar.expander("➕ Create New Twin", expanded=(len(twins) == 0)):
    with st.form("create_twin_form"):
        new_name = st.text_input("Twin Name (e.g., Hafiz Umair)", value="")
        new_desc = st.text_input("Short Tagline / Bio", value="Software Engineer & AI Researcher")
        new_persona = st.text_area(
            "Persona / Personality Style",
            value="I am Umair, an AI engineer from Lahore building digital twins. I speak professionally, enthusiastically, and honestly. I never guess when unsure.",
            height=120,
        )
        submitted = st.form_submit_button("Create Twin")
        if submitted:
            if not new_name.strip():
                st.error("Name is required.")
            else:
                new_twin = twin_svc.create_twin(
                    name=new_name.strip(),
                    description=new_desc.strip(),
                    persona_prompt=new_persona.strip(),
                )
                st.success(f"Twin '{new_twin.name}' created!")
                st.rerun()

# ─────────────────────────────────────────────────────────────
# Main Tabs
# ─────────────────────────────────────────────────────────────
if not selected_twin_id:
    st.info("👈 Please create or select a twin from the sidebar to start.")
    st.stop()

current_twin = twin_svc.get_twin(selected_twin_id)

tab_chat, tab_docs, tab_profile = st.tabs(["💬 Chat with Twin", "📚 Knowledge Management", "⚙️ Twin Profile"])

# ─────────────────────────────────────────────────────────────
# Tab 1: Chat with Twin
# ─────────────────────────────────────────────────────────────
with tab_chat:
    col_settings, col_chat = st.columns([1, 2.5])

    with col_settings:
        st.subheader("Visitor Session")
        visitor_name = st.text_input("Your Name / Role", value="Recruiter")
        access_tier = st.selectbox(
            "Visitor Access Tier",
            options=["public", "friends", "private"],
            help="Simulates access control. 'public' only retrieves public documents.",
        )
        if st.button("🗑️ Clear Chat History"):
            st.session_state.messages = []
            st.rerun()

        st.divider()
        st.markdown("**How this works:**")
        st.markdown("""
        - Queries are routed through **LangGraph**.
        - Only documents matching **your access tier** are retrieved.
        - **Grounding checks** prevent hallucinations.
        - If unsure, the twin **declines and escalates**.
        """)

    with col_chat:
        st.subheader(f"Talking to: {current_twin.name}")

        if "messages" not in st.session_state:
            st.session_state.messages = []

        # Display history
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if "inspection" in msg and msg["inspection"]:
                    insp = msg["inspection"]
                    with st.expander(f"🔍 Inspector: {insp.get('policy_decision', 'N/A').upper()} | {insp.get('latency_ms', 0)}ms | Conf: {insp.get('confidence_score', 0):.2f}"):
                        st.json(insp)

        # Chat input
        if prompt := st.chat_input("Ask a question about projects, background, education..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                with st.spinner("Thinking through LangGraph..."):
                    try:
                        res = conv_svc.chat(
                            twin_id=current_twin.id,
                            message=prompt,
                            visitor_name=visitor_name,
                            access_tier=access_tier,
                        )
                        answer = res["answer"]
                        st.markdown(answer)

                        insp_data = {
                            "policy_decision": res.get("policy_decision"),
                            "confidence_score": res.get("confidence_score"),
                            "latency_ms": res.get("latency_ms"),
                            "sources_count": len(res.get("sources", [])),
                            "sources": res.get("sources", []),
                        }
                        with st.expander(f"🔍 Inspector: {res.get('policy_decision', 'N/A').upper()} | {res.get('latency_ms', 0)}ms | Conf: {res.get('confidence_score', 0):.2f}"):
                            st.json(insp_data)

                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": answer,
                            "inspection": insp_data,
                        })
                    except Exception as e:
                        st.error(f"Error communicating with Twin: {e}")

# ─────────────────────────────────────────────────────────────
# Tab 2: Knowledge Management
# ─────────────────────────────────────────────────────────────
with tab_docs:
    st.subheader("Manage Knowledge Base")
    col_upload, col_text = st.columns(2)

    with col_upload:
        st.markdown("#### 📄 Upload Document (PDF, DOCX, TXT, MD)")
        uploaded_file = st.file_uploader(
            "Choose a file",
            type=["pdf", "docx", "txt", "md"],
            key="file_uploader",
        )
        file_vis = st.selectbox("Visibility", ["public", "friends", "private"], key="file_vis")

        if st.button("Upload & Ingest File", disabled=(uploaded_file is None)):
            upload_dir = Path(settings.UPLOAD_DIR)
            upload_dir.mkdir(parents=True, exist_ok=True)
            dest = upload_dir / f"{current_twin.id}_{uploaded_file.name}"
            with open(dest, "wb") as f:
                f.write(uploaded_file.getbuffer())

            ext = uploaded_file.name.split(".")[-1].lower()
            with st.spinner("Parsing, chunking, and indexing into ChromaDB..."):
                try:
                    doc = doc_svc.ingest_file(
                        twin_id=current_twin.id,
                        filename=uploaded_file.name,
                        file_path=str(dest),
                        content_type=ext,
                        visibility=file_vis,
                    )
                    st.success(f"Ingested '{doc.filename}' ({doc.chunk_count} chunks created)!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to ingest: {e}")

    with col_text:
        st.markdown("#### ✍️ Add Text / Notes / FAQ Directly")
        text_title = st.text_input("Document Name", value="Skills & Projects.txt")
        text_content = st.text_area("Paste text or notes", height=150)
        text_vis = st.selectbox("Visibility", ["public", "friends", "private"], key="text_vis")

        if st.button("Ingest Text Notes"):
            if not text_content.strip():
                st.error("Please enter some text.")
            else:
                with st.spinner("Chunking and indexing into ChromaDB..."):
                    try:
                        doc = doc_svc.ingest_raw_text(
                            twin_id=current_twin.id,
                            filename=text_title.strip(),
                            text_content=text_content.strip(),
                            visibility=text_vis,
                        )
                        st.success(f"Ingested '{doc.filename}' ({doc.chunk_count} chunks created)!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to ingest: {e}")

    st.divider()
    st.subheader(f"Existing Documents for {current_twin.name}")
    docs = doc_svc.list_documents(current_twin.id)

    if not docs:
        st.info("No documents uploaded yet.")
    else:
        for d in docs:
            col_info, col_del = st.columns([4, 1])
            with col_info:
                st.markdown(f"**{d.filename}** `[{d.visibility.upper()}]` — Status: `{d.ingestion_status}` | Chunks: `{d.chunk_count}`")
            with col_del:
                if st.button("Delete", key=f"del_{d.id}"):
                    doc_svc.delete_document(current_twin.id, d.id)
                    st.success("Deleted!")
                    st.rerun()

# ─────────────────────────────────────────────────────────────
# Tab 3: Twin Profile
# ─────────────────────────────────────────────────────────────
with tab_profile:
    st.subheader(f"Profile: {current_twin.name}")
    st.markdown(f"**ID:** `{current_twin.id}`")
    st.markdown(f"**Description:** {current_twin.description or 'None'}")
    st.text_area("System Persona Prompt", value=current_twin.persona_prompt or "", height=150, disabled=True)

    st.divider()
    st.subheader("Configured Access Tiers")
    for tier in current_twin.access_tiers:
        st.markdown(f"- **{tier.tier_name.upper()}**: {tier.description} *(Allowed: `{tier.allowed_visibilities}`)*")

    st.divider()
    if st.button("🚨 Delete Entire Twin", type="primary"):
        twin_svc.delete_twin(current_twin.id)
        st.success(f"Twin '{current_twin.name}' deleted.")
        st.rerun()

# Cleanup DB connection on script run
db.close()

