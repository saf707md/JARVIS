from memory.conversation import clear_history, load_recent, save_exchange
from memory.memory_manager import forget_memory, recall_memories, remember_fact


def test_remember_and_recall():
    assert remember_fact("The user's major project is JARVIS.").startswith("Remembered")
    assert "JARVIS" in recall_memories("major project")


def test_duplicate_facts_not_stored_twice():
    remember_fact("Likes lofi music.")
    assert remember_fact("likes lofi music.") == "I already remember that."


def test_forget_removes_fact():
    remember_fact("Has a guide meeting on Monday.")
    assert forget_memory("guide").startswith("Forgot 1")
    assert "guide" not in recall_memories("guide").lower().split("memories:")[-1]


def test_forget_refuses_vague_keyword():
    for i in range(7):
        remember_fact(f"Project note number {i}.")
    assert forget_memory("project").startswith("Error")


def test_conversation_history_round_trip():
    save_exchange("hello", "Good morning, Sir.")
    assert load_recent() == [("hello", "Good morning, Sir.")]
    clear_history()
    assert load_recent() == []
