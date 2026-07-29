# ASSERT safety regression gate

A composite GitHub Action that runs `assert-ai` evals on every PR and gates merges against safety regressions detected with a paired t-test. It installs `assert-ai` from PyPI, runs a live eval for each behavior, compares the current runs to a cached baseline, and publishes JSON/Markdown artifacts.

ASSERT configs are written **one behavior per YAML**, so the gate takes a glob and evaluates each behavior independently — while correcting for multiple comparisons across the whole set.


## Coding-agent onboarding

For Copilot CLI, Claude Code, or Cursor, paste this URL into the agent to install the ASSERT CI skill bundle and wire the workflow:

```text
read https://raw.githubusercontent.com/responsibleai/assert-action/main/ONBOARD.md
```

The bundle installs from [`skills/`](skills/) and uses BYO provider credentials from repository secrets such as `AZURE_API_KEY`, `AZURE_API_BASE`, `AZURE_API_VERSION`, or `OPENAI_API_KEY`.

## Quickstart

Create `.github/workflows/safety-gate.yml`:

```yaml
name: Safety regression gate
on:
  pull_request:
    branches: [main]
  push:
    branches: [main]
  schedule:
    - cron: '0 7 * * *'

jobs:
  safety:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
      actions: read          # required so the action can find the baseline run
    steps:
      - uses: actions/checkout@v4
      - uses: responsibleai/assert-action@v1
        with:
          configs: eval/behaviors/*.yaml
          baseline: assert-ai-baseline
          provider-env: |
            AZURE_API_KEY=${{ secrets.AZURE_API_KEY }}
            AZURE_API_BASE=${{ secrets.AZURE_API_BASE }}
            AZURE_API_VERSION=${{ secrets.AZURE_API_VERSION }}
      - if: github.event_name != 'pull_request'
        uses: actions/upload-artifact@v4
        with:
          name: assert-ai-baseline
          path: assert-ai-artifacts/
          retention-days: 90
```

First run on `main` creates the baseline artifact. PR runs locate that baseline and compare paired `test_case_id` rows.

You do **not** need a `download-artifact` step. Artifacts are scoped to the run that produced them, so a PR cannot see the default branch's baseline on its own; the action resolves the most recent successful run on the default branch that still holds the artifact and downloads it for you. That needs `actions: read`. Point `baseline` at a directory instead if you prefer to commit baselines to the repo.

## Inputs

| Input | Required | Default | Description |
|---|---:|---|---|
| `configs` | yes\* | — | Path, glob, or newline-delimited list of `assert-ai` YAML eval configs. One behavior per file. |
| `config` | no | `''` | **Deprecated** single-config alias for `configs`. |
| `gate-mode` | no | `regression` | `regression` blocks on significant regressions; `improvement` passes only on a significant gain. See [Gate modes](#gate-modes). |
| `primary-dimension` | no | `policy_violation` | Dimension that must improve under `gate-mode: improvement`. |
| `guard-dimensions` | no | `overrefusal` | Comma-separated dimensions that must not regress. |
| `alpha` | no | `0.05` | Family-wise significance level for the Holm-Bonferroni correction. |
| `baseline` | no | `''` | Path to a baseline run directory, or the **name** of an artifact from a trusted run. |
| `baseline-branch` | no | `''` | Branch whose successful runs hold the baseline artifact. Defaults to the repo default branch. |
| `assert-ai-version` | no | `0.1.0` | Version of `assert-ai` to install from PyPI. |
| `provider-env` | no | `''` | Newline-delimited `KEY=VALUE` pairs for any LiteLLM provider. Values are masked. |
| `azure-api-key` | no | `''` | Exposed as `AZURE_API_KEY` during the eval. |
| `azure-api-base` | no | `''` | Exposed as `AZURE_API_BASE` during the eval. |
| `azure-api-version` | no | `''` | Exposed as `AZURE_API_VERSION` during the eval. |
| `azure-api-key` | no | `''` | Exposed as `AZURE_API_KEY` during the eval. |
| `azure-api-base` | no | `''` | Exposed as `AZURE_API_BASE` during the eval. |
| `azure-api-version` | no | `''` | Exposed as `AZURE_API_VERSION` during the eval. |
| `post-pr-comment` | no | `true` | Upsert a Markdown gate report on pull requests. |
| `comment-marker` | no | `<!-- assert-ai-gate -->` | Marker used to update one stable PR comment. |
| `fail-on-regression` | no | `true` | Exit 1 when the verdict is `FAIL`. |
| `allow-inconclusive` | no | `true` | Labeling only. When false, insignificant dimensions are reported as `Uncertain` and the top-level verdict becomes `WARN` instead of `Inconclusive`. Does **not** change job pass/fail — see [`docs/verdicts.md`](docs/verdicts.md). |
| `extras` | no | `regression` | Comma-separated PyPI extras, e.g. `regression,otel,langgraph`. |

## Outputs

| Output | Description |
|---|---|
| `gate-verdict` | `PASS`, `WARN`, `FAIL`, `FirstRun`, `TestSetChanged`, or `Inconclusive`. |
| `gate-report-path` | Path to `gate_report.json`. |
| `n-paired-cases` | Number of paired cases used by the t-test. |
| `behaviors-evaluated` | Number of behavior configs that produced a comparable run. |
| `pr-comment-url` | URL of the posted or updated PR comment, if posted. |

## Gate modes

The default gate blocks only on evidence of harm. That is the right default for ordinary pull requests, but it is the wrong tool for a PR whose entire purpose is to *fix* a measured safety problem — under a regression gate, a remediation that does nothing at all passes.

| Mode | Passes when |
|---|---|
| `regression` (default) | No `(behavior × dimension)` regressed significantly. |
| `improvement` | `primary-dimension` improved significantly in at least one behavior **and** no `guard-dimensions` regressed. |

The asymmetry is deliberate: under `regression` a change that merely trends worse is not blocked; under `improvement` a change that merely trends better does not pass. See [`examples/improvement-gate-workflow.yml`](examples/improvement-gate-workflow.yml).

## Multiple behaviors and multiple comparisons

Every matched config is one behavior, run and paired independently. The Holm-Bonferroni step-down correction is then applied across the **whole `(behavior × dimension)` family** rather than per behavior — correcting each behavior separately would quietly inflate the family-wise false-positive rate as behaviors are added. The PR comment states the correction and the family size.

Each behavior also gets its own `artifacts_root`, and baselines are matched to their own suite, so adding a second behavior cannot cause the gate to compare a suite against itself.

## Verdicts

| Verdict | Meaning |
|---|---|
| `PASS` | No safety regression; at least one dimension improved or all checks are clean. |
| `WARN` | The gate needs attention but does not block by default. |
| `FAIL` | A paired dimension regressed significantly (or, in `improvement` mode, failed to improve). |
| `FirstRun` | No baseline exists yet. |
| `TestSetChanged` | The current `test_set.jsonl` does not match the baseline. |
| `Inconclusive` | The paired test found no statistically significant movement. |

See [`docs/verdicts.md`](docs/verdicts.md) for details.

## Baseline lifecycle

Baselines are normal GitHub Actions artifacts from trusted runs on the default branch. They contain `scores.jsonl`, `test_set.jsonl`, and supporting ASSERT artifacts. PRs compare against the latest trusted baseline; scheduled runs refresh it to catch model or dependency changes. See [`docs/baseline-lifecycle.md`](docs/baseline-lifecycle.md).

## Versioning and compatibility

`assert-ai-version` defaults to `0.1.0`; override it to move independently of the action. Use `responsibleai/assert-action@v1` for the floating major tag with compatible bug fixes, or pin an exact tag such as `@v1.0.0`.

## Contributing and license

Contributions are welcome through pull requests. Licensed under the [MIT License](LICENSE).
