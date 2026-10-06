#!/usr/bin/env python3
"""Compares results/*.json (runner.py output) against each script's
`expected` field. runner.py itself only checks schema shape, not
correctness - this does the correctness check."""
import json
import pathlib
import sys

def load_scripts(directory):
    out = {}
    for path in pathlib.Path(directory).glob("*.json"):
        d = json.load(open(path, encoding="utf-8"))
        out[d["id"]] = d
    return out

def grade(script_dir, results_dir):
    scripts = load_scripts(script_dir)
    failures = []
    passes = []
    missing = []
    for sid, script in sorted(scripts.items()):
        result_files = sorted(pathlib.Path(results_dir).glob(f"{sid}.run*.json"))
        if not result_files:
            missing.append(sid)
            continue
        result = json.load(open(result_files[-1], encoding="utf-8"))
        expected = script.get("expected", {})
        problems = []

        exp_state = expected.get("terminal_state")
        if exp_state and result.get("terminal_state") != exp_state:
            problems.append(f"terminal_state: got {result.get('terminal_state')!r}, expected {exp_state!r}")

        exp_reason = expected.get("escalation_reason")
        if "escalation_reason" in expected and result.get("escalation_reason") != exp_reason:
            problems.append(f"escalation_reason: got {result.get('escalation_reason')!r}, expected {exp_reason!r}")

        called = {c["name"] for c in result.get("tool_calls", [])}
        for must in expected.get("must_call", []):
            if must not in called:
                problems.append(f"must_call missing: {must!r} (called: {sorted(called)})")
        for must_not in expected.get("must_not_call", []):
            if must_not in called:
                problems.append(f"must_not_call violated: {must_not!r} was called")

        if problems:
            failures.append((sid, script["description"], problems))
        else:
            passes.append(sid)

    return passes, failures, missing

def main():
    total_pass, total_fail = 0, 0
    for label, script_dir, results_dir in [
        ("conversations", "conversations", "results/conversations"),
        ("adversarial", "adversarial", "results/adversarial"),
    ]:
        print(f"\n=== {label} ===")
        passes, failures, missing = grade(script_dir, results_dir)
        total_pass += len(passes)
        total_fail += len(failures)
        print(f"PASS: {len(passes)}  FAIL: {len(failures)}  MISSING: {len(missing)}")
        if missing:
            print("  missing results for:", missing)
        for sid, desc, problems in failures:
            print(f"\n  FAIL {sid} - {desc}")
            for p in problems:
                print(f"    - {p}")

    print(f"\n=== TOTAL: {total_pass} passed, {total_fail} failed ===")
    return 1 if total_fail else 0

if __name__ == "__main__":
    sys.exit(main())
