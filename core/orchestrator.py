import logging
import re

from google.genai import types

from core import actions
from core.actions import describe_plan
from core.plan_gate import ACTION_TOOLS, CHANGE_TOOLS, describe_call, needs_plan
from core.llm import JarvisLLM
from memory.conversation import clear_history, load_recent, save_exchange
from tools.registry import get_tool_functions, run_tool

logger = logging.getLogger("jarvis")

FALLBACK = "Sir, I couldn't reach my cloud brain right now."
MAX_TOOL_ROUNDS = 8  # safety limit so the AI can't loop forever
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

        actions.new_batch()  # everything done for this request can be undone together
        response = self.llm.send(user_text)
        # Plan state for this request: None (not needed yet), "approved" or "declined"
        self._plan = {"state": None, "done": 0, "changed": False, "approved": [], "done_steps": []}

        for _ in range(MAX_TOOL_ROUNDS):
            if response is None:
                return FALLBACK
            calls = response.function_calls
            if not calls:
                break
            pending = [(call.name, dict(call.args or {})) for call in calls]
            for name, args in pending:
                logger.info("[AGENT] Tool selected: %s %s", name, args)
            results = self._run_round(user_text, pending)
            result_parts = [
                types.Part.from_function_response(name=name, response={"result": result})
                for (name, _), result in zip(pending, results)
            ]
            response = self.llm.send(result_parts)

        if response is None:
            return FALLBACK
        reply = response.text or "Done, Sir."
        save_exchange(user_text, reply)
        return reply

    def _run_round(self, user_text: str, pending: list) -> list:
        """Run one round of tool calls, enforcing the plan rule. Returns one result per call."""
        plan = self._plan
        results = [None] * len(pending)

        # 1. If the AI proposed a plan itself, ask about it first
        for index, (name, args) in enumerate(pending):
            if name == "propose_plan" and plan["state"] is None:
                results[index] = run_tool(name, args, self.confirm)
                plan["state"] = "approved" if "APPROVED" in results[index] else "declined"

        # 2. If it skipped the plan but the request needs one, build it from the calls
        if plan["state"] is None and needs_plan(plan["done"], plan["changed"], pending):
            steps = [f"{step} (already done)" for step in plan["done_steps"]]
            steps += [describe_call(name, args) for name, args in pending if name in ACTION_TOOLS]
            goal = user_text if len(user_text) <= 60 else user_text[:57] + "..."
            logger.info("[SECURITY] Plan required for %d actions; asking the user", len(steps))
            approved = self.confirm is not None and self.confirm(describe_plan({"goal": goal, "steps": steps}))
            plan["state"] = "approved" if approved else "declined"
            if approved:
                plan["approved"] = [(name, args) for name, args in pending if name in ACTION_TOOLS]
            logger.info("[SECURITY] Plan %s", plan["state"])

        # 3. Run the rest
        for index, (name, args) in enumerate(pending):
            if results[index] is not None:
                continue
            if name == "propose_plan":
                results[index] = "A plan was already handled for this request."
                continue
            if name in ACTION_TOOLS and plan["state"] == "declined":
                results[index] = "Cancelled: the user declined the plan, so this was not done."
                continue
            # A step the user just approved in the plan is not asked about a second time
            confirm = (lambda description: True) if (name, args) in plan["approved"] else self.confirm
            results[index] = run_tool(name, args, confirm)
            if name in ACTION_TOOLS and not str(results[index]).startswith("Error") and "declined" not in str(results[index]):
                plan["done"] += 1
                plan["done_steps"].append(describe_call(name, args))
                plan["changed"] = plan["changed"] or name in CHANGE_TOOLS
        return results

    def _clear_history(self) -> str:
        description = "permanently delete the saved conversation history"
        if self.confirm is None or not self.confirm(description):
            return "Understood, Sir. I have kept the conversation history."
        clear_history()
        self.llm.reset_chat()
        self.restored_turns = 0
        return "Done, Sir. My conversation history has been cleared."
