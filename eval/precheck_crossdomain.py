"""
手順1: クロスドメインevalの事前検分スクリプト
各問の質問でsearch_chunks(hybrid top_k=20)を実行し、
expected_docsがヒットするか確認する。
"""
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.chdir(Path(__file__).parent.parent)

from dotenv import load_dotenv
load_dotenv()

import json as _json

# Temporarily disable reranker for speed
settings_path = Path("settings.json")
settings = _json.loads(settings_path.read_text(encoding="utf-8"))
original_rerank = settings.get("rerank_enabled", True)
settings["rerank_enabled"] = False
settings_path.write_text(_json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
print("rerank_enabled -> False (pre-check)")

try:
    from src.tools import search_chunks

    questions_path = Path("eval/questions_crossdomain.jsonl")
    questions = [json.loads(l) for l in questions_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    results = []
    for q in questions:
        qid = q["id"]
        question = q["question"]
        expected_docs = q["expected_docs"]
        print(f"\n[{qid}] {question[:60]}...")

        hits = search_chunks(query=question, top_k=20)
        hit_slugs = set()
        for h in hits:
            cid = h.get("chunk_id", "")
            for slug in expected_docs:
                if cid.startswith(slug):
                    hit_slugs.add(slug)

        found = [d for d in expected_docs if d in hit_slugs]
        missing = [d for d in expected_docs if d not in hit_slugs]

        print(f"  found:   {found}")
        print(f"  missing: {missing}")
        print(f"  hit chunk_ids: {[h['chunk_id'] for h in hits[:5]]}")

        results.append({
            "id": qid,
            "part": q["part"],
            "expected_docs": expected_docs,
            "found_in_top20": found,
            "missing_from_top20": missing,
            "all_hit": len(missing) == 0,
        })

    print("\n\n====== 事前検分結果サマリ ======")
    for r in results:
        status = "OK" if r["all_hit"] else "MISS"
        print(f"[{r['id']}] {status}  found={r['found_in_top20']}  missing={r['missing_from_top20']}")

    # Save results
    out_path = Path("eval/precheck_results.json")
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {out_path} に保存")

finally:
    settings["rerank_enabled"] = original_rerank
    settings_path.write_text(_json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    print("rerank_enabled -> restored")
