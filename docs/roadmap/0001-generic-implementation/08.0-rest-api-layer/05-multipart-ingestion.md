# 05 - Multipart upload ingestion

**Parent milestone:** 8 REST API Layer
**State:** ⬜ Pending
**Depends on:** 04
**Blocks:** 06

## Objective

Accept incident artifacts as `multipart/form-data` uploads, persist them safely
to per-incident storage, and hand back the local paths needed to build an
`IncidentSource`. Treat every byte as hostile.

## Files

- **Create** `src/aegis_swr/api/ingestion.py`

## Symbols

```python
@dataclass
class UploadedPaths:
    dump: Optional[str]
    logs: list[str]
    shots: list[str]
    pcaps: list[str]
    syms: list[str]
    workdir: Path          # per-incident temp dir for cleanup

async def ingest_upload(
    incident_id: str,
    form: "starlette.datastructures.FormData",
    settings: Settings,
    object_store: Optional[ObjectStore] = None,
) -> tuple[UploadedPaths, AnalyzeOptions]: ...

def cleanup_uploads(paths: UploadedPaths) -> None: ...
```

- file fields: `dump` (single), `log`/`shot`/`pcap`/`sym` (repeatable); plus an
  `options` text field carrying the `AnalyzeOptions` JSON.
- stream each `UploadFile` to a per-incident workdir
  (`<tmp>/aegis-uploads/<incident_id>/`) in chunks (never read whole into RAM).
- **size cap** per file and per request from a new
  `APISettings.max_upload_mb` (default e.g. 1024); exceed → `413`.
- **content guard**: sanitise filenames (basename only, no traversal); optional
  magic-byte sanity for the dump.
- when an `ObjectStore` is configured, also `upload_raw()` the dump for later
  retrieval (subtask 09) and record the object key.
- `cleanup_uploads` removes the workdir; called by the job runner after the run
  (subtask 06), and on ingestion failure.

## Constraints

- No raw payload bytes logged; log only filename + size + incident id.
- Path-traversal-safe: resolved paths must stay within the workdir.
- Streamed I/O via `aiofiles`/`await file.read(chunk)`; never block the loop.
- Malformed `options` JSON → `422` with a sanitised detail.

## Tests

**Unit / mock** (`tests/unit/test_api_ingestion.py`, fabricate `UploadFile`s):

- `test_ingest_saves_dump_and_logs` - files written to the workdir; paths returned.
- `test_ingest_parses_options_json` - the `options` field → `AnalyzeOptions`.
- `test_ingest_rejects_oversize` - a file beyond `max_upload_mb` → `413`.
- `test_ingest_sanitises_filenames` - a `../evil` filename is reduced to a safe
  basename inside the workdir.
- `test_ingest_bad_options_json_422` - invalid JSON → `422`.
- `test_cleanup_removes_workdir` - `cleanup_uploads` deletes the per-incident dir.
- `test_ingest_uploads_to_object_store` - with an `ObjectStore`, `upload_raw` is
  called and the key recorded (mock store).

## Success criteria

- [ ] Uploads stream to a per-incident workdir without loading whole files in RAM.
- [ ] Size caps enforced (413); filenames traversal-safe.
- [ ] `options` JSON parsed into `AnalyzeOptions` (422 on bad JSON).
- [ ] Workdir cleaned up after use; no payload bytes logged.
- [ ] Unit tests pass with fabricated uploads (no network).
