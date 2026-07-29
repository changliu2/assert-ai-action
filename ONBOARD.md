Read and follow this bootstrap exactly. Your job is to install the ASSERT coding-agent bundle into the current repository, then invoke `wire-assert-ci`.

BYO keys are required: there is no shared ASSERT endpoint. The user must provide provider credentials as repository secrets/environment variables such as `AZURE_API_KEY`, `AZURE_API_BASE`, `AZURE_API_VERSION`, `OPENAI_API_KEY`, or the names required by their LiteLLM provider. Never read or write credential values.

Detect the assistant and install the matching files:

- Claude Code:
  - Fetch `https://raw.githubusercontent.com/responsibleai/assert-action/main/skills/wire-assert-ci/SKILL.md` -> `.claude/skills/wire-assert-ci/SKILL.md`
  - Fetch `https://raw.githubusercontent.com/responsibleai/assert-action/main/skills/run-assert-eval/SKILL.md` -> `.claude/skills/run-assert-eval/SKILL.md`
- GitHub Copilot CLI:
  - Fetch `https://raw.githubusercontent.com/responsibleai/assert-action/main/skills/wire-assert-ci/wire-assert-ci.prompt.md` -> `.github/prompts/wire-assert-ci.prompt.md`
  - Fetch `https://raw.githubusercontent.com/responsibleai/assert-action/main/skills/run-assert-eval/run-assert-eval.prompt.md` -> `.github/prompts/run-assert-eval.prompt.md`
- Cursor:
  - Fetch `https://raw.githubusercontent.com/responsibleai/assert-action/main/skills/wire-assert-ci/assert-ci.mdc` -> `.cursor/rules/assert-ci.mdc`
  - Fetch `https://raw.githubusercontent.com/responsibleai/assert-action/main/skills/run-assert-eval/assert.mdc` -> `.cursor/rules/assert.mdc`

Create parent directories if missing. Do not overwrite unrelated local files without showing the diff first. After the matching files are written, invoke the `wire-assert-ci` skill and follow it until it either opens an ACS remediation PR or stops for required user confirmation.
