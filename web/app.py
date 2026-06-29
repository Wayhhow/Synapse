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
            reply = str(result.model_dump())
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
    return FileResponse("web/static/index.html")

app.mount("/static", StaticFiles(directory="web/static"), name="static")
