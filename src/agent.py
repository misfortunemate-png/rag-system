"""
Agent: tool-use loop for answering questions about construction specifications.

Usage (CLI):
    python src/agent.py "質問文"

Environment variables (see src/llm.py):
    LLM_PROVIDER    openrouter (default) | anthropic
    LLM_MODEL       model ID override
    OPENROUTER_API_KEY | ANTHROPIC_API_KEY
"""
import json
import logging
import sys

from src.llm import make_client
from src.tools import TOOLS, read_section, search_chunks

logger = logging.getLogger(__name__)

MAX_LOOPS = 10

_SYSTEM_PROMPT = """\
あなたは公共建築工事標準仕様書（電気設備工事編）の専門アシスタントです。
与えられたツールを使って条文を検索・精読し、根拠付きで回答してください。

回答ルール:
- 出典の章番号・条番号（例: 1.3.1）を必ず明示すること
- 参照条文に根拠が見当たらない場合は「該当なし」と答えること
- 根拠のない推測や補足を加えないこと
- 検索結果の refs に参照先がある場合、回答に必要であれば read_section で参照先を精読すること\
"""


def _dispatch(name: str, input_: dict):
    if name == "search_chunks":
        return search_chunks(**input_)
    if name == "read_section":
        return read_section(**input_)
    return f"[不明なツール: {name}]"


def run(question: str) -> dict:
    """
    Run the agent loop for a single question.

    Returns dict with keys:
        question   original question
        answer     final text answer
        trace      list of {loop, tool_calls: [{name, input, output}]}
        retrieved  chunk_ids from all search_chunks calls (in order)
    """
    client = make_client()
    messages = [{"role": "user", "text": question}]
    trace = []
    retrieved: list[str] = []

    for loop_num in range(MAX_LOOPS):
        response = client.chat(messages, TOOLS, _SYSTEM_PROMPT)

        if not response.tool_calls:
            return {
                "question": question,
                "answer": response.text or "",
                "trace": trace,
                "retrieved": retrieved,
            }

        tool_call_records = []
        tool_results = []

        for tc in response.tool_calls:
            result = _dispatch(tc.name, tc.input)
            result_str = (
                json.dumps(result, ensure_ascii=False)
                if not isinstance(result, str)
                else result
            )
            tool_call_records.append({"name": tc.name, "input": tc.input, "output": result})
            tool_results.append({"id": tc.id, "name": tc.name, "content": result_str})

            if tc.name == "search_chunks" and isinstance(result, list):
                for hit in result:
                    cid = hit.get("chunk_id", "")
                    if cid and cid not in retrieved:
                        retrieved.append(cid)

        trace.append({"loop": loop_num + 1, "tool_calls": tool_call_records})
        logger.info(
            "loop %d: %d tool call(s): %s",
            loop_num + 1,
            len(response.tool_calls),
            [tc.name for tc in response.tool_calls],
        )

        messages.append(
            {
                "role": "assistant",
                "text": response.text,
                "tool_calls": [
                    {"id": tc.id, "name": tc.name, "input": tc.input}
                    for tc in response.tool_calls
                ],
            }
        )
        messages.append({"role": "tool_results", "results": tool_results})

    return {
        "question": question,
        "answer": "[最大ループ数（10）に到達しました]",
        "trace": trace,
        "retrieved": retrieved,
    }


def main():
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    if len(sys.argv) < 2:
        print("Usage: python src/agent.py \"質問文\"", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]
    result = run(question)

    print(f"\n【質問】{result['question']}")
    print(f"\n【出典chunk_id】{', '.join(result['retrieved'])}")
    print(f"\n【回答】\n{result['answer']}")
    print(f"\n【トレース】{len(result['trace'])} ループ")
    for step in result["trace"]:
        for tc in step["tool_calls"]:
            args_preview = json.dumps(tc["input"], ensure_ascii=False)[:80]
            print(f"  loop{step['loop']}: {tc['name']}({args_preview})")


if __name__ == "__main__":
    main()
