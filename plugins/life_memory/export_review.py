from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import LifecycleStatus, ReviewStatus, Sensitivity


def export_review_markdown(
    *,
    target_dir: Path,
    data: dict[str, Any],
    include_archive: bool = True,
    include_sensitive: str = "summary_only",
) -> list[str]:
    target_dir.mkdir(parents=True, exist_ok=True)
    library = target_dir / "memory-library"
    journal = target_dir / "memory-journal"
    library.mkdir(parents=True, exist_ok=True)
    journal.mkdir(parents=True, exist_ok=True)

    memories = list(data.get("memories") or [])
    reports = list(data.get("reports") or [])

    files: list[str] = []
    _write(target_dir / "README.md", _render_readme(memories), target_dir, files)
    _write(journal / "README.md", _render_journal(reports), target_dir, files)
    _write(library / "facts.md", _render_category(memories, "personal_fact", include_sensitive), target_dir, files)
    _write(
        library / "preferences.md",
        _render_category(memories, "personal_preference", include_sensitive),
        target_dir,
        files,
    )
    _write(
        library / "patterns.md",
        _render_category(memories, "personal_pattern", include_sensitive),
        target_dir,
        files,
    )
    _write(target_dir / "review-needed.md", _render_review_needed(memories, include_sensitive), target_dir, files)
    _write(target_dir / "change-requests.md", _render_change_requests(), target_dir, files)
    if include_archive:
        _write(target_dir / "archive.md", _render_archive(memories, include_sensitive), target_dir, files)
    else:
        archive = target_dir / "archive.md"
        if archive.exists():
            archive.unlink()
    return files


def _write(path: Path, content: str, target_dir: Path, files: list[str]) -> None:
    path.write_text(content, encoding="utf-8")
    files.append(path.relative_to(target_dir).as_posix())


def _render_readme(memories: list[dict[str, Any]]) -> str:
    active_count = sum(1 for item in memories if item.get("status") != LifecycleStatus.ARCHIVED.value)
    archived_count = sum(1 for item in memories if item.get("status") == LifecycleStatus.ARCHIVED.value)
    return "\n".join(
        [
            "# Life Memory Review",
            "",
            "This is a read-only export from the local SQLite life memory database.",
            "",
            f"- Active or candidate memories: {active_count}",
            f"- Archived memories included: {archived_count}",
            "",
            "Use memory ids in `change-requests.md` when asking Hermes to correct or forget a memory.",
            "",
        ]
    )


def _render_journal(reports: list[dict[str, Any]]) -> str:
    lines = [
        "# Memory Journal",
        "",
        "Reflection and session reports appear here when available.",
        "",
    ]
    if not reports:
        lines.extend(["No reflection reports have been exported yet.", ""])
        return "\n".join(lines)
    for report in reports:
        lines.extend(
            [
                f"## {report.get('report_type', 'report')} {report.get('report_date') or ''}".strip(),
                "",
                _safe_text(report.get("content", "")),
                "",
            ]
        )
    return "\n".join(lines)


def _render_category(memories: list[dict[str, Any]], primary_category: str, sensitive_mode: str) -> str:
    title = {
        "personal_fact": "Facts",
        "personal_preference": "Preferences",
        "personal_pattern": "Patterns",
    }[primary_category]
    rows = [
        item
        for item in memories
        if item.get("primary_category") == primary_category
        and item.get("status") != LifecycleStatus.ARCHIVED.value
        and item.get("review_status") != ReviewStatus.NEEDS_REVIEW.value
    ]
    return _render_memory_list(f"# {title}", rows, sensitive_mode)


def _render_review_needed(memories: list[dict[str, Any]], sensitive_mode: str) -> str:
    rows = [item for item in memories if _is_review_needed(item)]
    return _render_memory_list("# Review Needed", rows, sensitive_mode)


def _is_review_needed(memory: dict[str, Any]) -> bool:
    review_status = memory.get("review_status")
    if review_status == ReviewStatus.NEEDS_REVIEW.value:
        return True
    if review_status in {
        ReviewStatus.APPROVED.value,
        ReviewStatus.REJECTED.value,
        ReviewStatus.AUTO_PROMOTED.value,
    }:
        return False
    return memory.get("status") in {LifecycleStatus.YOUNG.value, LifecycleStatus.PATTERN_CANDIDATE.value}


def _render_archive(memories: list[dict[str, Any]], sensitive_mode: str) -> str:
    rows = [item for item in memories if item.get("status") == LifecycleStatus.ARCHIVED.value]
    return _render_memory_list("# Archive", rows, sensitive_mode)


def _render_memory_list(title: str, memories: list[dict[str, Any]], sensitive_mode: str) -> str:
    lines = [title, ""]
    if not memories:
        lines.extend(["No entries.", ""])
        return "\n".join(lines)
    for memory in memories:
        lines.extend(_render_memory(memory, sensitive_mode))
    return "\n".join(lines)


def _render_memory(memory: dict[str, Any], sensitive_mode: str) -> list[str]:
    memory_id = str(memory.get("memory_id"))
    status = str(memory.get("status"))
    sensitivity = str(memory.get("sensitivity", Sensitivity.NORMAL.value))
    content = _display_content(memory, sensitive_mode)
    tags = ", ".join(str(tag) for tag in memory.get("tags") or [])
    lines = [
        f"## {memory_id}",
        "",
        f"- Status: {status}",
        f"- Category: {memory.get('primary_category', '')}",
        f"- Sensitivity: {sensitivity}",
        f"- Source: {memory.get('source', '')}",
    ]
    if tags:
        lines.append(f"- Tags: {tags}")
    lines.extend(
        [
            "",
            content,
            "",
        ]
    )
    return lines


def _display_content(memory: dict[str, Any], sensitive_mode: str) -> str:
    sensitivity = memory.get("sensitivity")
    if sensitivity in {Sensitivity.SENSITIVE.value, Sensitivity.RESTRICTED.value}:
        if sensitive_mode == "none":
            return "[Sensitive memory omitted from this export.]"
        if sensitivity == Sensitivity.RESTRICTED.value:
            return "[Restricted memory exported as metadata only.]"
        return _safe_text(_sensitive_export_summary(memory))
    return _safe_text(str(memory.get("content") or ""))


def _sensitive_export_summary(memory: dict[str, Any]) -> str:
    category = str(memory.get("primary_category") or "life memory")
    tags = ", ".join(str(tag) for tag in memory.get("tags") or [])
    suffix = f" Tags: {tags}." if tags else ""
    return (
        f"[Sensitive {category} memory exported as summary only. "
        "Raw content is hidden from Markdown review by default."
        f"{suffix}]"
    )


def _render_change_requests() -> str:
    return "\n".join(
        [
            "# Change Requests",
            "",
            "This file is the only Markdown review file that `life_memory_sync_review` reads.",
            "SQLite remains the source of truth. Sync is explicit and dry-run by default.",
            "Manual edits to memory-library, memory-journal, review-needed, or archive files are ignored.",
            "",
            "## Workflow",
            "",
            "1. Copy an exact `memory_id` from the exported review files.",
            "2. Add one or more fenced `life-memory-change` blocks below.",
            "3. Run `life_memory_sync_review` with `apply=false` to preview.",
            "4. Run again with `apply=true` and `confirm_apply=true` only after reviewing the plan.",
            "",
            "Supported actions: `delete`, `replace`, `merge`, `confirm`, `reject`, `mark_outdated`.",
            "",
            "## Examples",
            "",
            "Examples use `text` fences so the generated template is safe to dry-run as-is.",
            "When ready, copy an example and change the fence language to `life-memory-change`.",
            "",
            "```text",
            "id: req-delete-example",
            "action: delete",
            "memory_id: mem_example",
            "reason: This memory is wrong.",
            "confirm: true",
            "```",
            "",
            "```text",
            "id: req-replace-example",
            "action: replace",
            "memory_id: mem_example",
            "replacement: I now buy unsweetened soy milk after Saturday runs.",
            "reason: User corrected the older memory.",
            "confirm: true",
            "```",
            "",
            "```text",
            "id: req-merge-example",
            "action: merge",
            "memory_ids: [mem_first, mem_second]",
            "merged_content: User usually buys unsweetened soy milk after Saturday runs.",
            "reason: Duplicate running-drink memories.",
            "confirm: true",
            "```",
            "",
        ]
    )


def _safe_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()
