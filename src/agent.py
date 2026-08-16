"""
Agent: three-role + advisor tool-use loop for construction spec QA.

Architecture (M5b-4):
  Planner (optional) → Execution Loop → [Mid/Post-loop Advisor] → Composer

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

from src.config import AgentConfig, APP_VERSION, load_documents_yaml
from src.llm import make_client
from src.tools import TOOLS, read_section, search_chunks

logger = logging.getLogger(__name__)

# ── System prompts ────────────────────────────────────────────────────────────

def _build_scope_docs_text(config: "AgentConfig") -> str:
    """Build scope document list text from documents.yaml for system prompts."""
    docs = load_documents_yaml()
    if config.selected_doc_ids is not None:
        docs = [d for d in docs if d.get("id") in config.selected_doc_ids]
    if not docs:
        return "現在のスコープ内文書: （なし — 全文書が除外されています）"
    lines = ["現在のスコープ内文書（検索対象）:"]
    for d in docs:
        tags_str = "・".join(d.get("tags") or [])
        tag_part = f" [{tags_str}]" if tags_str else ""
        lines.append(
            f"- {d.get('title', d['id'])} "
            f"(domain: {d.get('domain', '')}{tag_part}, doc_id: {d['id']})"
        )
    return "\n".join(lines)


def _build_planner_system(scope_text: str, user_domains: list[str] | None = None) -> str:
    return f"""\
あなたは所蔵文書群を対象とする検索計画係です。
質問を分析し、以下の所蔵文書から回答を見つけるための検索計画を立ててください。

{scope_text}

出力（プレーンテキスト）:
質問タイプ: [可否確認/数値確認/手順確認/比較確認/オープン/その他]
ターゲット: [答えが記載されているであろう表・条番号（例: 第2節2.1.3「施工要件一覧表」、第3章3.2.1）]
クエリ1: [検索文字列]
クエリ2: [必要なら]
クエリ3: [必要なら]

重要: 可否確認の場合は個別言及より規定表・一覧表（使用可能材料を列挙したもの）の特定を優先。"""


def _build_loop_system(plan_section: str, scope_text: str) -> str:
    return f"""\
あなたは建築工事仕様書の条文収集アシスタントです。
ツールを使って質問の回答に必要な条文テキストを収集してください。

{scope_text}

{plan_section}収集ルール:
- 回答に直接関係する条文を取得すること
- refsに参照先がある場合、必要であればread_sectionで精読すること
- 権威ソース（規定表・一覧）を優先すること
- 素材収集が完了したらツール呼び出しを終了すること（回答は不要）"""


def _build_composer_system(
    style_instruction: str, scope_text: str, zero_result_mode: bool = False
) -> str:
    if zero_result_mode:
        structure_rules = """\
厳守事項（検索未到達モード — 所蔵チャンク取得数=0）:
1. 検索未到達の告知: 「今回の検索ではX回検索しましたが、所蔵文書から関連する記述を取得できませんでした」と冒頭に正直に記載する。取得チャンクがないため §1「所蔵から言えること」は書けない。条番号・文書名・チャンクIDを架空で補完することは厳禁。
2. 所蔵にないこと（推定）: 質問対象がコーパス外である可能性、またはクエリ語彙とコーパス語彙の不一致の可能性を説明する。利用者が自分で調べるための参照先・検索キーワードを提示する。
3. 推論で補えること: 一般知識・法規の一般原則からの推論は「推論」ラベル付きで記載してよい。"""
    else:
        structure_rules = """\
厳守事項（三部構成の標準形）:
1. 所蔵から言えること: 収集された条文素材に根拠がある部分は、チャンク引用付きで回答すること
2. 所蔵にないこと: 「所蔵文書に特段の規定がない」形式で明示し、あるべき規範領域を名指しすること。参照先の名称・検索キーワード等、利用者が自分で調べるための手がかりを必ず添えること
3. 推論で補えること: 法規の一般原則・物理法則・規定の目的からの推論を「推論」ラベル付きで提示してよい。裏取りのない断定はしない"""

    return f"""\
あなたは所蔵文書を参照する調べ物係です。
利用者は分野を往来する実務家です。「分野が違うので分かりません」は最も言ってはならない言葉です。

{scope_text}

{style_instruction}

{structure_rules}

禁止事項（違反は回答失敗と同等）:
- 謝罪表現（「申し訳ありません」「ご不便をおかけします」等）の使用
- 「無関係」「管轄外」等の断定（→「所蔵文書に特段の規定がない」に言い換える）
- 全面拒否（所蔵に根拠がある部分は必ず回答し、ない部分だけを不足として明示する）
- 「専門家にご相談ください」の丸投げ（→参照先の名指しと調査の手がかりを渡す）
- もっともらしい条番号・数値での穴埋め（根拠のない条番号を推測で記載しない）
- 質問の前提が誤り（規定が存在しない）場合は前提を訂正すること

出力形式（二部形式）:
まず回答本文（Markdown可）をそのまま出力すること。
次に必ず以下の区切り行を置き、引用IDのみをJSONで続けること。

<!-- CITATIONS -->
{{"cited_chunk_ids": ["chunk_id_1", "chunk_id_2"]}}"""

_ADVISOR_SYSTEM_BASE = """\
あなたは所蔵文書検索の行き詰まり判断アドバイザーです。
実行ループの難航を裁定する役であり、「この所蔵文書群を持つ調べ物係」として機能します。

以下の情報を受け取ります:
- 質問
- プランナーの計画（あれば）
- 実行ループのトレース要約
- これまでに収集したチャンク（chunk_id・見出し・本文抜粋）
- 現在のスコープ内文書一覧

次のいずれかを裁定してください:
(a) replan: まだ試していない検索軸があり、新クエリを提示して実行ループを続行する
(b) conclude: 所蔵からの追加取得は見込み薄と判断し、収集済み素材で結論の編纂に移る

「守備範囲外」という概念は存在しません。所蔵文書に規定がないことは検索後にのみ判断できます。
conclude を選ぶ場合は「所蔵に不足していると思われる規範領域」の所見を必ず一〜二文で添えてください。
その後の回答はコンポーザーが収集済み素材から三部構成で生成します。

判断基準:
- replan: まだ試していない検索軸（異なるキーワード・別の文書・別の章）がある場合
- conclude: これ以上検索しても新しいチャンクが得られる見込みが薄い場合

出力（JSONのみ。他のテキストは出力しないこと）:
再計画の場合:
{"decision": "replan", "reason": "裁定の理由（一文）", "new_queries": ["クエリ1", "クエリ2"]}

収束の場合:
{"decision": "conclude", "reason": "裁定の理由（一文）", "missing_coverage": "不足していると思われる規範領域の所見（一〜二文）"}\
"""

_STYLE_INSTRUCTIONS = {
    "brief": "回答は結論と根拠条番号のみを一〜二文で述べること。",
    "standard": "結論と根拠条文の要点を含む標準的な説明で回答すること。",
    "detailed": "引用付きの詳細な解説で回答し、関連条文への言及も含めること。",
}

_CITATIONS_MARKER = "<!-- CITATIONS -->"
_CITATIONS_MARKER_LEN = len(_CITATIONS_MARKER)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_relevant_domains(plan_text: str) -> list[str] | None:
    """Extract relevant_domains JSON list from planner output. Returns None on failure."""
    m = re.search(r"relevant_domains:\s*(\[.*?\])", plan_text)
    if not m:
        return None
    try:
        domains = json.loads(m.group(1))
        if isinstance(domains, list) and all(isinstance(d, str) for d in domains):
            return domains
    except Exception:
        pass
    return None


def _dispatch(
    name: str, input_: dict, top_k_default: int,
    doc_ids: list | None = None, domains: list[str] | None = None,
) -> object:
    if name == "search_chunks":
        if "top_k" not in input_:
            input_ = {**input_, "top_k": top_k_default}
        return search_chunks(**input_, doc_ids=doc_ids, domains=domains)
    if name == "read_section":
        return read_section(**input_)
    return f"[不明なツール: {name}]"


def _cached_search(
    inp: dict, top_k_default: int, cache: dict,
    doc_ids: list | None = None, domains: list[str] | None = None,
) -> list:
    query = inp.get("query", "")
    k = inp.get("top_k", top_k_default)
    doc_ids_key = tuple(sorted(doc_ids)) if doc_ids else None
    domains_key = tuple(sorted(domains)) if domains else None
    key = (query, k, doc_ids_key, domains_key)
    if key in cache:
        return cache[key]
    if "top_k" not in inp:
        inp = {**inp, "top_k": top_k_default}
    result = search_chunks(**inp, doc_ids=doc_ids, domains=domains)
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

def _run_planner(
    question: str, config: AgentConfig,
    scope_text: str = "", user_domains: list[str] | None = None,
) -> tuple:
    """Returns (plan_text, debug)."""
    t0 = time.perf_counter()
    client = make_client(config.planner_model)
    system = _build_planner_system(scope_text, user_domains)
    resp = client.chat([{"role": "user", "text": question}], [], system)
    elapsed = time.perf_counter() - t0
    return resp.text or "", {
        "model": config.planner_model,
        "usage": resp.usage,
        "time_s": round(elapsed, 2),
        "raw_response": resp.text,
        "thinking": resp.thinking,
    }


_CHUNK_BODY_LIMIT = 120
_ADVISOR_CHUNK_TOTAL_LIMIT = 8000


def _format_chunks_for_advisor(chunks: list) -> str:
    """chunk_id + heading + 本文先頭120字。合計8000字超の場合は超過分をID+見出しのみに落とす。"""
    if not chunks:
        return "（なし）"

    def full_entry(c: dict) -> str:
        heading = c.get("heading", "")
        body_preview = (c.get("body") or "")[:_CHUNK_BODY_LIMIT]
        return (
            f"[{c['chunk_id']}] 階層: {c.get('hierarchy', '')} "
            f"/ 見出し: {heading} / 本文: {body_preview}"
        )

    def short_entry(c: dict) -> str:
        return f"[{c['chunk_id']}] 階層: {c.get('hierarchy', '')} / 見出し: {c.get('heading', '')}"

    lines = []
    total_chars = 0
    for c in chunks:
        entry = full_entry(c)
        if total_chars + len(entry) <= _ADVISOR_CHUNK_TOTAL_LIMIT:
            lines.append(entry)
            total_chars += len(entry)
        else:
            lines.append(short_entry(c))
    return "\n".join(lines)


def _run_advisor(
    question: str, plan: str | None, trace: list, all_chunks: list, config: AgentConfig,
    scope_text: str = "",
) -> tuple:
    """Returns (result_dict, debug). result_dict has keys: decision, reason, new_queries/missing_coverage."""
    t0 = time.perf_counter()
    client = make_client(config.advisor_model)

    trace_summary = _summarize_trace(trace)
    chunks_text = _format_chunks_for_advisor(all_chunks)

    advisor_system = _ADVISOR_SYSTEM_BASE
    if scope_text:
        advisor_system = f"{scope_text}\n\n{_ADVISOR_SYSTEM_BASE}"

    user_text = (
        f"質問: {question}\n\n"
        f"プランナーの計画:\n{plan or 'なし'}\n\n"
        f"実行ループトレース:\n{trace_summary}\n\n"
        f"収集チャンク（{len(all_chunks)}件）:\n{chunks_text}"
    )
    input_size = len(advisor_system) + len(user_text)
    logger.info("advisor input size: %d chars", input_size)
    resp = client.chat([{"role": "user", "text": user_text}], [], advisor_system)
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
        # 旧 out_of_scope 裁定をフォールバックで conclude に変換（後方互換）
        if result.get("decision") == "out_of_scope":
            result["decision"] = "conclude"
            result.setdefault("missing_coverage", "（旧out_of_scope裁定を変換）")
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
    scope_text: str = "",
    domains: list[str] | None = None,
) -> tuple:
    """
    Returns (trace, all_chunks, retrieved, debug, max_loops_hit, early_stop).
    advisor_state: mutable dict with keys fired/result/debug — updated if advisor fires here.
    """
    t0 = time.perf_counter()
    total_usage = {"input_tokens": 0, "output_tokens": 0}
    doc_ids = config.selected_doc_ids  # None = all, [] = none, list = filter

    plan_section = (
        f"検索計画（プランナーより）:\n{plan}\n\n上記の計画に従って素材を収集してください。\n"
        if plan else ""
    )
    system = _build_loop_system(plan_section, scope_text)
    client = make_client(config.loop_model)

    messages = [{"role": "user", "text": question}]
    trace = []
    retrieved: list = []
    all_chunks: list = []
    seen_ids: set = set()
    query_cache: dict = {}
    max_loops_hit = True
    early_stop = False
    budget_stop = False
    consecutive_empty = 0
    total_search_calls = 0

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
                    ex.submit(_cached_search, tc.input, config.top_k, query_cache, doc_ids, domains): tc
                    for tc in search_tcs
                }
                for future in as_completed(future_to_tc):
                    tc = future_to_tc[future]
                    tc_results[tc.id] = future.result()
        elif search_tcs:
            tc = search_tcs[0]
            tc_results[tc.id] = _cached_search(tc.input, config.top_k, query_cache, doc_ids, domains)

        for tc in other_tcs:
            tc_results[tc.id] = _dispatch(tc.name, tc.input, config.top_k, doc_ids, domains)

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

        # ── 予算到達: アドバイザーなしで即打ち切り（W-4） ─────────────────────
        stall_threshold = config.advisor_k
        search_budget = int(config.max_loops * 0.6)
        if total_search_calls >= search_budget and not advisor_state["fired"]:
            budget_stop = True
            trace.append({
                "loop": loop_num + 1,
                "budget_stop": True,
                "tool_calls": [],
                "thinking": None,
            })
            logger.info("budget_stop triggered at loop %d (total_search_calls=%d >= %d)",
                        loop_num + 1, total_search_calls, search_budget)
            break

        # ── Mid-loop advisor: 難航検知（連続空振りのみ） ─────────────────────
        stall_hit = consecutive_empty >= stall_threshold
        if (
            not advisor_state["fired"]
            and config.advisor_trigger_stall
            and stall_hit
        ):
            logger.info("advisor firing: stall detected at loop %d", loop_num + 1)
            adv_result, adv_debug = _run_advisor(
                question, plan, trace, all_chunks, config, scope_text
            )
            advisor_state["fired"] = True
            advisor_state["result"] = adv_result
            advisor_state["debug"] = adv_debug

            trace.append({
                "loop": loop_num + 1,
                "advisor": True,
                "decision": adv_result.get("decision", ""),
                "reason": adv_result.get("reason", ""),
                "new_queries": adv_result.get("new_queries", []),
                "missing_coverage": adv_result.get("missing_coverage", ""),
                "tool_calls": [],
                "thinking": None,
            })

            if adv_result.get("decision") == "conclude":
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
        "loops": len([s for s in trace if not s.get("advisor") and not s.get("early_stop") and not s.get("budget_stop")]),
        "max_loops_hit": max_loops_hit,
        "early_stop": early_stop,
        "budget_stop": budget_stop,
    }, max_loops_hit, early_stop


def _build_composer_user_msg(
    question: str, chunks_text: str, advisor_conclude_reason: str | None = None,
    advisor_missing_coverage: str | None = None,
    valid_chunk_ids: list[str] | None = None,
) -> str:
    if valid_chunk_ids:
        id_list = "\n".join(f"- {cid}" for cid in valid_chunk_ids)
        citation_guard = (
            f"\n【引用可能なチャンクIDの一覧（これ以外のIDを角括弧・鍵括弧いずれの形式でも引用しないこと）】\n{id_list}\n"
        )
    else:
        citation_guard = (
            "\n【注意: 取得チャンク0件】架空のチャンクID・文書名・条番号を引用形式（[...]・【...】）で一切記載しないこと。\n"
        )

    if advisor_conclude_reason:
        note = f"アドバイザー所見: {advisor_conclude_reason}"
        if advisor_missing_coverage:
            note += f"（不足領域: {advisor_missing_coverage}）"
        return (
            f"質問: {question}\n\n{note}\n"
            "収集済み素材から言えることを回答し、不足は三部構成の形式で明示すること。\n"
            f"{citation_guard}\n--- 収集した条文素材 ---\n{chunks_text}"
        )
    return f"質問: {question}\n{citation_guard}\n--- 収集した条文素材 ---\n{chunks_text}"


_COMPOSER_FALLBACK_MSG = "回答の生成に失敗しました。同じ質問をもう一度お試しください。"


def _run_composer(
    question: str, all_chunks: list, config: AgentConfig,
    advisor_conclude_reason: str | None = None, scope_text: str = "",
    advisor_missing_coverage: str | None = None,
) -> tuple:
    """Returns (answer, cited_chunk_ids, raw_output, debug)."""
    t0 = time.perf_counter()
    client = make_client(config.composer_model)

    style_instr = _STYLE_INSTRUCTIONS.get(config.answer_style, _STYLE_INSTRUCTIONS["standard"])
    zero_result = not all_chunks
    system = _build_composer_system(style_instr, scope_text, zero_result_mode=zero_result)

    chunks_text = _format_chunks_for_composer(all_chunks) if all_chunks else "（検索結果なし）"
    valid_ids = [c["chunk_id"] for c in all_chunks] if all_chunks else []
    user_msg = _build_composer_user_msg(
        question, chunks_text, advisor_conclude_reason, advisor_missing_coverage,
        valid_chunk_ids=valid_ids,
    )

    resp = client.chat([{"role": "user", "text": user_msg}], [], system)

    raw = resp.text or ""
    parsed = _parse_composer_output(raw)
    answer = parsed.get("answer", raw)
    cited_ids = parsed.get("cited_chunk_ids", [])
    if not isinstance(cited_ids, list):
        cited_ids = []

    # W-1: 空答リトライ（1回）
    composer_retry = False
    combined_usage = resp.usage
    if not answer.strip():
        logger.warning("composer: empty answer — retrying once (composer_retry=True)")
        composer_retry = True
        resp2 = client.chat([{"role": "user", "text": user_msg}], [], system)
        raw2 = resp2.text or ""
        parsed2 = _parse_composer_output(raw2)
        answer = parsed2.get("answer", raw2)
        cited_ids = parsed2.get("cited_chunk_ids", [])
        if not isinstance(cited_ids, list):
            cited_ids = []
        combined_usage = {
            "input_tokens": resp.usage.get("input_tokens", 0) + resp2.usage.get("input_tokens", 0),
            "output_tokens": resp.usage.get("output_tokens", 0) + resp2.usage.get("output_tokens", 0),
        }
        if not answer.strip():
            logger.warning("composer: retry also empty — returning fallback message")
            answer = _COMPOSER_FALLBACK_MSG
            cited_ids = []

    elapsed = time.perf_counter() - t0

    return answer, cited_ids, raw, {
        "model": config.composer_model,
        "usage": combined_usage,
        "time_s": round(elapsed, 2),
        "raw_response": raw,
        "thinking": resp.thinking,
        "composer_retry": composer_retry,
    }


# ── Public streaming API ──────────────────────────────────────────────────────

def make_composer_stream(
    question: str,
    all_chunks: list,
    config: AgentConfig,
    advisor_conclude_reason: str | None = None,
    scope_text: str = "",
    advisor_missing_coverage: str | None = None,
):
    """
    Returns (display_generator, get_result_fn).
    Exhaust the generator first (e.g., via st.write_stream), then call get_result_fn().
    get_result_fn() returns (answer, cited_ids, raw, debug).
    """
    t0 = time.perf_counter()
    client = make_client(config.composer_model)

    style_instr = _STYLE_INSTRUCTIONS.get(config.answer_style, _STYLE_INSTRUCTIONS["standard"])
    zero_result = not all_chunks
    system = _build_composer_system(style_instr, scope_text, zero_result_mode=zero_result)

    chunks_text = _format_chunks_for_composer(all_chunks) if all_chunks else "（検索結果なし）"
    valid_ids = [c["chunk_id"] for c in all_chunks] if all_chunks else []
    user_msg = _build_composer_user_msg(
        question, chunks_text, advisor_conclude_reason, advisor_missing_coverage,
        valid_chunk_ids=valid_ids,
    )

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
        parsed = _parse_composer_output(raw)
        answer = parsed.get("answer", raw)
        cited_ids = parsed.get("cited_chunk_ids", [])
        if not isinstance(cited_ids, list):
            cited_ids = []

        # W-1: 空答リトライ（1回）
        composer_retry = False
        combined_usage = dict(usage_holder)
        if not answer.strip():
            logger.warning("composer(stream): empty answer — retrying once (composer_retry=True)")
            composer_retry = True
            resp2 = client.chat([{"role": "user", "text": user_msg}], [], system)
            raw2 = resp2.text or ""
            parsed2 = _parse_composer_output(raw2)
            answer = parsed2.get("answer", raw2)
            cited_ids = parsed2.get("cited_chunk_ids", [])
            if not isinstance(cited_ids, list):
                cited_ids = []
            combined_usage = {
                "input_tokens": usage_holder.get("input_tokens", 0) + resp2.usage.get("input_tokens", 0),
                "output_tokens": usage_holder.get("output_tokens", 0) + resp2.usage.get("output_tokens", 0),
            }
            if not answer.strip():
                logger.warning("composer(stream): retry also empty — returning fallback message")
                answer = _COMPOSER_FALLBACK_MSG
                cited_ids = []

        elapsed = time.perf_counter() - t0
        return answer, cited_ids, raw, {
            "model": config.composer_model,
            "usage": combined_usage,
            "time_s": round(elapsed, 2),
            "raw_response": raw,
            "thinking": None,
            "composer_retry": composer_retry,
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

    scope_text = _build_scope_docs_text(config)
    planner_output: str | None = None
    planner_debug: dict = {}

    user_domains = config.selected_domains  # None = all

    # ── Planner ───────────────────────────────────────────────────────────────
    if config.planner_enabled:
        planner_output, planner_debug = _run_planner(question, config, scope_text, user_domains)
        logger.info("planner: %s", (planner_output or "")[:200])

    # ── Domain narrowing (R-10) — disabled M5b-5 ────────────────────────────
    effective_domains = user_domains
    # プランナー由来のdomain自動絞り込みは廃止（M5b-5 発注者裁定）。
    # UIの手動選択（user_domains）は引き続き有効。
    # _parse_relevant_domains() は残置（将来の再有効化に備える）。
    logger.info("R-10 disabled (M5b-5): effective_domains=%s", effective_domains)

    # ── Execution loop ────────────────────────────────────────────────────────
    advisor_state = {"fired": False, "result": None, "debug": {}}
    trace, all_chunks, retrieved, loop_debug, max_loops_hit, early_stop = _run_loop(
        question, planner_output, config, advisor_state, scope_text, effective_domains
    )

    # ── Post-loop advisor: 未決着 ─────────────────────────────────────────────
    if not advisor_state["fired"] and config.advisor_trigger_unresolved and max_loops_hit:
        logger.info("advisor firing: post-loop unresolved")
        adv_result, adv_debug = _run_advisor(
            question, planner_output, trace, all_chunks, config, scope_text
        )
        advisor_state["fired"] = True
        advisor_state["result"] = adv_result
        advisor_state["debug"] = adv_debug
        trace.append({
            "loop": "post",
            "advisor": True,
            "decision": adv_result.get("decision", ""),
            "reason": adv_result.get("reason", ""),
            "new_queries": adv_result.get("new_queries", []),
            "missing_coverage": adv_result.get("missing_coverage", ""),
            "tool_calls": [],
            "thinking": None,
        })

    # アドバイザー conclude 時の所見をコンポーザーへ渡す
    advisor_result = advisor_state.get("result") or {}
    advisor_conclude_reason: str | None = None
    advisor_missing_coverage: str | None = None
    if advisor_result.get("decision") == "conclude":
        advisor_conclude_reason = advisor_result.get("reason", "")
        advisor_missing_coverage = advisor_result.get("missing_coverage", "")

    # Domain filter trace
    domain_filter_trace = None
    if user_domains is not None:
        domain_filter_trace = {
            "action": "domain_filter",
            "user_selected": user_domains,
            "planner_narrowed": planner_domains,
            "effective": effective_domains,
        }

    return {
        "question": question,
        "planner_output": planner_output,
        "trace": trace,
        "retrieved": retrieved,
        "all_chunks": all_chunks,
        "advisor_conclude_reason": advisor_conclude_reason,
        "advisor_missing_coverage": advisor_missing_coverage,
        "advisor_state": advisor_state,
        "scope_text": scope_text,
        "scope_doc_count": len(load_documents_yaml()) if config.selected_doc_ids is None
            else len([d for d in load_documents_yaml() if d.get("id") in (config.selected_doc_ids or [])]),
        "domain_filter": domain_filter_trace,
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
        question, pre["all_chunks"], config,
        advisor_conclude_reason=pre.get("advisor_conclude_reason"),
        scope_text=pre.get("scope_text", ""),
        advisor_missing_coverage=pre.get("advisor_missing_coverage"),
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
        elif step.get("budget_stop"):
            print(f"  💰 予算到達打ち切り")
        else:
            for tc in step["tool_calls"]:
                args_preview = json.dumps(tc["input"], ensure_ascii=False)[:80]
                print(f"  loop{step['loop']}: {tc['name']}({args_preview})")


if __name__ == "__main__":
    main()
