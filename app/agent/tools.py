import os
from langchain_core.tools import tool
from duckduckgo_search import DDGS
from langchain_experimental.tools.python.tool import PythonREPLTool
from langchain_community.agent_toolkits import FileManagementToolkit
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_mistralai import ChatMistralAI

import warnings
import time

# Suppress the annoying duckduckgo_search rename warning
warnings.filterwarnings("ignore", category=RuntimeWarning, module="duckduckgo_search")

# 1. Web Search Tool
@tool
def search_tool(query: str) -> str:
    """Search the web for information using DuckDuckGo."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            results = DDGS().text(query, max_results=5)
            parsed_results = [r for r in results]
            if parsed_results:
                return str(parsed_results)
            # If results are empty, sleep briefly and retry (could be temporary rate-limiting)
            time.sleep(1)
        except Exception as e:
            if attempt == max_retries - 1:
                return f"Search failed after {max_retries} attempts: {e}"
            time.sleep(1)
    return "Search returned no results. Try rephrasing your query."

# 2. Code Execution Tool
python_repl_tool = PythonREPLTool()

# 3. File I/O Tools
workspace_dir = os.path.join(os.getcwd(), "workspace")
os.makedirs(workspace_dir, exist_ok=True)
file_toolkit = FileManagementToolkit(
    root_dir=workspace_dir,
    selected_tools=["read_file", "write_file", "list_directory"],
)
file_tools = file_toolkit.get_tools()

# 4. Database Tool
db_path = os.path.join(workspace_dir, "orchestrator.db")
db = SQLDatabase.from_uri(f"sqlite:///{db_path}")

# Note: For LangGraph, the main reasoning LLM is separate, but SQL toolkit bundles its own logic.
llm = ChatMistralAI(model="mistral-large-latest", temperature=0)
sql_toolkit = SQLDatabaseToolkit(db=db, llm=llm)
sql_tools = sql_toolkit.get_tools()

# Combine all tools
all_tools = [search_tool, python_repl_tool] + file_tools + sql_tools
