"""The "evolving skill file": a concrete feedback loop, not a vague claim.

When a human reviewer marks a flag as a false positive, that decision is
recorded as a KnownExceptionPattern -- both in-memory (consulted by the
reconciliation engine to suppress the same noise next run) and appended to
a per-entity, human-readable markdown file under `skills_data/`. The
markdown file is the artifact a comptroller or the chat agent can read to
see what the platform has learned; the in-memory index is what actually
changes behavior.

This is deliberately narrow: it suppresses *recognized, reviewed* noise
(e.g. "Vendor X always pays 5 days late, stop flagging it"), not a
general-purpose self-modifying model. A pattern is only created when a
human records feedback -- the engine never invents or removes patterns on
its own.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.models import Flag, FlagType, new_id

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills_data"


@dataclass
class KnownExceptionPattern:
    id: str = field(default_factory=new_id)
    entity_id: str = ""
    flag_type: FlagType = FlagType.UNMATCHED_BANK
    match_text: str = ""
    note: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SkillStore:
    def __init__(self, skills_dir: Path = SKILLS_DIR):
        self._patterns: dict[str, list[KnownExceptionPattern]] = {}
        self._skills_dir = skills_dir

    def record_feedback(
        self,
        entity_id: str,
        flag_type: FlagType,
        match_text: str,
        note: str,
    ) -> KnownExceptionPattern:
        pattern = KnownExceptionPattern(
            entity_id=entity_id, flag_type=flag_type, match_text=match_text, note=note
        )
        self._patterns.setdefault(entity_id, []).append(pattern)
        self._write_skill_file(entity_id)
        return pattern

    def get_patterns(self, entity_id: str) -> list[KnownExceptionPattern]:
        return self._patterns.get(entity_id, [])

    def _pattern_matches(self, pattern: KnownExceptionPattern, flag: Flag) -> bool:
        if pattern.flag_type != flag.type:
            return False
        needle = pattern.match_text.strip().lower()
        if not needle:
            return False
        haystack = flag.message.lower() + " " + " ".join(str(v).lower() for v in flag.details.values())
        return needle in haystack

    def apply_suppression(self, flags: list[Flag], entity_id: str | None) -> tuple[list[Flag], int]:
        """Returns (kept_flags, suppressed_count)."""
        if not entity_id:
            return flags, 0
        patterns = self.get_patterns(entity_id)
        if not patterns:
            return flags, 0
        kept: list[Flag] = []
        suppressed = 0
        for flag in flags:
            if any(self._pattern_matches(p, flag) for p in patterns):
                suppressed += 1
            else:
                kept.append(flag)
        return kept, suppressed

    def _write_skill_file(self, entity_id: str) -> None:
        self._skills_dir.mkdir(parents=True, exist_ok=True)
        path = self._skills_dir / f"{entity_id}.md"
        lines = [
            f"# Reconciliation Skill Notes -- entity {entity_id}",
            "",
            "Patterns learned from reviewed exceptions. The reconciliation engine "
            "consults this file's underlying index to suppress flags matching a "
            "previously-confirmed false positive. Do not hand-edit this file to "
            "change engine behavior -- record feedback via POST /feedback instead; "
            "this file is the read-only human-facing record of what was learned.",
            "",
            "## Learned patterns",
            "",
        ]
        for p in self.get_patterns(entity_id):
            lines.append(
                f"- **[{p.flag_type.value}]** match: \"{p.match_text}\" -- {p.note} "
                f"(recorded {p.created_at})"
            )
        path.write_text("\n".join(lines) + "\n")


skill_store = SkillStore()
