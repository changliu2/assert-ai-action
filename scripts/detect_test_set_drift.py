#!/usr/bin/env python3
"""Detect baseline-vs-current test-set drift before running the paired gate.

When the test set changes (judged via SHA-256 of ``test_set.jsonl``), the
paired t-test is skipped because pairing is no longer valid. This script:

1. Emits a ``TestSetChanged`` gate report and PR comment.
2. Signals ``action.yml`` via ``GITHUB_OUTPUT`` to skip the comparator
   (``skip-compare=true``, ``gate-verdict=TestSetChanged``).

When SHAs match, the script just emits the SHAs and lets ``action.yml`` run
the comparator (``skip-compare=false``).

If the baseline lacks ``test_set.jsonl`` entirely, emits a ``FirstRun`` report
to match the no-baseline path in ``action.yml``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ACTION_VERSION = "v1.0.0-rc1"


def _find_file(root: Path, name: str) -> Path | None:
    if not root.exists():
        return None
    direct = root / name
    if direct.is_file():
        return direct
    matches = sorted(p for p in root.rglob(name) if p.is_file())
    return matches[0] if matches else None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _current_stats(root: Path) -> tuple[int, float]:
    scores = _find_file(root, "scores.jsonl")
    rows: list[dict] = []
    if scores and scores.is_file():
        for line in scores.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    violations = 0
    for row in rows:
        dims = ((row.get("verdict") or {}).get("dimensions") or {})
        if any(value is True for value in dims.values()):
            violations += 1
    return len(rows), violations / len(rows) if rows else 0.0


def _emit(**values: str) -> None:
    """Append ``key=value`` lines to ``$GITHUB_OUTPUT``; no-op locally."""
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        return
    with open(output, "a", encoding="utf-8") as f:
        for key, value in values.items():
            print(f"{key}={value}", file=f)


def _write_firstrun(args: argparse.Namespace) -> int:
    report = {
        "action_version": ACTION_VERSION,
        "decision": "FirstRun",
        "n_paired_cases": 0,
        "warnings": ["baseline is missing test_set.jsonl"],
        "dimensions": [],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    args.pr_comment.parent.mkdir(parents=True, exist_ok=True)
    args.pr_comment.write_text(
        "## 🛡️ ASSERT — safety regression gate\n\n"
        "**Gate: 🆕 FirstRun**\n\n"
        "🆕 First run on this branch — no usable baseline test set was found. "
        "Once this merges, future PRs will pair-test against it.\n",
        encoding="utf-8",
    )
    _emit(**{"skip-compare": "true", "gate-verdict": "FirstRun"})
    return 0


def _write_test_set_changed(
    args: argparse.Namespace,
    baseline_test: Path,
    current_test: Path,
    baseline_sha: str,
    current_sha: str,
) -> int:
    n_cases, violation_rate = _current_stats(args.current_run_root)
    report = {
        "action_version": ACTION_VERSION,
        "decision": "TestSetChanged",
        "n_paired_cases": 0,
        "current_n_cases": n_cases,
        "current_violation_rate": violation_rate,
        "baseline_test_set_sha256": baseline_sha,
        "current_test_set_sha256": current_sha,
        "baseline_test_set_path": str(baseline_test),
        "current_test_set_path": str(current_test),
        "warnings": ["test_set.jsonl changed; paired t-test skipped"],
        "dimensions": [],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    args.pr_comment.parent.mkdir(parents=True, exist_ok=True)
    args.pr_comment.write_text(
        "## 🛡️ ASSERT — safety regression gate\n\n"
        "**Gate: 🔄 TestSetChanged**\n\n"
        f"🔄 Test set changed (baseline SHA: `{baseline_sha[:7]}`, current SHA: `{current_sha[:7]}`) — "
        "paired t-test skipped. This is a baseline-refresh PR; merge to make it the new baseline.\n",
        encoding="utf-8",
    )
    _emit(**{
        "skip-compare": "true",
        "gate-verdict": "TestSetChanged",
        "baseline-test-set-sha": baseline_sha,
        "current-test-set-sha": current_sha,
    })
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline-root", required=True, type=Path)
    p.add_argument("--current-run-root", required=True, type=Path)
    p.add_argument(
        "--artifacts-root",
        required=True,
        type=Path,
        help="Workspace artifacts root; searched as a fallback for test_set.jsonl when current-run-root has none.",
    )
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--pr-comment", required=True, type=Path)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    baseline_test = _find_file(args.baseline_root, "test_set.jsonl")
    current_test = (
        _find_file(args.current_run_root, "test_set.jsonl")
        or _find_file(args.artifacts_root, "test_set.jsonl")
    )

    if baseline_test is None:
        return _write_firstrun(args)

    if current_test is None:
        print(
            "::error::current run did not produce test_set.jsonl; cannot validate paired cases",
            file=sys.stderr,
        )
        return 1

    baseline_sha = _sha256(baseline_test)
    current_sha = _sha256(current_test)
    if baseline_sha == current_sha:
        _emit(**{
            "skip-compare": "false",
            "gate-verdict": "",
            "baseline-test-set-sha": baseline_sha,
            "current-test-set-sha": current_sha,
        })
        return 0

    return _write_test_set_changed(args, baseline_test, current_test, baseline_sha, current_sha)


if __name__ == "__main__":
    sys.exit(main())
