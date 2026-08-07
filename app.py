"""
Streamlit UI — M3
Layout: sidebar (settings + debug) | left (chat + trace) | right (evidence panel)
"""
import json
import os
import time
from dataclasses import asdict
from pathlib import Path

# Fix CWD to repo root so relative paths in tools.py resolve correctly
os.chdir(Path(__file__).parent)

from dotenv import load_dotenv
load_dotenv()

import streamlit as st

from src.agent import run
from src.config import (
    ANSWER_STYLES,
    APP_VERSION,
    PRESETS,
    AgentConfig,
    estimate_cost,
    load_config,
    save_config,
)

st.set_page_config(
    page_title="規程エージェント",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session state init ────────────────────────────────────────────────────────

if "history" not in st.session_state:
    st.session_state.history = []
if "config" not in st.session_state:
    st.session_state.config = load_config()
if "last_debug" not in st.session_state:
    st.session_state.last_debug = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _model_selector(label: str, key_prefix: str, current: str) -> str:
    """Selectbox with presets + free text input for 'custom'."""
    opts = list(PRESETS) + ["（カスタム入力）"]
    is_custom = current not in PRESETS
    sel = st.selectbox(
        label,
        opts,
        index=len(PRESETS) if is_custom else PRESETS.index(current),
        key=f"sel_{key_prefix}",
    )
    if sel == "（カスタム入力）":
        return st.text_input(
            "モデルID",
            value=current if is_custom else "",
            key=f"txt_{key_prefix}",
            placeholder="例: deepseek/deepseek-r1",
            label_visibility="collapsed",
        )
    return sel


def _render_usage_row(label: str, model: str, usage: dict, elapsed: float) -> None:
    inp = usage.get("input_tokens", 0)
    out = usage.get("output_tokens", 0)
    cost = estimate_cost(model, inp, out)
    cost_str = f"≈${cost:.4f}" if cost is not None else "―"
    st.caption(
        f"**{label}** ({model.split('/')[-1]}) | "
        f"in {inp:,} / out {out:,} tok | {elapsed:.1f}s | {cost_str}"
    )


def _load_eval_questions(path: str) -> list:
    p = Path(path)
    if not p.exists():
        return []
    qs = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                qs.append(json.loads(line))
    return qs


def _render_thinking(thinking: str | None, label: str = "💭 thinking") -> None:
    if thinking:
        with st.expander(label, expanded=True):
            st.text(thinking)


def _render_trace_entries(trace: list) -> None:
    for step in trace:
        st.markdown(f"**🔄 実行ループ — {step['loop']}回目**")
        _render_thinking(step.get("thinking"))
        for tc in step["tool_calls"]:
            name = tc["name"]
            inp = tc["input"]
            if name == "search_chunks":
                st.write(f'🔍 search_chunks: "{inp.get("query", "")}"')
            elif name == "read_section":
                st.write(f'📖 read_section: "{inp.get("hierarchy", "")}"')
            else:
                st.write(f"🔧 {name}: {inp}")


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("⚙️ 設定")
    cfg = st.session_state.config

    st.subheader("三役モデル構成")
    planner_enabled = st.toggle("プランナー ON", value=cfg.planner_enabled)

    if planner_enabled:
        planner_model = _model_selector("プランナーモデル", "planner", cfg.planner_model)
    else:
        planner_model = cfg.planner_model

    loop_model = _model_selector("実行ループモデル", "loop", cfg.loop_model)
    composer_model = _model_selector("コンポーザーモデル", "composer", cfg.composer_model)

    st.subheader("チューニング")
    max_loops = st.slider("MAX_LOOPS", 5, 30, cfg.max_loops)
    top_k = st.slider("search top_k", 3, 15, cfg.top_k)
    answer_style = st.radio(
        "回答スタイル",
        list(ANSWER_STYLES.keys()),
        index=list(ANSWER_STYLES.keys()).index(cfg.answer_style),
        format_func=lambda x: ANSWER_STYLES[x],
    )

    new_cfg = AgentConfig(
        planner_enabled=planner_enabled,
        planner_model=planner_model,
        loop_model=loop_model,
        composer_model=composer_model,
        max_loops=max_loops,
        top_k=top_k,
        answer_style=answer_style,
    )
    if asdict(new_cfg) != asdict(cfg):
        st.session_state.config = new_cfg
        save_config(new_cfg)
        cfg = new_cfg

    # ── Debug panel ───────────────────────────────────────────────────────────

    st.divider()
    with st.expander("🛠 デバッグパネル", expanded=False):
        st.caption(f"**バージョン:** {APP_VERSION}")
        st.caption(
            f"loop={cfg.loop_model.split('/')[-1]} | "
            f"composer={cfg.composer_model.split('/')[-1]} | "
            f"max_loops={cfg.max_loops} | top_k={cfg.top_k} | "
            f"style={ANSWER_STYLES[cfg.answer_style]}"
        )

        dbg = st.session_state.last_debug
        if dbg:
            st.markdown("**トークン・コスト・時間**")
            if dbg.get("planner") and dbg["planner"].get("usage"):
                _render_usage_row(
                    "プランナー",
                    dbg["planner"].get("model", ""),
                    dbg["planner"]["usage"],
                    dbg["planner"].get("time_s", 0),
                )
            loop = dbg.get("loop", {})
            if loop.get("usage"):
                _render_usage_row(
                    f"実行ループ ({loop.get('loops', '?')}回)",
                    loop.get("model", ""),
                    loop["usage"],
                    loop.get("time_s", 0),
                )
                if loop.get("max_loops_hit"):
                    st.warning("⚠️ MAX_LOOPS に到達しました")
            comp = dbg.get("composer", {})
            if comp.get("usage"):
                _render_usage_row(
                    "コンポーザー",
                    comp.get("model", ""),
                    comp["usage"],
                    comp.get("time_s", 0),
                )

            if dbg.get("planner", {}).get("raw_response"):
                with st.expander("プランナー出力"):
                    st.text(dbg["planner"]["raw_response"])

            if dbg.get("raw_composer_output"):
                with st.expander("コンポーザー生出力"):
                    st.text(dbg["raw_composer_output"])

            # invalid_citations — read from last history item
            if st.session_state.history:
                last = st.session_state.history[-1]
                if last.get("invalid_citations"):
                    st.error(f"invalid_citation: {last['invalid_citations']}")

        st.divider()
        st.markdown("**eval質問ワンクリック投入**")
        eval_qs = _load_eval_questions("eval/questions.jsonl")
        for i, q in enumerate(eval_qs):
            short = q["question"][:35] + ("…" if len(q["question"]) > 35 else "")
            if st.button(short, key=f"eval_{i}"):
                st.session_state["pending_question"] = q["question"]
                st.rerun()

        refusal_qs = _load_eval_questions("eval/questions-refusal.jsonl")
        if refusal_qs:
            st.caption("refusal テスト")
            for i, q in enumerate(refusal_qs):
                short = q["question"][:35] + ("…" if len(q["question"]) > 35 else "")
                if st.button(short, key=f"refusal_{i}"):
                    st.session_state["pending_question"] = q["question"]
                    st.rerun()

        st.divider()
        if st.button("設定リセット", type="secondary"):
            st.session_state["_reset_confirm"] = True

        if st.session_state.get("_reset_confirm"):
            st.warning("既定値に戻します。よろしいですか？")
            col1, col2 = st.columns(2)
            if col1.button("はい", type="primary"):
                new_default = AgentConfig()
                st.session_state.config = new_default
                save_config(new_default)
                st.session_state.pop("_reset_confirm", None)
                st.rerun()
            if col2.button("キャンセル"):
                st.session_state.pop("_reset_confirm", None)
                st.rerun()


# ── Main layout ───────────────────────────────────────────────────────────────

st.title("規程エージェント")
st.caption("公共建築工事標準仕様書（電気設備工事編）令和7年版")

if st.button("🔄 新しい会話", type="secondary"):
    st.session_state.history = []
    st.session_state.last_debug = None
    st.rerun()

st.divider()

left, right = st.columns([2, 1])
current_result: dict | None = None

with left:
    # Show history
    for item in st.session_state.history:
        with st.chat_message("user"):
            st.markdown(item["question"])
        with st.chat_message("assistant"):
            with st.expander("エージェント動作ログ", expanded=False):
                if item.get("planner_output"):
                    st.markdown("**🗺 プランナー**")
                    _render_thinking(item.get("planner_thinking"))
                    st.text(item["planner_output"])
                if item.get("trace"):
                    _render_trace_entries(item["trace"])
                if item.get("composer_thinking"):
                    st.markdown("**✍ コンポーザー**")
                    _render_thinking(item["composer_thinking"])
            st.markdown(item["answer"])

    # Pending question from sidebar eval buttons
    pending = st.session_state.pop("pending_question", None)
    chat_input = st.chat_input("条文について質問してください...")
    question = pending or chat_input

    if question:
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.status("⏳ 回答を生成中...", expanded=True) as status:
                try:
                    t_start = time.perf_counter()
                    result = run(question, st.session_state.config)
                    t_total = time.perf_counter() - t_start

                    # — プランナー ——————————————————————————————
                    if result.get("planner_output"):
                        st.markdown("**🗺 プランナー**")
                        _render_thinking(result["debug"]["planner"].get("thinking"))
                        st.text(result["planner_output"])

                    # — 実行ループ ——————————————————————————————
                    _render_trace_entries(result["trace"])

                    # — コンポーザー ————————————————————————————
                    st.markdown("**✍ コンポーザー**")
                    _render_thinking(result["debug"]["composer"].get("thinking"))

                    status.update(
                        label=f"✅ 完了 ({t_total:.1f}s)",
                        state="complete",
                        expanded=False,
                    )
                except Exception as e:
                    status.update(label="❌ エラー", state="error", expanded=True)
                    st.error(f"エラーが発生しました: {e}")
                    result = None

            if result:
                st.markdown(result["answer"])

        if result:
            current_result = result
            st.session_state.last_debug = result.get("debug")
            dbg = result.get("debug", {})
            st.session_state.history.append(
                {
                    "question": question,
                    "answer": result["answer"],
                    "trace": result["trace"],
                    "cited_chunks": result.get("cited_chunks", []),
                    "all_chunks": result.get("all_chunks", []),
                    "invalid_citations": result.get("invalid_citations", []),
                    "planner_output": result.get("planner_output"),
                    "planner_thinking": dbg.get("planner", {}).get("thinking"),
                    "composer_thinking": dbg.get("composer", {}).get("thinking"),
                }
            )

with right:
    st.subheader("📚 根拠パネル")
    st.divider()

    # Use current result first, then last history item
    if current_result:
        cited = current_result.get("cited_chunks", [])
        all_ch = current_result.get("all_chunks", [])
    elif st.session_state.history:
        last = st.session_state.history[-1]
        cited = last.get("cited_chunks", [])
        all_ch = last.get("all_chunks", [])
    else:
        cited = []
        all_ch = []

    if not cited and not all_ch:
        st.info("質問すると出典条文がここに表示されます。")
    else:
        # Cited chunks (default display)
        if cited:
            for chunk in cited:
                with st.expander(f"📄 {chunk['hierarchy']}", expanded=True):
                    st.caption(
                        f"ページ: {chunk.get('pages', '―')}　系統: {chunk.get('domain', '―')}"
                    )
                    st.markdown("---")
                    st.markdown(chunk.get("body", "") or "*本文なし*")
        else:
            st.info("引用チャンクなし（回答内で条文を引用できませんでした）")

        # All retrieved chunks (folded)
        if all_ch:
            with st.expander(f"検索した全チャンク ({len(all_ch)}件)", expanded=False):
                for chunk in all_ch:
                    st.markdown(f"**{chunk['hierarchy']}**")
                    st.caption(
                        f"chunk_id: {chunk['chunk_id']} | "
                        f"pages: {chunk.get('pages', '―')}"
                    )
                    st.markdown(chunk.get("body", "")[:300] + ("…" if len(chunk.get("body", "")) > 300 else ""))
                    st.divider()
