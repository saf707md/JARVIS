import logging
from contextlib import closing

from memory.database import get_connection

logger = logging.getLogger("jarvis")

MAX_CHARS = 800   # long messages are shortened to keep the context small
KEEP_PAIRS = 8    # how many recent exchanges are restored at startup
MAX_STORED = 200  # older exchanges are removed automatically


def _ensure_table(connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_text TEXT NOT NULL,
            reply TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def save_exchange(user_text: str, reply: str) -> None:
    """Save one question and answer. Never raises."""
    try:
        with closing(get_connection()) as connection:
            _ensure_table(connection)
            connection.execute(
                "INSERT INTO conversation (user_text, reply) VALUES (?, ?)",
                (user_text[:MAX_CHARS], reply[:MAX_CHARS]),
            )
            connection.execute(
                "DELETE FROM conversation WHERE id <= (SELECT MAX(id) FROM conversation) - ?",
                (MAX_STORED,),
            )
            connection.commit()
        logger.info("[MEMORY] Conversation saved")
    except Exception as error:
        logger.error("[MEMORY] Could not save conversation: %s", error)


def load_recent(limit: int = KEEP_PAIRS):
    """Return the most recent exchanges as (question, reply) pairs, oldest first."""
    try:
        with closing(get_connection()) as connection:
            _ensure_table(connection)
            rows = connection.execute(
                "SELECT user_text, reply FROM conversation ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [(row["user_text"], row["reply"]) for row in reversed(rows)]
    except Exception as error:
        logger.error("[MEMORY] Could not load conversation: %s", error)
        return []


def clear_history() -> None:
    """Delete all saved conversation history."""
    with closing(get_connection()) as connection:
        _ensure_table(connection)
        connection.execute("DELETE FROM conversation")
        connection.commit()
    logger.info("[MEMORY] Conversation history cleared")
