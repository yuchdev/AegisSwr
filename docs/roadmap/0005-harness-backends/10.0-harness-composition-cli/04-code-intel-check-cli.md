# 04 - aegis code-intel check backend-agnostic CLI

**Parent task:** 10.0 Harness Composition Root & CLI
**State:** ⬜ Not started
**Depends on:** 01 (`harness.composition.build_code_agent`), 02
(`settings.harness` field); Task 04.0 (Claude Code auth-mode resolution and probe,
surfaced through this command per C7)
**Blocks:** none

## Objective

Make `aegis code-intel check` backend-agnostic. Today the command imports
`build_code_agent` from `aegis_swr.openclaude.composition`, passes
`settings.openclaude`, and prints OpenClaude-specific text ("registered
(OpenClaude)", "OPENCLAUDE_GRPC_URL unset"). After this subtask it imports the
factory from `aegis_swr.harness.composition`, passes `settings.harness`, and
reports **which** backend is active — or that the capability is unavailable — for
**every** C2 selection outcome. For the `claude_code` backend it additionally
reports the resolved auth mode (C4 / C7).

This is the operator-facing smoke test for the generalized composition factory
and the visible surface of the C2 selection contract.

## Reporting matrix (every C2 outcome must be covered)

| Harness state                      | `active_backend`                      | CLI output                                                                   | Exit     |
|------------------------------------|---------------------------------------|------------------------------------------------------------------------------|----------|
| selector unset, zero signals       | `None`                                | "Code intelligence unavailable (no backend active; no presence signal set)." | 0        |
| selector unset, exactly one signal | that family                           | "Code intelligence backend active: `<family>`…"                              | 0        |
| selector unset, >1 signal          | (raises at `Settings()` construction) | `HarnessConfigError` surfaced as a clear, secret-free error message          | non-zero |
| selector = X, X's signal present   | X                                     | "Code intelligence backend active: `X`…"                                     | 0        |
| selector = X, X's signal absent    | (raises at composition)               | `HarnessUnavailableError` surfaced as a clear, secret-free error message     | non-zero |
| active = `claude_code`             | `claude_code`                         | "…active: `claude_code` (auth mode: `<auto\|api_key\|subscription>`)…"       | 0        |

`HarnessConfigError` is raised while constructing `Settings()` (C2, Task 01.0),
so it must be caught around construction, not only around the async run.
`HarnessUnavailableError` is raised inside `build_code_agent` (subtask 01) at
composition/health-check time.

## File: `src/aegis_swr/cli/commands.py` (import + command — updated)

```python
# was: from aegis_swr.openclaude.composition import build_code_agent
from aegis_swr.harness.composition import build_code_agent
from aegis_swr.harness.exceptions import HarnessConfigError, HarnessUnavailableError


@code_intel_app.command("check")
def code_intel_check(
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run/--no-dry-run",
            help="Exercise the wiring only: build and register the active backend "
            "without entering any sidecar (no health check, no managed spawn) or "
            "opening any connection. --no-dry-run additionally health-checks / "
            "starts the active backend and tears it down again.",
        ),
    ] = True,
):
    """Verify the optional, backend-agnostic code-intelligence wiring.

    Operator-facing smoke test for the harness composition factory
    (:func:`aegis_swr.harness.composition.build_code_agent`). It reports **which**
    backend is active — ``openclaude``, ``claude_code`` (with its resolved C7
    auth mode), or ``openhands`` — or that the capability is unavailable, for
    every C2 selection outcome.

    Selection is resolved at settings-construction time (C2): more than one
    presence signal with no explicit selector raises
    :class:`HarnessConfigError` here; an explicitly-selected backend whose signal
    is absent raises :class:`HarnessUnavailableError` at composition time. With
    ``--dry-run`` (the default) the active backend's object graph is built and
    registered but no sidecar is entered and no connection/spawn occurs (C4/C13);
    ``--no-dry-run`` additionally exercises the sidecar lifecycle where the
    backend has one.
    """
    try:
        settings = Settings()  # C2 ambiguity (unset + >1 signal) raises here
    except HarnessConfigError as exc:
        console.print(
            f"[red]Code-intelligence configuration error[/red]: {exc}"
        )  # exc carries only field/backend/signal names, never secrets (C2/C13)
        raise typer.Exit(code=2) from exc

    bus = EventBus()
    active = settings.harness.active_backend

    async def _run() -> bool:
        """Build the code agent and confirm the active backend registered."""
        async with AsyncExitStack() as stack:
            agent = await build_code_agent(
                settings.harness,
                bus,
                stack,
                run_id=str(uuid4()),
                dry_run=dry_run,
            )
            return agent.available

    try:
        available = asyncio.run(_run())
    except HarnessUnavailableError as exc:
        console.print(
            f"[red]Code intelligence unavailable[/red]: selected backend "
            f"'{active}' is not reachable/enabled ({exc})."
        )
        raise typer.Exit(code=1) from exc

    if available and active is not None:
        suffix = " (dry-run: sidecar not started)" if dry_run else ""
        detail = _active_backend_detail(settings.harness, active)  # e.g. auth mode for claude_code
        # Parentheses, not brackets: rich parses a [...] suffix as markup.
        console.print(
            f"[green]Code intelligence backend active: {active}{detail}{suffix}.[/green]"
        )
    else:
        console.print(
            "[yellow]Code intelligence unavailable[/yellow] "
            "(no backend active; no presence signal set)."
        )


def _active_backend_detail(harness: HarnessSettings, active: str) -> str:
    """Return a short, secret-free parenthetical detail for the active backend.

    For ``claude_code`` this reports the resolved C7 auth mode
    (``auto`` | ``api_key`` | ``subscription``); other backends add no detail.
    The auth **mode** is a non-secret enum — no token, key, or credential-file
    content is ever included (C7/C13).

    :param harness: The composed ``settings.harness`` sub-settings.
    :param active: The resolved active backend family name.
    :return: A parenthetical string (possibly empty) to append to the status line.
    """
    if active == "claude_code":
        return f" (auth mode: {harness.claude_code.auth_mode})"
    return ""
```

## Implementation notes

- **`HarnessConfigError` is caught around `Settings()` construction**, not around
  the async run — C2 resolves ambiguity at settings-construction time (Task 01.0).
  `HarnessUnavailableError` is caught around `build_code_agent` (composition
  time). Keep the two catches distinct and their messages distinct (they are
  different failure classes per C2).
- **Only the auth *mode* is printed for Claude Code (C7/C13).** `auth_mode` is a
  non-secret enum sourced from `CLAUDE_CODE_AUTH_MODE`. Never print or log the
  token, `ANTHROPIC_API_KEY`, or credential-file contents. The startup auth-probe
  (Task 04.0) may surface a `ClaudeCodeUnavailableError`; under `--no-dry-run`
  that propagates through `HarnessUnavailableError`-style handling — report the
  failure *reason* enum only (e.g. `no_stored_login`), never the credential.
- **Dry-run wording generalizes.** The 0004 text said "process not started"
  (OpenClaude-specific); the new text says "sidecar not started", which is
  accurate for `openclaude`/`openhands` and harmless for `claude_code` (no
  sidecar; its one-shot subprocess is never spawned under dry-run either).
- **`settings.harness` replaces `settings.openclaude`** in the call (the subtask
  02 migration). This command is the "CLI subcommand" C12 names as a migration
  target.
- **No new composition logic in the CLI.** The command only calls the factory and
  formats the result; it must **not** branch on the backend family to build
  anything (that branch lives solely in `harness/composition.py`, C4). The only
  family-conditional here is the cosmetic `_active_backend_detail` string.
- **Exit codes.** Unavailable-by-absence is a clean `0` (capability simply off,
  0004 parity). `HarnessUnavailableError` (operator selected a backend that is
  not reachable) is a non-zero failure. `HarnessConfigError` (ambiguous config)
  is a distinct non-zero code so scripts can tell the two apart.

## Constraints

- The command imports `build_code_agent` from `aegis_swr.harness.composition`,
  not `aegis_swr.openclaude.composition` (which no longer exists, subtask 01).
- It reports the active backend (or "unavailable") for **every** C2 outcome (C4).
- For `claude_code` it reports the resolved auth mode; never a secret (C7/C13).
- No backend-build branch in the CLI — the sole C4 branch stays in
  `harness/composition.py` (C4).
- `--dry-run` (default) opens no connection and spawns no process for any backend
  (C4/C13).
- `HarnessConfigError` and `HarnessUnavailableError` are surfaced as clear,
  secret-free messages with distinct exit codes (C2/C13).
- `Optional[T]` from `typing`; `from __future__ import annotations`; loguru +
  `SensitiveFilter`; no secret/credential/payload text in output or logs (C13).
- `ruff check src/ tests/` - clean.

## Success criteria

- [ ] `aegis code-intel check` imports the factory from `aegis_swr.harness.composition` and passes `settings.harness`.
- [ ] Selector unset plus zero signals → unavailable (no backend active…), exit 0.
- [ ] Selector unset plus exactly one signal → backend active: `<family>`, exit 0.
- [ ] `active == "claude_code"` → output includes "auth mode: `<auto|api_key|subscription>`" and **no** token/key value (C7/C13).
- [ ] Selector unset plus more than one signal → `HarnessConfigError` reported clearly, distinct non-zero exit, a message carries only field/signal names (C2/C13).
- [ ] Selector set to a backend whose signal is absent → `HarnessUnavailableError` reported clearly, non-zero exit (C2).
- [ ] `--dry-run` (default) opens no connection / spawns no process for any backend; `--no-dry-run` exercises the sidecar lifecycle where present.
- [ ] No OpenClaude-specific text remains; no secret/credential appears in any output path (C13).
- [ ] `ruff check src/ tests/` - clean.
