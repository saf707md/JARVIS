import logging
import re
from contextlib import closing

from memory.database import get_connection

logger = logging.getLogger("jarvis")

STOP_WORDS = {
    "the", "what", "who", "which", "where", "when", "how", "and", "for", "you",
    "your", "about", "tell", "does", "did", "know", "remember", "that", "with",
}


def remember_fact(fact: str) -> str:
    """Save a fact about the user so it can be remembered in future sessions.

    Use this when the user says "remember ...", "note that ...", or shares a
    personal detail or preference they want kept.

    Args:
        fact: The fact written as one clear sentence, for example "The user's major project is ASAP."
    """
    fact = fact.strip()
    if not fact:
        return "Error: there is nothing to remember."

    with closing(get_connection()) as connection:
        existing = connection.execute(
            "SELECT 1 FROM memories WHERE lower(fact) = lower(?)", (fact,)
        ).fetchone()
        if existing:
            return "I already remember that."
        connection.execute("INSERT INTO memories (fact) VALUES (?)", (fact,))
        connection.commit()

    logger.info("[MEMORY] Saved: %s", fact)
    return f"Remembered: {fact}"


def recall_memories(query: str) -> str:
    """Look up facts previously saved about the user.

    Use this whenever the user asks about themselves, their projects, their
    preferences, or anything they may have asked you to remember.

    Args:
        query: Keywords describing what to look for, for example "major project".
    """
    words = [
        word for word in re.findall(r"\w+", query.lower())
        if len(word) > 2 and word not in STOP_WORDS
    ]

    with closing(get_connection()) as connection:
        rows = connection.execute("SELECT fact FROM memories ORDER BY id DESC").fetchall()

    if not rows:
        return "I have no stored memories yet."

    facts = [row["fact"] for row in rows]
    matches = [fact for fact in facts if any(word in fact.lower() for word in words)]
    chosen = matches or facts

    logger.info("[MEMORY] Retrieved %d memories", len(chosen[:30]))
    heading = "Matching memories" if matches else "No keyword match, so here are all stored memories"
    return heading + ":\n" + "\n".join("- " + fact for fact in chosen[:30])
