from fastapi import FastAPI, HTTPException
from app.models import PromptRequest, AgentResponse
from app.agent.graph import run_agent

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI(
    title="Prompt-to-Agent Orchestrator",
    description="A zero-config pipeline converting a single prompt into a fully executed multi-step workflow.",
    version="1.0.0"
)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this to your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/v1/execute", response_model=AgentResponse)
async def execute_prompt(request: PromptRequest):
    try:
        if not request.prompt.strip():
            raise HTTPException(status_code=400, detail="Prompt cannot be empty")
            
        result = run_agent(request.prompt)
        return AgentResponse(
            result=result["result"],
            messages=result["messages"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Mount Angular static files if they exist (built by multi-stage Dockerfile)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
