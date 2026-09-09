"""Database module for AI Health Manager.

This module provides:
- Database session management
- Index management and optimization
- Query optimization utilities
- Connection pool management
"""

from app.database import (
    AsyncSessionLocal,
    get_db,
    init_db,
    engine,
)

__all__ = [
    "AsyncSessionLocal",
    "get_db",
    "init_db",
    "engine",
]
