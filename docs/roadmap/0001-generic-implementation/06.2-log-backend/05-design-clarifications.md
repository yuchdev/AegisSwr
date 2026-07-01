# 05 – Design clarifications ← STOP

**Parent milestone:** 6.2 Log Backend – Fluentd Stack
**State:** ⬜ Awaiting answers
**Depends on:** 01, 02, 03, 04 (those can proceed; answers here gate 06–10)
**Blocks:** 06, 07, 08, 09, 10

---

> **Do not start subtasks 06–10 until every question in this document has a
> recorded answer.** Once answered, add the decision in the "Recorded decision"
> cell of each question's table row and mark this subtask ✅.

---

## Why this stop point exists

Fluentd and Fluent Bit are **push pipelines**: services ship logs _into_ the
collector; the collector forwards them onward. They are not designed as
queryable log stores. Making `FluentAdapter.query_window(service, t_start, t_end)`
work therefore requires one of several deployment-side decisions that Aegis
cannot make alone - the answers depend on how the target environment is built
and operated.

The architecture of subtasks 06–10 (HTTP client vs msgpack forward client,
authentication mechanism, buffer topology, Python library selection) is entirely
determined by the answers below.

---

## Questions

### Q1 - Fluent stack variant and version

| Field | Answer |
|-------|--------|
| Is the Fluent stack **Fluentd** (Ruby daemon), **Fluent Bit** (C daemon), or both? | _TBD_ |
| If Fluentd: version series (v1.x, v2.x)? | _TBD_ |
| If Fluent Bit: version series (2.x, 3.x)? | _TBD_ |
| Recorded decision | _TBD_ |

**Why it matters:** Fluentd and Fluent Bit expose completely different HTTP APIs.
Fluent Bit's built-in HTTP server (`port 2020`) exposes metrics and pipeline
state, not queryable log records. Fluentd's HTTP input (`in_http`) receives
forwarded events but does not serve them back. The correct client in subtask 06
or 07 depends entirely on this answer.

---

### Q2 - Pull query mechanism

Aegis needs to *pull* a time-range window of logs; Fluentd/Fluent Bit normally
*push* logs onward. Which of the following deployment patterns is in place (or
will be built)?

| Option | Description | Requires |
|--------|-------------|---------|
| **A** | Fluent stack writes JSON to a local directory; Aegis reads those files | Only `FileLogAdapter` (already done) |
| **B** | A thin HTTP sidecar (Python or otherwise) sits between the Fluent output and Aegis, buffers records, and serves time-range queries | Custom HTTP server + `httpx` client (subtask 06) |
| **C** | Fluentd is configured with `in_http` + a custom Ruby filter that serves a `/query` endpoint | `httpx` client to Fluentd HTTP port (subtask 06) |
| **D** | Fluent Bit is configured with its **HTTP output plugin** and Aegis receives the pushed batches (inversion of control) | Aegis acts as the receiver, not the querier - different design |
| **E** | Direct Fluentd **forward protocol** - Aegis connects to port 24224 and uses msgpack to subscribe to a tag | `msgpack` + forward protocol client (subtask 07) |
| **F** | Something else (describe) | _TBD_ |

| Field | Answer |
|-------|--------|
| Selected option(s) | _TBD_ |
| If B: what technology/framework powers the sidecar? | _TBD_ |
| If C/E: are there constraints on Fluentd plugin installation? | _TBD_ |
| Recorded decision | _TBD_ |

**Why it matters:** Options A–F lead to completely different client code. Option
A means no new network code is needed at all (the stub can be replaced with a
config-directed `FileLogAdapter` wrapper). Options B–C need subtask 06; option E
needs subtask 07; option D inverts the architecture entirely.

---

### Q3 - Authentication and transport security

| Question | Answer |
|----------|--------|
| Does the Fluent endpoint require authentication? (`none \| bearer-token \| mTLS \| basic-auth`) | _TBD_ |
| Is TLS required for the connection to the Fluent endpoint? | _TBD_ |
| Where are credentials stored? (`env-var \| secrets-manager \| vault \| file`) | _TBD_ |
| Should `SensitiveFilter` redact all `fluent_*` credential fields in application logs? | _TBD_ (assumed: yes) |
| Recorded decision | _TBD_ |

**Why it matters:** Subtask 01 already stubs `fluent_auth_token` and TLS fields.
The actual credential injection code in subtask 06/07 depends on the auth model.
mTLS needs a different `httpx.AsyncClient` construction than a bearer token.

---

### Q4 - Multi-service query semantics

| Question | Answer |
|----------|--------|
| Should a single network round-trip fetch all services at once (batch query), or one request per service (fan-out)? | _TBD_ |
| If batch: does the Fluent endpoint support a tag-list/pattern query (`aegis.*`, `aegis.auth \| aegis.order`)? | _TBD_ |
| Maximum number of services expected per incident query? | _TBD_ |
| Should services not found in the Fluent index be silently skipped or surfaced as a warning? | _TBD_ (assumed: warning per subtask 04) |
| Recorded decision | _TBD_ |

**Why it matters:** Subtask 02 already spec'd the fan-out default (N concurrent
`query_window` calls). If the Fluent endpoint supports batch queries, subtask 08
can override `query_window_multi` with a single-request implementation, which
is significantly more efficient for large service counts.

---

### Q5 - Python library selection

The `fluent-logger-python` package (`fluent.sender`) is the canonical Python
client for the Fluentd forward protocol, but it is a **write-only** client
(emitting events to Fluentd, not reading them back). For the read path, options
are:

| Library | Use case | Notes |
|---------|----------|-------|
| `fluent-logger` (`fluent.sender`) | Emitting events to Fluentd | Already available via Poetry? Not currently in `pyproject.toml`. |
| `httpx[asyncio]` | HTTP pull queries to any HTTP endpoint | Already a project dependency? |
| `msgpack` | Direct forward protocol decoding | Requires writing the forward protocol framing manually. |
| `aiohttp` | Alternative async HTTP client | Not currently in dependencies. |

| Question | Answer |
|----------|--------|
| Is `fluent-logger-python` (or `fluent-bit`) already a project dependency? | _TBD_ |
| Should `httpx` be the HTTP client (it is async-native and already in the Python ecosystem)? | _TBD_ |
| Is `msgpack` required (only if forward protocol is chosen)? | _TBD_ |
| Recorded decision | _TBD_ |

**Why it matters:** Any new library must be added to `pyproject.toml` and
audited via the `dep-audit` skill. The chosen library directly determines the
imports and class structure in subtask 06/07.

---

### Q6 - Fluent tag schema and service name mapping

| Question | Answer |
|----------|--------|
| What is the full tag format for a service? (`{prefix}.{service}`, `{service}.{host}`, etc.) | _TBD_ |
| Should service names be sanitised before use as tag components? (e.g. strip `/`, `.`, spaces) | _TBD_ |
| Are wildcard tag queries supported by the chosen mechanism (e.g. `aegis.*`)? | _TBD_ |
| Recorded decision | _TBD_ |

**Why it matters:** Subtask 01 already stubs `fluent_tag_prefix`. The actual
tag construction logic in subtask 08 depends on this answer.

---

### Q7 - Time window and result size expectations

| Question | Answer |
|----------|--------|
| Default incident window: `incident_time ± N minutes` - what is the expected N? | _TBD_ (subtask 01 defaults to 10 min) |
| Expected peak log volume per service per 10-minute window? (lines/records) | _TBD_ |
| Is the `fluent_max_lines_per_service` cap (5000, subtask 01) acceptable, or does it need adjustment? | _TBD_ |
| Should truncation at the cap be logged as a warning? | _TBD_ (assumed: yes) |
| Recorded decision | _TBD_ |

**Why it matters:** Determines whether client-side pagination or streaming is
required. If 5000 lines per service is too low for high-traffic services, the
adapter needs a paginated query loop; if it is too high, it wastes memory.

---

### Q8 - Deployment topology

| Question | Answer |
|----------|--------|
| Is the Fluent stack centralized (one aggregator) or distributed (sidecar per host)? | _TBD_ |
| Is the Fluent endpoint reachable from the machine running Aegis? | _TBD_ |
| Is there a staging / test Fluentd/Fluent Bit instance available for integration tests? | _TBD_ |
| Should integration tests spin up a Fluent stack via Docker Compose, or test against a shared instance? | _TBD_ |
| Recorded decision | _TBD_ |

**Why it matters:** If no test instance is available, the integration test in
subtask 10 must use a mock HTTP server or a pre-recorded response fixture.
Docker Compose approach needs a Fluentd/Fluent Bit image added to
`docker-compose.test.yml`.

---

## What can proceed right now (before answers)

Subtasks 01–04 are fully implementable without these answers:
- **01** - Configuration model (field table is stable regardless of protocol).
- **02** - `query_window_multi` default fan-out implementation (works for any adapter).
- **03** - `FluentRecordParser` (record normalisation is protocol-agnostic).
- **04** - Exception hierarchy (fail-open contract is fixed).

---

## Checklist (fill in when answers arrive)

- [ ] Q1 answered and recorded
- [ ] Q2 answered and recorded
- [ ] Q3 answered and recorded
- [ ] Q4 answered and recorded
- [ ] Q5 answered and recorded
- [ ] Q6 answered and recorded
- [ ] Q7 answered and recorded
- [ ] Q8 answered and recorded
- [ ] This subtask marked ✅
- [ ] Subtasks 06–10 unblocked and implementation specs updated accordingly
