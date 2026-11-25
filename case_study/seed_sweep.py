"""Seed sensitivity of the attempt-policy experiment (case study, fourth observation).

Re-runs policy_experiment() for seeds 1..50 and reports the share of
student-skill pairs whose label differs between the latest-attempt policy and
(a) Berkeley's average-if-improved rule, (b) the best attempt.
Usage: python3 seed_sweep.py [--output FILE]
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import case_study as c  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output")
    args = p.parse_args()
    _, _, edges, _ = c.build_graph(HERE / "data/mapping.csv")
    seeds = range(1, 51)
    shares = {"latest_vs_average_if_improved": [], "latest_vs_best": []}
    for s in seeds:
        d = c.policy_experiment(edges, seed=s)["label_differs_share"]
        for k in shares:
            shares[k].append(d[k])
    summary = {k: {"min": min(v), "mean": round(statistics.mean(v), 4), "max": max(v),
                   "stdev": round(statistics.stdev(v), 4)} for k, v in shares.items()}
    out = {"seeds": [seeds.start, seeds.stop - 1], "summary": summary, "per_seed": shares}
    print(json.dumps(summary, indent=2))
    if args.output:
        (HERE / args.output).write_text(json.dumps(out, indent=2) + "\n")


if __name__ == "__main__":
    main()
