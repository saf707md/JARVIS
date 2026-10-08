import logging

from google.genai import types

from core.llm import JarvisLLM
from tools.registry import get_tool_functions, run_tool

logger = logging.getLogger("jarvis")

FALLBACK = "Sir, I couldn't reach my cloud brain right now."
MAX_TOOL_ROUNDS = 5  # safety limit so the AI can't loop forever


class Orchestrator:
    """Decides what happens: asks the AI, runs approved tools, returns the answer."""

    def __init__(self, confirm=None):
        self.llm = JarvisLLM(tools=get_tool_functions())
        self.confirm = confirm  # function used to ask the user for permission

    def ask(self, user_text: str) -> str:
        response = self.llm.send(user_text)

        for _ in range(MAX_TOOL_ROUNDS):
            if response is None:
                return FALLBACK
            calls = response.function_calls
            if not calls:
                break

            result_parts = []
            for call in calls:
                args = dict(call.args or {})
                logger.info("[AGENT] Tool selected: %s %s", call.name, args)
                result = run_tool(call.name, args, self.confirm)
                result_parts.append(
                    types.Part.from_function_response(
                        name=call.name, response={"result": result}
                    )
                )
            response = self.llm.send(result_parts)

        if response is None:
            return FALLBACK
        return response.text or "Done, Sir."
