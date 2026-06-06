#!/usr/bin/env python3
"""Upsert an ASSERT gate report as a GitHub pull request comment.

The script reads ``gate_report.json`` for the decision and ``pr_comment.md`` for
the report body, wraps them with a stable marker and workflow metadata, then
POSTs or PATCHes a pull request comment. The marker is configurable through the
``COMMENT_MARKER`` environment variable so repeated runs update one comment
instead of appending noise.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import quote

DEFAULT_MARKER = "<!-- assert-ai-gate -->"


_BADGE_COLOR = {
    "PASS": "brightgreen",
    "FAIL": "red",
    "WARN": "yellow",
    "FirstRun": "blue",
    "TestSetChanged": "orange",
    "Inconclusive": "yellow",
}

_ALERT = {
    "PASS": ("TIP", "No statistically significant safety regression was detected."),
    "FAIL": ("CAUTION", "A statistically significant safety regression was detected. Review the failed dimensions before merging."),
    "WARN": ("WARNING", "The gate could not make a clean pass/fail decision. Review the details before merging."),
    "FirstRun": ("TIP", "No baseline was available yet. Merge a trusted run on the default branch to create one."),
    "TestSetChanged": ("WARNING", "The generated test set changed, so paired comparison was skipped. Treat this as a baseline refresh."),
    "Inconclusive": ("WARNING", "The gate was statistically inconclusive. This passes by default unless configured otherwise."),
}


def _load_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"gate report not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _pct(value: Any) -> str:
    try:
        return f"{float(value):.1%}"
    except (TypeError, ValueError):
        return "unknown"


def _special_body(report: dict[str, Any]) -> str | None:
    decision = report.get("decision")
    if decision == "FirstRun":
        n_cases = report.get("current_n_cases", report.get("n_current_cases", 0))
        violation_rate = _pct(report.get("current_violation_rate", 0.0))
        return (
            "## 🛡️ ASSERT — safety regression gate\n\n"
            "**Gate: 🆕 FirstRun**\n\n"
            f"🆕 First run on this branch — no baseline to compare. The current run is "
            f"`{n_cases}` test cases, `{violation_rate}` overall violation rate. "
            "Once this merges, future PRs will pair-test against it.\n"
        )
    if decision == "TestSetChanged":
        baseline_sha = str(report.get("baseline_test_set_sha256", "unknown"))[:7]
        current_sha = str(report.get("current_test_set_sha256", "unknown"))[:7]
        return (
            "## 🛡️ ASSERT — safety regression gate\n\n"
            "**Gate: 🔄 TestSetChanged**\n\n"
            f"🔄 Test set changed (baseline SHA: `{baseline_sha}`, current SHA: `{current_sha}`) — "
            "paired t-test skipped. This is a baseline-refresh PR; merge to make it the new baseline.\n"
        )
    return None


def _read_inner_body(body_path: Path, report: dict[str, Any]) -> str:
    special = _special_body(report)
    if special is not None:
        return special
    if body_path.is_file():
        return body_path.read_text(encoding="utf-8")
    decision = report.get("decision", "WARN")
    return f"## 🛡️ ASSERT — safety regression gate\n\n**Gate: {decision}**\n"


def _badge(decision: str) -> str:
    color = _BADGE_COLOR.get(decision, "lightgrey")
    label = quote(f"ASSERT {decision}")
    return f"![ASSERT gate](https://img.shields.io/badge/{label}-{color})"


def _run_url() -> str | None:
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return None


def build_comment(report: dict[str, Any], body_path: Path, marker: str) -> str:
    decision = str(report.get("decision", "WARN"))
    action_version = report.get("action_version", "unknown")
    alert_kind, alert_text = _ALERT.get(decision, _ALERT["WARN"])
    run_url = _run_url()
    metadata = [f"Action version: `{action_version}`"]
    if run_url:
        metadata.append(f"Workflow run: [open run]({run_url})")
    n_pairs = report.get("n_paired_cases")
    if n_pairs is not None:
        metadata.append(f"Paired cases: `{n_pairs}`")

    inner = _read_inner_body(body_path, report).strip()
    return "\n".join(
        [
            marker,
            f"### 🛡️ ASSERT safety gate {_badge(decision)}",
            "",
            f"> [!{alert_kind}]",
            f"> {alert_text}",
            "",
            " · ".join(metadata),
            "",
            "<details open>",
            "<summary>Gate report</summary>",
            "",
            inner,
            "",
            "</details>",
            "",
        ]
    )


def _api_with_requests(method: str, url: str, headers: dict[str, str], data: dict[str, Any] | None) -> Any:
    import requests  # type: ignore[import-not-found]

    response = requests.request(method, url, headers=headers, json=data, timeout=30)
    response.raise_for_status()
    if not response.content:
        return {}
    return response.json()


def _api_with_urllib(method: str, url: str, headers: dict[str, str], data: dict[str, Any] | None) -> Any:
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {method} {url} failed: {exc.code} {detail}") from exc
    return json.loads(payload.decode("utf-8")) if payload else {}


def github_api(method: str, endpoint: str, data: dict[str, Any] | None = None) -> Any:
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GH_TOKEN"]
    api_root = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    url = f"{api_root}/repos/{repo}{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "assert-ai-action",
    }
    try:
        return _api_with_requests(method, url, headers, data)
    except ImportError:
        return _api_with_urllib(method, url, headers, data)


def upsert_comment(pr_number: str, marker: str, body: str) -> str:
    comments = github_api("GET", f"/issues/{pr_number}/comments?per_page=100")
    for comment in comments:
        if marker in str(comment.get("body", "")):
            updated = github_api("PATCH", f"/issues/comments/{comment['id']}", {"body": body})
            return str(updated.get("html_url", ""))
    created = github_api("POST", f"/issues/{pr_number}/comments", {"body": body})
    return str(created.get("html_url", ""))


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=Path("gate_report.json"), help="Path to gate_report.json.")
    parser.add_argument("--body", type=Path, default=Path("pr_comment.md"), help="Path to the markdown body to wrap.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    marker = os.environ.get("COMMENT_MARKER", DEFAULT_MARKER)
    pr_number = os.environ.get("PR_NUMBER")
    token = os.environ.get("GH_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not pr_number or not token or not repo:
        raise SystemExit("PR_NUMBER, GH_TOKEN, and GITHUB_REPOSITORY are required")

    report = _load_report(args.report)
    comment = build_comment(report, args.body, marker)
    url = upsert_comment(pr_number, marker, comment)
    print(f"ASSERT PR comment: {url}")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as f:
            print(f"pr-comment-url={url}", file=f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
