"""
M5b-3: クロスドメインevalスクリプト
eval/questions_crossdomain.jsonl を実行し、doc_recall / retrieval_doc_recall を集計する。

Usage:
    python eval/run_crossdomain_eval.py [--dry-run]
"""
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.chdir(Path(__file__).parent.parent)

from dotenv import load_dotenv
load_dotenv()

from src.agent import run
from src.config import load_config, estimate_cost

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

QUESTIONS_FILE = Path("eval/questions_crossdomain.jsonl")
RESULTS_DIR = Path("eval/crossdomain_results")

# B部で「守備範囲外」宣言を検出するキーワード
BOUNDARY_KEYWORDS = [
    "守備範囲外", "根拠不足", "確認が必要", "根拠なし",
    "規定がない", "規定は見当たりません", "記載がない",
    "コーパス外", "スコープ外", "確認する必要",
]


def slug_of(chunk_id: str) -> str:
    """chunk_id から doc_slug を抽出。
    例: kaishu-denki-r7-0097 -> kaishu-denki-r7
        law-91b-168          -> law-91b
    """
    # 末尾の -数字 を除去
    m = re.match(r"^(.*?)-(\d+(?:-\d+)?)$", chunk_id)
    if m:
        return m.group(1)
    return chunk_id


def compute_doc_metrics(
    expected_docs: list[str],
    retrieved_chunk_ids: list[str],
    cited_chunk_ids: list[str],
) -> dict:
    """doc_recall と retrieval_doc_recall を計算。"""
    retrieved_slugs = {slug_of(cid) for cid in retrieved_chunk_ids}
    cited_slugs = {slug_of(cid) for cid in cited_chunk_ids}

    retrieval_hit = [d for d in expected_docs if d in retrieved_slugs]
    citation_hit = [d for d in expected_docs if d in cited_slugs]

    retrieval_miss = [d for d in expected_docs if d not in retrieved_slugs]
    citation_miss = [d for d in expected_docs if d not in cited_slugs]

    n = len(expected_docs)
    return {
        "retrieval_doc_recall": round(len(retrieval_hit) / n, 4) if n else 0.0,
        "doc_recall": round(len(citation_hit) / n, 4) if n else 0.0,
        "retrieval_hit": retrieval_hit,
        "retrieval_miss": retrieval_miss,
        "citation_hit": citation_hit,
        "citation_miss": citation_miss,
    }


def detect_boundary_keywords(answer: str) -> list[str]:
    return [kw for kw in BOUNDARY_KEYWORDS if kw in answer]


_TOP_K_OVERRIDE: int | None = None


def _slim_trace(trace: list) -> list:
    """トレースからthinkingとhitのbodyを除去し、query・hits件数のみ保持。"""
    slim = []
    for t in trace:
        entry = {k: v for k, v in t.items() if k != "thinking"}
        if "tool_calls" in entry:
            entry["tool_calls"] = [
                {
                    "name": tc["name"],
                    "input": tc["input"],
                    "hits": len(tc["output"]) if isinstance(tc.get("output"), list) else None,
                }
                for tc in entry["tool_calls"]
            ]
        slim.append(entry)
    return slim


def run_question(q: dict) -> dict:
    qid = q["id"]
    question = q["question"]
    expected_docs = q["expected_docs"]
    part = q["part"]

    print(f"\n[{qid}/{part}] {question[:70]}...")
    t0 = time.perf_counter()

    config = load_config()
    config.selected_domains = None  # フィルタなし
    if _TOP_K_OVERRIDE is not None:
        config.top_k = _TOP_K_OVERRIDE
    result = run(question, config)

    elapsed = round(time.perf_counter() - t0, 1)

    # トークン・コスト
    loop_usage = result["debug"].get("loop", {}).get("usage", {})
    planner_usage = result["debug"].get("planner", {}).get("usage", {})
    composer_usage = result["debug"].get("composer", {}).get("usage", {})

    total_in = (
        loop_usage.get("input_tokens", 0)
        + planner_usage.get("input_tokens", 0)
        + composer_usage.get("input_tokens", 0)
    )
    total_out = (
        loop_usage.get("output_tokens", 0)
        + planner_usage.get("output_tokens", 0)
        + composer_usage.get("output_tokens", 0)
    )
    model = config.loop_model
    cost_usd = estimate_cost(model, total_in, total_out)

    # メトリクス計算
    metrics = compute_doc_metrics(
        expected_docs,
        result["retrieved"],
        result["cited_chunk_ids"],
    )

    # B部用キーワード検出
    boundary_detected = detect_boundary_keywords(result["answer"])

    record = {
        "id": qid,
        "part": part,
        "question": question,
        "expected_docs": expected_docs,
        **metrics,
        "retrieved_chunk_ids": result["retrieved"],
        "cited_chunk_ids": result["cited_chunk_ids"],
        "answer": result["answer"],
        "planner_output": result.get("planner_output"),
        "loops": len(result["trace"]),
        "trace": _slim_trace(result.get("trace", [])),
        "elapsed_s": elapsed,
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "cost_usd": round(cost_usd, 6) if cost_usd is not None else None,
        "boundary_keywords_detected": boundary_detected,
    }

    if part == "B":
        record["boundary_observation"] = {
            "boundary_keywords_detected": boundary_detected,
            "has_boundary_declaration": len(boundary_detected) > 0,
            "expected_docs_cited": metrics["citation_hit"],
            "note": "最終判定はPMが回答全文を読んで行う",
        }

    print(f"  retrieval_doc_recall={metrics['retrieval_doc_recall']:.2f}  "
          f"doc_recall={metrics['doc_recall']:.2f}  "
          f"loops={len(result['trace'])}  {elapsed}s")
    if metrics["retrieval_miss"]:
        print(f"  retrieval_miss: {metrics['retrieval_miss']}")
    if metrics["citation_miss"]:
        print(f"  citation_miss:  {metrics['citation_miss']}")

    return record


def main():
    import argparse
    import json as _json
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="最初の1問だけ実行")
    parser.add_argument("--no-rerank", action="store_true",
                        help="リランカーを無効化して実行（CPU環境での速度改善）")
    parser.add_argument("--top-k", type=int, default=None, help="search top_k を上書き（例: --top-k 10）")
    parser.add_argument("--tag", default="", help="結果ディレクトリのサフィックス（例: --tag topk10）")
    args = parser.parse_args()

    settings_path = Path("settings.json")
    original_rerank = None
    original_top_k = None

    s = _json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}

    if args.no_rerank:
        original_rerank = s.get("rerank_enabled", True)
        s["rerank_enabled"] = False
        print("rerank_enabled -> False (--no-rerank)")

    if args.top_k is not None:
        global _TOP_K_OVERRIDE
        _TOP_K_OVERRIDE = args.top_k
        print(f"top_k override -> {args.top_k} (in-process, not written to settings.json)")

    if args.no_rerank:
        settings_path.write_text(_json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")

    global RESULTS_DIR
    if args.tag:
        RESULTS_DIR = Path(f"eval/crossdomain_results_{args.tag}")

    questions = [
        json.loads(l)
        for l in QUESTIONS_FILE.read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    if args.dry_run:
        questions = questions[:1]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    all_records = []
    total_cost = 0.0

    try:
        for q in questions:
            try:
                record = run_question(q)
            except Exception as e:
                print(f"  ERROR: {e}")
                record = {
                    "id": q["id"], "part": q["part"], "question": q["question"],
                    "expected_docs": q["expected_docs"], "error": str(e),
                }

            out_file = RESULTS_DIR / f"{q['id']}_result.json"
            out_file.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

            all_records.append(record)
            if record.get("cost_usd"):
                total_cost += record["cost_usd"]

        # A部集計
        a_records = [r for r in all_records if r.get("part") == "A" and "error" not in r]
        b_records = [r for r in all_records if r.get("part") == "B"]

        print("\n\n====== A部 集計 ======")
        avg_retrieval = 0.0
        avg_doc = 0.0
        if a_records:
            avg_retrieval = round(sum(r["retrieval_doc_recall"] for r in a_records) / len(a_records), 4)
            avg_doc = round(sum(r["doc_recall"] for r in a_records) / len(a_records), 4)
            print(f"問数: {len(a_records)}")
            print(f"avg retrieval_doc_recall: {avg_retrieval}")
            print(f"avg doc_recall:           {avg_doc}")
            print("\n問ごとの詳細:")
            for r in a_records:
                print(f"  [{r['id']}] ret={r['retrieval_doc_recall']:.2f}  cit={r['doc_recall']:.2f}  "
                      f"miss_ret={r.get('retrieval_miss',[])}  miss_cit={r.get('citation_miss',[])}")

        print("\n====== B部 観察 ======")
        for r in b_records:
            bkw = r.get("boundary_keywords_detected", [])
            print(f"  [{r['id']}] boundary_declared={len(bkw)>0}  keywords={bkw}")

        print(f"\n====== コスト合計 ======")
        print(f"合計コスト: ${total_cost:.4f} USD")

        summary = {
            "a_questions": len(a_records),
            "avg_retrieval_doc_recall": avg_retrieval if a_records else None,
            "avg_doc_recall": avg_doc if a_records else None,
            "a_detail": [
                {
                    "id": r["id"],
                    "retrieval_doc_recall": r["retrieval_doc_recall"],
                    "doc_recall": r["doc_recall"],
                    "retrieval_miss": r.get("retrieval_miss", []),
                    "citation_miss": r.get("citation_miss", []),
                } for r in a_records
            ],
            "b_observations": [
                {
                    "id": r["id"],
                    "boundary_keywords_detected": r.get("boundary_keywords_detected", []),
                    "has_boundary_declaration": len(r.get("boundary_keywords_detected", [])) > 0,
                } for r in b_records
            ],
            "total_cost_usd": round(total_cost, 4),
        }

        summary_file = RESULTS_DIR / "summary.json"
        summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n-> {summary_file} に保存")

    finally:
        restore = {}
        if original_rerank is not None:
            restore["rerank_enabled"] = original_rerank
        if restore:
            s = _json.loads(settings_path.read_text(encoding="utf-8"))
            s.update(restore)
            settings_path.write_text(_json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"settings restored: {restore}")


if __name__ == "__main__":
    main()
