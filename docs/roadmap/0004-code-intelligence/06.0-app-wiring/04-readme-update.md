# 04 - README / docs Code Intelligence pointer

**Parent task:** 06.0 App Wiring & agents.yaml
**State:** ⬜ Not started
**Depends on:** 01 (wiring exists), 02 (dry-run behaviour documented), 03
(`agents.yaml` finalised)
**Blocks:** none (Task 09.0 writes the full `docs/config/openclaude-setup.md` this
section points at)

## Objective

Add a short "Code Intelligence (OpenClaude)" section to the top-level
`README.md` documenting the **minimum enabling environment variable**
(`OPENCLAUDE_GRPC_URL`) and the recommended external-mode launch command, then
forward-link to the full setup guide. This is a deliberately **thin pointer**:
the complete setup/config reference (`docs/config/openclaude-setup.md`,
`docs/config/openclaude-config-reference.md`) is Task 09.0's deliverable. This subtask
only ensures a reader landing on the top-level README can discover that code
intelligence exists, learn the one variable that enables it, and follow a link
to the details.

## File: `README.md` (new section, appended in the appropriate place)

```markdown
## Code Intelligence (OpenClaude)

Aegis SWR can delegate open-ended, multi-file code-navigation tasks to
[OpenClaude](https://github.com/Gitlawb/openclaude) running as a headless gRPC
sidecar pointed at any OpenAI-compatible backend (including a self-hosted vLLM
instance). This capability is **optional** and **off by default**.

**Enable it with a single environment variable** — no Python changes:

    export OPENCLAUDE_GRPC_URL=localhost:50051

When `OPENCLAUDE_GRPC_URL` is unset, code intelligence is simply unavailable and
the rest of the pipeline is unaffected.

**Recommended external-mode launch** (OpenClaude already running, read-only
forensic allowlist):

    # 1. Start OpenClaude yourself (its model/provider is your concern):
    #    set CLAUDE_CODE_USE_OPENAI / OPENAI_BASE_URL / OPENAI_MODEL / OPENAI_API_KEY,
    #    launch it headless with a read-only tool allowlist, then:
    export OPENCLAUDE_GRPC_URL=localhost:50051
    python -m aegis.app            # code intelligence now active

> Aegis SWR does **not** manage OpenClaude's model or provider — you do, via
> OpenClaude's own environment variables. Aegis SWR only needs
> `OPENCLAUDE_GRPC_URL` to find the running server.

See **[docs/config/openclaude-setup.md](/docs/config/openclaude-setup.md)** for the full setup
guide (managed vs external mode, the tool/Bash allowlists, and the complete
environment-variable reference).
```

## Implementation notes

- Keep it short — a few sentences plus the two commands and one forward link.
  Do **not** duplicate the full env-var table from C1; that belongs in Task
  09.0's config reference.
- Mention only `OPENCLAUDE_GRPC_URL` as the minimum enabler. Reference (do not
  enumerate) OpenClaude's own provider vars (`CLAUDE_CODE_USE_OPENAI`,
  `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`) as the operator's concern.
- The forward link target (`docs/config/openclaude-setup.md`) is created by Task 09.0;
  it may not exist yet. Note in the PR that this link resolves once 09.0 lands,
  or gate the doc-link check accordingly. (Do not create a stub that Task 09.0
  would have to overwrite unless the repo's `check_doc_links.py` hard-fails on
  the missing target — in that case add a minimal placeholder that 09.0
  replaces.)
- Use the absolute-from-repo-root link convention (leading `/`) per
  `docs/roadmap/README.md`.
- Do not print or example any real endpoint, token, or credential; use the
  placeholder `localhost:50051`.

## Constraints

- No secrets or credentials in example commands (security rules).
- Thin pointer only — no setup detail that duplicates Task 09.0.
- Markdown links use the absolute-from-repo-root convention with a leading `/`.
- `python scripts/check_doc_links.py docs/` (and the `doc_link_check` hook)
  must pass — coordinate the forward link with Task 09.0's file creation.

## Success criteria

- [ ] Top-level `README.md` has a "Code Intelligence (OpenClaude)" section.
- [ ] The section names `OPENCLAUDE_GRPC_URL` as the minimum enabling variable
      and states that unsetting it disables the capability with no other effect.
- [ ] The section shows the recommended external-mode launch command.
- [ ] The section states Aegis SWR does not manage OpenClaude's model/provider.
- [ ] The section forward-links to `docs/config/openclaude-setup.md` (Task 09.0) using
      the absolute-from-repo-root convention.
- [ ] `check_doc_links.py` passes (once the 09.0 target exists, or via an agreed
      placeholder).
- [ ] No secrets/credentials appear in any example.
