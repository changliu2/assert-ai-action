import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "find_baseline_run.py"
_SPEC = importlib.util.spec_from_file_location("find_baseline_run", _MODULE_PATH)
assert _SPEC is not None
find_baseline_run = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(find_baseline_run)


def _fake_api(pages: dict[str, object]):
    def _get(path: str, token: str):
        for prefix, payload in pages.items():
            if path.startswith(prefix):
                return payload
        raise AssertionError(f"unexpected API path: {path}")

    return _get


def test_returns_the_newest_run_that_still_has_the_artifact(monkeypatch) -> None:
    monkeypatch.setattr(
        find_baseline_run,
        "_get",
        _fake_api(
            {
                "/repos/o/r/actions/runs?": {"workflow_runs": [{"id": 3}, {"id": 2}, {"id": 1}]},
                "/repos/o/r/actions/runs/3/artifacts": {"artifacts": [{"name": "other"}]},
                "/repos/o/r/actions/runs/2/artifacts": {
                    "artifacts": [{"name": "assert-ai-baseline", "expired": False}]
                },
            }
        ),
    )

    run_id = find_baseline_run.find_baseline_run(
        repo="o/r", token="t", artifact_name="assert-ai-baseline", branch="main", workflow=None
    )

    assert run_id == 2


def test_skips_expired_artifacts(monkeypatch) -> None:
    # An expired artifact is still listed but cannot be downloaded; treating it
    # as usable would produce a confusing mid-job download failure.
    monkeypatch.setattr(
        find_baseline_run,
        "_get",
        _fake_api(
            {
                "/repos/o/r/actions/runs?": {"workflow_runs": [{"id": 9}]},
                "/repos/o/r/actions/runs/9/artifacts": {
                    "artifacts": [{"name": "assert-ai-baseline", "expired": True}]
                },
            }
        ),
    )

    run_id = find_baseline_run.find_baseline_run(
        repo="o/r", token="t", artifact_name="assert-ai-baseline", branch="main", workflow=None
    )

    assert run_id is None


def test_missing_baseline_is_not_a_build_failure(monkeypatch, tmp_path) -> None:
    output = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setattr(
        find_baseline_run,
        "_get",
        _fake_api({"/repos/o/r/actions/runs?": {"workflow_runs": []}}),
    )

    rc = find_baseline_run.main(["--artifact-name", "assert-ai-baseline", "--branch", "main"])

    assert rc == 0
    assert "found=false" in output.read_text(encoding="utf-8")


def test_api_failure_degrades_to_firstrun(monkeypatch, tmp_path) -> None:
    output = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")

    def _boom(path: str, token: str):
        raise find_baseline_run.urllib.error.URLError("network down")

    monkeypatch.setattr(find_baseline_run, "_get", _boom)

    rc = find_baseline_run.main(["--artifact-name", "assert-ai-baseline"])

    assert rc == 0
    body = output.read_text(encoding="utf-8")
    assert "found=false" in body and "run-id=" in body


def test_no_token_skips_lookup(monkeypatch, tmp_path) -> None:
    output = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")

    rc = find_baseline_run.main(["--artifact-name", "assert-ai-baseline"])

    assert rc == 0
    assert "found=false" in output.read_text(encoding="utf-8")


@pytest.mark.parametrize("workflow,expected", [("gate.yml", True), (None, False)])
def test_workflow_scoping_changes_the_endpoint(monkeypatch, workflow, expected) -> None:
    seen: list[str] = []

    def _get(path: str, token: str):
        seen.append(path)
        return {"workflow_runs": []}

    monkeypatch.setattr(find_baseline_run, "_get", _get)
    find_baseline_run.find_baseline_run(
        repo="o/r", token="t", artifact_name="a", branch="main", workflow=workflow
    )

    assert ("/workflows/gate.yml/runs" in seen[0]) is expected
