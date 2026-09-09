"""Database optimization utilities for AI Health Manager."""

import logging
from typing import Any

from sqlalchemy import text

from app.models.database import engine

logger = logging.getLogger(__name__)


class IndexManager:
    """Manage database indexes for common query patterns."""

    RECOMMENDED_INDEXES: dict[str, list[dict[str, Any]]] = {
        "users": [
            {"columns": ["username"], "unique": True},
            {"columns": ["created_at"], "unique": False},
        ],
        "user_profiles": [
            {"columns": ["user_id"], "unique": True},
            {"columns": ["updated_at"], "unique": False},
        ],
        "chat_sessions": [
            {"columns": ["user_id", "updated_at"], "unique": False},
        ],
        "chat_messages": [
            {"columns": ["session_id", "created_at"], "unique": False},
        ],
    }

    @classmethod
    async def create_index(
        cls,
        table_name: str,
        columns: list[str],
        index_name: str | None = None,
        unique: bool = False,
    ) -> bool:
        """Create an index if it does not already exist."""
        index_name = index_name or f"idx_{table_name}_{'_'.join(columns)}"
        unique_sql = "UNIQUE" if unique else ""
        columns_sql = ", ".join(columns)

        try:
            async with engine.begin() as conn:
                exists = await conn.execute(
                    text(
                        """
                        SELECT name FROM sqlite_master
                        WHERE type='index' AND name=:index_name
                        """
                    ),
                    {"index_name": index_name},
                )
                if exists.scalar():
                    return True

                await conn.execute(
                    text(
                        f"CREATE {unique_sql} INDEX {index_name} "
                        f"ON {table_name} ({columns_sql})"
                    )
                )
                logger.info("Created index %s on %s(%s)", index_name, table_name, columns_sql)
                return True
        except Exception as exc:
            logger.warning("Failed to create index %s: %s", index_name, exc)
            return False

    @classmethod
    async def setup_recommended_indexes(cls) -> dict[str, bool]:
        """Create all recommended indexes."""
        results: dict[str, bool] = {}
        for table_name, indexes in cls.RECOMMENDED_INDEXES.items():
            for index_config in indexes:
                columns = index_config["columns"]
                index_name = f"idx_{table_name}_{'_'.join(columns)}"
                results[index_name] = await cls.create_index(
                    table_name=table_name,
                    columns=columns,
                    unique=index_config.get("unique", False),
                )
        return results

    @classmethod
    async def list_indexes(cls, table_name: str | None = None) -> list[dict[str, Any]]:
        """List database indexes."""
        try:
            async with engine.begin() as conn:
                if table_name:
                    result = await conn.execute(
                        text(
                            """
                            SELECT name, tbl_name, sql
                            FROM sqlite_master
                            WHERE type='index' AND tbl_name=:table_name
                            """
                        ),
                        {"table_name": table_name},
                    )
                else:
                    result = await conn.execute(
                        text(
                            """
                            SELECT name, tbl_name, sql
                            FROM sqlite_master
                            WHERE type='index'
                            """
                        )
                    )

                return [
                    {"name": row[0], "table": row[1], "sql": row[2]}
                    for row in result.fetchall()
                ]
        except Exception as exc:
            logger.warning("Failed to list indexes: %s", exc)
            return []


class QueryOptimizer:
    """Query optimization helper namespace."""

    @staticmethod
    def health_data_filters(
        user_id: str,
        record_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Build reusable health-data filter metadata."""
        filters: dict[str, Any] = {"user_id": user_id}
        if record_type:
            filters["record_type"] = record_type
        if start_date:
            filters["start_date"] = start_date
        if end_date:
            filters["end_date"] = end_date
        return filters


class ConnectionPoolManager:
    """Expose lightweight pool configuration/status helpers."""

    @staticmethod
    async def get_pool_status() -> dict[str, Any]:
        pool = engine.sync_engine.pool
        status = pool.status() if hasattr(pool, "status") else "unavailable"
        return {"status": status}

    @staticmethod
    async def configure_pool(
        pool_size: int = 10,
        max_overflow: int = 20,
        pool_timeout: int = 30,
        pool_recycle: int = 3600,
    ) -> dict[str, int]:
        """Return desired pool settings for deployment configuration."""
        return {
            "pool_size": pool_size,
            "max_overflow": max_overflow,
            "pool_timeout": pool_timeout,
            "pool_recycle": pool_recycle,
        }
