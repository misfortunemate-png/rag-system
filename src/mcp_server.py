"""
MCP Server for rag-system — stdio + SSE HTTP transport, three-layer tools.

Material: list_documents / search_chunks / read_section
Agent:    submit_question / get_answer
Feedback: report_feedback
Web:      web_search_tool / fetch_law

Transport:
  stdio (default): Claude Code ローカル利用
  sse:             HTTP SSE — Tailscale Funnel経由で公開。Bearer認証必須。

Concurrency guard (P-9): max 1 running, queue 2 waiting.
Cost guards: per-job cap (MCP_JOB_COST_CAP, default $0.10),
             daily cap   (MCP_DAILY_COST_CAP, default $1.00).
"""
from __future__ import annotations

import collections
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

logger = logging.getLogger(__name__)

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
    query = query[:500]
    config = load_config()
    return _search(query=query, top_k=top_k, doc_ids=config.selected_doc_ids, domains=domains)


@mcp.tool()
def read_section(doc_slug: str, hierarchy: str) -> str:
    """条番号または階層パスで条文全文を返す。hierarchyには '1.7.3' のような条番号を指定する。"""
    from src.tools import read_section as _read
    from src.config import load_documents_yaml
    known_slugs = {d.get("id", "") for d in load_documents_yaml()}
    if doc_slug not in known_slugs:
        return f"エラー: doc_slug {doc_slug!r} はdocuments.yamlに存在しません。"
    return _read(doc_slug=doc_slug, hierarchy=hierarchy)

@mcp.tool()
def web_search_tool(query: str, num_results: int = 3) -> list[dict]:
    """Webを検索し、格付け付きの結果を返す（tag/verified/category付き）。"""
    from src.web_search import web_search
    from src.web_fetch import fetch_and_extract
    from src.config import load_config

    query = query[:500]
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

    question = question[:2000]

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

    correction = correction[:5000]
    evidence = evidence[:2000]

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

# ── HTTP SSE transport: auth / rate limiting ──────────────────────────────────

# Rate limiting / brute-force state (module-level, guarded by _sec_lock)
_sec_lock = threading.Lock()
_rate_counters: dict[str, collections.deque] = {}   # IP -> deque of request timestamps
_bf_failures: dict[str, collections.deque] = {}     # IP -> deque of failure timestamps
_bf_blocks: dict[str, float] = {}                   # IP -> block-until epoch time

# Auth token lookup: {token -> id}  (populated at startup, read-only after that)
_AUTH_TOKENS: dict[str, str] = {}
# Reverse map: {id -> token}  (for OAuth client_secret / access_token issuance)
_AUTH_TOKENS_BY_ID: dict[str, str] = {}


def _load_auth_tokens() -> dict[str, str]:
    """Load data/auth_tokens.yaml. Returns {token -> id} map."""
    import yaml
    from datetime import date as _date

    path = _PROJECT_ROOT / "data" / "auth_tokens.yaml"
    if not path.exists():
        raise FileNotFoundError(
            "data/auth_tokens.yaml が見つかりません。"
            "data/auth_tokens.yaml.example を参考にセットアップしてください。"
        )

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("tokens", [])
    if not entries:
        raise ValueError("data/auth_tokens.yaml にトークンが定義されていません。")

    today = _date.today()
    result: dict[str, str] = {}
    for entry in entries:
        tid = str(entry.get("id", "")).strip()
        token = str(entry.get("token", "")).strip()
        expires_str = entry.get("expires")
        if not tid or not token:
            continue
        if expires_str:
            expires = _date.fromisoformat(str(expires_str))
            if today > expires:
                logger.info("auth: token id=%r expired (%s), skipping", tid, expires_str)
                continue
        result[token] = tid

    if not result:
        raise ValueError(
            "data/auth_tokens.yaml に有効なトークンがありません（全期限切れの可能性）。"
        )

    return result


def _load_auth_tokens_by_id() -> dict[str, str]:
    """Load data/auth_tokens.yaml. Returns {id -> token} map (valid non-expired entries only)."""
    import yaml
    from datetime import date as _date

    path = _PROJECT_ROOT / "data" / "auth_tokens.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("tokens", [])
    today = _date.today()
    result: dict[str, str] = {}
    for entry in entries:
        tid = str(entry.get("id", "")).strip()
        token = str(entry.get("token", "")).strip()
        expires_str = entry.get("expires")
        if not tid or not token:
            continue
        if expires_str:
            expires = _date.fromisoformat(str(expires_str))
            if today > expires:
                continue
        result[tid] = token
    return result


class _AuthRateLimitMiddleware:
    """ASGI middleware: rate limit → brute-force block → Bearer auth.

    Thread-safe rate counters are shared across all requests.
    auth failure → asyncio.sleep(3) to slow brute-force.
    """

    RATE_LIMIT = 10      # max requests per IP per minute
    RATE_WINDOW = 60.0
    BF_LIMIT = 5         # failures before temp block
    BF_WINDOW = 60.0
    BF_BLOCK_DURATION = 600.0   # 10 minutes

    def __init__(self, app, tokens: dict[str, str]) -> None:
        self.app = app
        self.tokens = tokens

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return

        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Extract client IP
        client = scope.get("client")
        ip = client[0] if client else "unknown"

        # 1. Brute-force block check
        now = time.monotonic()
        with _sec_lock:
            block_until = _bf_blocks.get(ip, 0.0)
        if now < block_until:
            remaining = int(block_until - now)
            _log("bf_blocked_request", ip=ip, remaining_s=remaining)
            await self._send_error(send, 403, f"Blocked for {remaining}s")
            return

        # 2. Rate limit check
        with _sec_lock:
            q = _rate_counters.setdefault(ip, collections.deque())
            cutoff = now - self.RATE_WINDOW
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self.RATE_LIMIT:
                _log("rate_limit_exceeded", ip=ip, count=len(q))
                await self._send_error(send, 429, "Too Many Requests")
                return
            q.append(now)

        # 3. Token check (Bearer header or URL query parameter)
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        auth_bytes: bytes = headers.get(b"authorization", b"")
        auth_str = auth_bytes.decode("utf-8", errors="replace")
        token = ""
        if auth_str.startswith("Bearer "):
            token = auth_str[len("Bearer "):].strip()
        if not token:
            # Fallback: ?token= query parameter (for claude.ai connector)
            qs = scope.get("query_string", b"").decode("utf-8", errors="replace")
            for part in qs.split("&"):
                if part.startswith("token="):
                    token = part[len("token="):]
                    break

        auth_id = self.tokens.get(token)
        if not auth_id:
            import asyncio
            await asyncio.sleep(3)
            with _sec_lock:
                fq = _bf_failures.setdefault(ip, collections.deque())
                cutoff = now - self.BF_WINDOW
                while fq and fq[0] < cutoff:
                    fq.popleft()
                fq.append(now)
                if len(fq) >= self.BF_LIMIT:
                    block_until = time.monotonic() + self.BF_BLOCK_DURATION
                    _bf_blocks[ip] = block_until
                    _log("bf_block_set", ip=ip, duration_s=self.BF_BLOCK_DURATION)
            _log("auth_failure", ip=ip)
            await self._send_error(send, 401, "Unauthorized")
            return

        # 4. Success — attach auth_id to scope for downstream logging
        ext = scope.setdefault("extensions", {})
        ext["auth_id"] = auth_id
        _log("auth_success", ip=ip, auth_id=auth_id)

        await self.app(scope, receive, send)

    @staticmethod
    async def _send_error(send, status: int, message: str) -> None:
        body = message.encode()
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body, "more_body": False})


# ── OAuth 2.1 minimal endpoints ──────────────────────────────────────────────

# In-memory OAuth state (cleared on restart; claude.ai re-registers automatically)
_oauth_lock = threading.Lock()
_oauth_clients: dict[str, dict] = {}   # client_id -> {client_secret, redirect_uris}
_oauth_codes: dict[str, dict] = {}     # code -> {client_id, redirect_uri, code_challenge, expires_at}

# Public URL used in metadata (read from MCP_PUBLIC_URL env var at SSE startup)
_MCP_PUBLIC_URL = ""


def _pkce_verify(verifier: str, challenge: str) -> bool:
    """Verify PKCE S256: SHA256(verifier) base64url-encoded == challenge."""
    import hashlib
    import base64
    digest = hashlib.sha256(verifier.encode()).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return computed == challenge


async def _oauth_metadata(request):
    """GET /.well-known/oauth-authorization-server"""
    from starlette.responses import JSONResponse
    base = _MCP_PUBLIC_URL
    return JSONResponse({
        "issuer": base,
        "authorization_endpoint": f"{base}/authorize",
        "token_endpoint": f"{base}/token",
        "registration_endpoint": f"{base}/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
        "code_challenge_methods_supported": ["S256"],
    })


async def _oauth_register(request):
    """POST /register — Dynamic Client Registration (RFC 7591)."""
    import asyncio
    from starlette.responses import JSONResponse

    ip = (request.client[0] if request.client else "unknown")
    try:
        body = await request.json()
    except Exception:
        body = {}

    client_name = str(body.get("client_name", "unknown"))
    redirect_uris = body.get("redirect_uris", [])
    if isinstance(redirect_uris, str):
        redirect_uris = [redirect_uris]

    client_id = "rag-system-client"
    client_secret = _AUTH_TOKENS_BY_ID.get("claude-ai", "")
    if not client_secret:
        await asyncio.sleep(3)
        _log("oauth_register_error", ip=ip, reason="no_claude_ai_token")
        return JSONResponse({"error": "server_error"}, status_code=500)

    with _oauth_lock:
        _oauth_clients[client_id] = {
            "client_secret": client_secret,
            "redirect_uris": redirect_uris,
        }

    _log("oauth_register", ip=ip, client_name=client_name)
    return JSONResponse({
        "client_id": client_id,
        "client_secret": client_secret,
        "client_name": client_name,
        "redirect_uris": redirect_uris,
    }, status_code=201)


async def _oauth_authorize(request):
    """GET /authorize — Auto-approve authorization endpoint (PKCE required)."""
    import secrets as _secrets
    from starlette.responses import JSONResponse, RedirectResponse

    params = dict(request.query_params)
    client_id = params.get("client_id", "")
    redirect_uri = params.get("redirect_uri", "")
    state = params.get("state", "")
    code_challenge = params.get("code_challenge", "")
    code_challenge_method = params.get("code_challenge_method", "S256")

    with _oauth_lock:
        client_info = _oauth_clients.get(client_id)

    if not client_info:
        return JSONResponse({"error": "unauthorized_client"}, status_code=400)
    if redirect_uri and redirect_uri not in client_info.get("redirect_uris", []):
        return JSONResponse({"error": "invalid_redirect_uri"}, status_code=400)

    code = _secrets.token_urlsafe(32)
    with _oauth_lock:
        _oauth_codes[code] = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "expires_at": time.monotonic() + 60.0,
        }

    _log("oauth_authorize", client_id=client_id)
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{sep}code={code}&state={state}", status_code=302)


async def _oauth_token(request):
    """POST /token — Token endpoint with client_secret + PKCE verification."""
    import asyncio
    from starlette.responses import JSONResponse

    ip = (request.client[0] if request.client else "unknown")
    try:
        form = await request.form()
        body = dict(form)
    except Exception:
        body = {}

    grant_type = body.get("grant_type", "")
    code = body.get("code", "")
    client_id = body.get("client_id", "")
    client_secret = body.get("client_secret", "")
    code_verifier = body.get("code_verifier", "")

    def _fail(reason: str, status: int = 400):
        _log("oauth_token_error", ip=ip, reason=reason)
        return JSONResponse({"error": reason}, status_code=status)

    if grant_type != "authorization_code":
        return _fail("unsupported_grant_type")

    # Validate client credentials
    with _oauth_lock:
        client_info = _oauth_clients.get(client_id)

    if not client_info or client_info.get("client_secret") != client_secret:
        await asyncio.sleep(3)
        now = time.monotonic()
        with _sec_lock:
            fq = _bf_failures.setdefault(ip, collections.deque())
            cutoff = now - _AuthRateLimitMiddleware.BF_WINDOW
            while fq and fq[0] < cutoff:
                fq.popleft()
            fq.append(now)
            if len(fq) >= _AuthRateLimitMiddleware.BF_LIMIT:
                _bf_blocks[ip] = now + _AuthRateLimitMiddleware.BF_BLOCK_DURATION
                _log("bf_block_set", ip=ip, source="token_endpoint")
        return _fail("invalid_client", 401)

    # Validate authorization code (single-use, 60s expiry)
    with _oauth_lock:
        code_info = _oauth_codes.pop(code, None)

    if not code_info:
        return _fail("invalid_grant")
    if time.monotonic() > code_info["expires_at"]:
        return _fail("invalid_grant")
    if code_info["client_id"] != client_id:
        return _fail("invalid_grant")

    # PKCE S256 verification
    if code_info.get("code_challenge"):
        if not code_verifier:
            return _fail("invalid_grant")
        if not _pkce_verify(code_verifier, code_info["code_challenge"]):
            await asyncio.sleep(3)
            return _fail("invalid_grant")

    access_token = _AUTH_TOKENS_BY_ID.get("claude-ai", "")
    if not access_token:
        return _fail("server_error", 500)

    _log("oauth_token_issued", ip=ip, client_id=client_id)
    return JSONResponse({
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 86400,
    })


def _build_oauth_starlette(public_url: str):
    """Build a Starlette app serving the 4 OAuth 2.1 endpoints."""
    from starlette.applications import Starlette
    from starlette.routing import Route

    global _MCP_PUBLIC_URL
    _MCP_PUBLIC_URL = public_url.rstrip("/")

    return Starlette(routes=[
        Route("/.well-known/oauth-authorization-server", _oauth_metadata, methods=["GET"]),
        Route("/register", _oauth_register, methods=["POST"]),
        Route("/authorize", _oauth_authorize, methods=["GET"]),
        Route("/token", _oauth_token, methods=["POST"]),
    ])


class _OAuthSSEDispatcher:
    """ASGI dispatcher: OAuth paths → oauth_app (no auth), others → auth-wrapped SSE app."""

    _OAUTH_PATHS = frozenset({
        "/.well-known/oauth-authorization-server",
        "/register",
        "/authorize",
        "/token",
    })

    def __init__(self, sse_app, oauth_app) -> None:
        self._sse = sse_app    # wrapped with _AuthRateLimitMiddleware
        self._oauth = oauth_app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "lifespan":
            await self._sse(scope, receive, send)
            return
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path in self._OAUTH_PATHS or path.startswith("/.well-known/"):
                await self._oauth(scope, receive, send)
                return
        await self._sse(scope, receive, send)


def _run_sse(port: int) -> None:
    """Validate config, build the SSE ASGI app, and serve with uvicorn."""
    global _AUTH_TOKENS, _AUTH_TOKENS_BY_ID

    # Validate auth_tokens.yaml before binding the port
    try:
        _AUTH_TOKENS = _load_auth_tokens()
        _AUTH_TOKENS_BY_ID = _load_auth_tokens_by_id()
    except (FileNotFoundError, ValueError) as e:
        print(f"[ERROR] {e}")
        raise SystemExit(1)

    public_url = os.environ.get("MCP_PUBLIC_URL", "https://fraine.tail204746.ts.net:8443").rstrip("/")
    token_ids = list(_AUTH_TOKENS.values())
    print(f"[rag-system MCP] SSEモードで起動します")
    print(f"[rag-system MCP] ポート         : {port}")
    print(f"[rag-system MCP] SSEエンドポイント: http://0.0.0.0:{port}/sse")
    print(f"[rag-system MCP] 有効トークンID  : {token_ids}")
    print(f"[rag-system MCP] Tailscale Funnel: tailscale funnel {port}")
    print(f"[rag-system MCP] OAuth endpoints enabled (issuer: {public_url})")
    print()

    # Build SSE ASGI app (transport_security=None for 0.0.0.0)
    from mcp.server.transport_security import TransportSecuritySettings
    try:
        sse_starlette = mcp.sse_app(
            sse_path="/sse",
            message_path="/messages/",
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=False,
            ),
            host="0.0.0.0",
        )
    except TypeError:
        # Older signature without host/transport_security kwargs
        sse_starlette = mcp.sse_app()

    # Wrap SSE with auth + rate-limit middleware
    auth_sse = _AuthRateLimitMiddleware(sse_starlette, _AUTH_TOKENS)

    # OAuth endpoints bypass auth middleware
    oauth_app = _build_oauth_starlette(public_url)

    # Dispatcher: OAuth paths → oauth_app, MCP paths → auth_sse
    asgi_app = _OAuthSSEDispatcher(auth_sse, oauth_app)

    import uvicorn
    uvicorn.run(
        asgi_app,
        host="0.0.0.0",
        port=port,
        log_level="warning",
        limit_max_requests=None,
    )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="rag-system MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="トランスポートモード (default: stdio)",
    )
    args = parser.parse_args()

    if args.transport == "sse":
        port = int(os.environ.get("MCP_HTTP_PORT", "8766"))
        _run_sse(port)
    else:
        logging.basicConfig(level=logging.WARNING)
        mcp.run(transport="stdio")
