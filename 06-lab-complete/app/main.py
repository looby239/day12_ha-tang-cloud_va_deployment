"""
Production AI Agent — Kết hợp tất cả Day 12 concepts

Checklist:
  ✅ Config từ environment (12-factor)
  ✅ Structured JSON logging
  ✅ API Key authentication
  ✅ Rate limiting
  ✅ Cost guard
  ✅ Input validation (Pydantic)
  ✅ Health check + Readiness probe
  ✅ Graceful shutdown
  ✅ Security headers
  ✅ CORS
  ✅ Error handling
"""
import os
import time
import signal
import logging
import json
from datetime import datetime, timezone
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Security, Depends, Request, Response
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from app.config import settings

# Mock LLM (thay bằng OpenAI/Anthropic khi có API key)
from utils.mock_llm import ask as llm_ask

# ── Redis (optional — fallback to in-memory dict nếu không có Redis)
USE_REDIS = False
_redis = None
_memory_store: dict = {}

# ─────────────────────────────────────────────────────────
# Logging — JSON structured
# ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

# Initialize Redis
if settings.redis_url:
    try:
        import redis
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
        _redis.ping()
        USE_REDIS = True
        logger.info("Connected to Redis successfully.")
    except Exception as e:
        logger.warning(f"Redis not available — using in-memory store: {e}")

START_TIME = time.time()
_is_ready = False
_request_count = 0
_error_count = 0

# ─────────────────────────────────────────────────────────
# Rate Limiter
# ─────────────────────────────────────────────────────────
_rate_windows: dict[str, deque] = defaultdict(deque)

def check_rate_limit(key: str):
    now = time.time()
    limit = settings.rate_limit_per_minute
    
    if USE_REDIS:
        try:
            # Pipe commands for atomicity
            pipe = _redis.pipeline()
            # Remove timestamps older than 60s
            pipe.zremrangebyscore(f"rate_limit:{key}", 0, now - 60)
            # Count requests in window
            pipe.zcard(f"rate_limit:{key}")
            # Add current request
            pipe.zadd(f"rate_limit:{key}", {str(now): now})
            # Set expire to prevent leaks
            pipe.expire(f"rate_limit:{key}", 60)
            # Execute
            _, count, _, _ = pipe.execute()
            
            if count > limit:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded: {limit} req/min",
                    headers={"Retry-After": "60"},
                )
            return
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Redis rate limiter failed, falling back to memory: {e}")
            
    # Memory fallback
    window = _rate_windows[key]
    while window and window[0] < now - 60:
        window.popleft()
    if len(window) >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {limit} req/min",
            headers={"Retry-After": "60"},
        )
    window.append(now)

# ─────────────────────────────────────────────────────────
# Cost Guard
# ─────────────────────────────────────────────────────────
_daily_cost = 0.0
_cost_reset_day = time.strftime("%Y-%m-%d")

def check_and_record_cost(user_id: str, input_tokens: int, output_tokens: int):
    global _daily_cost, _cost_reset_day
    today = time.strftime("%Y-%m-%d")
    cost = (input_tokens / 1000) * 0.00015 + (output_tokens / 1000) * 0.0006
    
    if USE_REDIS:
        try:
            key = f"cost:{user_id}:{today}"
            current_cost = float(_redis.get(key) or 0.0)
            if current_cost + cost > settings.daily_budget_usd:
                raise HTTPException(status_code=402, detail="Daily budget exceeded.")
            _redis.incrbyfloat(key, cost)
            _redis.expire(key, 86400 * 2) # expire in 2 days
            return
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Redis cost guard failed, falling back to memory: {e}")
            
    # memory fallback
    if today != _cost_reset_day:
        _daily_cost = 0.0
        _cost_reset_day = today
    if _daily_cost + cost > settings.daily_budget_usd:
        raise HTTPException(status_code=402, detail="Daily budget exhausted.")
    _daily_cost += cost

# ─────────────────────────────────────────────────────────
# Session Storage (Redis-backed, Stateless-compatible)
# ─────────────────────────────────────────────────────────
def load_history(user_id: str) -> list:
    if USE_REDIS:
        try:
            data = _redis.get(f"history:{user_id}")
            return json.loads(data) if data else []
        except Exception as e:
            logger.warning(f"Failed to load history from Redis: {e}")
    return _memory_store.get(f"history:{user_id}", [])

def save_history(user_id: str, history: list):
    if len(history) > 20:
        history = history[-20:]
    if USE_REDIS:
        try:
            _redis.setex(f"history:{user_id}", 3600, json.dumps(history))
            return
        except Exception as e:
            logger.warning(f"Failed to save history to Redis: {e}")
    _memory_store[f"history:{user_id}"] = history

# ─────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    if not api_key or api_key != settings.agent_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Include header: X-API-Key: <key>",
        )
    return api_key

# ─────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready
    logger.info(json.dumps({
        "event": "startup",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }))
    time.sleep(0.1)  # simulate init
    _is_ready = True
    logger.info(json.dumps({"event": "ready"}))

    yield

    _is_ready = False
    logger.info(json.dumps({"event": "shutdown"}))

# ─────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _request_count, _error_count
    start = time.time()
    _request_count += 1
    try:
        response: Response = await call_next(request)
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if "server" in response.headers:
            del response.headers["server"]
        duration = round((time.time() - start) * 1000, 1)
        logger.info(json.dumps({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": duration,
        }))
        return response
    except Exception as e:
        _error_count += 1
        raise

# ─────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000,
                          description="Your question for the agent")
    user_id: str | None = Field(default=None, description="Optional user ID for conversation context")

class AskResponse(BaseModel):
    question: str
    answer: str
    model: str
    timestamp: str

# ─────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────

@app.get("/", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "endpoints": {
            "ask": "POST /ask (requires X-API-Key)",
            "health": "GET /health",
            "ready": "GET /ready",
        },
    }


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
async def ask_agent(
    body: AskRequest,
    request: Request,
    _key: str = Depends(verify_api_key),
):
    """
    Send a question to the AI agent.

    **Authentication:** Include header `X-API-Key: <your-key>`
    """
    user_id = body.user_id or _key[:8]

    # Rate limit per API key
    check_rate_limit(user_id)

    # Budget check
    input_tokens = len(body.question.split()) * 2
    check_and_record_cost(user_id, input_tokens, 0)

    logger.info(json.dumps({
        "event": "agent_call",
        "q_len": len(body.question),
        "client": str(request.client.host) if request.client else "unknown",
    }))

    # Load history
    history = load_history(user_id)

    # Context awareness check
    question_lower = body.question.lower()
    answer = None
    if "what is my name" in question_lower or "who am i" in question_lower:
        for msg in reversed(history):
            if msg["role"] == "user":
                content_lower = msg["content"].lower()
                if "my name is " in content_lower:
                    idx = content_lower.find("my name is ") + 11
                    name = msg["content"][idx:].strip(" .!?")
                    if name:
                        answer = f"Tên của bạn là {name}."
                        break
                elif "i am " in content_lower:
                    idx = content_lower.find("i am ") + 5
                    name = msg["content"][idx:].strip(" .!?")
                    if name:
                        answer = f"Tên của bạn là {name}."
                        break

    if not answer:
        answer = llm_ask(body.question)

    output_tokens = len(answer.split()) * 2
    check_and_record_cost(user_id, 0, output_tokens)

    # Save to history
    history.append({"role": "user", "content": body.question, "timestamp": datetime.now(timezone.utc).isoformat()})
    history.append({"role": "assistant", "content": answer, "timestamp": datetime.now(timezone.utc).isoformat()})
    save_history(user_id, history)

    return AskResponse(
        question=body.question,
        answer=answer,
        model=settings.llm_model,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/health", tags=["Operations"])
def health():
    """Liveness probe. Platform restarts container if this fails."""
    redis_status = "N/A"
    if USE_REDIS:
        try:
            _redis.ping()
            redis_status = "ok"
        except Exception:
            redis_status = "error"
    status = "ok" if (not USE_REDIS or redis_status == "ok") else "degraded"
    checks = {
        "llm": "mock" if not settings.openai_api_key else "openai",
        "redis": redis_status
    }
    return {
        "status": status,
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    """Readiness probe. Load balancer stops routing here if not ready."""
    if not _is_ready:
        raise HTTPException(503, "Not ready")
    if USE_REDIS:
        try:
            _redis.ping()
        except Exception:
            raise HTTPException(503, "Redis not available")
    return {"ready": True}


@app.get("/metrics", tags=["Operations"])
def metrics(_key: str = Depends(verify_api_key)):
    """Basic metrics (protected)."""
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "error_count": _error_count,
        "daily_cost_usd": round(_daily_cost, 4),
        "daily_budget_usd": settings.daily_budget_usd,
        "budget_used_pct": round(_daily_cost / settings.daily_budget_usd * 100, 1),
    }


# ─────────────────────────────────────────────────────────
# Graceful Shutdown
# ─────────────────────────────────────────────────────────
def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal", "signum": signum}))

signal.signal(signal.SIGTERM, _handle_signal)


if __name__ == "__main__":
    logger.info(f"Starting {settings.app_name} on {settings.host}:{settings.port}")
    logger.info(f"API Key: {settings.agent_api_key[:4]}****")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
