from collections import defaultdict


class ShortTermMemory:
    """In-memory short-term memory. Stores last N messages per session."""

    def __init__(self, max_turns: int = 10):
        self.max_turns = max_turns
        self._store: dict[str, list[dict]] = defaultdict(list)

    def add_message(self, session_id: str, role: str, content: str):
        messages = self._store[session_id]
        messages.append({"role": role, "content": content})
        if len(messages) > self.max_turns * 2:
            self._store[session_id] = messages[-(self.max_turns * 2):]

    def get_history(self, session_id: str) -> list[dict]:
        return list(self._store[session_id])

    def clear(self, session_id: str):
        self._store.pop(session_id, None)


short_term_memory = ShortTermMemory()
