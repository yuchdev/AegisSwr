import os

import pytest

from aegis_swr.config import settings as settings_module
from aegis_swr.config.settings import Settings
from aegis_swr.core.schemas import IncidentMode, IncidentSource


@pytest.fixture(autouse=True)
def _isolate_runtime_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep ``Settings()`` hermetic across the suite.

    Without this, every ``Settings()`` constructed in a test would merge in the
    developer's real ``~/.local/state/.aegis-swr/config.json`` and any ``AEGIS__*``
    environment overrides, so a local config (e.g. ``backends.ai.provider=openai``)
    would silently flip default-asserting tests. We neutralise the JSON settings
    source (the only caller of ``_read_json_object``) and drop ``AEGIS__*`` env vars
    so unit tests always see pristine schema defaults. The ``CONFIG_JSON`` /
    ``AGENTS_JSON`` path constants are left untouched, so tests asserting the
    canonical config location still see the production values.
    """
    monkeypatch.setattr(settings_module, "_read_json_object", lambda _path: {})
    for key in list(os.environ):
        if key.startswith("AEGIS__"):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def sample_source() -> IncidentSource:
    return IncidentSource(
        mode=IncidentMode.CRASH_DUMP,
        dump_path="tests/unit/fixtures/sample.dmp",
        user_assumption="The service was recently redeployed.",
    )
