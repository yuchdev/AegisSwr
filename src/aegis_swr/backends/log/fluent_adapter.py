"""Fluentd / Fluent Bit log backend — stub.

Shipped as a stub (mirrors ``PostgresStore``) so the factory and config can
select ``provider: fluent`` ahead of a full implementation.

Intended production design (for the future implementer): connect to
``fluent_host:fluent_port``, issue a tag-scoped (``fluent_tag_prefix.{service}``)
time-range query against the Fluent forward/HTTP API, and map the returned
records to log lines. The stub makes no network connection.

See ``docs/specs/PRODUCTION_DESIGN_SPEC.md`` §6.4.2.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from loguru import logger

from aegis_swr.backends.base import LogBackend

if TYPE_CHECKING:
    from aegis_swr.config.settings import LogBackendSettings

_MSG = (
    "FluentAdapter is a stub. "
    "Implement the Fluent forward/HTTP query in a future phase."
)


class FluentAdapter(LogBackend):
    """Fluent backend stub — ``query_window`` raises ``NotImplementedError``."""

    def __init__(self, settings: LogBackendSettings) -> None:
        self._settings = settings
        logger.warning("FluentAdapter is a stub and does not query any log source.")

    async def query_window(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
        severity_levels: list[str] | None = None,
    ) -> list[str]:
        raise NotImplementedError(_MSG)
