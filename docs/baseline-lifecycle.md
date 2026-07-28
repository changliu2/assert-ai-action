# Baseline lifecycle

A baseline is the trusted ASSERT artifact set that PRs compare against. It must contain at least:

- `scores.jsonl` — judge verdicts for each test case.
- `test_set.jsonl` — the exact generated cases used for pairing.
- `metrics.json` — aggregate run metrics, useful for humans.

## How baselines are produced

Run the action on `main` after a trusted merge, then upload `assert-ai-artifacts/` as a GitHub Actions artifact named `assert-ai-baseline`.

```yaml
- uses: responsibleai/assert-action@v1
  with:
    config: eval/eval_config.yaml
    azure-api-key: ${{ secrets.AZURE_API_KEY }}
    azure-api-base: ${{ secrets.AZURE_API_BASE }}
    azure-api-version: ${{ secrets.AZURE_API_VERSION }}
- uses: actions/upload-artifact@v4
  with:
    name: assert-ai-baseline
    path: assert-ai-artifacts/
    retention-days: 90
```

## How baselines are refreshed

Use both `push` to `main` and a nightly `schedule`. The push path captures code changes. The scheduled path catches model, prompt dependency, and tool-backend drift even when code is unchanged.

## How PRs consume baselines

Download the latest trusted baseline artifact before invoking the action, then pass the local path through `baseline`.

```yaml
- uses: actions/download-artifact@v4
  continue-on-error: true
  with:
    name: assert-ai-baseline
    path: assert-ai-baseline
- uses: responsibleai/assert-action@v1
  with:
    config: eval/eval_config.yaml
    baseline: assert-ai-baseline
```

If no artifact is available, the action returns `FirstRun` and still uploads the current artifacts.

## Test-set drift

The paired t-test is valid only when baseline and current runs score the same cases. The action compares SHA256 hashes of `test_set.jsonl`:

- same hash: run the paired gate.
- different hash: return `TestSetChanged` and skip the t-test.

Treat `TestSetChanged` as a baseline-refresh PR. Review why the cases changed, merge if expected, then let the next `main` run publish the new baseline.

## Manual recovery

If a baseline is stale or missing:

1. Run the workflow on `main` with known-good code.
2. Confirm `assert-ai-artifacts/` includes `scores.jsonl`, `test_set.jsonl`, and `metrics.json`.
3. Upload or retain it as `assert-ai-baseline`.
4. Re-run the PR workflow.

## Version tags

Release tags use semantic versions such as `v1.0.0`. The release workflow force-updates the matching major tag, so `v1` points to the latest compatible `v1.x.y` release. Pin `@v1` for compatible fixes or an exact tag for maximum repeatability.
