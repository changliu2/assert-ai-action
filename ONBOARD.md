Read and follow this bootstrap exactly. Your job is to install the ASSERT coding-agent bundle into the current repository, then invoke `wire-assert-ci`.

BYO keys are required: there is no shared ASSERT endpoint. The user must provide provider credentials as repository secrets/environment variables such as `AZURE_API_KEY`, `AZURE_API_BASE`, `AZURE_API_VERSION`, `OPENAI_API_KEY`, or the names required by their LiteLLM provider. Never read or write credential values.

## Step 1 — install the skills

**Preferred.** If Node is available, run this and skip to Step 2. It covers 40+ agents, detects the host automatically, and stays current without this file being edited:

```bash
npx skills add changliu2/assert-ai-action --skill "*" --yes
```

**Fallback.** Only if `npx` is unavailable or the command fails, detect the assistant and fetch the matching files by hand:

- Claude Code:
  - `https://raw.githubusercontent.com/changliu2/assert-ai-action/main/skills/wire-assert-ci/SKILL.md` -> `.claude/skills/wire-assert-ci/SKILL.md`
  - `https://raw.githubusercontent.com/changliu2/assert-ai-action/main/skills/run-assert-eval/SKILL.md` -> `.claude/skills/run-assert-eval/SKILL.md`
- GitHub Copilot CLI:
  - `https://raw.githubusercontent.com/changliu2/assert-ai-action/main/skills/wire-assert-ci/wire-assert-ci.prompt.md` -> `.github/prompts/wire-assert-ci.prompt.md`
  - `https://raw.githubusercontent.com/changliu2/assert-ai-action/main/skills/run-assert-eval/run-assert-eval.prompt.md` -> `.github/prompts/run-assert-eval.prompt.md`
- Cursor:
  - `https://raw.githubusercontent.com/changliu2/assert-ai-action/main/skills/wire-assert-ci/assert-ci.mdc` -> `.cursor/rules/assert-ci.mdc`
  - `https://raw.githubusercontent.com/changliu2/assert-ai-action/main/skills/run-assert-eval/assert.mdc` -> `.cursor/rules/assert.mdc`

Create parent directories if missing. Do not overwrite unrelated local files without showing the diff first.

## Step 2 — run the skill

Invoke the `wire-assert-ci` skill and follow it until it either opens an ACS remediation PR or stops for required user confirmation.
