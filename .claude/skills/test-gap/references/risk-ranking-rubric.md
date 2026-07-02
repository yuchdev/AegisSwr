# Test-gap risk-ranking rubric

Expands the P0/P1/P2 tiers in `SKILL.md` with Aegis-specific criteria and
concrete module examples, so the `testing-expert` agent ranks uncovered code
consistently across runs. The ranking question is always: *if this uncovered
branch is wrong, what is the blast radius?*

## P0 — must test (safety- or correctness-critical)

An untested defect here causes a missed escalation, a wrong RCA acted on, or a
security exposure. Rank first.

- **Consensus & convergence** (`core/consensus.py`, `orchestrator._skeptic_node`,
  `_route_after_skeptic`): the three-part convergence rule, the max-rounds → HITL
  fallback, weight application per fault class. A bug here can silently ship a
  weak report or loop forever.
- **Escalation / HITL paths** (`orchestrator._hitl_node`, `_build_report` HITL
  branch, `HITLRequest` construction): a genuinely inconclusive investigation
  must always produce a `HITLRequest`.
- **Payload / dump / log parsing** (`data_adapter`, debug backends, `fault_codes`
  mapping): attacker-influenced input; malformed dumps must fail safe, not crash
  or leak.
- **Security-relevant branches** (`SensitiveFilter`, secret redaction, auth on API
  routes, anything reading env/settings): a gap here is a disclosure risk.
- **De-duplication** (`incident_similarity`, the `run` cache gate): both
  over-suppression (missed incident) and under-suppression (alert fatigue).

## P1 — should test (behavioural correctness)

Wrong output but bounded blast radius; caught downstream or degrades gracefully.

- Backend strategy implementations (AI/debug/store/log/code) and their factories.
- Orchestrator node folding (`_fold_turn`, token accumulation, primary-hypothesis
  propagation).
- Schema validation & serialisation round-trips (`RCAReport`, `IncidentBrief`,
  `InvestigationState`), including `Optional` fields and defaults.
- `DomainEvent` emission from node updates (`_events_from_update`).

## P2 — nice to have (low-risk / cosmetic)

- CLI/view formatting, Rich/TUI rendering.
- Logging output shape (beyond the redaction guarantee, which is P0).
- Help text, argument parsing niceties.

## Ranking procedure

1. Map each uncovered line/branch (from `--cov-report=term-missing`) to a
   behaviour, not just a line number.
2. Ask the blast-radius question; assign the highest tier that applies.
3. Within a tier, order by likelihood × reachability (a hot path beats a rare
   error branch).
4. For each P0, name a concrete suggested test (input → expected outcome), so the
   list is directly actionable by `testing-expert`.

## Anti-patterns

- Ranking by coverage-percentage delta instead of risk (a 2% gain over consensus
  logic beats a 20% gain over CLI formatting).
- Listing "add tests for module X" without the specific untested behaviour.
- Treating a security/redaction branch as P1 because it "looks simple".
