"""
Query: search Chroma with ruri-v3-310m, then generate answer via Claude API.

Usage:
    python -m src.query "分電盤の保護等級は屋内形と屋外形でそれぞれ何か？"
    python -m src.query --k 5 "質問文"

Returns retrieved chunks + LLM answer with mandatory source citation.
"""
import argparse
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

CHROMA_DIR = Path("data/chroma")
COLLECTION_NAME = "kitei_spec"
MODEL_NAME = "cl-nagoya/ruri-v3-310m"
CLAUDE_MODEL = "claude-sonnet-4-6"

# Query-side prefix for ruri-v3-310m.
# Source: cl-nagoya/ruri-v3-310m HuggingFace model card (verified 2026-08-04).
QUERY_PREFIX = "クエリ: "

_SYSTEM_PROMPT = """\
あなたは公共建築工事標準仕様書（電気設備工事編）の専門アシスタントです。
与えられた参照条文のみを根拠に回答してください。
- 回答には必ず出典の章番号・条番号（例: 1.3.1）を明示すること。
- 参照条文に根拠が見当たらない場合は「該当なし」と答えること。
- 根拠のない推測や補足を加えないこと。\
"""


def _load_model():
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL_NAME)
    return model


def _search(model, query: str, k: int = 3) -> list[dict]:
    import chromadb
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    col = client.get_collection(COLLECTION_NAME)

    vec = model.encode([QUERY_PREFIX + query], normalize_embeddings=True).tolist()[0]
    results = col.query(query_embeddings=[vec], n_results=k, include=["documents", "metadatas"])

    hits = []
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    for doc, meta in zip(docs, metas):
        hits.append({"document": doc, "metadata": meta})
    return hits


def _build_context(hits: list[dict]) -> str:
    parts = []
    for i, h in enumerate(hits, 1):
        meta = h["metadata"]
        parts.append(
            f"【参照{i}】{meta.get('hierarchy', '')}（p.{meta.get('pages', '?')}）\n{h['document']}"
        )
    return "\n\n".join(parts)


def _generate(query: str, context: str) -> str:
    import anthropic
    client = anthropic.Anthropic()
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"以下の参照条文を元に質問に答えてください。\n\n{context}\n\n質問: {query}",
            }
        ],
    )
    return message.content[0].text


def query(question: str, k: int = 3) -> dict:
    """
    Returns dict with keys: question, retrieved (list of chunk_id), answer.
    """
    model = _load_model()
    hits = _search(model, question, k=k)
    retrieved = [h["metadata"].get("chunk_id", "") for h in hits]
    context = _build_context(hits)
    answer = _generate(question, context)
    return {"question": question, "retrieved": retrieved, "answer": answer}


def main():
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Query the RAG system")
    parser.add_argument("question", help="質問文")
    parser.add_argument("--k", type=int, default=3, help="検索件数")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    result = query(args.question, k=args.k)
    print(f"\n【質問】{result['question']}")
    print(f"\n【出典chunk_id】{', '.join(result['retrieved'])}")
    print(f"\n【回答】\n{result['answer']}")


if __name__ == "__main__":
    main()
