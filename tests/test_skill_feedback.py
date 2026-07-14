from datetime import date
from decimal import Decimal

from app.models import Flag, FlagSeverity, FlagType
from app.skills.store import SkillStore


def make_flag(message: str, details: dict | None = None) -> Flag:
    return Flag(
        type=FlagType.UNMATCHED_BANK,
        severity=FlagSeverity.WARNING,
        message=message,
        entry_ids=["e1"],
        details=details or {},
    )


def test_no_patterns_no_suppression():
    store = SkillStore(skills_dir=None)  # type: ignore[arg-type]
    flags = [make_flag("Bank transaction WIRE-1 for 100 USD, Vendor X, has no matching GL entry")]

    kept, suppressed = store.apply_suppression(flags, entity_id="entity-1")

    assert kept == flags
    assert suppressed == 0


def test_recorded_pattern_suppresses_matching_flag(tmp_path):
    store = SkillStore(skills_dir=tmp_path)
    store.record_feedback(
        entity_id="entity-1",
        flag_type=FlagType.UNMATCHED_BANK,
        match_text="Vendor X",
        note="Vendor X always pays 5 days late, not a real exception",
    )

    flags = [
        make_flag("Bank transaction WIRE-1 for 100 USD, Vendor X, has no matching GL entry"),
        make_flag("Bank transaction WIRE-2 for 200 USD, Vendor Y, has no matching GL entry"),
    ]

    kept, suppressed = store.apply_suppression(flags, entity_id="entity-1")

    assert suppressed == 1
    assert len(kept) == 1
    assert "Vendor Y" in kept[0].message


def test_pattern_scoped_to_entity(tmp_path):
    store = SkillStore(skills_dir=tmp_path)
    store.record_feedback(
        entity_id="entity-1",
        flag_type=FlagType.UNMATCHED_BANK,
        match_text="Vendor X",
        note="known recurring pattern",
    )

    flags = [make_flag("Vendor X wire with no GL match")]

    kept, suppressed = store.apply_suppression(flags, entity_id="entity-2")

    assert suppressed == 0
    assert kept == flags


def test_skill_file_written(tmp_path):
    store = SkillStore(skills_dir=tmp_path)
    store.record_feedback(
        entity_id="entity-1",
        flag_type=FlagType.UNMATCHED_BANK,
        match_text="Vendor X",
        note="known recurring pattern",
    )

    skill_file = tmp_path / "entity-1.md"
    assert skill_file.exists()
    content = skill_file.read_text()
    assert "Vendor X" in content
    assert "known recurring pattern" in content
