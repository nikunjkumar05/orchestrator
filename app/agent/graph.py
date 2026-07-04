from langgraph.prebuilt import create_react_agent
from langchain_mistralai import ChatMistralAI
from langgraph.checkpoint.memory import MemorySaver
from app.agent.tools import all_tools

# Initialize LLM
llm = ChatMistralAI(model="mistral-large-latest", temperature=0.05)

# Initialize checkpointer for HITL state persistence
memory = MemorySaver()

# Compile the ReAct agent graph with checkpoints and HITL interrupts before executing tools
agent_executor = create_react_agent(
    llm, 
    all_tools,
    checkpointer=memory,
    interrupt_before=["tools"]
)