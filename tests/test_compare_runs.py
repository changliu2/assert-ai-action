import importlib.util
from itertools import count
from pathlib import Path
from types import SimpleNamespace


_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "compare_runs.py"
_SPEC = importlib.util.spec_from_file_location("compare_runs", _MODULE_PATH)
assert _SPEC is not None
compare_runs = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(compare_runs)


def test_holm_bonferroni_stops_after_first_miss() -> None:
    # The first ordered p-value misses alpha / 2, so true Holm step-down rejects
    # neither hypothesis. Checking each rank independently would wrongly reject
    # the second p-value against alpha / 1.
    assert compare_runs._holm_bonferroni_rejections([0.03, 0.04], 0.05) == [
        (0.025, False),
        (0.05, False),
    ]


def test_holm_bonferroni_continues_until_first_miss() -> None:
    assert compare_runs._holm_bonferroni_rejections([0.01, 0.03, 0.04], 0.05) == [
        (0.05 / 3, True),
        (0.05 / 2, False),
        (0.05, False),
    ]


def test_verdict_uses_holm_rejection_not_independent_threshold() -> None:
    # This is the customer-visible failure mode: a later dimension must stay
    # inconclusive if an earlier ordered p-value already stopped Holm step-down.
    entries = []
    for p_value, delta_pp in [(0.03, 1.0), (0.04, 2.0)]:
        entries.append({"p_value": p_value, "delta_pp": delta_pp, "n_pairs": 30})

    for entry, (threshold, rejected) in zip(
        entries,
        compare_runs._holm_bonferroni_rejections([e["p_value"] for e in entries], 0.05),
    ):
        entry["alpha_corrected"] = threshold
        entry["holm_rejected"] = rejected
        entry["verdict"] = compare_runs._verdict_for(
            delta_pp=entry["delta_pp"],
            rejected=rejected,
            n_pairs=entry["n_pairs"],
            min_pairs=30,
            allow_inconclusive=True,
        )

    assert [entry["holm_rejected"] for entry in entries] == [False, False]
    assert [entry["verdict"] for entry in entries] == ["Inconclusive", "Inconclusive"]
    assert compare_runs._overall_decision(entries) == "Inconclusive"


def test_compare_applies_holm_stepdown_to_dimension_verdicts(tmp_path, monkeypatch) -> None:
    baseline = tmp_path / "baseline"
    current = tmp_path / "current"
    baseline.mkdir()
    current.mkdir()
    (baseline / "scores.jsonl").write_text("{}\n", encoding="utf-8")
    (current / "scores.jsonl").write_text("{}\n", encoding="utf-8")

    score_rows = {
        "baseline": {
            f"case-{i}": {"dim_a": False, "dim_b": False}
            for i in range(30)
        },
        "current": {
            f"case-{i}": {"dim_a": True, "dim_b": True}
            for i in range(30)
        },
    }

    monkeypatch.setattr(compare_runs, "_find_scores_jsonl", lambda root: root / "scores.jsonl")
    monkeypatch.setattr(
        compare_runs,
        "_load_scores",
        lambda path: score_rows[path.parent.name],
    )
    calls = count(1)

    def fake_ttest(cur_vec, base_vec):
        call_number = next(calls)
        return SimpleNamespace(statistic=1.0, pvalue=0.03 if call_number == 1 else 0.04)

    monkeypatch.setattr(compare_runs.stats, "ttest_rel", fake_ttest)

    report = compare_runs.compare(baseline, current)

    assert [
        (d["name"], d["p_value"], d["alpha_corrected"], d["holm_rejected"], d["verdict"])
        for d in report["dimensions"]
    ] == [
        ("dim_a", 0.03, 0.025, False, "Inconclusive"),
        ("dim_b", 0.04, 0.05, False, "Inconclusive"),
    ]
    assert report["decision"] == "Inconclusive"
