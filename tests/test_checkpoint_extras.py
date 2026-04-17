"""Tests for checkpoint stderr output and extended token snapshot fields."""
from __future__ import annotations

from pathlib import Path


STORE_PY = Path(__file__).resolve().parent.parent / "checkpoint" / "store.py"


def test_store_imports_sys():
    """store.py must import sys for stderr output."""
    import checkpoint.store as mod

    assert hasattr(mod, "sys"), "checkpoint.store should import sys"


class TestCheckpointPrintsToStderr:
    """All [checkpoint] print() calls must use file=sys.stderr."""

    def test_all_checkpoint_prints_use_stderr(self):
        source = STORE_PY.read_text(encoding="utf-8")
        lines = source.split("\n")
        violations = []
        i = 0
        while i < len(lines):
            if "print(" in lines[i] and "[checkpoint]" in lines[i]:
                depth = 0
                statement_lines = []
                j = i
                while j < len(lines):
                    statement_lines.append(lines[j])
                    depth += lines[j].count("(") - lines[j].count(")")
                    if depth == 0:
                        break
                    j += 1
                statement = "\n".join(statement_lines)
                if "file=sys.stderr" not in statement:
                    violations.append(f"Line {i + 1}: {lines[i].strip()}")
                i = j + 1
            else:
                i += 1
        assert not violations, (
            "print() with [checkpoint] missing file=sys.stderr:\n"
            + "\n".join(violations)
        )


class TestTokenSnapshotExtendedFields:
    """token_snapshot dict must include cache_read, cache_creation, distinct_base."""

    def test_cache_read_in_source(self):
        source = STORE_PY.read_text(encoding="utf-8")
        assert '"cache_read"' in source, "Missing cache_read field in token_snapshot"

    def test_cache_creation_in_source(self):
        source = STORE_PY.read_text(encoding="utf-8")
        assert '"cache_creation"' in source, "Missing cache_creation field"

    def test_distinct_base_in_source(self):
        source = STORE_PY.read_text(encoding="utf-8")
        assert '"distinct_base"' in source, "Missing distinct_base field"
