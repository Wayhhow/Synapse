import os
import uuid
import logging
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
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
    session_id: str

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if not router_instance:
        raise HTTPException(status_code=503, detail="Router not initialized")
    session_id = request.session_id or str(uuid.uuid4())
    try:
        result = await router_instance.process_query(request.message, session_id=session_id)
        if isinstance(result, PydanticModel):
            # Bug-20 fix: previously we did `str(result.model_dump())`,
            # which produced a Python dict repr like
            # `{'location': 'Seattle', 'temperature': 25.0}` — single
            # quotes, no indentation. JSON output is friendlier for API
            # consumers (and consistent with how `curl` users expect JSON
            # services to respond).
            reply = result.model_dump_json(indent=2)
            skill_used = type(result).__name__
        else:
            reply = str(result)
            skill_used = None
        return ChatResponse(reply=reply, skill_used=skill_used, session_id=session_id)
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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

@app.get("/history/{session_id}")
async def history(session_id: str):
    if router_instance is None:
        raise HTTPException(status_code=503, detail="Router not initialized")
    return router_instance.memory.get_history(session_id)

@app.get("/")
async def index():
    # Bug-11 fix: serve the static index.html using the resolved absolute
    # path so the route works regardless of the launcher's CWD.
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"))

# Bug-11 fix: mount the static directory using the absolute path too.
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
