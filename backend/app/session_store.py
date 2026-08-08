"""
Session Store Seam Abstraction.

Provides a clean interface for session tracking and auth rate limiting,
defaulting to an in-memory store while allowing future Redis/Memcached implementations
without touching application call sites.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseSessionStore(ABC):
    @abstractmethod
    def get_session(self, username: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def set_session(self, username: str, data: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def delete_session(self, username: str) -> None:
        pass


class InMemorySessionStore(BaseSessionStore):
    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def get_session(self, username: str) -> Optional[Dict[str, Any]]:
        return self._sessions.get(username)

    def set_session(self, username: str, data: Dict[str, Any]) -> None:
        self._sessions[username] = data

    def delete_session(self, username: str) -> None:
        self._sessions.pop(username, None)


# Default global instance
default_session_store = InMemorySessionStore()
