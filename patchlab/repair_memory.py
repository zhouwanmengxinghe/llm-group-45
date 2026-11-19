"""Small factual failure ledger pinned separately from compressed file evidence."""
from __future__ import annotations

from hashlib import sha256
import copy
import json


def fingerprint(value) -> str:
    return sha256(json.dumps(value, ensure_ascii=True, sort_keys=True).encode()).hexdigest()


class RepairMemory:
    def __init__(self):
        self.entries: list[dict] = []

    def reject(self, action: dict, feedback: dict):
        edits = action.get("edits", [])
        if not isinstance(edits, list):
            edits = []
        entry = {
            "attempt": feedback.get("attempt"), "stage": feedback.get("stage", "patch_application"),
            "hypothesis": str(action.get("diagnosis", action.get("rationale", "")))[:500],
            "failure": str(feedback.get("failure", ""))[:700],
            "evidence": str(feedback.get("evidence", ""))[-900:],
            "issue_contract_passed": feedback.get("issue_contract_passed", False),
            "action_fingerprint": fingerprint(edits if edits else action),
            "test": str(action.get("code", ""))[-700:],
            "edits": [{"path": e.get("path"), "before": str(e.get("before", ""))[:200],
                       "after": str(e.get("after", ""))[:240]}
                      for e in edits if isinstance(e, dict)][:8],
        }
        self.entries.append(entry)

    def view(self, max_chars=8000):
        records = copy.deepcopy(self.entries[-5:])
        for record in records:
            record["action_fingerprint"] = record["action_fingerprint"][:12]
        for index, entry in enumerate(records[:-1]):
            if len(json.dumps(records)) <= max_chars:
                break
            records[index] = {
                "attempt": entry["attempt"], "stage": entry["stage"],
                "hypothesis": entry["hypothesis"][:180], "failure": entry["failure"][:260],
                "issue_contract_passed": entry["issue_contract_passed"],
                "changed_paths": [e["path"] for e in entry["edits"]],
                "action_fingerprint": entry["action_fingerprint"],
            }
        if records and len(json.dumps(records)) > max_chars:
            records[-1]["hypothesis"] = records[-1]["hypothesis"][:250]
            records[-1]["failure"] = records[-1]["failure"][:350]
            records[-1]["evidence"] = records[-1]["evidence"][-450:]
        return records
