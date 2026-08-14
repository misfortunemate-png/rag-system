"""
Contextualizer: prepend a short context sentence to each chunk.

Two modes:
  deterministic — jouban (spec) and law chunks: hierarchy-based, no LLM call.
  llm           — generic chunks: DeepSeek V4 Flash via OpenRouter.
"""
import logging
import os
import time

logger = logging.getLogger(__name__)

CONTEXT_MODEL = "deepseek/deepseek-v4-flash"
_MAX_NEIGHBOR_CHARS = 500


def _deterministic_context(chunk: dict, doc_title: str) -> str:
    hierarchy = chunk.get("hierarchy", "")
    heading = chunk.get("heading", "")
    parts = [doc_title]
    if hierarchy:
        parts.append(hierarchy)
    return "。".join(parts)


def _build_contextualized_text(context: str, chunk: dict) -> str:
    heading = chunk.get("heading", "")
    body = chunk.get("body", "")
    return context + "\n" + heading + "\n" + body


def _make_llm_client():
    from openai import OpenAI
    return OpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url="https://openrouter.ai/api/v1",
    )


def _llm_context_single(
    oai_client, chunk_text: str, doc_title: str,
    prev_text: str, next_text: str,
) -> str:
    prompt = (
        f'以下は「{doc_title}」の一部です。'
        f'このテキストが文書内でどのような内容に位置づけられるか、50〜100字の日本語1文で説明してください。'
        f'説明のみを出力し、他の文言は含めないでください。\n\n'
        f'前のチャンク: {prev_text[:_MAX_NEIGHBOR_CHARS]}\n---\n'
        f'対象チャンク: {chunk_text}\n---\n'
        f'次のチャンク: {next_text[:_MAX_NEIGHBOR_CHARS]}'
    )
    try:
        resp = oai_client.chat.completions.create(
            model=CONTEXT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            extra_body={"reasoning": {"enabled": False}},
        )
        text = (resp.choices[0].message.content or "").strip()
        if text:
            return text
    except Exception as e:
        logger.warning("LLM context failed: %s", e)
    return doc_title


def contextualize(
    chunks: list[dict],
    doc_title: str,
    doc_type: str,
) -> list[dict]:
    """Add context and contextualized_text to each chunk. Returns modified chunks."""
    det_count = 0
    llm_count = 0
    llm_fail = 0
    client = None

    needs_llm = doc_type == "generic"
    if needs_llm:
        try:
            client = _make_llm_client()
        except Exception as e:
            logger.warning("Cannot init LLM client, falling back to title-only: %s", e)
            client = None

    for i, chunk in enumerate(chunks):
        if doc_type in ("spec", "law"):
            ctx = _deterministic_context(chunk, doc_title)
            det_count += 1
        elif client is not None:
            chunk_text = chunk.get("heading", "") + "\n" + chunk.get("body", "")
            prev_text = (chunks[i - 1].get("heading", "") + "\n" + chunks[i - 1].get("body", "")) if i > 0 else ""
            next_text = (chunks[i + 1].get("heading", "") + "\n" + chunks[i + 1].get("body", "")) if i < len(chunks) - 1 else ""
            ctx = _llm_context_single(client, chunk_text, doc_title, prev_text, next_text)
            if ctx == doc_title:
                llm_fail += 1
            llm_count += 1
        else:
            ctx = doc_title
            llm_fail += 1
            llm_count += 1

        chunk["context"] = ctx
        chunk["contextualized_text"] = _build_contextualized_text(ctx, chunk)

    logger.info(
        "contextualize: %d deterministic, %d LLM (%d fallback) for '%s'",
        det_count, llm_count, llm_fail, doc_title,
    )
    return chunks
