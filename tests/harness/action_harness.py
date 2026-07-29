"""Local runner for the ASSERT composite action's bash glue."""
from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
ACTION = ROOT / "action.yml"
STUB_BIN = Path(__file__).resolve().parent / "bin"


@dataclass
class StepResult:
    id: str | None
    name: str
    skipped: bool
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
    outputs: dict[str, str] = field(default_factory=dict)


@dataclass
class HarnessResult:
    workspace: Path
    returncode: int
    steps: list[StepResult]
    outputs: dict[str, dict[str, str]]
    env: dict[str, str]

    @property
    def log(self) -> str:
        return "".join(s.stdout + s.stderr for s in self.steps)

    def step(self, name: str) -> StepResult:
        for step in self.steps:
            if step.name == name or step.id == name:
                return step
        raise KeyError(name)


def _bash_path(path: Path) -> str:
    resolved = path.resolve()
    if os.name == "nt":
        drive = resolved.drive.rstrip(":").lower()
        rest = resolved.as_posix().split(":", 1)[1]
        return f"/{drive}{rest}"
    return resolved.as_posix()


def _find_bash() -> str:
    preferred = Path(r"C:\Program Files\Git\bin\bash.exe")
    if preferred.is_file():
        return str(preferred)
    return shutil.which("bash") or "bash"


def _read_outputs(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    lines = path.read_text(encoding="utf-8").splitlines()
    out: dict[str, str] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if "<<" in line:
            key, delim = line.split("<<", 1)
            i += 1
            value: list[str] = []
            while i < len(lines) and lines[i] != delim:
                value.append(lines[i])
                i += 1
            out[key] = "\n".join(value)
        elif "=" in line:
            key, value = line.split("=", 1)
            out[key] = value
        i += 1
    return out


def _read_env(path: Path) -> dict[str, str]:
    updates: dict[str, str] = {}
    if not path.is_file():
        return updates
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        updates[key] = value
    return updates


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value != "" and value.lower() != "false"
    return bool(value)


def _split_top(expr: str, op: str) -> list[str]:
    parts: list[str] = []
    start = 0
    quote: str | None = None
    i = 0
    while i < len(expr):
        c = expr[i]
        if quote:
            if c == quote:
                quote = None
        elif c in {"'", '"'}:
            quote = c
        elif expr.startswith(op, i):
            parts.append(expr[start:i].strip())
            start = i + len(op)
            i += len(op) - 1
        i += 1
    if parts:
        parts.append(expr[start:].strip())
    return parts


class ActionRunner:
    def __init__(self, workspace: Path, *, inputs: dict[str, str] | None = None, env: dict[str, str] | None = None):
        self.workspace = workspace
        self.action = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
        defaults = {name: str(spec.get("default", "")) for name, spec in self.action["inputs"].items()}
        defaults.update(inputs or {})
        self.inputs = defaults
        self.github = {
            "action_path": _bash_path(ROOT),
            "workspace": ".",
            "token": "stub-token",
            "repository": "owner/repo",
            "event_name": "push",
            "event.repository.default_branch": "main",
            "event.pull_request.number": "123",
        }
        self.outputs: dict[str, dict[str, str]] = {}
        self.env = dict(env or {})
        self.results: list[StepResult] = []

    def _ref(self, token: str) -> Any:
        if token.startswith("inputs."):
            return self.inputs.get(token[len("inputs."):], "")
        if token.startswith("steps."):
            m = re.fullmatch(r"steps\.([^.]+)\.outputs\.([A-Za-z0-9_-]+)", token)
            if m:
                return self.outputs.get(m.group(1), {}).get(m.group(2), "")
        if token.startswith("github."):
            return self.github.get(token[len("github."):], "")
        if token == "true":
            return True
        if token == "false":
            return False
        return ""

    def eval_expr(self, expr: str) -> Any:
        expr = expr.strip()
        if expr.startswith("${{") and expr.endswith("}}"):
            expr = expr[3:-2].strip()
        if expr == "always()":
            return True
        m = re.fullmatch(r"hashFiles\('([^']+)'\)", expr)
        if m:
            return m.group(1) if any(self.workspace.glob(m.group(1))) else ""
        for part in _split_top(expr, "||"):
            value = self.eval_expr(part)
            if _truthy(value):
                return value
        parts = _split_top(expr, "&&")
        if parts:
            value: Any = True
            for part in parts:
                value = self.eval_expr(part)
                if not _truthy(value):
                    return False
            return value
        for op in ("!=", "=="):
            parts = _split_top(expr, op)
            if parts:
                left = self.eval_expr(parts[0])
                right = self.eval_expr(parts[1])
                return (str(left) != str(right)) if op == "!=" else (str(left) == str(right))
        if (expr.startswith("'") and expr.endswith("'")) or (expr.startswith('"') and expr.endswith('"')):
            return expr[1:-1]
        return self._ref(expr)

    def interpolate(self, value: str) -> str:
        return re.sub(r"\$\{\{(.*?)\}\}", lambda m: str(self.eval_expr(m.group(0))), value, flags=re.DOTALL)

    def should_run(self, step: dict[str, Any]) -> bool:
        cond = step.get("if")
        return True if cond is None else _truthy(self.eval_expr(str(cond)))

    def run(self) -> HarnessResult:
        self.workspace.mkdir(parents=True, exist_ok=True)
        harness_dir = self.workspace / ".harness"
        harness_dir.mkdir(exist_ok=True)
        stub = STUB_BIN / "assert-ai"
        try:
            stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except OSError:
            pass

        persisted_env: dict[str, str] = {}
        rc = 0
        for index, step in enumerate(self.action["runs"]["steps"]):
            name = step.get("name", f"step-{index}")
            step_id = step.get("id")
            if not self.should_run(step):
                self.results.append(StepResult(step_id, name, skipped=True))
                continue
            if "uses" in step:
                self.results.append(StepResult(step_id, name, skipped=True))
                continue
            if name == "Install assert-ai":
                # Dependency installation is not action glue, and the harness supplies a stub CLI.
                self.results.append(StepResult(step_id, name, skipped=True))
                continue

            output_file = harness_dir / f"{index:02d}-{step_id or 'step'}.out"
            env_file = harness_dir / f"{index:02d}-{step_id or 'step'}.env"
            summary_file = harness_dir / "summary.md"
            script_file = harness_dir / f"{index:02d}-{step_id or 'step'}.sh"
            script_file.write_text("set -e\n" + self.interpolate(step["run"]), encoding="utf-8")

            proc_env = os.environ.copy()
            proc_env.update(self.env)
            proc_env.update(persisted_env)
            proc_env["PATH"] = str(STUB_BIN) + os.pathsep + proc_env.get("PATH", "")
            proc_env.update(
                {
                    "GITHUB_OUTPUT": output_file.as_posix(),
                    "GITHUB_ENV": env_file.as_posix(),
                    "GITHUB_WORKSPACE": ".",
                    "GITHUB_STEP_SUMMARY": summary_file.as_posix(),
                }
            )
            for key, raw in (step.get("env") or {}).items():
                proc_env[key] = self.interpolate(str(raw))

            proc = subprocess.run(
                [_find_bash(), "-e", script_file.as_posix()],
                cwd=self.workspace,
                env=proc_env,
                text=True,
                capture_output=True,
            )
            outputs = _read_outputs(output_file)
            persisted_env.update(_read_env(env_file))
            if step_id:
                self.outputs[step_id] = outputs
            self.results.append(
                StepResult(step_id, name, skipped=False, returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr, outputs=outputs)
            )
            if proc.returncode != 0:
                rc = proc.returncode
                break
        merged_env = {**self.env, **persisted_env}
        return HarnessResult(self.workspace, rc, self.results, self.outputs, merged_env)


def run_action(workspace: Path, *, inputs: dict[str, str] | None = None, env: dict[str, str] | None = None) -> HarnessResult:
    return ActionRunner(workspace, inputs=inputs, env=env).run()
