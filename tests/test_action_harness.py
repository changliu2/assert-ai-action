from __future__ import annotations

import json
import os
import re
from pathlib import Path

import yaml

from tests.harness.action_harness import ACTION, run_action

N = 60


def _write_config(path: Path, suite: str, behavior: str | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "suite": suite,
                "behavior": {"name": behavior or suite, "description": "Harness behavior"},
                "pipeline": {"inference": {"target": {"callable": "agent:chat"}}},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def _write_run(
    root: Path,
    suite: str,
    run: str,
    *,
    policy_rate: float,
    over_rate: float = 0.0,
    n: int = N,
    test_id_prefix: str = "case",
) -> Path:
    run_dir = root / "results" / suite / run
    run_dir.mkdir(parents=True, exist_ok=True)
    policy_true = round(policy_rate * n)
    over_true = round(over_rate * n)
    with (run_dir / "test_set.jsonl").open("w", encoding="utf-8") as fh:
        for i in range(n):
            fh.write(json.dumps({"id": f"{test_id_prefix}-{i}", "prompt": f"Prompt {i}"}) + "\n")
    with (run_dir / "scores.jsonl").open("w", encoding="utf-8") as fh:
        for i in range(n):
            fh.write(
                json.dumps(
                    {
                        "test_case_id": f"case-{i}",
                        "verdict": {
                            "dimensions": {
                                "policy_violation": i < policy_true,
                                "overrefusal": i < over_true,
                            }
                        },
                    }
                )
                + "\n"
            )
    (run_dir / "inference_set.jsonl").write_text(
        "".join(json.dumps({"test_case_id": f"case-{i}", "output": "baseline"}) + "\n" for i in range(n)),
        encoding="utf-8",
    )
    (run_dir / "metrics.json").write_text(json.dumps({"n_cases": n}, indent=2), encoding="utf-8")
    return run_dir


def _report(workspace: Path) -> dict:
    return json.loads((workspace / "gate_report.json").read_text(encoding="utf-8"))


def test_firstrun_has_no_baseline(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path / "eval" / "behavior.yaml", "first-run")
    result = run_action(
        tmp_path,
        inputs={"configs": str(cfg), "baseline": ""},
        env={"ASSERT_STUB_POLICY_RATE": "0.1", "ASSERT_STUB_OVERREFUSAL_RATE": "0"},
    )

    assert result.returncode == 0, result.log
    report = _report(tmp_path)
    assert report["decision"] == "FirstRun"
    assert report["current_n_cases"] == N
    assert result.outputs["locate"]["baseline-available"] == "false"
    assert result.outputs["locate"]["first-current"]


def test_regression_gate_clean_is_non_blocking(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path / "eval" / "behavior.yaml", "clean")
    base = tmp_path / "baseline"
    _write_run(base, "clean", "base", policy_rate=0.1)

    result = run_action(
        tmp_path,
        inputs={"configs": str(cfg), "baseline": str(base)},
        env={"ASSERT_STUB_POLICY_RATE": "0.1", "ASSERT_STUB_OVERREFUSAL_RATE": "0"},
    )

    assert result.returncode == 0, result.log
    assert _report(tmp_path)["decision"] in {"Inconclusive", "PASS", "WARN"}
    assert result.outputs["decide"]["gate-verdict"] != "FAIL"


def test_regression_gate_regressed_fails_decide_step(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path / "eval" / "behavior.yaml", "regressed")
    base = tmp_path / "baseline"
    _write_run(base, "regressed", "base", policy_rate=0.0)

    result = run_action(
        tmp_path,
        inputs={"configs": str(cfg), "baseline": str(base)},
        env={"ASSERT_STUB_POLICY_RATE": "0.5", "ASSERT_STUB_OVERREFUSAL_RATE": "0"},
    )

    assert result.returncode != 0
    assert result.step("Decide exit code").returncode != 0
    assert _report(tmp_path)["decision"] == "FAIL"
    assert result.outputs["decide"]["gate-verdict"] == "FAIL"


def test_improvement_gate_insignificant_change_fails(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path / "eval" / "behavior.yaml", "prompt-only")
    base = tmp_path / "baseline"
    _write_run(base, "prompt-only", "base", policy_rate=0.5)

    result = run_action(
        tmp_path,
        inputs={"configs": str(cfg), "baseline": str(base), "gate-mode": "improvement"},
        env={"ASSERT_STUB_POLICY_RATE": "0.45", "ASSERT_STUB_OVERREFUSAL_RATE": "0"},
    )

    assert result.returncode != 0
    assert _report(tmp_path)["decision"] == "FAIL"


def test_improvement_gate_significant_gain_passes(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path / "eval" / "behavior.yaml", "control-plane")
    base = tmp_path / "baseline"
    _write_run(base, "control-plane", "base", policy_rate=0.5)

    result = run_action(
        tmp_path,
        inputs={"configs": str(cfg), "baseline": str(base), "gate-mode": "improvement"},
        env={"ASSERT_STUB_POLICY_RATE": "0.08", "ASSERT_STUB_OVERREFUSAL_RATE": "0"},
    )

    assert result.returncode == 0, result.log
    report = _report(tmp_path)
    assert report["decision"] == "PASS"
    assert result.outputs["decide"]["gate-verdict"] == "PASS"


def test_min_pairs_input_allows_small_test_set_to_reach_verdict(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path / "eval" / "behavior.yaml", "small-regression")
    base = tmp_path / "baseline"
    _write_run(base, "small-regression", "base", policy_rate=0.0, n=20)

    too_few = run_action(
        tmp_path / "default",
        inputs={"configs": str(cfg), "baseline": str(base)},
        env={
            "ASSERT_STUB_CASES": "20",
            "ASSERT_STUB_POLICY_RATE": "1.0",
            "ASSERT_STUB_OVERREFUSAL_RATE": "0",
        },
    )
    assert too_few.returncode == 0, too_few.log
    assert _report(tmp_path / "default")["decision"] != "FAIL"

    lowered = run_action(
        tmp_path / "lowered",
        inputs={"configs": str(cfg), "baseline": str(base), "min-pairs": "5"},
        env={
            "ASSERT_STUB_CASES": "20",
            "ASSERT_STUB_POLICY_RATE": "1.0",
            "ASSERT_STUB_OVERREFUSAL_RATE": "0",
        },
    )
    assert lowered.returncode != 0
    assert _report(tmp_path / "lowered")["decision"] == "FAIL"


def test_target_install_runs_when_set_and_is_skipped_when_empty(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path / "eval" / "behavior.yaml", "install-target")

    empty = run_action(
        tmp_path / "empty",
        inputs={"configs": str(cfg), "baseline": ""},
        env={"ASSERT_STUB_POLICY_RATE": "0.0"},
    )
    assert empty.returncode == 0, empty.log
    assert empty.step("Install target").skipped

    marker = "target-install-marker.txt"
    configured = run_action(
        tmp_path / "configured",
        inputs={
            "configs": str(cfg),
            "baseline": "",
            "target-install": f"python -c \"open('{marker}','w').write('installed')\"",
        },
        env={"ASSERT_STUB_POLICY_RATE": "0.0"},
    )
    assert configured.returncode == 0, configured.log
    assert not configured.step("Install target").skipped
    assert (tmp_path / "configured" / marker).read_text(encoding="utf-8") == "installed"


def test_target_install_failure_is_loud(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path / "eval" / "behavior.yaml", "install-fails")
    result = run_action(
        tmp_path,
        inputs={"configs": str(cfg), "baseline": "", "target-install": "echo broken target install; exit 42"},
        env={"ASSERT_STUB_POLICY_RATE": "0.0"},
    )

    assert result.returncode == 42
    assert result.step("Install target").returncode == 42
    assert "broken target install" in result.step("Install target").stdout


def test_multi_behavior_glob_gets_distinct_artifact_roots(tmp_path: Path) -> None:
    for i in range(3):
        _write_config(tmp_path / "eval" / "behaviors" / f"behavior {i}.yaml", f"family-{i}", f"behavior {i}")
    base = tmp_path / "baseline"
    for i in range(3):
        _write_run(base, f"family-{i}", "base", policy_rate=0.5)

    result = run_action(
        tmp_path,
        inputs={"configs": "eval/behaviors/*.yaml", "baseline": str(base), "gate-mode": "improvement"},
        env={"ASSERT_STUB_POLICY_RATE": "0.08", "ASSERT_STUB_OVERREFUSAL_RATE": "0"},
    )

    assert result.returncode == 0, result.log
    manifest = json.loads((tmp_path / "assert-ai-behaviors.json").read_text(encoding="utf-8"))
    roots = {entry["artifacts_root"] for entry in manifest}
    assert len(manifest) == 3
    assert len(roots) == 3
    report = _report(tmp_path)
    assert report["behaviors_evaluated"] == 3
    assert report["family_size"] == 6
    assert result.outputs["decide"]["behaviors-evaluated"] == "3"


def test_multi_behavior_drift_reports_only_drifted_behavior(tmp_path: Path) -> None:
    _write_config(tmp_path / "eval" / "behaviors" / "stable.yaml", "stable-suite", "stable")
    _write_config(tmp_path / "eval" / "behaviors" / "drifted.yaml", "drifted-suite", "drifted")
    base = tmp_path / "baseline"
    _write_run(base, "stable-suite", "base", policy_rate=0.1)
    _write_run(base, "drifted-suite", "base", policy_rate=0.1, test_id_prefix="old-case")

    result = run_action(
        tmp_path,
        inputs={"configs": "eval/behaviors/*.yaml", "baseline": str(base)},
        env={"ASSERT_STUB_POLICY_RATE": "0.1", "ASSERT_STUB_OVERREFUSAL_RATE": "0"},
    )

    assert result.returncode == 0, result.log
    report = _report(tmp_path)
    assert report["decision"] == "TestSetChanged"
    assert report["drifted_behaviors"] == ["drifted"]
    assert "drifted" in (tmp_path / "pr_comment.md").read_text(encoding="utf-8")


def test_deprecated_config_input_still_warns_and_runs(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path / "eval" / "legacy.yaml", "legacy")
    result = run_action(
        tmp_path,
        inputs={"configs": "", "config": str(cfg), "baseline": ""},
        env={"ASSERT_STUB_POLICY_RATE": "0.0"},
    )

    assert result.returncode == 0, result.log
    assert "::warning::'config' is deprecated" in result.step("Resolve config input").stdout
    assert _report(tmp_path)["decision"] == "FirstRun"


def test_provider_env_masks_values_and_preserves_equals_without_trailing_newline(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path / "eval" / "behavior.yaml", "provider-env")
    provider_env = "TOKEN=abc=def\n# ignored\nEMPTY=\nLAST=line-without-newline"
    result = run_action(
        tmp_path,
        inputs={"configs": str(cfg), "provider-env": provider_env, "azure-api-key": "az-secret", "baseline": ""},
        env={"ASSERT_STUB_POLICY_RATE": "0.0"},
    )

    assert result.returncode == 0, result.log
    export = result.step("Export provider credentials")
    assert "::add-mask::az-secret" in export.stdout
    assert "::add-mask::abc=def" in export.stdout
    assert "::add-mask::line-without-newline" in export.stdout
    assert result.env["TOKEN"] == "abc=def"
    assert result.env["LAST"] == "line-without-newline"
    assert "EMPTY" not in result.env

    action = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
    script = next(s["run"] for s in action["runs"]["steps"] if s.get("name") == "Export provider credentials")
    emit_body = re.search(r"emit\(\) \{(.*?)\n\}", script, re.S).group(1)
    assert emit_body.index("echo \"::add-mask::$value\"") < emit_body.index("printf '%s=%s\\n'")


def test_resolve_config_heredoc_preserves_glob_newlines_and_spaces(tmp_path: Path) -> None:
    _write_config(tmp_path / "eval" / "space dir" / "one.yaml", "one")
    _write_config(tmp_path / "eval" / "two.yaml", "two")
    selected = "eval/space dir/*.yaml\neval/two.yaml"
    result = run_action(
        tmp_path,
        inputs={"configs": selected, "baseline": ""},
        env={"ASSERT_STUB_POLICY_RATE": "0.0"},
    )

    assert result.returncode == 0, result.log
    assert result.outputs["configs"]["selected"] == selected
    manifest = json.loads((tmp_path / "assert-ai-behaviors.json").read_text(encoding="utf-8"))
    assert [entry["suite"] for entry in manifest] == ["one", "two"]


def test_referenced_step_outputs_are_produced_or_declared_optional() -> None:
    action = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
    scripts_by_id = {s.get("id"): s.get("run", "") for s in action["runs"]["steps"] if s.get("id")}
    refs = set(re.findall(r"steps\.([^.]+)\.outputs\.([A-Za-z0-9_-]+)", ACTION.read_text(encoding="utf-8")))
    optional = {("post-comment", "pr-comment-url")}  # Only produced when PR commenting runs.
    helper_sources = {
        "baseline-run": (ACTION.parent / "scripts" / "find_baseline_run.py").read_text(encoding="utf-8"),
        "locate": (ACTION.parent / "scripts" / "plan_behaviors.py").read_text(encoding="utf-8"),
        "drift": (ACTION.parent / "scripts" / "detect_test_set_drift.py").read_text(encoding="utf-8"),
    }
    for step_id, output in refs - optional:
        script = scripts_by_id.get(step_id, "")
        source = script + "\n" + helper_sources.get(step_id, "")
        assert step_id in scripts_by_id, f"missing step id {step_id} for output {output}"
        assert output in source or output.replace("-", "_") in source, (step_id, output)


def test_action_does_not_depend_on_files_in_the_consumer_repo() -> None:
    """The action must run in a repo that has no Python dependency manifest.

    `actions/setup-python` with `cache: pip` hashes a dependency file from the
    *calling* repo and hard-fails with "No file matched to
    [**/requirements.txt or **/pyproject.toml]" when the consumer has neither at
    its root. Setup Python is this action's first step, so that failure skips
    every step after it and the gate silently evaluates nothing rather than
    reporting a verdict. A live consumer-path smoke run caught exactly that.

    Consumers legitimately look like this: a Node repo with a Python agent, a
    repo whose pyproject.toml lives in a subdirectory, or one that vendors deps.
    We install assert-ai from PyPI, so the cache is worth a few seconds and not
    worth excluding those repos.
    """
    action = yaml.safe_load(ACTION.read_text(encoding="utf-8"))

    for step in action["runs"]["steps"]:
        uses = step.get("uses", "")
        if not uses.startswith("actions/setup-python"):
            continue
        with_block = step.get("with") or {}
        assert "cache" not in with_block, (
            f"{step.get('name')!r} sets cache={with_block.get('cache')!r}; this fails "
            "in any consumer repo without a root requirements.txt or pyproject.toml, "
            "which skips every later step and makes the gate a no-op."
        )
        assert "cache-dependency-path" not in with_block, (
            f"{step.get('name')!r} pins cache-dependency-path to a consumer-repo file."
        )
