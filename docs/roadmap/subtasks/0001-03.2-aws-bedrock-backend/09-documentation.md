# 09 - Configuration & CLI documentation

**Parent milestone:** 3.2 AWS Bedrock Backend
**State:** ✅ Done - verify after subtask 08
**Depends on:** 08
**Blocks:** none

## Objective

Document the Bedrock backend for operators: its config section, auth modes, and
the `--ai` flag. Keep the docs index and cross-links intact.

## Current state

- ✅ `docs/config/config.md` has a `backends.ai.bedrock` section (field table +
  dual-mode authentication note).
- ✅ `docs/config/cli.md` documents `--ai` with the `bedrock` value and the
  required `backends.ai.bedrock.model_id` + `AWS_BEARER_TOKEN_BEDROCK`/AWS-creds
  note.

> Note: the docs live under `docs/config/` (not `docs/configuration/` as the plan
> prose says). Use the real path.

## Files

- **Verify/extend** `docs/config/config.md` - confirm the field table matches the
  `BedrockSettings` defaults after subtask 01/08; add a one-line pointer to
  `.env.example` for the auth variables.
- **Verify/extend** `docs/config/cli.md` - confirm the `--ai` row names all three
  providers and the Bedrock prerequisites.
- **Verify** `docs/README.md` index still references the config docs.

## Constraints

- Docs must state plainly that **no AWS credentials live in config files** -
  auth is environment-only (bearer token or the standard chain).
- All relative links and heading anchors resolve (`/link-check`).

## Tests / validation

- Run `/link-check docs/config/config.md docs/config/cli.md` (or
  `scripts/check_doc_links.py`) - zero dangling links/anchors.
- Manual: the `backends.ai.bedrock` table values equal `BedrockSettings`
  defaults; the auth note matches the provider's dual-mode behaviour.

## Success criteria

- [ ] `config.md` documents every `backends.ai.bedrock` field with correct
      defaults and the dual-mode auth note.
- [ ] `cli.md` documents `--ai bedrock` and its prerequisites.
- [ ] Docs explicitly state credentials are environment-only.
- [ ] `link-check` passes; `docs/README.md` index is current.
