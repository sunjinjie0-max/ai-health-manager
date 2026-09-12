from collections import defaultdict


class ShortTermMemory:
    """In-memory short-term memory. Stores last N messages per session."""

    def __init__(self, max_turns: int = 10):
        self.max_turns = max_turns
        self._store: dict[str, list[dict]] = defaultdict(list)
        self._pending_profile_confirmations: dict[str, list[dict]] = {}

    def add_message(self, session_id: str, role: str, content: str):
        messages = self._store[session_id]
        messages.append({"role": role, "content": content})
        if len(messages) > self.max_turns * 2:
            self._store[session_id] = messages[-(self.max_turns * 2):]

    def get_history(self, session_id: str) -> list[dict]:
        return list(self._store[session_id])

    def clear(self, session_id: str):
        self._store.pop(session_id, None)
        self._pending_profile_confirmations.pop(session_id, None)

    def set_pending_profile_confirmations(self, session_id: str, candidates: list[dict]) -> None:
        """Keep high-risk profile candidates session-local until the user confirms."""
        if not session_id or not candidates:
            return
        merged = list(self._pending_profile_confirmations.get(session_id, []))
        seen = {
            f"{item.get('section')}::{item.get('field')}::{item.get('value')}"
            for item in merged
        }
        for candidate in candidates:
            key = f"{candidate.get('section')}::{candidate.get('field')}::{candidate.get('value')}"
            if key not in seen:
                merged.append(dict(candidate))
                seen.add(key)
        self._pending_profile_confirmations[session_id] = merged

    def get_pending_profile_confirmations(self, session_id: str) -> list[dict]:
        return list(self._pending_profile_confirmations.get(session_id, []))

    def pop_pending_profile_confirmations(self, session_id: str) -> list[dict]:
        return list(self._pending_profile_confirmations.pop(session_id, []))


short_term_memory = ShortTermMemory()
