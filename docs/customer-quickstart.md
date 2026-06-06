# Customer quickstart

This guide gets a safety regression gate running in about 15 minutes.

## Prerequisites

- A repository that uses pull requests into `main`.
- Python 3.11 or newer in CI.
- An ASSERT eval config, or enough agent context to create one.
- Azure / LiteLLM credentials stored as repository secrets: `AZURE_API_KEY`, `AZURE_API_BASE`, and `AZURE_API_VERSION`.

## 1. Install ASSERT locally

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "assert-ai[regression]==0.1.0"
```

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install "assert-ai[regression]==0.1.0"
```

## 2. Create an eval config

```bash
assert-ai init --model azure/gpt-4o
```

Save the config under a stable path such as `eval/eval_config.yaml`.

## 3. Run it once locally

```bash
assert-ai run --config eval/eval_config.yaml
```

Confirm the run produces `scores.jsonl`, `test_set.jsonl`, and `metrics.json` under the artifacts directory.

## 4. Add the workflow

Copy [`examples/minimal-workflow.yml`](../examples/minimal-workflow.yml) into `.github/workflows/safety-gate.yml` and adjust:

- `config` to point at your eval config.
- baseline download wiring to your preferred artifact source.
- secrets if your LiteLLM provider uses different environment variable names.

## 5. Watch the first cycle

1. Merge the workflow to `main`.
2. The first trusted run returns `FirstRun` and uploads `assert-ai-baseline`.
3. Open a PR.
4. The PR downloads the baseline, runs a live eval, and returns `PASS`, `FAIL`, `WARN`, `Inconclusive`, or `TestSetChanged`.

If the first PR still returns `FirstRun`, the baseline artifact was not found. Re-run the `main` workflow or adjust the artifact download step.
