"""Baseline profiles on the Table II ledger of Article 1.

Compares the specified profile with two simpler record-keeping designs:
  gradebook  - one current value per observation: corrections and revocations
               overwrite earlier values, so only the assessment-time cutoff t
               can be applied (equivalent to tau = infinity).
  event_log  - every stored row known by tau with occurrence <= t and status
               valid counts as one weighted contribution: no revision
               resolution, no attempt selection.
Usage: python3 baselines.py [--output FILE]
"""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_models import Evidence, profile, replace


def ledger():
    a = Evidence("a1", 1, "u", "python", "A", 1, 1, 1, 0.8)
    b = Evidence("b1", 1, "u", "python", "B", 1, 2, 2, 0.4, 0.5)
    a2 = Evidence("a2", 1, "u", "python", "A", 2, 3, 3, 0.6)
    return [a, b, a2, replace(a2, revision=2, recorded=5, score=0.9),
            replace(b, revision=2, recorded=6, status="revoked")]


def gradebook(records, t):
    return profile(records, "u", "python", t, math.inf)


def event_log(records, t, tau):
    rows = [e for e in records if e.occurred <= t and e.recorded <= tau and e.status == "valid"]
    if not rows:
        return {"estimate": None, "support": 0.0}
    w = math.fsum(e.weight for e in rows)
    return {"estimate": math.fsum(e.weight * e.score for e in rows) / w, "support": w}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output")
    args = ap.parse_args()
    records = ledger()
    rows = []
    for t, tau in [(2, 2), (3, 4), (3, 5), (3, 6)]:
        spec = profile(records, "u", "python", t, tau)
        gb = gradebook(records, t)
        log = event_log(records, t, tau)
        rows.append({"t": t, "tau": tau,
                     "specified": [round(spec["estimate"], 3), spec["support"]],
                     "gradebook": [round(gb["estimate"], 3), gb["support"]],
                     "event_log": [round(log["estimate"], 3), log["support"]]})
    # Expected values, derived by hand from Table II.
    expected = {"specified": [0.667, 0.533, 0.733, 0.9],
                "gradebook": [0.8, 0.9, 0.9, 0.9],
                "event_log": [0.667, 0.64, 0.714, 0.714]}
    for name, values in expected.items():
        assert [r[name][0] for r in rows] == values, (name, [r[name][0] for r in rows])
    out = {"ledger": "Table II", "queries": rows}
    text = json.dumps(out, indent=2)
    print(text)
    if args.output:
        open(args.output, "w").write(text + "\n")


if __name__ == "__main__":
    main()
