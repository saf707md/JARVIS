import logging
import re

from google.genai import types

from core.llm import JarvisLLM
from memory.conversation import clear_history, load_recent, save_exchange
from tools.registry import get_tool_functions, run_tool

logger = logging.getLogger("jarvis")

FALLBACK = "Sir, I couldn't reach my cloud brain right now."
MAX_TOOL_ROUNDS = 5  # safety limit so the AI can't loop forever
CLEAR_PHRASES = {
    "clear history", "clear chat history", "clear conversation history",
    "clear my chat history", "delete chat history", "forget our conversation",
}


class Orchestrator:
    """Decides what happens: asks the AI, runs approved tools, returns the answer."""

    def __init__(self, confirm=None):
        self.confirm = confirm  # function used to ask the user for permission

        # Restore the last few exchanges from previous sessions
        history = []
        for user_text, reply in load_recent():
            history.append(types.Content(role="user", parts=[types.Part(text=user_text)]))
            history.append(types.Content(role="model", parts=[types.Part(text=reply)]))
        self.restored_turns = len(history)

        self.llm = JarvisLLM(tools=get_tool_functions(), history=history)

    def ask(self, user_text: str) -> str:
        if re.sub(r"[^a-z ]", "", user_text.lower()).strip() in CLEAR_PHRASES:
            return self._clear_history()

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
        reply = response.text or "Done, Sir."
        save_exchange(user_text, reply)
        return reply

    def _clear_history(self) -> str:
        description = "permanently delete the saved conversation history"
        if self.confirm is None or not self.confirm(description):
            return "Understood, Sir. I have kept the conversation history."
        clear_history()
        self.llm.reset_chat()
        self.restored_turns = 0
        return "Done, Sir. My conversation history has been cleared."
