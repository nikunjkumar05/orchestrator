import os
from langchain_core.tools import tool
from duckduckgo_search import DDGS
from langchain_experimental.tools.python.tool import PythonREPLTool
from langchain_community.agent_toolkits import FileManagementToolkit
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_mistralai import ChatMistralAI

# 1. Web Search Tool
@tool
def search_tool(query: str) -> str:
    """Search the web for information using DuckDuckGo."""
    try:
        results = DDGS().text(query, max_results=5)
        return str([r for r in results])
    except Exception as e:
        return f"Search failed: {e}"

# 2. Code Execution Tool
python_repl_tool = PythonREPLTool()

# 3. File I/O Tools
# Create a workspace directory for safe file I/O
workspace_dir = os.path.join(os.getcwd(), "workspace")
os.makedirs(workspace_dir, exist_ok=True)
file_toolkit = FileManagementToolkit(
    root_dir=workspace_dir,
    selected_tools=["read_file", "write_file", "list_directory"],
)
file_tools = file_toolkit.get_tools()

# 4. Database Tool
# We'll use a local SQLite database for zero-config
db_path = os.path.join(workspace_dir, "orchestrator.db")
db = SQLDatabase.from_uri(f"sqlite:///{db_path}")

# Initialize a dummy LLM for the SQL toolkit (it needs one to generate SQL queries)
# Note: For LangGraph, the main reasoning LLM is separate, but SQL toolkit bundles its own logic.
llm = ChatMistralAI(model="mistral-large-latest", temperature=0)
sql_toolkit = SQLDatabaseToolkit(db=db, llm=llm)
sql_tools = sql_toolkit.get_tools()

# Combine all tools
all_tools = [search_tool, python_repl_tool] + file_tools + sql_tools
