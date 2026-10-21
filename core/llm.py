import logging
import time

from google import genai
from google.genai import types

import config
from core.prompts import SYSTEM_PROMPT

logger = logging.getLogger("jarvis")


class JarvisLLM:
    """The cloud 'brain'. Keeps chat history, can request tools, and switches
    to a backup model if the current one is busy or unavailable."""

    def __init__(self, tools=None):
        if not config.GEMINI_API_KEY or config.GEMINI_API_KEY == "your_key_here":
            raise ValueError("No real GEMINI_API_KEY found in .env")
        self.client = genai.Client(api_key=config.GEMINI_API_KEY)
        self.tools = tools
        backups = [name for name in config.GEMINI_FALLBACK_MODELS if name != config.GEMINI_MODEL]
        self.models = [config.GEMINI_MODEL] + backups
        self.model_index = 0
        self.chat = self._new_chat()

    @property
    def model_name(self) -> str:
        return self.models[self.model_index]

    def _new_chat(self, history=None):
        chat_config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=self.tools or None,
            # We run tools ourselves, through the security layer
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        return self.client.chats.create(
            model=self.model_name, config=chat_config, history=history
        )

    def _switch_model(self) -> bool:
        """Move to the next backup model, keeping the conversation. False if none are left."""
        if self.model_index + 1 >= len(self.models):
            return False
        try:
            history = self.chat.get_history(curated=True)
        except Exception:
            history = None
        self.model_index += 1
        logger.warning("[LLM] Switching to backup model: %s", self.model_name)
        try:
            self.chat = self._new_chat(history or None)
        except Exception:
            self.chat = self._new_chat()
        return True

    def send(self, message):
        """Send text or tool results to the AI. Returns the response, or None on failure."""
        reset_tried = False
        while True:
            for attempt in range(2):
                try:
                    logger.info("[LLM] Processing request (%s)", self.model_name)
                    return self.chat.send_message(message)
                except Exception as error:
                    text = str(error)
                    busy = "429" in text or "503" in text
                    gone = "404" in text or "NOT_FOUND" in text
                    if busy and attempt == 0:
                        logger.warning("[LLM] Service busy, retrying in 8 seconds...")
                        time.sleep(8)
                        continue
                    if busy or gone:
                        break  # give up on this model and try the next one
                    if "400" in text and isinstance(message, str) and not reset_tried:
                        # The carried-over conversation may not suit this model: start fresh
                        reset_tried = True
                        logger.warning("[LLM] Conversation rejected, starting a fresh chat")
                        self.chat = self._new_chat()
                        continue
                    logger.error("[LLM] Error: %s", text)
                    return None

            if not self._switch_model():
                logger.error("[LLM] All models are busy or unavailable")
                return None
