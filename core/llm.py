import logging
import time

from google import genai
from google.genai import types

import config
from core.prompts import SYSTEM_PROMPT

logger = logging.getLogger("jarvis")


class JarvisLLM:
    """The cloud 'brain'. Keeps conversation history and can request tools."""

    def __init__(self, tools=None):
        if not config.GEMINI_API_KEY or config.GEMINI_API_KEY == "your_key_here":
            raise ValueError("No real GEMINI_API_KEY found in .env")
        self.client = genai.Client(api_key=config.GEMINI_API_KEY)
        self.chat = self.client.chats.create(
            model=config.GEMINI_MODEL,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=tools or None,
                # We run tools ourselves, through the security layer
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True
                ),
            ),
        )

    def send(self, message):
        """Send text or tool results to the AI. Returns the response, or None on failure."""
        for attempt in range(4):
            try:
                logger.info("[LLM] Processing request")
                return self.chat.send_message(message)
            except Exception as error:
                text = str(error)
                # 429 = rate limit, 503 = servers busy: wait and retry
                if ("429" in text or "503" in text) and attempt < 3:
                    logger.warning("[LLM] Service busy, retrying in 10 seconds...")
                    time.sleep(10)
                    continue
                logger.error("[LLM] Error: %s", text)
                return None
        return None
