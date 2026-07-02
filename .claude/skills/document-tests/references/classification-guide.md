# Test classification & docstring guide

Backs `/document-tests`. The `scripts/document_tests.py` codemod classifies
**mechanically** from structural signals; this guide gives the **semantic**
definitions you use to hand-resolve the `Ambiguous classification` cases it flags,
plus the docstring format the script emits.

## How the script classifies (match its logic when overriding)

Path first, then body markers:

1. Path contains `e2e` (dir or filename) → **E2E**.
2. Path contains `integration` → **E2E** if the body uses an end-to-end runner,
   else **Integration**.
3. Path contains `unit` → **Mock** if the body uses a mocking marker, else **Unit**.
4. Unrecognised directory → same body-based guess, **flagged `ambiguous`**.

Body markers the script looks for:

- **E2E runners:** `CliRunner`, `TestClient(`, `playwright`, `async_playwright`.
- **Mocking:** `mock.patch`, `@patch`, `MagicMock`, `Mock(`, `monkeypatch`, `mocker.`.

`ambiguous` means "no directory convention matched" — the script guessed from the
body only. Those are the cases you must read and confirm.

## Semantic definitions (the ground truth for resolving ambiguity)

| Class | Real meaning | Aegis examples |
|-------|--------------|----------------|
| **Unit** | Pure logic, no mocks, no I/O. Exercises one function/class in isolation with real inputs. | `ConfidenceLevel.from_score`, consensus weight math, `fault_codes` mapping. |
| **Mock** | Unit-scoped but a collaborator is replaced with a mock/patch/monkeypatch. Tests behaviour *around* an external boundary without hitting it. | An agent node with the `AIAPIBackend` patched; orchestrator routing with mocked stores. |
| **Integration** | Two or more real components wired together, externals mocked at the process edge. Not a pure unit; not a full user flow. | `DataAdapter` + a real debug backend over a fixture dump; store round-trip against a temp SQLite. |
| **E2E** | A full user-facing entry point driven end to end — CLI via `CliRunner`, API via `TestClient`, or browser via Playwright. | `aegis analyze` through `CliRunner`; a FastAPI route through `TestClient`. |

Resolution rule of thumb when the script flags ambiguous:

- Mocks present but only one unit under test → **Mock**, not Integration.
- Real collaborators wired together, external edge mocked → **Integration**.
- A CLI/HTTP/browser runner anywhere in the body → **E2E**, regardless of mocks.
- No mocks, no runners, pure inputs/outputs → **Unit**.

The Aegis convention: `tests/unit/` is CI-gated; `tests/integration/` mocks
externals. A test's *directory* should match its true class — if reading the body
tells you the directory is wrong, that is a finding to raise, not something to
paper over with a mislabelled docstring.

## Docstring format the script emits

Title line must match:
`^\[(Unit|Mock|Integration|E2E)\] <name>: verifies <one sentence>.$`
followed by **Scenario**, **Boundaries**, and **On-failure-first-check** stanzas.

A full worked specimen — one correctly-documented test per class, each also
exhibiting the body signal the codemod keys on — is in
[../example/test-docstring-example.py](../example/test-docstring-example.py).

### Good

```python
def test_from_score_low_below_threshold():
    """[Unit] from_score low: verifies scores under 0.50 map to ConfidenceLevel.LOW.

    Scenario: Call ConfidenceLevel.from_score(0.49) with no mocks or I/O.
    Boundaries: Pure function; exercises only the <0.50 branch.
    On-failure-first-check: If this fails, inspect the 0.50/0.80 thresholds in from_score.
    """
```

### Bad (why)

```python
def test_stuff():                      # non-descriptive name
    """Tests the score thing."""       # no [Class] tag, no 'verifies', no stanzas
```

The bad one fails the title regex, carries no classification, and gives an
on-call reader nothing to act on when it breaks.

## Boundaries of this skill

Docstrings only. Never change test logic, fixtures, assertions, or imports.
Leave any test that already has a custom (non-generated) docstring untouched
unless the user explicitly asked to `--force` that specific file.
