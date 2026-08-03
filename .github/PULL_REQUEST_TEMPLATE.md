## Summary

## Validation

- [ ] `$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"; python -m pytest tests/ -q`
- [ ] `python scripts/check_bundle.py`
- [ ] `python scripts/check_onboard_urls.py`

## Safety and release checklist

- [ ] No secrets, `.env` files, raw model I/O, generated artifacts, or logs are committed.
- [ ] Workflow snippets use resolvable actions pinned to a major or exact tag.
- [ ] Documentation changed if inputs, outputs, verdicts, or onboarding changed.