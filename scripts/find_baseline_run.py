#!/usr/bin/env python3
"""Find the workflow run that holds the trusted baseline artifact.

GitHub Actions artifacts are scoped to the run that produced them. A pull
request therefore cannot see the baseline uploaded by the last push to the
default branch unless it is told which run to look in. Without this step
``actions/download-artifact`` silently finds nothing, every PR reports
``FirstRun``, and the gate never actually gates -- which is the most common way
a safety gate ends up green forever.

This resolves the most recent successful run on the default branch that still
has a live artifact with the wanted name, and emits its id for
``actions/download-artifact``'s ``run-id`` input.

Emits ``run-id`` (empty when nothing suitable was found) and ``found``.
Never fails the build: a missing baseline is a legitimate FirstRun.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

API_ROOT = os.environ.get("GITHUB_API_URL", "https://api.github.com")


def _get(path: str, token: str) -> Any:
    request = urllib.request.Request(
        f"{API_ROOT}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "assert-action",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _emit(**values: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        for key, value in values.items():
            print(f"{key}={value}")
        return
    with open(output, "a", encoding="utf-8") as fh:
        for key, value in values.items():
            fh.write(f"{key}={value}\n")


def find_baseline_run(
    *,
    repo: str,
    token: str,
    artifact_name: str,
    branch: str,
    workflow: str | None,
    limit: int = 20,
) -> int | None:
    query = f"?branch={branch}&status=success&per_page={limit}"
    endpoint = (
        f"/repos/{repo}/actions/workflows/{workflow}/runs{query}"
        if workflow
        else f"/repos/{repo}/actions/runs{query}"
    )
    runs = _get(endpoint, token).get("workflow_runs", [])
    for run in runs:
        run_id = run.get("id")
        if not run_id:
            continue
        try:
            artifacts = _get(
                f"/repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100", token
            ).get("artifacts", [])
        except urllib.error.HTTPError:
            continue
        for artifact in artifacts:
            # Expired artifacts still appear in the listing but cannot be
            # downloaded, so skipping them avoids a confusing download failure.
            if artifact.get("name") == artifact_name and not artifact.get("expired"):
                return int(run_id)
    return None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--artifact-name", required=True)
    p.add_argument("--branch", default="")
    p.add_argument("--workflow", default="")
    p.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    args = p.parse_args(argv)

    token = os.environ.get("GITHUB_TOKEN", "")
    branch = args.branch or os.environ.get("GITHUB_DEFAULT_BRANCH", "main")

    if not token or not args.repo:
        sys.stderr.write("[find_baseline_run] no token or repo; skipping lookup\n")
        _emit(**{"run-id": "", "found": "false"})
        return 0

    try:
        run_id = find_baseline_run(
            repo=args.repo,
            token=token,
            artifact_name=args.artifact_name,
            branch=branch,
            workflow=args.workflow or None,
        )
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as exc:
        # A lookup failure must not fail the job; the gate falls back to FirstRun.
        sys.stderr.write(f"[find_baseline_run] lookup failed: {exc}\n")
        _emit(**{"run-id": "", "found": "false"})
        return 0

    if run_id is None:
        print(
            f"[find_baseline_run] no successful run on '{branch}' has a live "
            f"'{args.artifact_name}' artifact yet"
        )
        _emit(**{"run-id": "", "found": "false"})
        return 0

    print(f"[find_baseline_run] baseline artifact found in run {run_id} on '{branch}'")
    _emit(**{"run-id": str(run_id), "found": "true"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
