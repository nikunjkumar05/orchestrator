from fastapi import FastAPI, HTTPException
from app.models import PromptRequest, AgentResponse
from app.agent.graph import run_agent

app = FastAPI(
    title="Prompt-to-Agent Orchestrator",
    description="A zero-config pipeline converting a single prompt into a fully executed multi-step workflow.",
    version="1.0.0"
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
