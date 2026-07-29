"""Verify every raw URL in ONBOARD.md resolves to a real file in this repo.

Both cold-read testers hit 404s on these URLs. That was attributed to the repo
being private and the branch unmerged -- but if a path is also simply wrong, it
will still 404 after publishing, and the bugbash dies on the first line the
user pastes. This checks the paths independently of repo visibility.
"""

import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
onboard = io.open(ROOT / "ONBOARD.md", encoding="utf-8").read()

RAW = r"https://raw\.githubusercontent\.com/responsibleai/assert-action/([^/]+)/(\S+?)(?=[\s`)]|$)"

problems = []
urls = re.findall(RAW, onboard)
if not urls:
    problems.append("ONBOARD.md contains no raw skill URLs at all")

print(f"{len(urls)} raw URL(s) found in ONBOARD.md\n")
for ref, rel in urls:
    target = ROOT / rel
    ok = target.is_file()
    print(f"  [{'OK ' if ok else 'MISSING'}] {ref}/{rel}")
    if ref != "main":
        problems.append(f"{rel}: pinned to '{ref}', not 'main'")
    if not ok:
        problems.append(f"{rel}: no such file in the repo")

# The install destinations the skill writes into the user's repo must match the
# conventions each assistant actually loads from.
EXPECTED_DESTS = {
    ".claude/skills/wire-assert-ci/SKILL.md",
    ".claude/skills/run-assert-eval/SKILL.md",
    ".github/prompts/wire-assert-ci.prompt.md",
    ".github/prompts/run-assert-eval.prompt.md",
    ".cursor/rules/assert-ci.mdc",
    ".cursor/rules/assert.mdc",
}
missing_dests = sorted(d for d in EXPECTED_DESTS if d not in onboard)
for d in missing_dests:
    problems.append(f"ONBOARD.md never names install destination {d}")

# Every skill file that exists should be reachable from ONBOARD.md, or a user
# on that assistant silently gets a partial install.
declared = {rel for _, rel in urls}
for p in sorted((ROOT / "skills").rglob("*")):
    if p.is_file() and p.suffix in {".md", ".mdc"} and p.name != "README.md":
        rel = p.relative_to(ROOT).as_posix()
        if rel not in declared:
            problems.append(f"{rel} exists but ONBOARD.md never fetches it")

print()
if problems:
    print(f"{len(problems)} PROBLEM(S):")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("ONBOARD.md paths and install destinations are all consistent.")
