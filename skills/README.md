# ASSERT skill bundle

This directory is the canonical source for the customer-facing ASSERT coding-agent bundle installed by [`ONBOARD.md`](../ONBOARD.md).

## Install paths in a user repository

| Assistant | Source in this repo | Destination in the user's repo |
|---|---|---|
| Claude Code | `skills/<name>/SKILL.md` | `.claude/skills/<name>/SKILL.md` |
| GitHub Copilot CLI | `skills/<name>/<name>.prompt.md` | `.github/prompts/<name>.prompt.md` |
| Cursor | `skills/<name>/*.mdc` | `.cursor/rules/<name>.mdc` |

## Skills

- `wire-assert-ci` owns repository scanning, target wrapping, draft spec extraction and confirmation, behavior splitting, CI workflow authoring, the baseline/config commit, and the ACS remediation PR flow.
- `run-assert-eval` is vendored from `responsibleai/ASSERT` and owns `assert-ai init`, live pipeline runs, result reporting, Results Q&A, and viewer hand-off. Keep the vendored copies in sync with upstream except for customer-repo orientation/provenance text.

The target decision tree stays in the ASSERT docs: <https://github.com/responsibleai/ASSERT/blob/main/docs/targets/README.md>.

## BYO credentials

There is no shared endpoint. Users provide their own provider credentials as repository secrets/environment variables such as `AZURE_API_KEY`, `AZURE_API_BASE`, `AZURE_API_VERSION`, or `OPENAI_API_KEY`. Never store credential values in configs, workflows, prompts, or logs.
