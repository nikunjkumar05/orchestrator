from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import json
import asyncio
from app.models import PromptRequest, AgentResponse
from app.agent.graph import agent_executor
from langchain_core.messages import AIMessage, ToolMessage

app = FastAPI(
    title="Prompt-to-Agent Orchestrator",
    description="A zero-config pipeline converting a single prompt into a fully executed multi-step workflow.",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/v1/execute", response_model=AgentResponse)
async def execute_prompt(request: PromptRequest):
    # Backward compatibility endpoint
    try:
        if not request.prompt.strip():
            raise HTTPException(status_code=400, detail="Prompt cannot be empty")
        
        config = {"configurable": {"thread_id": "legacy_thread"}}
        inputs = {"messages": [("user", request.prompt)]}
        
        result = await agent_executor.ainvoke(inputs, config=config)
        final_message = result["messages"][-1].content
        
        return AgentResponse(
            result=final_message,
            messages=[msg.model_dump() for msg in result["messages"]]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Generate unique thread ID for the WebSocket session
    thread_id = str(id(websocket))
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        while True:
            # Receive prompt payload
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            if "prompt" in message_data:
                prompt = message_data["prompt"]
                inputs = {"messages": [("user", prompt)]}
                
                # Stream the LangGraph execution events asynchronously
                async for event in agent_executor.astream_events(inputs, config=config, version="v2"):
                    kind = event["event"]
                    
                    # 1. Stream token generation in real-time
                    if kind == "on_chat_model_stream":
                        content = event["data"]["chunk"].content
                        if content:
                            await websocket.send_json({
                                "type": "token",
                                "content": content
                            })
                            
                    # 2. Stream tool call notifications
                    elif kind == "on_tool_start":
                        tool_name = event["name"]
                        await websocket.send_json({
                            "type": "status",
                            "content": f"Preparing to run tool: {tool_name}..."
                        })

                # Check if graph paused due to Human-in-the-Loop interrupt
                state = await agent_executor.aget_state(config)
                while state.next:
                    last_message = state.values["messages"][-1]
                    if isinstance(last_message, AIMessage) and last_message.tool_calls:
                        tool_call = last_message.tool_calls[0]
                        
                        # Send approval request to frontend
                        await websocket.send_json({
                            "type": "approval_required",
                            "tool": tool_call["name"],
                            "args": tool_call["args"],
                            "id": tool_call["id"]
                        })
                        
                        # Halt execution and wait for user's approval response
                        raw_approval = await websocket.receive_text()
                        approval_data = json.loads(raw_approval)
                        
                        if approval_data.get("approved") is True:
                            await websocket.send_json({
                                "type": "status",
                                "content": "Access granted. Running tool..."
                            })
                            # Resume execution with approval
                            async for event in agent_executor.astream_events(None, config=config, version="v2"):
                                if event["event"] == "on_chat_model_stream":
                                    content = event["data"]["chunk"].content
                                    if content:
                                        await websocket.send_json({"type": "token", "content": content})
                                elif event["event"] == "on_tool_start":
                                    await websocket.send_json({"type": "status", "content": f"Executing: {event['name']}..."})
                        else:
                            await websocket.send_json({
                                "type": "status",
                                "content": "Access denied. Notifying the agent..."
                            })
                            # Inject rejection context directly into graph state
                            rejection = ToolMessage(
                                content="Error: Execution denied by user.",
                                tool_call_id=tool_call["id"]
                            )
                            await agent_executor.aupdate_state(config, {"messages": [rejection]}, as_node="tools")
                            
                            # Resume execution with the rejection state loaded
                            async for event in agent_executor.astream_events(None, config=config, version="v2"):
                                if event["event"] == "on_chat_model_stream":
                                    content = event["data"]["chunk"].content
                                    if content:
                                        await websocket.send_json({"type": "token", "content": content})
                    
                    # Re-check the state
                    state = await agent_executor.aget_state(config)

                # Send completion signal
                await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        print("WebSocket client disconnected.")
    except Exception as e:
        print(f"Error: {e}")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Mount compiled static frontend files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")