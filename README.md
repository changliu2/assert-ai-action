# ASSERT safety regression gate

A composite GitHub Action that runs `assert-ai` evals on every PR and gates merges against safety regressions detected with a paired t-test. It installs `assert-ai==0.1.0` from PyPI, runs a live eval, compares the current run to a cached baseline, and publishes JSON/Markdown artifacts.

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
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - id: download-baseline
        if: github.event_name == 'pull_request'
        uses: actions/download-artifact@v4
        continue-on-error: true
        with:
          name: assert-ai-baseline
          path: assert-ai-baseline
      - uses: responsibleai/assert-ai-action@v1
        with:
          config: eval/eval_config.yaml
          baseline: assert-ai-baseline
          azure-api-key: ${{ secrets.AZURE_API_KEY }}
          azure-api-base: ${{ secrets.AZURE_API_BASE }}
          azure-api-version: ${{ secrets.AZURE_API_VERSION }}
      - if: github.event_name != 'pull_request'
        uses: actions/upload-artifact@v4
        with:
          name: assert-ai-baseline
          path: assert-ai-artifacts/
          retention-days: 90
```

First run on `main` creates the baseline artifact. PR runs download that baseline and compare paired `test_case_id` rows.

## Inputs

| Input | Required | Default | Description |
|---|---:|---|---|
| `config` | yes | — | Path to the `assert-ai` YAML eval config. |
| `baseline` | no | `''` | Path or artifact name for a cached baseline containing `scores.jsonl` and `test_set.jsonl`. |
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
| `pr-comment-url` | URL of the posted or updated PR comment, if posted. |

## Verdicts

| Verdict | Meaning |
|---|---|
| `PASS` | No safety regression; at least one dimension improved or all checks are clean. |
| `WARN` | The gate needs attention but does not block by default. |
| `FAIL` | A paired dimension regressed significantly. |
| `FirstRun` | No baseline exists yet. |
| `TestSetChanged` | The current `test_set.jsonl` does not match the baseline. |
| `Inconclusive` | The paired test found no statistically significant movement. |

See [`docs/verdicts.md`](docs/verdicts.md) for details.

## Baseline lifecycle

Baselines are normal GitHub Actions artifacts from trusted runs on `main`. They contain `scores.jsonl`, `test_set.jsonl`, and supporting ASSERT artifacts. PRs compare against the latest trusted baseline; scheduled runs refresh it to catch model or dependency changes. See [`docs/baseline-lifecycle.md`](docs/baseline-lifecycle.md).

## Versioning and compatibility

This action pins `assert-ai==0.1.0`. Use `responsibleai/assert-ai-action@v1` for the floating major tag with compatible bug fixes, or pin an exact tag such as `@v1.0.0`.

## Contributing and license

Contributions are welcome through pull requests. Licensed under the [MIT License](LICENSE).
