"""
Agent: three-role + advisor tool-use loop for construction spec QA.

Architecture (M4):
  Planner (optional) → [Pre-loop Advisor] → Execution Loop → [Post-loop Advisor] → Composer

Public API:
  run_pre_composer(question, config) → dict  (planner + loop, no composer)
  make_composer_stream(question, all_chunks, config, ...) → (gen, get_result_fn)
  run(question, config) → dict               (full pipeline, non-streaming)
"""
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict

from src.config import AgentConfig, APP_VERSION
from src.llm import make_client
from src.tools import TOOLS, read_section, search_chunks

logger = logging.getLogger(__name__)

# ── System prompts ────────────────────────────────────────────────────────────

_PLANNER_SYSTEM = """\
あなたは公共建築工事標準仕様書（電気設備工事編）の検索計画専門家です。
質問を分析し、仕様書から回答を見つけるための検索計画を立ててください。

出力（プレーンテキスト）:
質問タイプ: [可否確認/数値確認/手順確認/比較確認/オープン/その他]
ターゲット: [答えが記載されているであろう表・条番号（例: 表1.1.1「電線類」、2.2.3）]
クエリ1: [検索文字列]
クエリ2: [必要なら]
クエリ3: [必要なら]
advisor_recommended: [true/false — 質問が広範囲・守備範囲不明・曖昧な場合はtrue]

重要: 可否確認の場合は個別言及より規定表・一覧表（使用可能材料を列挙したもの）の特定を優先。\
"""

_LOOP_SYSTEM_TEMPLATE = """\
あなたは公共建築工事標準仕様書（電気設備工事編）の条文収集アシスタントです。
ツールを使って質問の回答に必要な条文テキストを収集してください。

{plan_section}収集ルール:
- 回答に直接関係する条文を取得すること
- refsに参照先がある場合、必要であればread_sectionで精読すること
- 権威ソース（規定表・一覧）を優先すること
- 素材収集が完了したらツール呼び出しを終了すること（回答は不要）\
"""

_COMPOSER_SYSTEM_TEMPLATE = """\
あなたは公共建築工事標準仕様書（電気設備工事編）の回答生成専門家です。

本システムが保有する文書:
- 公共建築工事標準仕様書（電気設備工事編）令和7年版（doc_slug: denki-setsubi）

{style_instruction}

厳守事項:
- 提供された条文素材に明確な根拠がある場合のみ断定的に回答すること
- 素材に根拠がない場合は「根拠不足」と明記し、もっともらしい条番号で穴を埋めないこと
- 可否を問う質問は権威ソース（規定表・一覧表）を引用できた場合のみ断定すること
- 質問が本システムの保有文書の守備範囲外の場合（内線規程・電技解釈等）は、
  その旨を明記して「本文書には該当規定が見当たらない」と回答すること
- 質問の前提が誤り（「AはよくBはダメ」といった規定が存在しない）場合は前提を訂正すること

出力形式（二部形式）:
まず回答本文（Markdown可）をそのまま出力すること。
次に必ず以下の区切り行を置き、引用IDのみをJSONで続けること。

<!-- CITATIONS -->
{{"cited_chunk_ids": ["chunk_id_1", "chunk_id_2"]}}\
"""

_ADVISOR_SYSTEM = """\
あなたは公共建築工事標準仕様書（電気設備工事編）の検索アドバイザーです。
実行ループの行き詰まりを判断し、方針を裁定する役です。

以下の情報を受け取ります:
- 質問
- プランナーの計画（あれば）
- 実行ループのトレース要約
- これまでに収集したチャンク一覧

次のいずれかを裁定してください:
(a) 再計画（replan）: 新しい検索クエリを提示し、実行ループを続行する
(b) 守備範囲外（out_of_scope）: 当文書の守備範囲外と判定し、コンポーザーへ渡す

判断基準:
- 再計画: まだ試していない検索軸がある場合。クエリの方向性を変えれば関連チャンクが得られると判断できる場合
- 守備範囲外: 検索を尽くしても関連チャンクが得られず、質問が他の規範（内線規程・電技解釈等）の領域の場合

出力（JSONのみ。他のテキストは出力しないこと）:
再計画の場合:
{"decision": "replan", "reason": "裁定の理由（一文）", "new_queries": ["クエリ1", "クエリ2"]}

守備範囲外の場合:
{"decision": "out_of_scope", "reason": "裁定の理由（一文）"}\
"""

_STYLE_INSTRUCTIONS = {
    "brief": "回答は結論と根拠条番号のみを一〜二文で述べること。",
    "standard": "結論と根拠条文の要点を含む標準的な説明で回答すること。",
    "detailed": "引用付きの詳細な解説で回答し、関連条文への言及も含めること。",
}

_CITATIONS_MARKER = "<!-- CITATIONS -->"
_CITATIONS_MARKER_LEN = len(_CITATIONS_MARKER)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_advisor_recommended(plan_text: str) -> bool:
    """Extract advisor_recommended: true/false from planner output."""
    m = re.search(r"advisor_recommended:\s*(true|false)", plan_text, re.IGNORECASE)
    return m.group(1).lower() == "true" if m else False


def _dispatch(name: str, input_: dict, top_k_default: int) -> object:
    if name == "search_chunks":
        if "top_k" not in input_:
            input_ = {**input_, "top_k": top_k_default}
        return search_chunks(**input_)
    if name == "read_section":
        return read_section(**input_)
    return f"[不明なツール: {name}]"


def _cached_search(inp: dict, top_k_default: int, cache: dict) -> list:
    query = inp.get("query", "")
    k = inp.get("top_k", top_k_default)
    key = (query, k)
    if key in cache:
        return cache[key]
    if "top_k" not in inp:
        inp = {**inp, "top_k": top_k_default}
    result = search_chunks(**inp)
    cache[key] = result
    return result


def _format_chunks_for_composer(chunks: list) -> str:
    lines = []
    for c in chunks:
        lines.append(f"[chunk_id: {c['chunk_id']}]")
        lines.append(f"階層: {c['hierarchy']}")
        lines.append(f"{c.get('heading', '')}\n{c.get('body', '')}")
        lines.append("---")
    return "\n".join(lines)


def _parse_composer_output(text: str) -> dict:
    """Parse two-part composer output (answer text + <!-- CITATIONS --> + JSON)."""
    if not text:
        return {"answer": "", "cited_chunk_ids": []}

    if _CITATIONS_MARKER in text:
        parts = text.split(_CITATIONS_MARKER, 1)
        answer = parts[0].strip()
        json_part = parts[1].strip()
        try:
            data = json.loads(json_part)
            return {"answer": answer, "cited_chunk_ids": data.get("cited_chunk_ids", [])}
        except Exception:
            return {"answer": answer, "cited_chunk_ids": []}

    # Fallback: try to parse as old JSON format
    try:
        s = text.strip()
        if "```" in s:
            for part in s.split("```"):
                p = part.lstrip("json").strip()
                if p.startswith("{"):
                    s = p
                    break
        data = json.loads(s)
        return {"answer": data.get("answer", text), "cited_chunk_ids": data.get("cited_chunk_ids", [])}
    except Exception:
        return {"answer": text, "cited_chunk_ids": []}


def _summarize_trace(trace: list) -> str:
    if not trace:
        return "（なし）"
    lines = []
    for step in trace:
        tcs = []
        for tc in step["tool_calls"]:
            label = tc["input"].get("query", tc["input"].get("hierarchy", ""))
            tcs.append(f"{tc['name']}({label[:40]})")
        lines.append(f"ループ{step['loop']}: {', '.join(tcs)}")
    return "\n".join(lines)


# ── Three roles + Advisor ─────────────────────────────────────────────────────

def _run_planner(question: str, config: AgentConfig) -> tuple:
    """Returns (plan_text, debug)."""
    t0 = time.perf_counter()
    client = make_client(config.planner_model)
    resp = client.chat([{"role": "user", "text": question}], [], _PLANNER_SYSTEM)
    elapsed = time.perf_counter() - t0
    return resp.text or "", {
        "model": config.planner_model,
        "usage": resp.usage,
        "time_s": round(elapsed, 2),
        "raw_response": resp.text,
        "thinking": resp.thinking,
    }


def _run_advisor(
    question: str, plan: str | None, trace: list, all_chunks: list, config: AgentConfig
) -> tuple:
    """Returns (result_dict, debug). result_dict has keys: decision, reason, new_queries."""
    t0 = time.perf_counter()
    client = make_client(config.advisor_model)

    trace_summary = _summarize_trace(trace)
    chunk_ids = ", ".join(c["chunk_id"] for c in all_chunks) if all_chunks else "（なし）"

    user_text = (
        f"質問: {question}\n\n"
        f"プランナーの計画:\n{plan or 'なし'}\n\n"
        f"実行ループトレース:\n{trace_summary}\n\n"
        f"収集チャンク（{len(all_chunks)}件）: {chunk_ids}"
    )
    resp = client.chat([{"role": "user", "text": user_text}], [], _ADVISOR_SYSTEM)
    elapsed = time.perf_counter() - t0

    raw = resp.text or ""
    try:
        s = raw.strip()
        if "```" in s:
            for part in s.split("```"):
                p = part.lstrip("json").strip()
                if p.startswith("{"):
                    s = p
                    break
        result = json.loads(s)
    except Exception:
        result = {"decision": "replan", "reason": "解析失敗", "new_queries": []}

    return result, {
        "model": config.advisor_model,
        "usage": resp.usage,
        "time_s": round(elapsed, 2),
        "decision": result.get("decision", ""),
        "reason": result.get("reason", ""),
    }


def _run_loop(
    question: str,
    plan: str | None,
    config: AgentConfig,
    advisor_state: dict,
) -> tuple:
    """
    Returns (trace, all_chunks, retrieved, debug, max_loops_hit, early_stop).
    advisor_state: mutable dict with keys fired/result/debug — updated if advisor fires here.
    """
    t0 = time.perf_counter()
    total_usage = {"input_tokens": 0, "output_tokens": 0}

    plan_section = (
        f"検索計画（プランナーより）:\n{plan}\n\n上記の計画に従って素材を収集してください。\n"
        if plan else ""
    )
    system = _LOOP_SYSTEM_TEMPLATE.format(plan_section=plan_section)
    client = make_client(config.loop_model)

    messages = [{"role": "user", "text": question}]
    trace = []
    retrieved: list = []
    all_chunks: list = []
    seen_ids: set = set()
    query_cache: dict = {}
    max_loops_hit = True
    early_stop = False
    consecutive_empty = 0
    total_search_calls = 0

    any_trigger_active = (
        config.advisor_trigger_stall
    )

    for loop_num in range(config.max_loops):
        response = client.chat(messages, TOOLS, system)
        total_usage["input_tokens"] += response.usage.get("input_tokens", 0)
        total_usage["output_tokens"] += response.usage.get("output_tokens", 0)

        if not response.tool_calls:
            max_loops_hit = False
            break

        # ── Parallel search_chunks + sequential other tools ───────────────────
        search_tcs = [tc for tc in response.tool_calls if tc.name == "search_chunks"]
        other_tcs = [tc for tc in response.tool_calls if tc.name != "search_chunks"]

        tc_results: dict = {}

        if len(search_tcs) > 1:
            with ThreadPoolExecutor(max_workers=len(search_tcs)) as ex:
                future_to_tc = {
                    ex.submit(_cached_search, tc.input, config.top_k, query_cache): tc
                    for tc in search_tcs
                }
                for future in as_completed(future_to_tc):
                    tc = future_to_tc[future]
                    tc_results[tc.id] = future.result()
        elif search_tcs:
            tc = search_tcs[0]
            tc_results[tc.id] = _cached_search(tc.input, config.top_k, query_cache)

        for tc in other_tcs:
            tc_results[tc.id] = _dispatch(tc.name, tc.input, config.top_k)

        # ── Collect results in original order ─────────────────────────────────
        tool_call_records = []
        tool_results = []
        new_in_this_loop = 0

        for tc in response.tool_calls:
            result = tc_results[tc.id]
            result_str = (
                json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result
            )
            tool_call_records.append({"name": tc.name, "input": tc.input, "output": result})
            tool_results.append({"id": tc.id, "name": tc.name, "content": result_str})

            if tc.name == "search_chunks" and isinstance(result, list):
                for hit in result:
                    cid = hit.get("chunk_id", "")
                    if cid and cid not in retrieved:
                        retrieved.append(cid)
                    if cid and cid not in seen_ids:
                        seen_ids.add(cid)
                        all_chunks.append(hit)
                        new_in_this_loop += 1

        # Track stall
        had_search = bool(search_tcs)
        total_search_calls += len(search_tcs)
        if had_search and new_in_this_loop == 0:
            consecutive_empty += 1
        elif new_in_this_loop > 0:
            consecutive_empty = 0

        trace.append({
            "loop": loop_num + 1,
            "thinking": response.thinking,
            "tool_calls": tool_call_records,
        })
        logger.info("loop %d: %s  (total_search_calls=%d, consecutive_empty=%d)",
                    loop_num + 1, [tc.name for tc in response.tool_calls],
                    total_search_calls, consecutive_empty)

        messages.append({
            "role": "assistant",
            "text": response.text,
            "tool_calls": [
                {"id": tc.id, "name": tc.name, "input": tc.input}
                for tc in response.tool_calls
            ],
        })
        messages.append({"role": "tool_results", "results": tool_results})

        # ── Mid-loop advisor: 難航検知 ─────────────────────────────────────────
        stall_threshold = config.advisor_k
        search_budget = int(config.max_loops * 0.6)
        stall_hit = (consecutive_empty >= stall_threshold) or (total_search_calls >= search_budget)
        if (
            not advisor_state["fired"]
            and config.advisor_trigger_stall
            and stall_hit
        ):
            logger.info("advisor firing: stall detected at loop %d", loop_num + 1)
            adv_result, adv_debug = _run_advisor(question, plan, trace, all_chunks, config)
            advisor_state["fired"] = True
            advisor_state["result"] = adv_result
            advisor_state["debug"] = adv_debug

            trace.append({
                "loop": loop_num + 1,
                "advisor": True,
                "decision": adv_result.get("decision", ""),
                "reason": adv_result.get("reason", ""),
                "new_queries": adv_result.get("new_queries", []),
                "tool_calls": [],
                "thinking": None,
            })

            if adv_result.get("decision") == "out_of_scope":
                break
            elif adv_result.get("decision") == "replan":
                consecutive_empty = 0
                new_qs = adv_result.get("new_queries", [])
                if new_qs:
                    replan_msg = (
                        f"[アドバイザー指示] {adv_result.get('reason', '')}\n"
                        f"新しい検索クエリ:\n" + "\n".join(f"- {q}" for q in new_qs) +
                        "\nこの方針で検索を再開してください。"
                    )
                    messages.append({"role": "user", "text": replan_msg})
            continue  # continue loop from next iteration

        # ── Early stop (safety net) ────────────────────────────────────────────
        if consecutive_empty >= config.early_stop_k:
            early_stop = True
            trace.append({
                "loop": loop_num + 1,
                "early_stop": True,
                "tool_calls": [],
                "thinking": None,
            })
            logger.info("early stop triggered at loop %d", loop_num + 1)
            break

    elapsed = time.perf_counter() - t0
    return trace, all_chunks, retrieved, {
        "model": config.loop_model,
        "usage": total_usage,
        "time_s": round(elapsed, 2),
        "loops": len([s for s in trace if not s.get("advisor") and not s.get("early_stop")]),
        "max_loops_hit": max_loops_hit,
        "early_stop": early_stop,
    }, max_loops_hit, early_stop


def _run_composer(
    question: str, all_chunks: list, config: AgentConfig, advisor_out_of_scope: bool = False
) -> tuple:
    """Returns (answer, cited_chunk_ids, raw_output, debug)."""
    t0 = time.perf_counter()
    client = make_client(config.composer_model)

    style_instr = _STYLE_INSTRUCTIONS.get(config.answer_style, _STYLE_INSTRUCTIONS["standard"])
    system = _COMPOSER_SYSTEM_TEMPLATE.format(style_instruction=style_instr)

    chunks_text = _format_chunks_for_composer(all_chunks) if all_chunks else "（検索結果なし）"
    if advisor_out_of_scope:
        user_msg = (
            f"質問: {question}\n\n"
            "アドバイザーがこの質問を当文書の守備範囲外と判定しました。"
            "第二段回答（守備範囲外宣言）を生成してください。\n\n"
            f"--- 収集した条文素材 ---\n{chunks_text}"
        )
    else:
        user_msg = f"質問: {question}\n\n--- 収集した条文素材 ---\n{chunks_text}"

    resp = client.chat([{"role": "user", "text": user_msg}], [], system)
    elapsed = time.perf_counter() - t0

    raw = resp.text or ""
    parsed = _parse_composer_output(raw)
    answer = parsed.get("answer", raw)
    cited_ids = parsed.get("cited_chunk_ids", [])
    if not isinstance(cited_ids, list):
        cited_ids = []

    return answer, cited_ids, raw, {
        "model": config.composer_model,
        "usage": resp.usage,
        "time_s": round(elapsed, 2),
        "raw_response": raw,
        "thinking": resp.thinking,
    }


# ── Public streaming API ──────────────────────────────────────────────────────

def make_composer_stream(
    question: str,
    all_chunks: list,
    config: AgentConfig,
    advisor_out_of_scope: bool = False,
):
    """
    Returns (display_generator, get_result_fn).
    Exhaust the generator first (e.g., via st.write_stream), then call get_result_fn().
    get_result_fn() returns (answer, cited_ids, raw, debug).
    """
    t0 = time.perf_counter()
    client = make_client(config.composer_model)

    style_instr = _STYLE_INSTRUCTIONS.get(config.answer_style, _STYLE_INSTRUCTIONS["standard"])
    system = _COMPOSER_SYSTEM_TEMPLATE.format(style_instruction=style_instr)

    chunks_text = _format_chunks_for_composer(all_chunks) if all_chunks else "（検索結果なし）"
    if advisor_out_of_scope:
        user_msg = (
            f"質問: {question}\n\n"
            "アドバイザーがこの質問を当文書の守備範囲外と判定しました。"
            "第二段回答（守備範囲外宣言）を生成してください。\n\n"
            f"--- 収集した条文素材 ---\n{chunks_text}"
        )
    else:
        user_msg = f"質問: {question}\n\n--- 収集した条文素材 ---\n{chunks_text}"

    full_text_holder = [""]
    usage_holder: dict = {}

    def gen():
        accumulated = ""
        yielded = 0
        past_marker = False

        for chunk in client.chat_stream(
            [{"role": "user", "text": user_msg}], system, _usage_holder=usage_holder
        ):
            accumulated += chunk
            if not past_marker:
                marker_pos = accumulated.find(_CITATIONS_MARKER)
                if marker_pos != -1:
                    past_marker = True
                    if marker_pos > yielded:
                        yield accumulated[yielded:marker_pos]
                    yielded = marker_pos
                else:
                    safe_end = max(yielded, len(accumulated) - _CITATIONS_MARKER_LEN)
                    if safe_end > yielded:
                        yield accumulated[yielded:safe_end]
                        yielded = safe_end

        # Drain remaining display text if marker never appeared
        if not past_marker and len(accumulated) > yielded:
            yield accumulated[yielded:]

        full_text_holder[0] = accumulated

    def get_result():
        raw = full_text_holder[0]
        elapsed = time.perf_counter() - t0
        parsed = _parse_composer_output(raw)
        answer = parsed.get("answer", raw)
        cited_ids = parsed.get("cited_chunk_ids", [])
        if not isinstance(cited_ids, list):
            cited_ids = []
        return answer, cited_ids, raw, {
            "model": config.composer_model,
            "usage": dict(usage_holder),
            "time_s": round(elapsed, 2),
            "raw_response": raw,
            "thinking": None,
        }

    return gen(), get_result


# ── Main pre-composer entry ───────────────────────────────────────────────────

def run_pre_composer(question: str, config: AgentConfig | None = None) -> dict:
    """
    Run planner + advisor (pre/mid/post-loop) + execution loop.
    Returns partial result dict (no composer step).
    Keys: question, planner_output, trace, retrieved, all_chunks,
          advisor_out_of_scope, debug_partial.
    """
    if config is None:
        config = AgentConfig()

    planner_output: str | None = None
    planner_debug: dict = {}
    advisor_recommended = False

    # ── Planner ───────────────────────────────────────────────────────────────
    if config.planner_enabled:
        planner_output, planner_debug = _run_planner(question, config)
        advisor_recommended = _parse_advisor_recommended(planner_output or "")
        logger.info("planner: %s", (planner_output or "")[:200])

    # ── Pre-loop advisor: 常時 / プランナー裁量 ───────────────────────────────
    advisor_state = {"fired": False, "result": None, "debug": {}}
    effective_plan = planner_output
    pre_loop_skip = False

    fire_pre = config.advisor_trigger_always or (
        config.advisor_trigger_planner and advisor_recommended
    )
    pre_advisor_trace: dict | None = None
    if fire_pre:
        logger.info("advisor firing: pre-loop (always=%s, planner=%s)", config.advisor_trigger_always, advisor_recommended)
        adv_result, adv_debug = _run_advisor(question, planner_output, [], [], config)
        advisor_state["fired"] = True
        advisor_state["result"] = adv_result
        advisor_state["debug"] = adv_debug

        pre_advisor_trace = {
            "loop": "pre",
            "advisor": True,
            "decision": adv_result.get("decision", ""),
            "reason": adv_result.get("reason", ""),
            "new_queries": adv_result.get("new_queries", []),
            "tool_calls": [],
            "thinking": None,
        }

        if adv_result.get("decision") == "out_of_scope":
            pre_loop_skip = True
        elif adv_result.get("decision") == "replan":
            new_qs = adv_result.get("new_queries", [])
            if new_qs:
                extra = "\nアドバイザー補足クエリ:\n" + "\n".join(f"- {q}" for q in new_qs)
                effective_plan = (planner_output or "") + extra

    # ── Execution loop ────────────────────────────────────────────────────────
    if not pre_loop_skip:
        trace, all_chunks, retrieved, loop_debug, max_loops_hit, early_stop = _run_loop(
            question, effective_plan, config, advisor_state
        )
    else:
        trace, all_chunks, retrieved = [], [], []
        loop_debug = {"model": config.loop_model, "usage": {}, "time_s": 0.0, "loops": 0, "max_loops_hit": False, "early_stop": False}
        max_loops_hit = False
        early_stop = False

    # Prepend pre-loop advisor entry so it appears first in the trace UI
    if pre_advisor_trace is not None:
        trace = [pre_advisor_trace] + trace

    # ── Post-loop advisor: 未決着 ─────────────────────────────────────────────
    if not advisor_state["fired"] and config.advisor_trigger_unresolved and max_loops_hit:
        logger.info("advisor firing: post-loop unresolved")
        adv_result, adv_debug = _run_advisor(question, planner_output, trace, all_chunks, config)
        advisor_state["fired"] = True
        advisor_state["result"] = adv_result
        advisor_state["debug"] = adv_debug
        trace.append({
            "loop": "post",
            "advisor": True,
            "decision": adv_result.get("decision", ""),
            "reason": adv_result.get("reason", ""),
            "new_queries": adv_result.get("new_queries", []),
            "tool_calls": [],
            "thinking": None,
        })

    advisor_out_of_scope = (
        advisor_state["result"] is not None
        and advisor_state["result"].get("decision") == "out_of_scope"
    )

    return {
        "question": question,
        "planner_output": planner_output,
        "trace": trace,
        "retrieved": retrieved,
        "all_chunks": all_chunks,
        "advisor_out_of_scope": advisor_out_of_scope,
        "advisor_state": advisor_state,
        "debug_partial": {
            "app_version": APP_VERSION,
            "config": asdict(config),
            "planner": planner_debug,
            "loop": loop_debug,
            "advisor": advisor_state["debug"],
        },
    }


# ── Main entry (non-streaming) ────────────────────────────────────────────────

def run(question: str, config: AgentConfig | None = None) -> dict:
    """
    Run the full pipeline (non-streaming).
    Returns dict with keys:
        question, answer, trace, retrieved,
        cited_chunk_ids, cited_chunks, all_chunks,
        invalid_citations, planner_output, debug
    """
    if config is None:
        config = AgentConfig()

    pre = run_pre_composer(question, config)

    answer, cited_ids, raw_composer, composer_debug = _run_composer(
        question, pre["all_chunks"], config, pre["advisor_out_of_scope"]
    )

    # Citation verification
    retrieved_set = {c["chunk_id"] for c in pre["all_chunks"]}
    valid_cited = [cid for cid in cited_ids if cid in retrieved_set]
    invalid_citations = [cid for cid in cited_ids if cid not in retrieved_set]
    cited_chunks = [c for c in pre["all_chunks"] if c["chunk_id"] in set(valid_cited)]

    if invalid_citations:
        logger.warning("invalid_citations discarded: %s", invalid_citations)

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
        "all_chunks": pre["all_chunks"],
        "invalid_citations": invalid_citations,
        "planner_output": pre["planner_output"],
        "debug": debug,
    }


def main():
    import sys
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    if len(sys.argv) < 2:
        print("Usage: python src/agent.py \"質問文\"", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]
    result = run(question)

    print(f"\n【質問】{result['question']}")
    print(f"\n【回答】\n{result['answer']}")
    print(f"\n【引用チャンク】{result['cited_chunk_ids']}")
    print(f"\n【トレース】{len(result['trace'])} ループ")
    for step in result["trace"]:
        if step.get("advisor"):
            print(f"  [アドバイザー]: {step['decision']} — {step['reason']}")
        elif step.get("early_stop"):
            print(f"  ⏹ 早期打ち切り")
        else:
            for tc in step["tool_calls"]:
                args_preview = json.dumps(tc["input"], ensure_ascii=False)[:80]
                print(f"  loop{step['loop']}: {tc['name']}({args_preview})")


if __name__ == "__main__":
    main()
