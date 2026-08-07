"""
Batch evaluation: runs all questions in eval/questions.jsonl through the agent.

Output:
    eval/results.jsonl   question, expected_source, retrieved, answer, verdict (blank)
    eval/traces.jsonl    per-question agent traces

Usage:
    python eval/run_eval.py
"""
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent import run

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

QUESTIONS_FILE = Path("eval/questions.jsonl")
RESULTS_FILE = Path("eval/results.jsonl")
TRACES_FILE = Path("eval/traces.jsonl")


def main():
    questions = []
    with open(QUESTIONS_FILE, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                questions.append(json.loads(line))

    results = []
    traces = []

    for i, q in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] {q['question'][:60]}...")
        result = run(q["question"])
        record = {
            "question": q["question"],
            "expected_source": q["expected_source"],
            "retrieved": result["retrieved"],
            "answer": result["answer"],
            "verdict": "",
        }
        results.append(record)
        traces.append({"question": q["question"], "trace": result["trace"]})
        print(f"  → retrieved: {result['retrieved'][:3]}, loops: {len(result['trace'])}")

    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with open(TRACES_FILE, "w", encoding="utf-8") as f:
        for t in traces:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")

    print(f"\n完了: {len(results)} 問 → {RESULTS_FILE}")


if __name__ == "__main__":
    main()
