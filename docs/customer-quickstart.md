# Customer quickstart

This guide gets a safety regression gate wired quickly. A real committed gate usually takes tens of minutes per run because it needs enough paired cases for statistics.

## Prerequisites

- A repository that uses pull requests into `main`.
- Python 3.11 or newer in CI.
- An ASSERT eval config, or enough agent context to create one.
- Azure / LiteLLM credentials stored as repository secrets: `AZURE_API_KEY`, `AZURE_API_BASE`, and `AZURE_API_VERSION`.

## 1. Install ASSERT locally

Install ASSERT from PyPI. Do not use `pip install -e .` unless you are inside the ASSERT repository itself.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "assert-ai[regression,otel]==0.1.0"
```

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install "assert-ai[regression,otel]==0.1.0"
```

Use extras for your target route: `regression,otel` for traced `target.callable`, `regression,otel,langgraph` for LangGraph, `regression,aiohttp` for native `target.endpoint`, and `regression` for a plain model target.

## 2. Create an eval config

```bash
assert-ai init --model azure/gpt-4o
```

Save configs under stable paths such as `eval/behaviors/<behavior>.yaml`, one behavior per YAML. For Python callables, follow the callable target signature in https://github.com/responsibleai/ASSERT/blob/main/docs/targets/callable.md. For HTTP services that accept `{"message": ..., "history": [...]}` and return `{"response": ...}`, use `target.endpoint`; use a callable shim only for a different HTTP shape.

## 3. Run it once locally

A smoke run can be small to prove imports and credentials. A committed gate needs at least `min-pairs` paired cases per behavior (default 30; use about 40 for margin). Below that, dimensions become `TooFewSamples` non-verdicts and will not protect the PR.

```bash
assert-ai run --config eval/behaviors/<behavior>.yaml
```

Confirm the run produces `scores.jsonl`, `test_set.jsonl`, and `metrics.json` under the artifacts directory.

## 4. Add the workflow

Copy [`examples/minimal-workflow.yml`](../examples/minimal-workflow.yml) into `.github/workflows/safety-gate.yml` and adjust:

- `configs` to point at your one-behavior-per-YAML files.
- `extras` for your target route.
- `target-install` so CI installs the repository under test, for example `python -m pip install -e .` for Python and `src/` layouts.
- secrets if your LiteLLM provider uses different environment variable names.

Do not add a manual baseline download step. The action resolves the default-branch baseline artifact itself and needs `permissions: actions: read`.

## 5. Watch the first cycle

1. Merge the workflow to `main`.
2. The first trusted run returns `FirstRun` and uploads `assert-ai-baseline`.
3. Open a PR.
4. The PR resolves the trusted baseline, runs a live eval, and returns `PASS`, `FAIL`, `WARN`, `Inconclusive`, `TooFewSamples`, or `TestSetChanged`.

If the first PR still returns `FirstRun`, the baseline artifact was not found. Re-run the `main` workflow and confirm the job has `actions: read` permission.
