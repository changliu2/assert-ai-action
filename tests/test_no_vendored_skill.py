"""The anti-vendoring guard is the only thing preventing a silent fork.

`run-assert-eval` is owned upstream in responsibleai/ASSERT. It was previously
copied into `skills/` here, and the two copies drifted in opposite directions
within weeks without anyone noticing. The guard in check_bundle.py is what stops
that from coming back, so it needs its own test: a guard that silently stops
working is worse than no guard, because the bundle looks protected.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_check_bundle():
    """Import check_bundle.py fresh so module-level state is not shared."""
    spec = importlib.util.spec_from_file_location(
        "check_bundle_under_test", ROOT / "scripts" / "check_bundle.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


UPSTREAM_SKILL = """---
name: run-assert-eval
description: >
  Run an ASSERT evaluation from a plain-language behavior requirement.
---

# Run an ASSERT evaluation
"""

LOCAL_SKILL = """---
name: wire-assert-ci
description: >
  Wire the ASSERT safety regression gate into a repository.
---

# Wire ASSERT CI
"""


@pytest.fixture
def guard(tmp_path, monkeypatch):
    mod = load_check_bundle()
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    mod.FAILURES.clear()
    (tmp_path / "skills").mkdir()
    return mod, tmp_path


def write_skill(root: Path, directory: str, body: str) -> None:
    d = root / "skills" / directory
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(body, encoding="utf-8")


def test_passes_when_only_local_skills_present(guard):
    mod, root = guard
    write_skill(root, "wire-assert-ci", LOCAL_SKILL)

    mod.check_no_vendored_upstream_skill()

    assert mod.FAILURES == []


def test_fails_when_upstream_skill_vendored_at_its_usual_path(guard):
    mod, root = guard
    write_skill(root, "run-assert-eval", UPSTREAM_SKILL)

    mod.check_no_vendored_upstream_skill()

    assert mod.FAILURES, "vendoring run-assert-eval must fail the build"
    assert any("must not be vendored" in f for f in mod.FAILURES)


def test_fails_when_upstream_skill_vendored_under_a_renamed_directory(guard):
    """A path-only check would miss this, which is why the guard reads frontmatter."""
    mod, root = guard
    write_skill(root, "eval-runner", UPSTREAM_SKILL)

    mod.check_no_vendored_upstream_skill()

    assert mod.FAILURES, "renaming the directory must not defeat the guard"
    assert any("declares name 'run-assert-eval'" in f for f in mod.FAILURES)


def test_ignores_files_without_frontmatter(guard):
    mod, root = guard
    d = root / "skills" / "wire-assert-ci"
    d.mkdir(parents=True)
    (d / "notes.md").write_text("plain markdown, mentions run-assert-eval\n", encoding="utf-8")

    mod.check_no_vendored_upstream_skill()

    assert mod.FAILURES == [], "prose mentioning the skill name is not a copy"


def test_malformed_frontmatter_does_not_crash_the_guard(guard):
    mod, root = guard
    write_skill(root, "broken", "---\nname: [unclosed\n---\n\n# broken\n")

    mod.check_no_vendored_upstream_skill()

    assert mod.FAILURES == []


def test_real_repo_has_no_vendored_upstream_skill():
    """Guards the actual shipped tree, not just a fixture."""
    mod = load_check_bundle()
    mod.FAILURES.clear()

    mod.check_no_vendored_upstream_skill()

    assert mod.FAILURES == [], f"vendored upstream skill present: {mod.FAILURES}"


def test_onboard_installs_run_assert_eval_from_upstream():
    """If ONBOARD.md stops fetching the upstream skill, users get half a bundle."""
    onboard = (ROOT / "ONBOARD.md").read_text(encoding="utf-8")

    assert "responsibleai/ASSERT" in onboard
    assert "run-assert-eval" in onboard
    assert ".claude/skills/run-assert-eval/SKILL.md" in onboard


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
