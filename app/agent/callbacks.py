from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult


class TokenTrackingCallback(AsyncCallbackHandler):
    """Tracks token usage and estimated cost per LLM call."""

    INPUT_COST_PER_TOKEN = 0.27 / 1_000_000
    OUTPUT_COST_PER_TOKEN = 0.81 / 1_000_000

    def __init__(self):
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.estimated_cost = 0.0

    async def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        pass

    async def on_llm_end(self, response: LLMResult, *, run_id, **kwargs):
        if not response.llm_output:
            return
        usage = response.llm_output.get("token_usage") or response.llm_output.get("usage")
        if not usage:
            return
        self.prompt_tokens += usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
        self.completion_tokens += usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)
        self.total_tokens = self.prompt_tokens + self.completion_tokens
        self.estimated_cost = (
            self.prompt_tokens * self.INPUT_COST_PER_TOKEN
            + self.completion_tokens * self.OUTPUT_COST_PER_TOKEN
        )

    def get_stats(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost": round(self.estimated_cost, 6),
        }
