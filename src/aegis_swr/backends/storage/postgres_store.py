"""PostgreSQL storage backend - stub.

Full implementation (SQLAlchemy async + alembic migration) is deferred to a
dedicated future phase. This stub exists so the factory can return a
``RelationalStore`` for ``provider: postgres`` and the Orchestrator can be
configured in advance without import errors.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from loguru import logger

from aegis_swr.backends.base import RelationalStore
from aegis_swr.config.settings import StorageSettings
from aegis_swr.core.schemas import RCAReport

_MSG = (
    "PostgresStore is a stub. "
    "Implement with SQLAlchemy async + asyncpg in a future phase."
)


class PostgresStore(RelationalStore):
    """PostgreSQL backend stub - all methods raise ``NotImplementedError``"""

    def __init__(self, settings: StorageSettings):
        self._settings = settings
        logger.warning("PostgresStore is a stub and does not persist any data.")

    async def save_report(self, report: RCAReport):
        raise NotImplementedError(_MSG)

    async def get_report(self, incident_id: UUID) -> Optional[RCAReport]:
        raise NotImplementedError(_MSG)

    async def find_by_hash(self, dump_hash: str) -> Optional[RCAReport]:
        raise NotImplementedError(_MSG)

    async def update_hitl_response(
        self,
        incident_id: UUID,
        response: dict[str, object],
    ):
        raise NotImplementedError(_MSG)

    async def load_recent(self, limit: int = 100) -> list[RCAReport]:
        raise NotImplementedError(_MSG)
