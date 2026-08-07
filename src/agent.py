"""
Agent: three-role tool-use loop for construction spec QA.

Architecture (M3):
  Planner (optional) → Execution Loop → Composer

run(question, config) → dict with keys:
  question, answer, trace, retrieved,
  cited_chunk_ids, cited_chunks, all_chunks,
  invalid_citations, planner_output, debug
"""
import json
import logging
import time
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
質問タイプ: [可否確認/数値確認/手順確認/比較確認/その他]
ターゲット: [答えが記載されているであろう表・条番号（例: 表1.1.1「電線類」、2.2.3）]
クエリ1: [検索文字列]
クエリ2: [必要なら]
クエリ3: [必要なら]

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
- 回答で引用した素材のchunk_idをcited_chunk_idsに列挙すること

出力形式（JSON のみ。他のテキストは出力しないこと）:
{{
  "answer": "回答本文（Markdown可）",
  "cited_chunk_ids": ["chunk_id_1", "chunk_id_2"]
}}\
"""

_STYLE_INSTRUCTIONS = {
    "brief": "回答は結論と根拠条番号のみを一〜二文で述べること。",
    "standard": "結論と根拠条文の要点を含む標準的な説明で回答すること。",
    "detailed": "引用付きの詳細な解説で回答し、関連条文への言及も含めること。",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _dispatch(name: str, input_: dict, top_k_default: int) -> object:
    if name == "search_chunks":
        if "top_k" not in input_:
            input_ = {**input_, "top_k": top_k_default}
        return search_chunks(**input_)
    if name == "read_section":
        return read_section(**input_)
    return f"[不明なツール: {name}]"


def _format_chunks_for_composer(chunks: list) -> str:
    lines = []
    for c in chunks:
        lines.append(f"[chunk_id: {c['chunk_id']}]")
        lines.append(f"階層: {c['hierarchy']}")
        lines.append(f"{c.get('heading', '')}\n{c.get('body', '')}")
        lines.append("---")
    return "\n".join(lines)


def _parse_composer_output(text: str) -> dict:
    """Parse JSON from composer. Falls back to full text if parse fails."""
    if not text:
        return {"answer": "", "cited_chunk_ids": []}
    try:
        s = text.strip()
        # Strip markdown code fences if present
        if "```" in s:
            parts = s.split("```")
            for part in parts:
                p = part.lstrip("json").strip()
                if p.startswith("{"):
                    s = p
                    break
        return json.loads(s)
    except Exception:
        return {"answer": text, "cited_chunk_ids": []}


# ── Three roles ───────────────────────────────────────────────────────────────

def _run_planner(question: str, config: AgentConfig) -> tuple:
    """Returns (plan_text: str, debug: dict)"""
    t0 = time.perf_counter()
    client = make_client(config.planner_model)
    resp = client.chat([{"role": "user", "text": question}], [], _PLANNER_SYSTEM)
    elapsed = time.perf_counter() - t0
    return resp.text or "", {
        "model": config.planner_model,
        "usage": resp.usage,
        "time_s": round(elapsed, 2),
        "raw_response": resp.text,
    }


def _run_loop(question: str, plan: str | None, config: AgentConfig) -> tuple:
    """Returns (trace, all_chunks, retrieved_ids, debug, max_loops_hit)"""
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
    max_loops_hit = True

    for loop_num in range(config.max_loops):
        response = client.chat(messages, TOOLS, system)
        total_usage["input_tokens"] += response.usage.get("input_tokens", 0)
        total_usage["output_tokens"] += response.usage.get("output_tokens", 0)

        if not response.tool_calls:
            max_loops_hit = False
            break

        tool_call_records = []
        tool_results = []

        for tc in response.tool_calls:
            result = _dispatch(tc.name, tc.input, config.top_k)
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

        trace.append({"loop": loop_num + 1, "tool_calls": tool_call_records})
        logger.info(
            "loop %d: %s",
            loop_num + 1,
            [tc.name for tc in response.tool_calls],
        )
        messages.append({
            "role": "assistant",
            "text": response.text,
            "tool_calls": [
                {"id": tc.id, "name": tc.name, "input": tc.input}
                for tc in response.tool_calls
            ],
        })
        messages.append({"role": "tool_results", "results": tool_results})

    elapsed = time.perf_counter() - t0
    return trace, all_chunks, retrieved, {
        "model": config.loop_model,
        "usage": total_usage,
        "time_s": round(elapsed, 2),
        "loops": len(trace),
        "max_loops_hit": max_loops_hit,
    }, max_loops_hit


def _run_composer(question: str, all_chunks: list, config: AgentConfig) -> tuple:
    """Returns (answer, cited_chunk_ids, raw_output, debug)"""
    t0 = time.perf_counter()
    client = make_client(config.composer_model)

    style_instr = _STYLE_INSTRUCTIONS.get(config.answer_style, _STYLE_INSTRUCTIONS["standard"])
    system = _COMPOSER_SYSTEM_TEMPLATE.format(style_instruction=style_instr)

    chunks_text = _format_chunks_for_composer(all_chunks) if all_chunks else "（検索結果なし）"
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
    }


# ── Main entry ────────────────────────────────────────────────────────────────

def run(question: str, config: AgentConfig | None = None) -> dict:
    """
    Run the three-role agent loop.

    Returns dict with keys:
        question, answer, trace, retrieved,
        cited_chunk_ids, cited_chunks, all_chunks,
        invalid_citations, planner_output, debug
    """
    if config is None:
        config = AgentConfig()

    planner_output: str | None = None
    planner_debug: dict = {}

    # ── Planner ───────────────────────────────────────────────────────────────
    if config.planner_enabled:
        planner_output, planner_debug = _run_planner(question, config)
        logger.info("planner: %s", (planner_output or "")[:200])

    # ── Execution loop ────────────────────────────────────────────────────────
    trace, all_chunks, retrieved, loop_debug, max_loops_hit = _run_loop(
        question, planner_output, config
    )

    # ── Composer ──────────────────────────────────────────────────────────────
    answer, cited_ids, raw_composer, composer_debug = _run_composer(
        question, all_chunks, config
    )

    # ── Deterministic citation verification ───────────────────────────────────
    retrieved_set = {c["chunk_id"] for c in all_chunks}
    valid_cited = [cid for cid in cited_ids if cid in retrieved_set]
    invalid_citations = [cid for cid in cited_ids if cid not in retrieved_set]
    cited_chunks = [c for c in all_chunks if c["chunk_id"] in set(valid_cited)]

    if invalid_citations:
        logger.warning("invalid_citations discarded: %s", invalid_citations)

    return {
        "question": question,
        "answer": answer,
        "trace": trace,
        "retrieved": retrieved,
        "cited_chunk_ids": valid_cited,
        "cited_chunks": cited_chunks,
        "all_chunks": all_chunks,
        "invalid_citations": invalid_citations,
        "planner_output": planner_output,
        "debug": {
            "app_version": APP_VERSION,
            "config": asdict(config),
            "planner": planner_debug,
            "loop": loop_debug,
            "composer": composer_debug,
            "raw_composer_output": raw_composer,
            "max_loops_hit": max_loops_hit,
        },
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
        for tc in step["tool_calls"]:
            args_preview = json.dumps(tc["input"], ensure_ascii=False)[:80]
            print(f"  loop{step['loop']}: {tc['name']}({args_preview})")


if __name__ == "__main__":
    main()
