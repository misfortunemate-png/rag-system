"""
MCP Server for rag-system — stdio transport, three-layer tools.

Material: list_documents / search_chunks / read_section
Agent:    submit_question / get_answer
Feedback: report_feedback

Concurrency guard (P-9): max 1 running, queue 2 waiting.
Cost guards: per-job cap (MCP_JOB_COST_CAP, default $0.10),
             daily cap   (MCP_DAILY_COST_CAP, default $1.00).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ── CWD = project root (parent of this file's src/ directory) ────────────────
_PROJECT_ROOT = Path(__file__).parent.parent
os.chdir(_PROJECT_ROOT)

# ── .env ──────────────────────────────────────────────────────────────────────
from dotenv import load_dotenv  # noqa: E402
load_dotenv()

from mcp.server.mcpserver import MCPServer  # noqa: E402

mcp = MCPServer("rag-system")

# ── Guards ────────────────────────────────────────────────────────────────────

JOB_COST_CAP = float(os.environ.get("MCP_JOB_COST_CAP", "0.10"))
DAILY_COST_CAP = float(os.environ.get("MCP_DAILY_COST_CAP", "1.00"))

# ── Paths ─────────────────────────────────────────────────────────────────────

LOGS_DIR = _PROJECT_ROOT / "logs"
FEEDBACK_INBOX = _PROJECT_ROOT / "data" / "feedback" / "inbox.jsonl"

# ── Cost logging ──────────────────────────────────────────────────────────────

_log_lock = threading.Lock()


def _log(event: str, **fields) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    log_path = LOGS_DIR / f"{today}.log"
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
    with _log_lock:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _daily_cost() -> float:
    today = datetime.now().strftime("%Y-%m-%d")
    log_path = LOGS_DIR / f"{today}.log"
    if not log_path.exists():
        return 0.0
    total = 0.0
    with _log_lock:
        with open(log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("event") == "job_done":
                        total += entry.get("cost_usd") or 0.0
                except Exception:
                    pass
    return total

# ── Job store ─────────────────────────────────────────────────────────────────

_jobs: dict = {}
_jobs_lock = threading.Lock()
_done_ids: list = []       # ordered list of completed job_ids
MAX_DONE_JOBS = 20

# Concurrency: max 1 running, queue 2 waiting
_pending_lock = threading.Lock()
_pending_count = 0
MAX_PENDING = 3            # 1 running + 2 queued
_exec_semaphore = threading.Semaphore(1)


def _job_set(job_id: str, **kwargs) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)


def _job_mark_done(job_id: str) -> None:
    with _jobs_lock:
        _done_ids.append(job_id)
        while len(_done_ids) > MAX_DONE_JOBS:
            old_id = _done_ids.pop(0)
            _jobs.pop(old_id, None)

# ── Background worker ─────────────────────────────────────────────────────────


def _run_job(job_id: str, question: str, style: str, domains: list[str] | None = None) -> None:
    global _pending_count

    _exec_semaphore.acquire()
    try:
        _job_set(job_id, status="running", started_at=time.time())
        t0 = time.perf_counter()

        from src.agent import run as agent_run
        from src.config import load_config, estimate_cost

        config = load_config()
        config.answer_style = style
        if domains is not None:
            config.selected_domains = domains

        _log("job_submitted", job_id=job_id, question=question[:200], style=style, domains=domains)

        result = agent_run(question, config)
        elapsed = round(time.perf_counter() - t0, 2)

        # Accumulate per-stage usage & cost
        debug = result.get("debug", {})
        stage_summary = {}
        total_cost = 0.0
        for stage in ("planner", "loop", "composer", "advisor"):
            sdata = debug.get(stage, {})
            usage = sdata.get("usage", {})
            in_t = usage.get("input_tokens", 0)
            out_t = usage.get("output_tokens", 0)
            model = sdata.get("model", "")
            cost = estimate_cost(model, in_t, out_t) or 0.0
            total_cost += cost
            stage_summary[stage] = {
                "model": model,
                "input_tokens": in_t,
                "output_tokens": out_t,
                "cost_usd": round(cost, 6),
            }

        # Per-job cost cap (checked after execution since pipeline is not interruptible)
        if total_cost > JOB_COST_CAP:
            _job_set(job_id, status="error", reason="cost_cap_exceeded")
            _log(
                "job_error",
                job_id=job_id,
                reason="cost_cap_exceeded",
                cost_usd=round(total_cost, 6),
                elapsed_s=elapsed,
            )
            return

        total_in = sum(s["input_tokens"] for s in stage_summary.values())
        total_out = sum(s["output_tokens"] for s in stage_summary.values())
        loops = len([
            s for s in result.get("trace", [])
            if not s.get("advisor") and not s.get("early_stop")
        ])

        job_result = {
            "answer": result.get("answer", ""),
            "cited_chunk_ids": result.get("cited_chunk_ids", []),
            "cited_chunks": result.get("cited_chunks", []),
            "meta": {
                "loops": loops,
                "elapsed_s": elapsed,
                "cost_usd": round(total_cost, 6),
                "stages": stage_summary,
            },
        }

        _job_set(job_id, status="done", result=job_result, elapsed_s=elapsed)
        _job_mark_done(job_id)

        _log(
            "job_done",
            job_id=job_id,
            model=config.loop_model,
            usage={"input_tokens": total_in, "output_tokens": total_out},
            cost_usd=round(total_cost, 6),
            elapsed_s=elapsed,
            loops=loops,
            stages=stage_summary,
        )

    except Exception as exc:
        _job_set(job_id, status="error", reason=str(exc))
        _log("job_error", job_id=job_id, reason=str(exc)[:500])

    finally:
        _exec_semaphore.release()
        with _pending_lock:
            _pending_count -= 1

# ── Material layer ────────────────────────────────────────────────────────────


@mcp.tool()
def list_documents() -> list:
    """documents.yamlのアクティブ文書一覧を返す。id・title・domain・tags・profileを含む。"""
    from src.config import load_documents_yaml
    docs = load_documents_yaml()
    return [
        {
            "id": d.get("id", ""),
            "title": d.get("title", ""),
            "domain": d.get("domain", ""),
            "tags": d.get("tags") or [],
            "profile": d.get("profile", ""),
        }
        for d in docs
        if d.get("status") == "active"
    ]


@mcp.tool()
def search_chunks(query: str, top_k: int = 5, domains: list[str] | None = None) -> list:
    """条文テキストをハイブリッド検索（密ベクトル＋BM25＋リランキング）し関連チャンクを返す。domainsで検索対象分野を指定可能（例: ["消防","法令"]）。"""
    from src.tools import search_chunks as _search
    from src.config import load_config
    config = load_config()
    return _search(query=query, top_k=top_k, doc_ids=config.selected_doc_ids, domains=domains)


@mcp.tool()
def read_section(doc_slug: str, hierarchy: str) -> str:
    """条番号または階層パスで条文全文を返す。hierarchyには '1.7.3' のような条番号を指定する。"""
    from src.tools import read_section as _read
    return _read(doc_slug=doc_slug, hierarchy=hierarchy)

@mcp.tool()
def web_search_tool(query: str, num_results: int = 3) -> list[dict]:
    """Webを検索し、格付け付きの結果を返す（tag/verified/category付き）。"""
    from src.web_search import web_search
    from src.web_fetch import fetch_and_extract
    from src.config import load_config

    config = load_config()
    search_results = web_search(query, num_results=num_results, backend=config.web_search_backend)
    results = []
    for sr in search_results:
        url = sr.get("url", "")
        if not url:
            continue
        fetched = fetch_and_extract(url)
        results.append({
            "url": url,
            "title": fetched.get("title") or sr.get("title", ""),
            "snippet": sr.get("snippet", ""),
            "tier": fetched["tier"],
            "tier_label": fetched["tier_label"],
            "tag": fetched.get("tag"),
            "verified": fetched.get("verified"),
            "category": fetched.get("category"),
            "text": fetched.get("text", ""),
        })
    return results


@mcp.tool()
def fetch_law(law_id: str) -> dict:
    """e-Gov法令APIから法令条文を取得する。law_idはe-Gov法令API v1の法令ID（例: 325AC0000000201）。"""
    from src.web_fetch import fetch_law_text
    return fetch_law_text(law_id)


# ── Agent layer ───────────────────────────────────────────────────────────────


@mcp.tool()
def submit_question(question: str, style: str = "standard", domains: list[str] | None = None) -> dict:
    """
    質問をサブミットしjob_idを即時返却する。
    style: brief / standard / detailed。
    domains: 検索対象分野のリスト（例: ["消防","法令"]）。省略で全分野対象。
    get_answerでジョブ状態をポーリングする。
    同時実行1・待機キュー2。超過時はerrorを返す。
    """
    global _pending_count

    # Daily cap check
    daily = _daily_cost()
    if daily >= DAILY_COST_CAP:
        return {
            "error": "daily_cost_cap_exceeded",
            "daily_cost_usd": round(daily, 4),
            "cap_usd": DAILY_COST_CAP,
            "message": f"本日のコスト上限 ${DAILY_COST_CAP} に達しました。翌日0時以降に再試行してください。",
        }

    # Concurrency gate
    with _pending_lock:
        if _pending_count >= MAX_PENDING:
            return {
                "error": "queue_full",
                "message": (
                    f"実行中1件＋待機{_pending_count - 1}件で上限（待機{MAX_PENDING - 1}件）に達しています。"
                    "しばらく後に再試行してください。"
                ),
            }
        _pending_count += 1

    style = style if style in ("brief", "standard", "detailed") else "standard"
    job_id = str(uuid.uuid4())

    with _jobs_lock:
        _jobs[job_id] = {
            "status": "queued",
            "question": question,
            "style": style,
            "domains": domains,
            "submitted_at": time.time(),
        }

    t = threading.Thread(target=_run_job, args=(job_id, question, style, domains), daemon=True)
    t.start()

    return {"job_id": job_id}


@mcp.tool()
def get_answer(job_id: str) -> dict:
    """ジョブ状態を返す。status: running / done / error / not_found。"""
    with _jobs_lock:
        job = _jobs.get(job_id)

    if job is None:
        return {"status": "not_found", "job_id": job_id}

    status = job["status"]

    if status in ("queued", "running"):
        elapsed = round(time.time() - job.get("submitted_at", time.time()), 1)
        return {"status": "running", "job_id": job_id, "elapsed_s": elapsed}

    if status == "done":
        res = job.get("result", {})
        return {
            "status": "done",
            "job_id": job_id,
            "answer": res.get("answer", ""),
            "cited_chunk_ids": res.get("cited_chunk_ids", []),
            "cited_chunks": res.get("cited_chunks", []),
            "meta": res.get("meta", {}),
        }

    return {"status": status, "job_id": job_id, "reason": job.get("reason", "")}

# ── Feedback layer ────────────────────────────────────────────────────────────


@mcp.tool()
def report_feedback(job_id: str, verdict: str, correction: str = "", evidence: str = "") -> dict:
    """
    フィードバックを受信箱に記録する（自動反映なし）。
    verdict: correct / incorrect / incomplete。
    """
    valid_verdicts = {"correct", "incorrect", "incomplete"}
    if verdict not in valid_verdicts:
        return {"error": "invalid_verdict", "valid": sorted(valid_verdicts)}

    with _jobs_lock:
        job = _jobs.get(job_id)
    question = job.get("question", "") if job else ""

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source_client": "mcp",
        "job_id": job_id,
        "question": question,
        "verdict": verdict,
        "correction": correction,
        "evidence": evidence,
    }

    FEEDBACK_INBOX.parent.mkdir(parents=True, exist_ok=True)
    with open(FEEDBACK_INBOX, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    _log("feedback_received", job_id=job_id, verdict=verdict)
    return {"accepted": True, "job_id": job_id}

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    mcp.run(transport="stdio")
