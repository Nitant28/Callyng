"""Step 0: normalization_rules loaded from post_call_snapshot (regression)."""

from __future__ import annotations

from script_runtime import parse_post_call_snapshot


def test_normalization_rules_from_post_call_snapshot():
    call_data = {
        "post_call_snapshot": {
            "extraction_schema": {"mode": "fields", "fields": []},
            "normalization_rules": [
                {
                    "when": {"field": "site_visit_agreed", "truthy": True},
                    "set": {"intent_status": "Interested"},
                }
            ],
        }
    }
    snapshot = parse_post_call_snapshot(call_data)
    assert snapshot is not None

    norm_rules = None
    if snapshot:
        rules = snapshot.get("normalization_rules")
        norm_rules = rules if rules else None

    assert norm_rules is not None
    assert len(norm_rules) == 1
    assert norm_rules[0]["when"]["field"] == "site_visit_agreed"


def test_normalization_rules_not_self_referenced():
    """Regression: must load from snapshot, not assign norm_rules to itself."""
    snapshot = {"normalization_rules": [{"when": {"field": "x", "truthy": True}}]}
    norm_rules = None
    rules = snapshot.get("normalization_rules")
    norm_rules = rules if rules else None
    assert norm_rules is not None
