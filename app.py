"""
Streamlit UI — M4
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

from src.agent import make_composer_stream, run, run_pre_composer
from src.config import (
    ANSWER_STYLES,
    APP_VERSION,
    PRESETS,
    AgentConfig,
    estimate_cost,
    load_config,
    load_documents_yaml,
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
        # Advisor entry
        if step.get("advisor"):
            decision = step.get("decision", "")
            reason = step.get("reason", "")
            icon = "🎯"
            label = "守備範囲外裁定" if decision == "out_of_scope" else "再計画裁定"
            phase = step.get("loop", "")
            phase_label = "（プレループ）" if phase == "pre" else "（ポストループ）" if phase == "post" else ""
            st.markdown(f"**{icon} アドバイザー{phase_label} — {label}**")
            st.caption(f"理由: {reason}")
            new_qs = step.get("new_queries", [])
            if new_qs:
                st.caption("新クエリ: " + " / ".join(new_qs))
            continue

        # Early stop entry
        if step.get("early_stop"):
            st.markdown("**⏹ 早期打ち切り（連続空振りによる強制終了）**")
            continue

        # Normal loop entry
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


def _build_meta(debug: dict, t_total: float, scope_doc_count: int | None = None) -> dict:
    return {
        "t_total": round(t_total, 1),
        "planner": debug.get("planner", {}),
        "loop": debug.get("loop", {}),
        "composer": debug.get("composer", {}),
        "advisor": debug.get("advisor", {}),
        "config": debug.get("config", {}),
        "scope_doc_count": scope_doc_count,
    }


def _render_meta_footer(meta: dict | None) -> None:
    if not meta:
        return
    planner = meta.get("planner", {})
    loop = meta.get("loop", {})
    composer = meta.get("composer", {})
    advisor = meta.get("advisor", {})
    cfg = meta.get("config", {})

    stage_parts = []
    if planner.get("usage"):
        u = planner["usage"]
        stage_parts.append(
            f"🗺 {planner.get('time_s', 0):.1f}s "
            f"({u.get('input_tokens', 0):,}/{u.get('output_tokens', 0):,}tok)"
        )
    if loop.get("usage"):
        u = loop["usage"]
        loop_count = loop.get("loops", "?")
        early_flag = "⏹" if loop.get("early_stop") else ""
        stage_parts.append(
            f"🔄×{loop_count}{early_flag} {loop.get('time_s', 0):.1f}s "
            f"({u.get('input_tokens', 0):,}/{u.get('output_tokens', 0):,}tok)"
        )
    if advisor.get("usage"):
        u = advisor["usage"]
        decision = advisor.get("decision", "")
        dec_icon = "🎯b" if decision == "out_of_scope" else "🎯a" if decision == "replan" else "🎯"
        stage_parts.append(
            f"{dec_icon} {advisor.get('time_s', 0):.1f}s "
            f"({u.get('input_tokens', 0):,}/{u.get('output_tokens', 0):,}tok)"
        )
    if composer.get("usage"):
        u = composer["usage"]
        stage_parts.append(
            f"✍ {composer.get('time_s', 0):.1f}s "
            f"({u.get('input_tokens', 0):,}/{u.get('output_tokens', 0):,}tok)"
        )

    total_cost = 0.0
    has_cost = False
    for role_dbg in [planner, loop, advisor, composer]:
        cost = estimate_cost(
            role_dbg.get("model", ""),
            role_dbg.get("usage", {}).get("input_tokens", 0),
            role_dbg.get("usage", {}).get("output_tokens", 0),
        )
        if cost is not None:
            total_cost += cost
            has_cost = True

    model_parts = []
    if cfg.get("planner_enabled"):
        model_parts.append(f"planner={cfg.get('planner_model', '').split('/')[-1]}")
    model_parts.append(f"loop={cfg.get('loop_model', '').split('/')[-1]}")
    if advisor.get("model"):
        model_parts.append(f"advisor={advisor['model'].split('/')[-1]}")
    model_parts.append(f"composer={cfg.get('composer_model', '').split('/')[-1]}")

    scope_count = meta.get("scope_doc_count")
    scope_str = f"　📂 検索スコープ: {scope_count}件" if scope_count is not None else ""
    timing_line = f"合計 {meta['t_total']:.1f}s　" + "　".join(stage_parts) + scope_str
    cost_str = f"≈${total_cost:.4f}" if has_cost else "―"
    model_line = f"{cost_str}　" + " / ".join(model_parts)
    st.caption(timing_line)
    st.caption(model_line)


def _finalize_result(question: str, pre: dict, answer: str, cited_ids: list,
                     raw_composer: str, composer_debug: dict, t_total: float) -> dict:
    """Assemble final result dict after streaming composer."""
    all_chunks = pre["all_chunks"]
    retrieved_set = {c["chunk_id"] for c in all_chunks}
    valid_cited = [cid for cid in cited_ids if cid in retrieved_set]
    invalid_citations = [cid for cid in cited_ids if cid not in retrieved_set]
    cited_chunks = [c for c in all_chunks if c["chunk_id"] in set(valid_cited)]

    debug = pre["debug_partial"].copy()
    debug["composer"] = composer_debug
    debug["raw_composer_output"] = raw_composer
    debug["max_loops_hit"] = pre["debug_partial"]["loop"].get("max_loops_hit", False)

    return {
        "question": question,
        "answer": answer,
        "trace": pre["trace"],
        "retrieved": pre["retrieved"],
        "cited_chunk_ids": valid_cited,
        "cited_chunks": cited_chunks,
        "all_chunks": all_chunks,
        "invalid_citations": invalid_citations,
        "planner_output": pre["planner_output"],
        "debug": debug,
        "t_total": t_total,
    }


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("⚙️ 設定")
    cfg = st.session_state.config

    # ── 文書スコープ ───────────────────────────────────────────────────────────
    st.subheader("📂 文書")
    all_docs = [d for d in load_documents_yaml() if d.get("status") == "active"]
    all_doc_ids = [d["id"] for d in all_docs]

    # Tag filter
    all_tags: list[str] = sorted({t for d in all_docs for t in (d.get("tags") or [])})
    tag_filter: list[str] = []
    if all_tags:
        tag_filter = st.multiselect("タグ絞り込み", all_tags, key="doc_tag_filter", label_visibility="collapsed",
                                    placeholder="タグで絞り込み（空=全表示）")

    filtered_docs = [d for d in all_docs if not tag_filter or any(t in (d.get("tags") or []) for t in tag_filter)]

    # Group by domain
    domains: dict[str, list] = {}
    for d in filtered_docs:
        dom = d.get("domain") or "未分類"
        domains.setdefault(dom, []).append(d)

    # Determine initial checked state (None = all checked)
    _cur_sel = cfg.selected_doc_ids  # None=all, list=explicit

    col_a, col_b = st.columns(2)
    _select_all = col_a.button("全選択", key="doc_sel_all", use_container_width=True)
    _deselect_all = col_b.button("全解除", key="doc_sel_none", use_container_width=True)

    if _select_all:
        _cur_sel = None
    elif _deselect_all:
        _cur_sel = []

    checked_ids: list[str] = []
    for dom, dom_docs in domains.items():
        with st.expander(f"📁 {dom} ({len(dom_docs)})", expanded=True):
            for d in dom_docs:
                if _cur_sel is None:
                    default_val = True
                else:
                    default_val = d["id"] in _cur_sel
                checked = st.checkbox(
                    d.get("title", d["id"]),
                    value=default_val,
                    key=f"doc_chk_{d['id']}",
                )
                if checked:
                    checked_ids.append(d["id"])

    # Normalize: if all docs checked → None (no filter)
    if set(checked_ids) >= set(all_doc_ids):
        selected_doc_ids: list | None = None
    elif not checked_ids:
        selected_doc_ids = []
    else:
        selected_doc_ids = checked_ids

    if not all_docs:
        st.caption("documents.yaml に登録済み文書がありません")

    st.divider()

    # ── 三役モデル構成 ─────────────────────────────────────────────────────────
    st.subheader("三役モデル構成")
    planner_enabled = st.toggle("プランナー ON", value=cfg.planner_enabled)

    if planner_enabled:
        planner_model = _model_selector("プランナーモデル", "planner", cfg.planner_model)
    else:
        planner_model = cfg.planner_model

    loop_model = _model_selector("実行ループモデル", "loop", cfg.loop_model)
    composer_model = _model_selector("コンポーザーモデル", "composer", cfg.composer_model)

    # ── チューニング ───────────────────────────────────────────────────────────
    st.subheader("チューニング")
    max_loops = st.slider("MAX_LOOPS", 5, 30, cfg.max_loops)
    top_k = st.slider("search top_k", 3, 15, cfg.top_k)
    answer_style = st.radio(
        "回答スタイル",
        list(ANSWER_STYLES.keys()),
        index=list(ANSWER_STYLES.keys()).index(cfg.answer_style),
        format_func=lambda x: ANSWER_STYLES[x],
    )

    # ── アドバイザー ───────────────────────────────────────────────────────────
    st.subheader("🎯 アドバイザー")
    advisor_model = _model_selector("アドバイザーモデル", "advisor", cfg.advisor_model)

    st.caption("**発動条件**（複数選択可・既定: 難航検知のみ）")
    advisor_trigger_always = st.checkbox("常時（全質問・プランナー直後）", value=cfg.advisor_trigger_always)
    advisor_trigger_planner = st.checkbox(
        "プランナー裁量（advisor_recommended=true）",
        value=cfg.advisor_trigger_planner,
        disabled=not planner_enabled,
        help="プランナーONのときのみ有効",
    )
    advisor_trigger_stall = st.checkbox("難航検知（連続空振り検知）", value=cfg.advisor_trigger_stall)
    advisor_trigger_unresolved = st.checkbox(
        "未決着（MAX_LOOPS到達時）", value=cfg.advisor_trigger_unresolved
    )

    if advisor_trigger_stall:
        advisor_k = st.slider(
            "難航検知 k（連続空振りループ数）", 1, 5, cfg.advisor_k,
            help="即時型: 直近kループ連続で新規チャンク獲得ゼロ / 予算型: 探索コール総数 >= 0.6×MAX_LOOPS のいずれかで発動"
        )
    else:
        advisor_k = cfg.advisor_k

    early_stop_k = st.slider(
        "早期打ち切り k（安全網）", 2, 5, cfg.early_stop_k,
        help="連続空振りがこのk以上続いたら問答無用で終了（アドバイザー発動後も有効）"
    )

    # Build new config
    new_cfg = AgentConfig(
        planner_enabled=planner_enabled,
        planner_model=planner_model,
        loop_model=loop_model,
        composer_model=composer_model,
        max_loops=max_loops,
        top_k=top_k,
        answer_style=answer_style,
        advisor_model=advisor_model,
        advisor_trigger_always=advisor_trigger_always,
        advisor_trigger_planner=advisor_trigger_planner,
        advisor_trigger_stall=advisor_trigger_stall,
        advisor_trigger_unresolved=advisor_trigger_unresolved,
        advisor_k=advisor_k,
        early_stop_k=early_stop_k,
        selected_doc_ids=selected_doc_ids,
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
            if dbg.get("loop", {}).get("max_loops_hit"):
                st.warning("⚠️ MAX_LOOPS に到達しました")

            if dbg.get("loop", {}).get("early_stop"):
                st.info("⏹ 早期打ち切りが発動しました")

            advisor_dbg = dbg.get("advisor", {})
            if advisor_dbg.get("decision"):
                dec = advisor_dbg["decision"]
                label = "守備範囲外" if dec == "out_of_scope" else "再計画"
                st.info(f"🎯 アドバイザー発動: {label} — {advisor_dbg.get('reason', '')}")

            if dbg.get("planner", {}).get("raw_response"):
                with st.expander("プランナー出力（生）"):
                    st.text(dbg["planner"]["raw_response"])

            if dbg.get("raw_composer_output"):
                with st.expander("コンポーザー生出力"):
                    st.text(dbg["raw_composer_output"])

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
            _render_meta_footer(item.get("meta"))

    # Pending question from sidebar eval buttons
    pending = st.session_state.pop("pending_question", None)
    chat_input = st.chat_input("条文について質問してください...")
    question = pending or chat_input

    if question:
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            result = None
            try:
                with st.status("⏳ 回答を生成中...", expanded=True) as status:
                    t_start = time.perf_counter()

                    # ── Planner + Loop ────────────────────────────────────────
                    pre = run_pre_composer(question, st.session_state.config)

                    if pre.get("planner_output"):
                        st.markdown("**🗺 プランナー**")
                        planner_thinking = pre["debug_partial"]["planner"].get("thinking")
                        _render_thinking(planner_thinking)
                        st.text(pre["planner_output"])

                    _render_trace_entries(pre["trace"])

                    # ── Composer (streaming) ──────────────────────────────────
                    st.markdown("**✍ コンポーザー**")
                    stream_gen, get_result_fn = make_composer_stream(
                        question,
                        pre["all_chunks"],
                        st.session_state.config,
                        pre.get("advisor_out_of_scope", False),
                        pre.get("scope_text", ""),
                    )
                    st.write_stream(stream_gen)

                    answer, cited_ids, raw_composer, composer_debug = get_result_fn()
                    t_total = time.perf_counter() - t_start

                    status.update(
                        label=f"✅ 完了 ({t_total:.1f}s)",
                        state="complete",
                        expanded=False,
                    )

                result = _finalize_result(
                    question, pre, answer, cited_ids, raw_composer, composer_debug, t_total
                )
                meta = _build_meta(result["debug"], t_total, pre.get("scope_doc_count"))
                _render_meta_footer(meta)

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
                result = None

        if result:
            current_result = result
            st.session_state.last_debug = result["debug"]
            dbg = result["debug"]
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
                    "meta": _build_meta(dbg, result.get("t_total", 0), pre.get("scope_doc_count")),
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
