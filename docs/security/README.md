# Security

Threat models, security review outputs, and posture documentation for Aegis SWR.

The `security-auditor` agent owns this directory. Every change touching auth,
secrets, external integrations, or incident-payload ingestion triggers a security
review whose output is stored here.

## Naming convention

`threat-model-<scope>.md` for threat models, `review-<scope>-<YYYY-MM-DD>.md`
for point-in-time reviews.

## What a threat model must contain

1. **Scope** - which components and trust boundaries are in scope.
2. **Assets** - what secrets, PII, and data are handled.
3. **Threat actors** - attacker profiles considered.
4. **STRIDE analysis** - Spoofing, Tampering, Repudiation, Info Disclosure, DoS, Elevation.
5. **Mitigations** - existing controls and open gaps.
6. **Verdict** - CRITICAL (merge blocked) / HIGH / MEDIUM / LOW / INFO.

## Security rules (non-negotiable)

- Never log secrets; rely on `SensitiveFilter` and verify it covers new sinks.
- Never hard-code credentials. Read from settings/env.
- Treat all incident payloads as sensitive - no unredacted dump/log/stack text
  in logs, exceptions, stored reports, or API error bodies.
- Untrusted payload text must never reach a shell, SQL string, `eval`, or an AI
  prompt without sanitisation/parameterisation.

<!-- SME REVIEW NEEDED: populate with first threat model for the ingestion pipeline. -->
