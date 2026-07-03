from pydantic import BaseModel
from typing import List, Optional, Any

class PromptRequest(BaseModel):
    prompt: str

class AgentResponse(BaseModel):
    result: str
    messages: Optional[List[Any]] = None
