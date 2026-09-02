import os
import uuid
import json
import logging
from typing import Optional, List
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel as PydanticModel
from dotenv import load_dotenv
from router.router import SkillRouter

logger = logging.getLogger(__name__)

router_instance: Optional[SkillRouter] = None

# Bug-11 fix: compute the absolute path to the static directory relative to
# this module's __file__ rather than the process's current working directory.
# Previously the routes used the relative path "web/static/...", which 404'd
# when uvicorn was launched from a directory other than the project root
# (e.g. `cd /tmp && uvicorn web.app:app --app-dir /workspace`).
_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global router_instance
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    load_dotenv()
    router_instance = SkillRouter()
    logger.info("SkillRouter initialized")
    yield

app = FastAPI(title="Synapse Agent", lifespan=lifespan)

class ChatRequest(PydanticModel):
    message: str
    session_id: Optional[str] = None

class ChatResponse(PydanticModel):
    reply: str
    skill_used: Optional[str] = None
    skills_used: List[str] = []
    session_id: str


def _format_reply(result) -> str:
    if isinstance(result, PydanticModel):
        # Bug-20 fix: JSON output is friendlier for API consumers than a
        # Python dict repr.
        return result.model_dump_json(indent=2)
    return str(result)


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if not router_instance:
        raise HTTPException(status_code=503, detail="Router not initialized")
    session_id = request.session_id or str(uuid.uuid4())
    try:
        result = await router_instance.process_query(request.message, session_id=session_id)
        # The loop-mode router reports which skills it used; fall back to the
        # response model's class name for legacy/single-shot routers.
        raw_used = getattr(router_instance, "last_skills_used", None)
        skills_used = list(raw_used) if isinstance(raw_used, list) else []
        if skills_used:
            skill_used = skills_used[0]
        elif isinstance(result, PydanticModel):
            skill_used = type(result).__name__
            skills_used = [skill_used]
        else:
            skill_used = None
        reply = _format_reply(result)
        return ChatResponse(
            reply=reply,
            skill_used=skill_used,
            skills_used=skills_used,
            session_id=session_id,
        )
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Server-Sent Events stream of agent-loop progress.

    Each SSE ``data:`` line carries one JSON event from
    ``SkillRouter.process_query_events`` (``llm`` / ``tool_start`` /
    ``tool_result`` / ``meta`` / ``final``). The ``final`` event is always
    last."""
    if not router_instance:
        raise HTTPException(status_code=503, detail="Router not initialized")
    session_id = request.session_id or str(uuid.uuid4())

    async def event_source():
        # First event pins the session id for the client.
        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"
        try:
            async for event in router_instance.process_query_events(request.message, session_id=session_id):
                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: {json.dumps({'type': 'final', 'text': f'Error: {e}', 'result': None, 'skills_used': []})}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/skills")
async def list_skills():
    if not router_instance:
        raise HTTPException(status_code=503, detail="Router not initialized")
    return [
        {"name": skill.name, "description": skill.description}
        for skill in router_instance.skills.values()
    ]

@app.get("/health")
async def health():
    if router_instance is None:
        return JSONResponse(status_code=503, content={"status": "initializing"})
    return {"status": "ok", "skills_count": len(router_instance.skills)}

@app.get("/stats")
async def stats():
    if router_instance is None:
        raise HTTPException(status_code=503, detail="Router not initialized")
    return router_instance.evaluator.generate_improvement_report()

@app.get("/traces")
async def traces(limit: int = 20):
    """Most recent agent-loop execution traces (newest first)."""
    if router_instance is None:
        raise HTTPException(status_code=503, detail="Router not initialized")
    return router_instance.tracer.read_recent(limit=max(1, min(limit, 200)))

@app.get("/history/{session_id}")
async def history(session_id: str):
    if router_instance is None:
        raise HTTPException(status_code=503, detail="Router not initialized")
    return router_instance.memory.get_history(session_id)

@app.delete("/history/{session_id}")
async def clear_history(session_id: str):
    if router_instance is None:
        raise HTTPException(status_code=503, detail="Router not initialized")
    router_instance.memory.clear(session_id)
    return {"status": "cleared", "session_id": session_id}

@app.get("/")
async def index():
    # Bug-11 fix: serve the static index.html using the resolved absolute
    # path so the route works regardless of the launcher's CWD.
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"))

# Bug-11 fix: mount the static directory using the absolute path too.
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
