# Release procedure

Use semantic release tags such as `v1.0.0` and keep the floating major tag (`v1`) on the same commit as the latest compatible `v1.x.y` release.

## Cut a release

```powershell
git fetch live --tags
git checkout main
git pull --ff-only live main
python scripts/check_bundle.py
python scripts/check_onboard_urls.py
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest tests/ -q

git tag v1.0.1
git push live v1.0.1
```

The release workflow moves the matching major tag to the new release commit. Verify it:

```powershell
git fetch live --tags --force
git rev-parse v1
git rev-parse v1.0.1
```

The two hashes must match. Then create the GitHub Release from the exact tag with customer-facing release notes.

## Do not

- Do not move an exact release tag such as `v1.0.0` after publishing it.
- Do not publish a release before the action helper tests pass.
- Do not include private prompts, provider outputs, secrets, or `.env` values in release notes.