import pytest

from aegis_swr.config.settings import Settings
from aegis_swr.core.schemas import IncidentMode, IncidentSource


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
