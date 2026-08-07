"""
Streamlit UI — M2
Layout: left (chat + trace) | right (evidence panel)
"""
import os
from pathlib import Path

# Fix CWD to repo root so relative paths in tools.py resolve correctly
os.chdir(Path(__file__).parent)

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
from src.agent import run

st.set_page_config(
    page_title="規程エージェント",
    layout="wide",
    initial_sidebar_state="collapsed",
)

if "history" not in st.session_state:
    st.session_state.history = []


def _render_trace_static(trace: list):
    """Render trace from completed exchange (collapsed expander)."""
    with st.expander("エージェント動作ログ", expanded=False):
        for step in trace:
            for tc in step["tool_calls"]:
                name = tc["name"]
                inp = tc["input"]
                if name == "search_chunks":
                    st.write(f'🔍 search_chunks: "{inp.get("query", "")}"')
                elif name == "read_section":
                    st.write(f'📖 read_section: "{inp.get("hierarchy", "")}"')
                else:
                    st.write(f"🔧 {name}: {inp}")


def _collect_chunks(trace: list) -> list:
    """Extract unique chunks from search_chunks outputs in trace."""
    seen: set = set()
    chunks = []
    for step in trace:
        for tc in step["tool_calls"]:
            if tc["name"] == "search_chunks" and isinstance(tc.get("output"), list):
                for hit in tc["output"]:
                    cid = hit.get("chunk_id", "")
                    if cid not in seen:
                        seen.add(cid)
                        chunks.append(hit)
    return chunks


# ── Header ──────────────────────────────────────────────────────────────────
st.title("規程エージェント")
st.caption("公共建築工事標準仕様書（電気設備工事編）令和7年版")

if st.button("🔄 新しい会話", type="secondary"):
    st.session_state.history = []
    st.rerun()

st.divider()

# ── Layout ───────────────────────────────────────────────────────────────────
left, right = st.columns([2, 1])
new_chunks: list = []

with left:
    # Show conversation history
    for item in st.session_state.history:
        with st.chat_message("user"):
            st.markdown(item["question"])
        with st.chat_message("assistant"):
            if item.get("trace"):
                _render_trace_static(item["trace"])
            st.markdown(item["answer"])

    # Question input
    question = st.chat_input("条文について質問してください...")

    if question:
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.status("⏳ 回答を生成中...", expanded=True) as status:
                try:
                    result = run(question)
                except Exception as e:
                    status.update(label="❌ エラー", state="error", expanded=True)
                    st.error(f"エラーが発生しました: {e}")
                    result = None

                if result:
                    for step in result["trace"]:
                        for tc in step["tool_calls"]:
                            name = tc["name"]
                            inp = tc["input"]
                            if name == "search_chunks":
                                st.write(f'🔍 search_chunks: "{inp.get("query", "")}"')
                            elif name == "read_section":
                                st.write(f'📖 read_section: "{inp.get("hierarchy", "")}"')
                    status.update(label="✅ 完了", state="complete", expanded=False)

            if result:
                st.markdown(result["answer"])

        if result:
            new_chunks = _collect_chunks(result["trace"])
            st.session_state.history.append(
                {
                    "question": question,
                    "answer": result["answer"],
                    "trace": result["trace"],
                    "retrieved": result["retrieved"],
                    "chunks": new_chunks,
                }
            )

with right:
    st.subheader("📚 根拠パネル")
    st.divider()

    chunks_to_show = new_chunks or (
        st.session_state.history[-1].get("chunks", []) if st.session_state.history else []
    )

    if not chunks_to_show:
        st.info("質問すると出典条文がここに表示されます。")
    else:
        for chunk in chunks_to_show:
            with st.expander(f"📄 {chunk['hierarchy']}", expanded=True):
                st.caption(
                    f"ページ: {chunk.get('pages', '―')}　"
                    f"系統: {chunk.get('domain', '―')}"
                )
                st.markdown("---")
                body = chunk.get("body", "")
                st.markdown(body if body else "*本文なし*")
