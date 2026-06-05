"""Filesystem storage backend.

Stores ``RCAReport`` objects as JSON files and raw binary artifacts as files on
disk. Suitable for local development, CI, and single-host deployments.

Directory layout::

    reports_dir/
        {incident_id}.json          # one report per incident
        _hash_index/
            {dump_hash}             # content = incident_id (plain text)

    objects_dir/
        {incident_id}/
            {filename}              # raw binary artifacts
"""
from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path
from uuid import UUID

from loguru import logger

from aegis_swr.backends.base import ObjectStore, RelationalStore
from aegis_swr.core.exceptions import IncidentNotFoundError
from aegis_swr.core.schemas import RCAReport
from aegis_swr.config.settings import StorageSettings


def _safe_path(base: Path, *parts: str) -> Path:
    """Resolve and validate that the joined path stays inside *base*"""
    candidate = base.joinpath(*parts).resolve()
    if not str(candidate).startswith(str(base.resolve())):
        raise ValueError(f"Path traversal attempt: {parts!r} escapes {base}")
    return candidate


def _report_to_markdown(report: RCAReport) -> str:
    """Render *report* as a human-readable Markdown document"""
    lines: list[str] = []

    lines.append(f"# RCA Report — {report.incident_id}")
    lines.append("")
    lines.append(f"**Created:** {report.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}  ")
    lines.append(f"**Mode:** {report.mode.value}  ")
    if report.dump_hash:
        lines.append(f"**Dump Hash:** `{report.dump_hash}`  ")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Root cause
    lines.append("## Root Cause")
    lines.append("")
    lines.append(report.root_cause)
    lines.append("")
    if report.faulting_module:
        lines.append(f"**Faulting Module:** `{report.faulting_module}`  ")
    if report.faulting_function:
        lines.append(f"**Faulting Function:** `{report.faulting_function}`  ")
    conf_pct = f"{report.confidence_score:.1%}"
    lines.append(f"**Confidence:** {conf_pct} ({report.confidence_level.value.upper()})  ")
    if report.symbol_resolution_score is not None:
        lines.append(f"**Symbol Resolution Score:** {report.symbol_resolution_score:.2f}  ")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Agent dialogue
    if report.agent_dialogue:
        lines.append("## Agent Dialogue")
        lines.append("")
        lines.append("| Round | Agent | Conf | Message |")
        lines.append("|-------|-------|------|---------|")
        for turn in report.agent_dialogue:
            msg = turn.message.replace("\n", " ").replace("|", "\\|")
            if len(msg) > 200:
                msg = msg[:200] + "…"
            conf = f"{turn.confidence_score:.0%}"
            lines.append(f"| {turn.turn_number} | {turn.agent} | {conf} | {msg} |")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Skeptic challenges
    if report.skeptic_challenges:
        lines.append("## Skeptic Challenges")
        lines.append("")
        for challenge in report.skeptic_challenges:
            lines.append(f"- {challenge}")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Probabilistic fix
    if report.probabilistic_fix:
        fix_conf = f"{report.fix_confidence:.1%}" if report.fix_confidence is not None else "n/a"
        lines.append(f"## Probabilistic Fix  *(confidence {fix_conf})*")
        lines.append("")
        lines.append("```diff")
        lines.append(report.probabilistic_fix)
        lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Mitigation
    if report.mitigation_instructions:
        lines.append("## Mitigation Instructions")
        lines.append("")
        for i, step in enumerate(report.mitigation_instructions, 1):
            lines.append(f"{i}. {step}")
        lines.append("")
        lines.append("---")
        lines.append("")

    # HITL
    if report.hitl_request:
        lines.append("## Human Input Required")
        lines.append("")
        lines.append(f"**Question:** {report.hitl_request.question}")
        lines.append("")
        lines.append(report.hitl_request.context_summary)
        lines.append("")
        for item in report.hitl_request.requested_data:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Metrics
    lines.append("## Metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Consensus rounds | {report.consensus_rounds} |")
    lines.append(f"| Input tokens | {report.total_input_tokens:,} |")
    lines.append(f"| Output tokens | {report.total_output_tokens:,} |")
    lines.append("")

    return "\n".join(lines)


class FilesystemStore(RelationalStore, ObjectStore):
    """JSON-file and binary-file storage; implements both ABCs"""

    def __init__(self, settings: StorageSettings):
        self._reports_dir = Path(settings.reports_dir).expanduser()
        self._objects_dir = Path(settings.objects_dir).expanduser()
        self._hash_index_dir = self._reports_dir / "_hash_index"

    # ------------------------------------------------------------------
    # RelationalStore
    # ------------------------------------------------------------------

    async def save_report(self, report: RCAReport):
        await asyncio.to_thread(self._sync_save_report, report)

    def _sync_save_report(self, report: RCAReport):
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        path = _safe_path(self._reports_dir, f"{report.incident_id}.json")
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        md_path = _safe_path(self._reports_dir, f"{report.incident_id}.md")
        md_path.write_text(_report_to_markdown(report), encoding="utf-8")
        if report.dump_hash:
            self._hash_index_dir.mkdir(parents=True, exist_ok=True)
            safe_hash = report.dump_hash.replace(":", "_")
            idx_path = _safe_path(self._hash_index_dir, safe_hash)
            idx_path.write_text(str(report.incident_id), encoding="utf-8")
        logger.debug(f"FilesystemStore: saved report {report.incident_id}")

    async def get_report(self, incident_id: UUID) -> RCAReport | None:
        return await asyncio.to_thread(self._sync_get_report, incident_id)

    def _sync_get_report(self, incident_id: UUID) -> RCAReport | None:
        try:
            path = _safe_path(self._reports_dir, f"{incident_id}.json")
            return RCAReport.model_validate_json(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None

    async def find_by_hash(self, dump_hash: str) -> RCAReport | None:
        return await asyncio.to_thread(self._sync_find_by_hash, dump_hash)

    def _sync_find_by_hash(self, dump_hash: str) -> RCAReport | None:
        try:
            safe_hash = dump_hash.replace(":", "_")
            idx_path = _safe_path(self._hash_index_dir, safe_hash)
            incident_id_str = idx_path.read_text(encoding="utf-8").strip()
            return self._sync_get_report(UUID(incident_id_str))
        except (FileNotFoundError, ValueError):
            return None

    async def update_hitl_response(
        self,
        incident_id: UUID,
        response: dict[str, object],
    ):
        await asyncio.to_thread(self._sync_update_hitl, incident_id, response)

    def _sync_update_hitl(
        self,
        incident_id: UUID,
        response: dict[str, object],
    ):
        path = _safe_path(self._reports_dir, f"{incident_id}.json")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise IncidentNotFoundError(f"Report not found: {incident_id}") from exc
        data["hitl_request"] = response
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    async def load_recent(self, limit: int = 100) -> list[RCAReport]:
        return await asyncio.to_thread(self._sync_load_recent, limit)

    def _sync_load_recent(self, limit: int) -> list[RCAReport]:
        if not self._reports_dir.is_dir():
            return []
        reports: list[RCAReport] = []
        for path in self._reports_dir.iterdir():
            if path.suffix == ".json" and path.parent == self._reports_dir:
                with contextlib.suppress(Exception):
                    reports.append(
                        RCAReport.model_validate_json(path.read_text(encoding="utf-8"))
                    )
        reports.sort(key=lambda r: r.created_at, reverse=True)
        return reports if limit == 0 else reports[:limit]

    # ------------------------------------------------------------------
    # ObjectStore
    # ------------------------------------------------------------------

    async def upload_raw(
        self,
        incident_id: UUID,
        filename: str,
        data: bytes,
    ) -> str:
        return await asyncio.to_thread(self._sync_upload_raw, incident_id, filename, data)

    def _sync_upload_raw(self, incident_id: UUID, filename: str, data: bytes) -> str:
        dest = _safe_path(self._objects_dir, str(incident_id), filename)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return f"{incident_id}/{filename}"

    async def get_raw(self, object_key: str) -> bytes:
        return await asyncio.to_thread(self._sync_get_raw, object_key)

    def _sync_get_raw(self, object_key: str) -> bytes:
        parts = object_key.split("/", 1)
        try:
            path = _safe_path(self._objects_dir, *parts)
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise IncidentNotFoundError(f"Object not found: {object_key}") from exc
