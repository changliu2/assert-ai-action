#!/usr/bin/env python3
"""Keep the vendored copy of ASSERT's run-assert-eval skill honest.

`wire-assert-ci` delegates every live evaluation to `run-assert-eval`, which is
owned upstream in responsibleai/ASSERT. We vendor a copy so that a single
`npx skills add` installs both halves of the flow in one command -- but a copy
that nobody checks is a fork, and this one had already drifted: the vendored
SKILL.md dropped upstream's `target.endpoint` guidance while upstream still told
users to run an editable install of their own repo.

So: the vendored files must be byte-identical to upstream apart from a single
provenance header line. This script checks that (default) or rewrites the
vendored copies from upstream (--sync).

Upstream is read from a local ASSERT checkout when available, otherwise fetched
over HTTPS from the default branch.

    python scripts/sync_vendored_skill.py            # verify, exit 1 on drift
    python scripts/sync_vendored_skill.py --sync     # pull upstream down
    python scripts/sync_vendored_skill.py --assert-repo ../ASSERT
"""

from __future__ import annotations

import argparse
import difflib
import os
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_REPO = "responsibleai/ASSERT"
UPSTREAM_BRANCH = "main"

# vendored path -> path within the ASSERT repo
PAIRS = {
    "skills/run-assert-eval/SKILL.md": ".claude/skills/run-assert-eval/SKILL.md",
    "skills/run-assert-eval/run-assert-eval.prompt.md": ".github/prompts/run-assert-eval.prompt.md",
    "skills/run-assert-eval/assert.mdc": ".cursor/rules/assert.mdc",
}

HEADER = (
    "> Provenance: vendored verbatim from {repo} ({url}).\n"
    "> Do not edit this copy -- change it upstream, then run\n"
    "> `python scripts/sync_vendored_skill.py --sync`. CI enforces that this file\n"
    "> matches upstream exactly apart from this header.\n"
)


def raw_url(rel: str) -> str:
    return f"https://raw.githubusercontent.com/{UPSTREAM_REPO}/{UPSTREAM_BRANCH}/{rel}"


def fetch_upstream(rel: str, assert_repo: Path | None) -> str:
    if assert_repo is not None:
        local = assert_repo / rel
        if not local.is_file():
            raise SystemExit(f"missing in --assert-repo: {local}")
        return local.read_text(encoding="utf-8")
    with urllib.request.urlopen(raw_url(rel), timeout=30) as resp:  # noqa: S310
        if resp.status != 200:
            raise SystemExit(f"HTTP {resp.status} fetching {raw_url(rel)}")
        return resp.read().decode("utf-8")


def render(body: str, rel: str) -> str:
    """Insert the provenance header *after* any YAML frontmatter.

    Skill loaders (npx skills, Claude Code, Cursor) require the ``---`` block to
    be the very first thing in the file. Putting the header above it silently
    breaks name/description discovery, so the header goes immediately after.
    """
    header = HEADER.format(repo=UPSTREAM_REPO, url=raw_url(rel))
    lines = body.splitlines(keepends=True)

    if lines and lines[0].strip() == "---":
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                head = "".join(lines[: idx + 1])
                rest = "".join(lines[idx + 1 :])
                return f"{head}\n{header}\n{rest.lstrip(chr(10))}"

    return f"{header}\n{body.lstrip(chr(10))}"


def strip_header(text: str) -> str:
    """Remove the provenance header wherever it sits, so only content compares."""
    out = [ln for ln in text.splitlines(keepends=True) if not ln.startswith("> ")]
    return "".join(out).replace("\n\n\n", "\n\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sync", action="store_true", help="rewrite vendored files from upstream")
    ap.add_argument(
        "--assert-repo",
        type=Path,
        default=os.environ.get("ASSERT_REPO"),
        help="local ASSERT checkout to read instead of fetching over HTTPS",
    )
    args = ap.parse_args()

    assert_repo = Path(args.assert_repo).resolve() if args.assert_repo else None
    if assert_repo is not None and not assert_repo.is_dir():
        raise SystemExit(f"--assert-repo is not a directory: {assert_repo}")

    drifted: list[str] = []
    for vendored_rel, upstream_rel in sorted(PAIRS.items()):
        vendored_path = REPO_ROOT / vendored_rel
        upstream_body = fetch_upstream(upstream_rel, assert_repo)
        expected = render(upstream_body, upstream_rel)

        if args.sync:
            vendored_path.parent.mkdir(parents=True, exist_ok=True)
            vendored_path.write_text(expected, encoding="utf-8", newline="\n")
            print(f"synced  {vendored_rel}  <- {upstream_rel}")
            continue

        if not vendored_path.is_file():
            drifted.append(vendored_rel)
            print(f"MISSING {vendored_rel}")
            continue

        actual = vendored_path.read_text(encoding="utf-8")
        if strip_header(actual) == strip_header(expected):
            print(f"ok      {vendored_rel}")
            continue

        drifted.append(vendored_rel)
        print(f"DRIFT   {vendored_rel}  (upstream: {upstream_rel})")
        diff = difflib.unified_diff(
            strip_header(expected).splitlines(),
            strip_header(actual).splitlines(),
            fromfile=f"upstream/{upstream_rel}",
            tofile=f"vendored/{vendored_rel}",
            lineterm="",
            n=1,
        )
        for line in list(diff)[:40]:
            print(f"        {line}")

    if args.sync:
        print("\nSynced. Review the diff, then commit.")
        return 0

    if drifted:
        print(
            f"\n{len(drifted)} vendored file(s) drifted from {UPSTREAM_REPO}.\n"
            "The vendored copy must not be edited directly. Change it upstream, "
            "then run: python scripts/sync_vendored_skill.py --sync"
        )
        return 1

    print(f"\nAll {len(PAIRS)} vendored file(s) match {UPSTREAM_REPO}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
