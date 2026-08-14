"""
Retrieval evaluation: recall@k and MRR across three search configurations.

Usage:
    python eval/run_retrieval_eval.py --mode dense
    python eval/run_retrieval_eval.py --mode hybrid
    python eval/run_retrieval_eval.py --mode full
    python eval/run_retrieval_eval.py --mode all

Modes:
    dense:  Chroma dense vector only (rerank off, BM25 skipped)
    hybrid: dense + BM25 (RRF fusion, rerank off)
    full:   dense + BM25 + RRF + reranking
    all:    run all three modes sequentially

Input:  eval/questions_m5b.jsonl
Output: eval/retrieval_results.jsonl
"""
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.chdir(Path(__file__).parent.parent)

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

QUESTIONS_PATH = Path("eval/questions_m5b.jsonl")
RESULTS_PATH = Path("eval/retrieval_results.jsonl")


def _load_questions() -> list[dict]:
    if not QUESTIONS_PATH.exists():
        print(f"Error: {QUESTIONS_PATH} not found.", file=sys.stderr)
        sys.exit(1)
    qs = []
    with open(QUESTIONS_PATH, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                qs.append(json.loads(line))
    return qs


def _run_search(query: str, top_k: int, mode: str) -> list[dict]:
    """Run search_chunks with mode-specific settings."""
    from src.tools import search_chunks, _get_bm25_data, BM25_INDEX_PATH

    original_settings = Path("settings.json")
    settings_data = {}
    if original_settings.exists():
        settings_data = json.loads(original_settings.read_text(encoding="utf-8"))

    if mode == "dense":
        settings_data["rerank_enabled"] = False
        original_settings.write_text(json.dumps(settings_data, ensure_ascii=False, indent=2), encoding="utf-8")
        # Force BM25 to not be used by temporarily hiding it
        import src.tools as tools_mod
        saved_bm25 = tools_mod._bm25_data
        tools_mod._bm25_data = "SKIP"  # sentinel to skip
        try:
            # Monkey-patch _get_bm25_data to return None for dense mode
            original_get_bm25 = tools_mod._get_bm25_data
            tools_mod._get_bm25_data = lambda: None
            result = search_chunks(query=query, top_k=top_k)
        finally:
            tools_mod._get_bm25_data = original_get_bm25
            tools_mod._bm25_data = saved_bm25
            settings_data["rerank_enabled"] = True
            original_settings.write_text(json.dumps(settings_data, ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    elif mode == "hybrid":
        settings_data["rerank_enabled"] = False
        original_settings.write_text(json.dumps(settings_data, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            result = search_chunks(query=query, top_k=top_k)
        finally:
            settings_data["rerank_enabled"] = True
            original_settings.write_text(json.dumps(settings_data, ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    else:  # full
        settings_data["rerank_enabled"] = True
        original_settings.write_text(json.dumps(settings_data, ensure_ascii=False, indent=2), encoding="utf-8")
        return search_chunks(query=query, top_k=top_k)


def _evaluate(questions: list[dict], mode: str, top_ks: list[int]) -> dict:
    max_k = max(top_ks)
    results_per_q = []

    for q in questions:
        query = q["question"]
        expected_slugs = q.get("expected_chunks", [])

        t0 = time.perf_counter()
        hits = _run_search(query, max_k, mode)
        elapsed = time.perf_counter() - t0

        hit_ids = [h["chunk_id"] for h in hits]
        hit_slugs = []
        for cid in hit_ids:
            parts = cid.split("-")
            for i in range(len(parts) - 1, 0, -1):
                if parts[i].isdigit() and len(parts[i]) >= 4:
                    hit_slugs.append("-".join(parts[:i]))
                    break
            else:
                hit_slugs.append(cid)

        recall_at = {}
        for k_val in top_ks:
            top_slugs = set(hit_slugs[:k_val])
            found = sum(1 for s in expected_slugs if s in top_slugs)
            recall_at[k_val] = found / len(expected_slugs) if expected_slugs else 0.0

        rr = 0.0
        for rank, slug in enumerate(hit_slugs, 1):
            if slug in expected_slugs:
                rr = 1.0 / rank
                break

        results_per_q.append({
            "question": query,
            "expected_domain": q.get("expected_domain", ""),
            "expected_chunks": expected_slugs,
            "retrieved_ids": hit_ids[:max_k],
            "recall": recall_at,
            "rr": rr,
            "elapsed_s": round(elapsed, 3),
        })

    # Aggregate
    n = len(results_per_q)
    avg_recall = {}
    for k_val in top_ks:
        avg_recall[k_val] = sum(r["recall"][k_val] for r in results_per_q) / n if n else 0.0

    mrr = sum(r["rr"] for r in results_per_q) / n if n else 0.0

    return {
        "mode": mode,
        "n_questions": n,
        "recall": {f"@{k}": round(v, 4) for k, v in avg_recall.items()},
        "mrr": round(mrr, 4),
        "per_question": results_per_q,
    }


def main():
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Retrieval evaluation")
    parser.add_argument(
        "--mode",
        choices=["dense", "hybrid", "full", "all"],
        default="full",
        help="Search configuration to evaluate",
    )
    args = parser.parse_args()

    questions = _load_questions()
    top_ks = [5, 10, 20]

    modes = ["dense", "hybrid", "full"] if args.mode == "all" else [args.mode]

    all_results = []
    for mode in modes:
        print(f"\n{'='*60}")
        print(f"Mode: {mode}")
        print(f"{'='*60}")

        result = _evaluate(questions, mode, top_ks)
        all_results.append(result)

        print(f"  Questions: {result['n_questions']}")
        for k_label, val in result["recall"].items():
            print(f"  Recall{k_label}: {val:.4f}")
        print(f"  MRR:       {result['mrr']:.4f}")

        for qr in result["per_question"]:
            status = "HIT" if qr["rr"] > 0 else "MISS"
            print(f"  [{status}] {qr['question'][:50]}  rr={qr['rr']:.2f}  recall@5={qr['recall'][5]:.2f}")

    # Save results
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        for r in all_results:
            summary = {
                "mode": r["mode"],
                "n_questions": r["n_questions"],
                "recall": r["recall"],
                "mrr": r["mrr"],
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            f.write(json.dumps(summary, ensure_ascii=False) + "\n")

    print(f"\nResults saved to {RESULTS_PATH}")

    # Comparison table if all modes
    if len(all_results) > 1:
        print(f"\n{'='*60}")
        print("Comparison")
        print(f"{'Mode':<10} {'R@5':>8} {'R@10':>8} {'R@20':>8} {'MRR':>8}")
        print(f"{'-'*10} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
        for r in all_results:
            print(
                f"{r['mode']:<10} "
                f"{r['recall'].get('@5', 0):>8.4f} "
                f"{r['recall'].get('@10', 0):>8.4f} "
                f"{r['recall'].get('@20', 0):>8.4f} "
                f"{r['mrr']:>8.4f}"
            )


if __name__ == "__main__":
    main()
