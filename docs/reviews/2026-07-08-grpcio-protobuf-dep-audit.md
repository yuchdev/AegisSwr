# Background Review — grpcio / protobuf / grpcio-tools Dependency Audit — 2026-07-08

**Trigger:** `pyproject.toml` manifest change, Milestone 0004 Task 02.0 subtask 02
(gRPC Proto & Client). **Verdict: CLEAN** (two Low-priority floor-hardening items,
both actioned in the same task).

## Scope

Three dependencies were newly added; this audit covers only those additions and
their immediate transitive impact (not the whole tree). Resolved versions per
`uv.lock`: **grpcio 1.82.1, protobuf 7.35.1, grpcio-tools 1.82.1**.

Advisory sources: OSV (osv.dev), GitHub Advisory Database, Red Hat Security
Advisories, Snyk, CVEDetails. `pip-audit` was not installed in the environment;
WebSearch/WebFetch advisory cross-checks were substituted. Installing
`pip-audit` (`uv add --dev pip-audit`) would enable automated scanning in the
weekly scheduled dep-audit.

## Findings

### Low — protobuf lower bound admitted vulnerable 5.x/6.x sub-ranges *(actioned)*

- **Original constraint:** `protobuf>=4.25,<8`. CVE-2026-0994 (GHSA-7gcm-g887-7qv7,
  CVSS 7.5) is a JSON-recursion-depth-bypass DoS affecting `<=5.29.5` and
  `6.30.0rc1–6.33.4`. The wide floor would let a from-scratch re-lock legally
  resolve into a vulnerable sub-range; the JSON `ParseDict()` path could be
  reachable given the platform ingests untrusted incident payloads.
- **Resolution:** floor tightened to `protobuf>=7.0,<8`. `uv lock` re-run —
  resolution unchanged (still 7.35.1, outside the affected range).

### Low — grpcio floor pre-dated CVE-2024-11407 fix *(actioned)*

- **Original constraint:** `grpcio>=1.60,<2`. CVE-2024-11407 (RHSA-2025:1019,
  CVSS 5.3) affected grpcio before ~1.68.1; CVE-2023-33953 before 1.56.0. Both
  fixed well below the resolved 1.82.1, but the wide floor was a latent regression
  risk if the lockfile were discarded.
- **Resolution:** floor tightened to `grpcio>=1.68.1,<2`. Resolution unchanged
  (still 1.82.1).

## Confirmed CLEAN

| Item | Result |
|------|--------|
| **Licences** | grpcio 1.82.1 Apache-2.0; grpcio-tools 1.82.1 Apache-2.0; protobuf 7.35.1 BSD-3-Clause. No copyleft (GPL/LGPL/AGPL) introduced by any package or its immediate sub-deps. Compatible with proprietary distribution. |
| **grpcio 1.82.1 CVEs** | CVE-2024-11407 (fixed ~1.68.1), CVE-2023-33953 (fixed ~1.56.0) — both below resolved version. CLEAN. |
| **protobuf 7.35.1 CVEs** | CVE-2026-0994 affects ≤5.29.5 / 6.30.0rc1–6.33.4 only; 7.35.1 not in range. (protobuf.js CVE cluster is JavaScript, N/A.) CLEAN. |
| **grpcio-tools 1.82.1 CVEs** | No direct advisories; sub-deps inherit the clean grpcio/protobuf status. CLEAN. |
| **Resolver sanity** | grpcio 1.82.1 declares no protobuf upper bound; qdrant-client 1.18.0 requires `protobuf>=3.20.0` (no ceiling). Both satisfied by 7.35.1. No genuine conflict (`uv lock` succeeded). |
| **Runtime/dev split** | grpcio + protobuf in `[project].dependencies` (runtime — correct); grpcio-tools in `[dependency-groups].dev` only. A `uv sync --no-dev` production install excludes it. Confirmed via `requires-dev` vs `requires-dist` in `uv.lock`. |
| **Yank handling** | grpcio 1.82.0 was yanked upstream (bad protobuf dep spec); the exact pin `grpcio-tools==1.82.1` deliberately skips it, and runtime `grpcio` resolves to 1.82.1 as the highest non-yanked release. Codegen/runtime version parity maintained. |

## Summary

| Severity | Count | Items |
|----------|-------|-------|
| Critical / High / Medium | 0 | — |
| Low | 2 | protobuf & grpcio floors admitted vulnerable sub-ranges — **both actioned** (floors tightened, re-locked, resolution unchanged) |
| Clean | 4 | licences, resolved-version CVEs, runtime/dev split, resolver sanity |

**Per-dependency:** grpcio 1.82.1 — Apache-2.0, clean; protobuf 7.35.1 —
BSD-3-Clause, clean; grpcio-tools 1.82.1 — Apache-2.0, dev-only, exact pin avoids
the yanked 1.82.0.

## Suggested future follow-ups

- Add `pip-audit` to the dev group so the weekly scheduled dep-audit runs
  automated scanning rather than manual advisory cross-checks.
- If `grpcio`'s server component is ever enabled with
  `GRPC_ARG_TCP_TX_ZEROCOPY_ENABLED`, re-check CVE-2024-11407 applicability to
  the channel configuration (currently mitigated by 1.82.1).
