from langgraph.prebuilt import create_react_agent
from langchain_mistralai import ChatMistralAI
from app.agent.tools import all_tools

# Initialize the main reasoning LLM
# Ensure MISTRAL_API_KEY is set in your environment
llm = ChatMistralAI(model="mistral-large-latest", temperature=0)

# Create the ReAct agent using LangGraph's prebuilt function
# This automatically handles the ToolNode and state management
agent_executor = create_react_agent(llm, all_tools)

def run_agent(prompt: str) -> dict:
    """
    Runs the LangGraph agent with a given prompt.
    """
    inputs = {"messages": [("user", prompt)]}
    # Invoke the agent executor
    result = agent_executor.invoke(inputs)
    
    # Extract the final message content
    final_message = result["messages"][-1].content
    
    return {
        "result": final_message,
        "messages": [msg.model_dump() for msg in result["messages"]]
    }
