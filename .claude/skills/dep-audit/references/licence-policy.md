# Licence compatibility policy

Deterministic ruling for the licence step of `/dep-audit`. Aegis SWR is
distributed as a **proprietary / commercially-licensed** product, so strong
copyleft is a real distribution risk, not a theoretical one. Classify every
direct dependency's licence into one of the three tiers below and report
accordingly.

## Tiers

### ✅ Allow (permissive — no action)

MIT, BSD-2-Clause, BSD-3-Clause, Apache-2.0, ISC, PSF/Python-2.0, MPL-2.0
(file-level copyleft — fine for a dependency we don't modify), Unlicense, CC0,
Zlib. These impose only attribution/notice obligations. Ensure NOTICE/attribution
is preserved but take no further action.

### ⚠️ Flag (review before shipping)

- **LGPL-2.1 / LGPL-3.0** — usable only if dynamically linked and the user can
  relink; for a Python dep this is usually OK but must be confirmed not vendored
  or statically bundled. Flag for `security-auditor` / legal note.
- **MPL-2.0 when we modify the source** — file-level copyleft triggers.
- **Weak/unusual permissive with extra clauses** (e.g. BSD-4-Clause advertising
  clause, EPL, CDDL) — compatible but note the obligation.
- **Dual-licensed** where one option is copyleft — record which option we elect.

### ⛔ Block (incompatible with proprietary distribution)

- **GPL-2.0 / GPL-3.0** (strong copyleft).
- **AGPL-3.0** (network copyleft — the most dangerous; triggers even for SaaS use).
- **SSPL**, **BUSL/Commons-Clause**, and other source-available/non-OSI licences.
- **No licence / UNKNOWN / "proprietary"** on a third-party package — treat as
  block until identified; an unlicensed dep grants us no rights.

## Ruling procedure

1. Enumerate **direct** deps from `pyproject.toml` (transitive deps inherit the
   obligation but the direct dep is where we act).
2. Identify each licence: prefer `pip-licenses`; fall back to the package's
   metadata / PyPI classifier; last resort `WebSearch` the package + "license".
3. Assign a tier. Any ⛔ is a **blocking** finding; any ⚠️ is a warning that needs
   a human/security-auditor decision; ✅ is silent.
4. For a ⛔ or ⚠️, propose the remedy: a permissively-licensed replacement, or an
   isolation boundary (separate process / optional extra) if the dep is essential.

## Output rows

```
### Licence risks
| Package | Licence | Tier | Action |
| some-agpl-lib | AGPL-3.0 | ⛔ Block | replace with <permissive alt> before release |
| some-lgpl-lib | LGPL-3.0 | ⚠️ Flag | confirm dynamic link only; security-auditor sign-off |
```

Report `UNKNOWN` licences explicitly — a silent omission reads as "all clear"
when it is actually "unclassified".
