import os
import time
import warnings
from langchain_core.tools import tool
from duckduckgo_search import DDGS
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_community.agent_toolkits import FileManagementToolkit
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_mistralai import ChatMistralAI, MistralAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from e2b_code_interpreter import CodeInterpreter

# Suppress all duckduckgo_search package warnings
warnings.filterwarnings("ignore", message=".*duckduckgo_search.*")

# 1. Web Search Tool
@tool
def search_tool(query: str) -> str:
    """Search the web for information using Tavily (on Cloud) or DuckDuckGo (Locally)."""
    if os.getenv("TAVILY_API_KEY"):
        try:
            tavily = TavilySearchResults(max_results=5)
            results = tavily.invoke(query)
            if results:
                return str(results)
        except Exception as e:
            print(f"Tavily search failed, falling back to DuckDuckGo: {e}")

    max_retries = 3
    for attempt in range(max_retries):
        try:
            results = DDGS().text(query, max_results=5)
            parsed_results = [r for r in results]
            if parsed_results:
                return str(parsed_results)
            time.sleep(1)
        except Exception as e:
            if attempt == max_retries - 1:
                return f"Search failed after {max_retries} attempts: {e}"
            time.sleep(1)
    return "Search returned no results. Try rephrasing your query."

# 2. Secure Code Execution Sandbox (E2B)
@tool
def e2b_sandbox_tool(code: str) -> str:
    """Execute Python code inside a secure, ephemeral cloud sandbox.
    Use this to run algorithms, analyze files, process data, or perform calculations.
    """
    if not os.getenv("E2B_API_KEY"):
        return "Error: E2B_API_KEY is not set in the environment. Secure sandbox is unavailable."
    
    try:
        with CodeInterpreter() as sandbox:
            exec_result = sandbox.notebook.exec_cell(code)
            
            output = ""
            if exec_result.results:
                for result in exec_result.results:
                    if result.is_image:
                        output += "[Chart/Visualization generated successfully]\n"
                    else:
                        output += f"{result}\n"
            if exec_result.logs.stdout:
                output += "".join(exec_result.logs.stdout)
            if exec_result.logs.stderr:
                output += "[ERROR] " + "".join(exec_result.logs.stderr)
            
            return output if output else "Code executed successfully with no output."
    except Exception as e:
        return f"Sandbox execution failed: {str(e)}"

# 3. File I/O Tools
workspace_dir = os.path.join(os.getcwd(), "workspace")
os.makedirs(workspace_dir, exist_ok=True)
file_toolkit = FileManagementToolkit(
    root_dir=workspace_dir,
    selected_tools=["read_file", "write_file", "list_directory"],
)
file_tools = file_toolkit.get_tools()

# 4. RAG / Vector Database Tools (ChromaDB)
embeddings = MistralAIEmbeddings(model="mistral-embed")
chroma_dir = os.path.join(workspace_dir, "chroma")
vector_store = Chroma(
    persist_directory=chroma_dir,
    embedding_function=embeddings
)

@tool
def index_document_tool(filename: str, content: str) -> str:
    """Index a document's content into the vector database for semantic RAG search.
    Args:
        filename: The filename or title.
        content: The text content of the document.
    """
    try:
        doc = Document(page_content=content, metadata={"source": filename})
        vector_store.add_documents([doc])
        return f"Successfully indexed '{filename}' into vector database."
    except Exception as e:
        return f"Failed to index document: {e}"

@tool
def semantic_search_tool(query: str) -> str:
    """Perform a semantic search across all indexed workspace files to retrieve relevant content.
    Use this to answer questions using files or databases you indexed.
    """
    try:
        results = vector_store.similarity_search(query, k=3)
        if not results:
            return "No relevant sections found in vector database."
        output = []
        for i, doc in enumerate(results):
            output.append(f"[Result {i+1} - Source: {doc.metadata.get('source')}]:\n{doc.page_content}\n")
        return "\n".join(output)
    except Exception as e:
        return f"Semantic search failed: {e}"

# 5. SQL Database Tools
db_path = os.path.join(workspace_dir, "orchestrator.db")
db = SQLDatabase.from_uri(f"sqlite:///{db_path}")
llm = ChatMistralAI(model="mistral-large-latest", temperature=0)
sql_toolkit = SQLDatabaseToolkit(db=db, llm=llm)
sql_tools = sql_toolkit.get_tools()

# Combine all tools
all_tools = [search_tool, e2b_sandbox_tool, index_document_tool, semantic_search_tool] + file_tools + sql_tools