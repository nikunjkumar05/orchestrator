import os
import aiosqlite
from langgraph.prebuilt import create_react_agent
from langchain_mistralai import ChatMistralAI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from app.agent.tools import all_tools

# Initialize LLM
llm = ChatMistralAI(model="mistral-large-latest", temperature=0.05)

# Persistent SQLite checkpointer — construct directly (from_conn_string returns a context manager)
WORKSPACE_DIR = os.getenv(
    "WORKSPACE_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "workspace")
)
db_path = os.path.join(WORKSPACE_DIR, "checkpoints.db")
os.makedirs(os.path.dirname(db_path), exist_ok=True)

# We'll initialize the connection in an async context; store reference for now
conn = None
memory = None

async def init_checkpointer():
    global conn, memory
    conn = await aiosqlite.connect(db_path)
    memory = AsyncSqliteSaver(conn)
    await memory.setup()
    return memory

# Compile the ReAct agent graph — we need memory initialized before first request,
# so we lazy-init on startup. Store the config for compile.
def build_agent(checkpointer):
    return create_react_agent(
        llm,
        all_tools,
        checkpointer=checkpointer,
        interrupt_before=["tools"]
    )