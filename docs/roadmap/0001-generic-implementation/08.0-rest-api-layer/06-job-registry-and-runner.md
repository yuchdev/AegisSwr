# 06 - In-memory job registry + background streaming runner

**Parent milestone:** 8 REST API Layer
**State:** ⬜ Pending
**Depends on:** 04, 05
**Blocks:** 07, 08, 09, 10

## Objective

Bridge HTTP to the engine: a per-process registry of in-flight investigations,
each with an `asyncio.Queue` of War Room events, fed by a background task that
drains `Orchestrator.run_streaming(source)`. This is where "all intermediary
steps from all agents" are captured and made available to the SSE endpoint and
the report endpoint.

## Files

- **Create** `src/aegis_swr/api/jobs.py`

## Symbols

```python
class JobStatus(str, Enum):
    RUNNING = "running"; COMPLETE = "complete"; HITL = "hitl"; ERROR = "error"

@dataclass
class JobState:
    incident_id: str
    status: JobStatus
    queue: asyncio.Queue[dict[str, Any]]   # run_streaming dicts; sentinel on end
    report: Optional[RCAReport] = None
    error: Optional[str] = None
    created_at: datetime = ...

class JobRegistry:
    def create(self, incident_id: str) -> JobState: ...
    def get(self, incident_id: str) -> Optional[JobState]: ...
    def remove(self, incident_id: str): ...

async def run_investigation_job(
    job: JobState,
    orchestrator: Orchestrator,
    source: IncidentSource,
    relational_store: Optional[RelationalStore],
    uploads: Optional[UploadedPaths] = None,
): ...
```

- `run_investigation_job`: iterate `orchestrator.run_streaming(source)`, `put`
  each event dict on `job.queue`; on terminal `complete`/`hitl_request` set
  `job.report` + `job.status`, persist via `relational_store.save_report(report)`;
  on exception set `job.status=ERROR`, `job.error=<sanitised>`; **always** put a
  terminal sentinel (`{"type": "_end"}`) and `cleanup_uploads(uploads)` in a
  `finally`.
- registry is a single `JobRegistry` instance stored on `app.state` (documented
  single-process limitation; multi-worker needs shared state - deferred).
- a bounded `queue` (maxsize) applies backpressure if no consumer is attached.

## Constraints

- The background task is created with `asyncio.create_task` (or FastAPI
  `BackgroundTasks`) and must never crash the event loop - all exceptions are
  caught and turned into an `ERROR` job state + sentinel.
- `job.error` is sanitised (no payload/secret).
- Token usage from the final report is preserved (already in `RCAReport`).
- Document: SSE/registry require `--workers 1`.

## Tests

**Unit / mock** (`tests/unit/test_api_jobs.py`, fake `run_streaming` async gen):

- `test_registry_create_get_remove` - lifecycle; unknown id → `None`.
- `test_runner_enqueues_all_events` - every event from a fake `run_streaming`
  reaches the queue in order, ending with the sentinel.
- `test_runner_complete_sets_report_and_persists` - terminal `complete` →
  `status=COMPLETE`, `report` set, `save_report` called.
- `test_runner_hitl_sets_status` - terminal `hitl_request` → `status=HITL`.
- `test_runner_exception_sets_error_and_sentinel` - a raising generator →
  `status=ERROR`, sanitised `error`, sentinel still enqueued.
- `test_runner_cleans_up_uploads` - `cleanup_uploads` called in `finally`.

## Success criteria

- [ ] Every `run_streaming` event is captured on the per-incident queue, in order,
      terminated by a sentinel.
- [ ] Terminal states set `report`/`status` and persist the report.
- [ ] Exceptions become an `ERROR` job (sanitised), never crash the loop.
- [ ] Uploads are cleaned up after the run.
- [ ] Unit tests pass with a faked orchestrator (no network/LLM).
