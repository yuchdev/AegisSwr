"""Reference specimen for /document-tests — the docstring format, one per class.

This is a *teaching example*, not a collected test (it lives under `.claude/`,
outside `tests/`, so pytest never runs it). Each function below shows two things
at once:

1. the structural signal `scripts/document_tests.py` keys on to classify it, and
2. the exact docstring the codemod emits and that
   [../references/classification-guide.md](../references/classification-guide.md)
   describes.

Docstring contract (enforced by the codemod's title regex
``^\\[(Unit|Mock|Integration|E2E)\\] .+: verifies .+\\.$``):

    [<Class>] <short name>: verifies <one sentence ending in a period>.

    Scenario: <what is set up and exercised>
    Boundaries: <what is real vs mocked; scope of the test>
    On-failure-first-check: <where to look first when this fails>

Note on classification: the codemod decides by **directory first, then body
markers**. This file is in an unrecognised directory, so the codemod would tag
each case `ambiguous` and fall back to the body signal — exactly the situation
where a human uses the semantic definitions in the classification guide. The
body of each function is written so the *intended* class is unambiguous.
"""

from __future__ import annotations

from unittest import mock

import pytest

from aegis_swr.core.fault_codes import FaultClass, map_linux_signal
from aegis_swr.core.schemas import ConfidenceLevel


# --------------------------------------------------------------------------- #
# [Unit] — pure logic, no mocks, no I/O. Signal: no mock/runner markers.
# --------------------------------------------------------------------------- #
def test_from_score_below_threshold_is_low():
    """[Unit] from_score low branch: verifies a score under 0.50 maps to LOW.

    Scenario: Call ConfidenceLevel.from_score(0.49) with a plain float, no mocks or I/O.
    Boundaries: Pure function; exercises only the <0.50 branch of the threshold ladder.
    On-failure-first-check: If this fails, inspect the 0.50 / 0.80 cutoffs in
        ConfidenceLevel.from_score.
    """
    assert ConfidenceLevel.from_score(0.49) is ConfidenceLevel.LOW


# --------------------------------------------------------------------------- #
# [Mock] — unit-scoped, but a collaborator is patched. Signal: mock./monkeypatch.
# --------------------------------------------------------------------------- #
def test_signal_mapping_uses_lookup_table(monkeypatch: pytest.MonkeyPatch):
    """[Mock] signal mapping: verifies map_linux_signal delegates to its lookup table.

    Scenario: monkeypatch the module's _SIGNAL_MAP to a controlled entry, then map a signal.
    Boundaries: Only the one function under test runs for real; the table it reads is a mock.
    On-failure-first-check: If this fails, check that map_linux_signal reads _SIGNAL_MAP
        rather than hard-coding the mapping.
    """
    monkeypatch.setattr(
        "aegis_swr.core.fault_codes._SIGNAL_MAP",
        {11: FaultClass.MEMORY_ACCESS_VIOLATION},
    )
    assert map_linux_signal(11) is FaultClass.MEMORY_ACCESS_VIOLATION
    # An unmapped signal still falls back to UNKNOWN through the patched table.
    assert map_linux_signal(99) is FaultClass.UNKNOWN


# --------------------------------------------------------------------------- #
# [Integration] — two+ real components wired together, external edge mocked.
# Signal: no e2e runner, real collaborators. (Body is an illustrative sketch.)
# --------------------------------------------------------------------------- #
@pytest.mark.skip(reason="illustrative sketch — shows the [Integration] shape, not a live test")
def test_report_store_round_trip(tmp_path):
    """[Integration] store round-trip: verifies a saved RCAReport reloads by dump_hash.

    Scenario: Persist an RCAReport to a real filesystem store rooted at tmp_path,
        then load it back through the store's find_by_hash.
    Boundaries: Real store + real serialisation wired together; only the on-disk
        location is a test fixture (tmp_path). No AI backend, no network.
    On-failure-first-check: If this fails, compare the serialised dump_hash written
        to disk against the value find_by_hash queries with.
    """
    # from aegis_swr.backends.store.filesystem import FilesystemStore
    # store = FilesystemStore(root=tmp_path)
    # report = make_report(dump_hash="abc123")
    # await store.save_report(report)
    # assert (await store.find_by_hash("abc123")).dump_hash == "abc123"
    ...


# --------------------------------------------------------------------------- #
# [E2E] — a full user entry point driven end to end. Signal: CliRunner/TestClient.
# (Body is an illustrative sketch of the runner shape.)
# --------------------------------------------------------------------------- #
@pytest.mark.skip(reason="illustrative sketch — shows the [E2E] shape, not a live test")
def test_analyze_cli_reports_fault_class():
    """[E2E] analyze CLI: verifies `aegis analyze` prints the resolved fault class.

    Scenario: Invoke the Typer app through CliRunner with a fixture dump and mocked
        AI backend, then assert on the rendered CLI output.
    Boundaries: The whole CLI entry point runs (parsing → orchestrator → view); only
        the external AI backend is mocked at the process edge.
    On-failure-first-check: If this fails, run the same command manually and compare
        the fault_class line in the output to the fixture's expected class.
    """
    # from typer.testing import CliRunner
    # from aegis_swr.cli.commands import app
    # with mock.patch("aegis_swr.backends.ai.factory.build_ai_backend", return_value=FakeAI()):
    #     result = CliRunner().invoke(app, ["analyze", "--dump", "fixtures/av.dmp"])
    # assert result.exit_code == 0
    # assert "memory_access_violation" in result.stdout
    _ = mock  # referenced so the [E2E]/[Mock] body markers are visible to the codemod
