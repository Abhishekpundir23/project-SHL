from fastapi import FastAPI
import logging
import time
from fastapi import Request

from app.agent import SHLAgent
from app.models import ChatRequest, ChatResponse

app = FastAPI(title="Conversational SHL Assessment Recommender")
agent = SHLAgent()
logger = logging.getLogger("shl_recommender")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        "request path=%s method=%s status=%s elapsed_ms=%s",
        request.url.path,
        request.method,
        response.status_code,
        elapsed_ms,
    )
    return response


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "shl-assessment-recommender", "health": "/health", "chat": "/chat", "docs": "/docs"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    return agent.respond(request.messages)
