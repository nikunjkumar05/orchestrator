from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import os
import json
import uuid
import logging
from datetime import datetime, timezone
from app.models import PromptRequest, AgentResponse
from app.agent import graph
from app.agent.graph import init_checkpointer, build_agent
from langchain_core.messages import AIMessage, ToolMessage

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Prompt-to-Agent Orchestrator",
    description="A zero-config pipeline converting a single prompt into a fully executed multi-step workflow.",
    version="1.0.0"
)

allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

agent_executor = None


@app.on_event("startup")
async def startup():
    global agent_executor
    memory = await init_checkpointer()
    agent_executor = build_agent(memory)
    logger.info("SQLite checkpointer initialized.")


@app.on_event("shutdown")
async def shutdown():
    if graph.conn:
        await graph.conn.close()
    logger.info("SQLite checkpointer connection closed.")


def _generate_thread_name(preview: str) -> str:
    """Generate a short, friendly thread name from the first user message."""
    if not preview:
        return "New conversation"
    words = preview.split()[:6]
    name = " ".join(words)
    if len(preview) > len(name):
        name += "..."
    return name


def _extract_created_at(state) -> str:
    """Extract a valid ISO timestamp from checkpoint data."""
    if not state or not state.checkpoint:
        return ""
    # Try checkpoint metadata first
    meta = state.checkpoint.get("metadata", {})
    if isinstance(meta, dict):
        ts = meta.get("ts", "")
        if ts:
            return ts
    # Try top-level checkpoint fields
    for key in ("ts", "created_at"):
        val = state.checkpoint.get(key, "")
        if val:
            return val
    return ""


@app.get("/api/v1/threads")
async def list_threads():
    """List all conversation threads with their last message and timestamp."""
    try:
        cursor = await graph.conn.execute(
            "SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id DESC LIMIT 50"
        )
        rows = await cursor.fetchall()

        threads = []
        for row in rows:
            thread_id = row[0]
            preview = ""
            created_at = ""
            try:
                state = await agent_executor.aget_state(
                    {"configurable": {"thread_id": thread_id}}
                )
                if state and state.values:
                    msgs = state.values.get("messages", [])
                    for m in msgs:
                        if hasattr(m, "type") and m.type == "human" and hasattr(m, "content") and m.content:
                            content = m.content if isinstance(m.content, str) else str(m.content)
                            preview = content[:80]
                            break
                created_at = _extract_created_at(state)
            except Exception:
                pass
            name = _generate_thread_name(preview)
            threads.append({
                "thread_id": thread_id,
                "name": name,
                "created_at": created_at,
                "preview": preview,
            })

        return threads
    except Exception as e:
        logger.error(f"Failed to list threads: {e}")
        return []


@app.get("/api/v1/threads/{thread_id}/history")
async def get_thread_history(thread_id: str):
    """Load the full message history for a thread."""
    try:
        state = await agent_executor.aget_state(
            {"configurable": {"thread_id": thread_id}}
        )
        messages = []
        if state and state.values:
            for msg in state.values.get("messages", []):
                if isinstance(msg, dict):
                    msg_type = msg.get("type", "")
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        # Multimodal content — extract text
                        text_parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
                        content = " ".join(text_parts) if text_parts else str(content)
                    if msg_type == "ai":
                        messages.append({"role": "assistant", "content": content})
                    elif msg_type == "human":
                        messages.append({"role": "user", "content": content})
                elif isinstance(msg, AIMessage):
                    messages.append({"role": "assistant", "content": msg.content})
                elif hasattr(msg, "type") and msg.type == "human":
                    messages.append({"role": "user", "content": msg.content})
                elif isinstance(msg, ToolMessage):
                    pass  # skip tool messages for frontend
        return {"thread_id": thread_id, "messages": messages}
    except Exception as e:
        logger.error(f"Failed to load thread history: {e}", exc_info=True)
        raise HTTPException(status_code=404, detail="Thread not found")


async def stream_astream_results(websocket: WebSocket, config: dict, inputs=None, silent=False):
    async for event in agent_executor.astream(inputs, config=config):
        for node_name, node_output in event.items():
            if node_name == "agent" and isinstance(node_output, dict):
                messages = node_output.get("messages", [])
                for msg in messages:
                    if isinstance(msg, AIMessage):
                        if not silent and msg.content:
                            await websocket.send_json({"type": "token", "content": msg.content})
                        if msg.tool_calls:
                            for tc in msg.tool_calls:
                                await websocket.send_json({
                                    "type": "status",
                                    "content": f"Preparing to run tool: {tc['name']}..."
                                })
            elif node_name == "tools" and isinstance(node_output, dict):
                messages = node_output.get("messages", [])
                for msg in messages:
                    if isinstance(msg, ToolMessage):
                        content = msg.content if isinstance(msg.content, str) else str(msg.content)
                        if "**File created:**" in content or "```" in content:
                            await websocket.send_json({"type": "file_preview", "content": content})
            elif node_name == "__interrupt__":
                return True
    return False


@app.post("/api/v1/execute", response_model=AgentResponse)
async def execute_prompt(request: PromptRequest):
    try:
        if not request.prompt.strip():
            raise HTTPException(status_code=400, detail="Prompt cannot be empty")

        config = {"configurable": {"thread_id": str(uuid.uuid4())}}
        inputs = {"messages": [("user", request.prompt)]}

        result = await agent_executor.ainvoke(inputs, config=config)
        final_message = result["messages"][-1].content

        return AgentResponse(
            result=final_message,
            messages=[msg.model_dump() for msg in result["messages"]]
        )
    except Exception as e:
        logger.error(f"Agent execution failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal agent error")


@app.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message_data = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "content": "Invalid JSON"})
                continue

            if "thread_id" in message_data and message_data["thread_id"]:
                thread_id = message_data["thread_id"]
                config = {"configurable": {"thread_id": thread_id}}
            else:
                thread_id = str(uuid.uuid4())
                config = {"configurable": {"thread_id": thread_id}}

            await websocket.send_json({"type": "thread_id", "thread_id": thread_id})

            if "prompt" not in message_data:
                continue

            prompt = message_data["prompt"]
            inputs = {"messages": [("user", prompt)]}

            interrupted = await stream_astream_results(websocket, config, inputs)

            if interrupted:
                state = await agent_executor.aget_state(config)
                while state.next:
                    last_message = state.values["messages"][-1]
                    if isinstance(last_message, AIMessage) and last_message.tool_calls:
                        tool_call = last_message.tool_calls[0]

                        await websocket.send_json({
                            "type": "approval_required",
                            "tool": tool_call["name"],
                            "args": tool_call["args"],
                            "id": tool_call["id"]
                        })

                        raw_approval = await websocket.receive_text()
                        try:
                            approval_data = json.loads(raw_approval)
                        except json.JSONDecodeError:
                            await websocket.send_json({"type": "error", "content": "Invalid approval payload"})
                            continue

                        if approval_data.get("approved") is True:
                            await websocket.send_json({
                                "type": "status",
                                "content": "Access granted. Running tool..."
                            })
                            await stream_astream_results(websocket, config, silent=True)
                            await websocket.send_json({
                                "type": "status",
                                "content": f"Tool '{tool_call['name']}' completed successfully."
                            })
                        else:
                            await websocket.send_json({
                                "type": "status",
                                "content": "Access denied. Notifying the agent..."
                            })
                            rejection = ToolMessage(
                                content="Error: Execution denied by user.",
                                tool_call_id=tool_call["id"]
                            )
                            await agent_executor.aupdate_state(config, {"messages": [rejection]}, as_node="tools")
                            await stream_astream_results(websocket, config, silent=True)
                            await websocket.send_json({
                                "type": "status",
                                "content": "Tool denied. Agent notified."
                            })

                    state = await agent_executor.aget_state(config)

            await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected.")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        try:
            await websocket.send_json({"type": "error", "content": "Agent error occurred"})
        except Exception:
            pass


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
