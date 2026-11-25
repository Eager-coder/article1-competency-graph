"""Case study on public course specifications and real vacancies.

Loads two public course specifications (University of Sydney COMP5347,
UC Berkeley INFO 253B) and three hh.kz vacancies into the typed graph of
Article 1. Each course is analysed on its own; the two cases share only the
skill vocabulary and the vacancies. Student evidence is synthetic and is used
only to compare attempt policies.

Python 3.10+, standard library only. Imports the model from
../verification/verify_models.py.

Run: python case_study.py [--mapping data/mapping.csv]
                          [--second OTHER_MAPPING.csv]  # optional: Cohen's kappa
                          [--output results.json]
"""
from __future__ import annotations
import argparse
import csv
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "verification"))
from verify_models import Evidence, canonical, profile, alignment, validate_edge  # noqa: E402

COURSES = ("SYD", "BRK")
ROLES = ("V1", "V2", "V3")
MAPPED_TYPES = {"LearningOutcome": "addresses", "Assessment": "assesses", "Requirement": "requires"}


def read_csv(name):
    with open(HERE / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_mapping(path):
    mapping = {}
    for row in read_csv(path):
        mapping[row["item_id"]] = sorted(s.strip() for s in row["skills"].split(";") if s.strip())
    return mapping


def build_graph(mapping_file):
    entities = {e["entity_id"]: e for e in read_csv("data/entities.csv")}
    skills = {s["skill_id"] for s in read_csv("data/skills.csv")}
    types = {k: e["type"] for k, e in entities.items()} | {s: "Skill" for s in skills}
    edges = []
    for e in read_csv("data/official_edges.csv"):
        validate_edge(types[e["source"]], e["relation"], types[e["target"]], f'{e["source_id"]}: {e["locator"]}')
        edges.append((e["source"], e["relation"], e["target"]))
    mapping = load_mapping(mapping_file)
    items = [k for k, e in entities.items() if e["type"] in MAPPED_TYPES]
    missing = sorted(set(items) - set(mapping))
    if missing:
        raise ValueError(f"mapping lacks items: {missing}")
    for item in items:
        for skill in mapping[item]:
            if skill not in skills:
                raise ValueError(f"unknown skill {skill} for {item}")
            relation = MAPPED_TYPES[types[item]]
            validate_edge(types[item], relation, "Skill", f"mapping: {Path(mapping_file).name}")
            edges.append((item, relation, skill))
    return entities, skills, edges, mapping


def out(edges, node, relation):
    return {v for u, r, v in edges if u == node and r == relation}


def flags(entity):
    return {f.split("=")[0] for f in entity["flags"].split(";") if f}


def course_coverage(edges, course):
    outcomes = out(edges, course, "targets")
    assessments = out(edges, course, "contains")
    covered = {lo for a in assessments for lo in out(edges, a, "covers")}
    targeted = {s for lo in outcomes for s in out(edges, lo, "addresses")}
    assessed = {s for a in assessments for s in out(edges, a, "assesses")}
    via_outcomes = {s for a in assessments for lo in out(edges, a, "covers") for s in out(edges, lo, "addresses")}
    return {
        "outcomes": len(outcomes),
        "assessments": len(assessments),
        "official_outcome_coverage_available": any(out(edges, a, "covers") for a in assessments),
        "outcomes_without_covering_assessment": sorted(outcomes - covered) if covered else None,
        "outcomes_without_skill": sorted(lo for lo in outcomes if not out(edges, lo, "addresses")),
        "assessments_without_skill": sorted(a for a in assessments if not out(edges, a, "assesses")),
        "targeted_skills": sorted(targeted),
        "directly_assessed_skills": sorted(assessed),
        "skills_reached_only_through_covered_outcomes": sorted(via_outcomes - assessed),
        "targeted_not_directly_assessed": sorted(targeted - assessed),
        "assessed_not_targeted": sorted(assessed - targeted),
    }


def role_vs_course(entities, edges, role, coverage):
    assessed, targeted = set(coverage["directly_assessed_skills"]), set(coverage["targeted_skills"])
    rows = []
    for req in sorted(out(edges, role, "has_requirement")):
        needed = out(edges, req, "requires")
        f = flags(entities[req])
        if not needed:
            status = "outside vocabulary"
        else:
            test = any if "alternatives" in f else all
            if test(s in assessed for s in needed):
                status = "assessed"
            elif test(s in assessed | targeted for s in needed):
                status = "targeted only"
            else:
                status = "not covered"
        rows.append({"requirement": req, "skills": sorted(needed), "flags": sorted(f), "status": status})
    counts = defaultdict(int)
    for r in rows:
        counts[r["status"]] += 1
    return {"requirements": rows, "counts": dict(sorted(counts.items()))}


def representational_findings(entities, coverage_by_course):
    def with_flag(flag):
        return sorted(k for k, e in entities.items() if flag in flags(e))
    return {
        "requirements_with_alternatives": with_flag("alternatives"),
        "optional_requirements": with_flag("optional"),
        "non_technical_requirements": with_flag("non_technical"),
        "pass_fail_assessments": with_flag("pass_fail"),
        "course_level_drop_lowest_rules": with_flag("drop_lowest_lab"),
        "assessments_with_resubmission": with_flag("resubmission"),
        "hurdle_assessments": with_flag("hurdle"),
        "courses_with_official_assessment_outcome_map": [c for c, v in coverage_by_course.items()
                                                         if v["official_outcome_coverage_available"]],
    }


# --- attempt policies on synthetic evidence ---------------------------------

def visible_valid(records, student, skill, t, tau):
    """Visibility exactly as in profile(): latest revision before revocation filtering."""
    versions = {}
    for e in canonical(records):
        if e.student != student or e.skill != skill or e.occurred > t or e.recorded > tau:
            continue
        if e.evidence_id not in versions or e.revision > versions[e.evidence_id].revision:
            versions[e.evidence_id] = e
    return [e for e in versions.values() if e.status == "valid"]


def policy_estimate(records, student, skill, t, tau, policy):
    by_assessment = defaultdict(list)
    for e in visible_valid(records, student, skill, t, tau):
        by_assessment[e.assessment].append(e)
    values = []
    for attempts in by_assessment.values():
        attempts.sort(key=lambda e: (e.occurred, e.attempt, e.evidence_id))
        first, latest = attempts[0], attempts[-1]
        if policy == "latest":
            score = latest.score
        elif policy == "best":
            score = max(e.score for e in attempts)
        elif policy == "average_if_improved":  # Berkeley INFO 253B, Spring 2025 syllabus
            score = max(first.score, (first.score + latest.score) / 2) if len(attempts) > 1 else first.score
        else:
            raise ValueError(policy)
        values.append((latest.weight, score))
    if not values:
        return None
    support = math.fsum(w for w, _ in values)
    return math.fsum(w * z for w, z in values) / support


def synthetic_ledger(rng, students, assessed):
    """First submission for A1 and A2; with probability 0.5 a resubmission one
    week later whose score moves by N(0.06, 0.12). The rubric item scores are not
    public, so every skill an assignment assesses receives the assignment score."""
    records, day = [], {"BRK.A1": 40, "BRK.A2": 75}
    for i in range(students):
        u = f"u{i:04d}"
        for a in ("BRK.A1", "BRK.A2"):
            z1 = rng.betavariate(5, 2.5)
            scores = [z1]
            if rng.random() < 0.5:
                scores.append(min(1.0, max(0.0, z1 + rng.gauss(0.06, 0.12))))
            for attempt, z in enumerate(scores, start=1):
                t = day[a] + 7 * (attempt - 1)
                for s in sorted(assessed[a]):
                    records.append(Evidence(f"{u}-{a}-{s}-{attempt}", 1, u, s, a, attempt, t, t + 2, round(z, 4)))
    return records


def policy_experiment(edges, seed=7, students=1000, level=0.70):
    rng = random.Random(seed)
    assessed = {a: out(edges, a, "assesses") for a in ("BRK.A1", "BRK.A2")}
    records = synthetic_ledger(rng, students, assessed)
    skills = sorted(assessed["BRK.A1"] | assessed["BRK.A2"])
    t = tau = 10**6
    labels = defaultdict(lambda: defaultdict(int))
    differ = defaultdict(int)
    total = 0
    index = defaultdict(list)  # (student, skill) -> records; avoids rescanning the ledger per query
    for e in records:
        index[(e.student, e.skill)].append(e)
    for i in range(students):
        u = f"u{i:04d}"
        for s in skills:
            subset = index[(u, s)]
            est = {p: policy_estimate(subset, u, s, t, tau, p) for p in ("latest", "average_if_improved", "best")}
            reference = profile(subset, u, s, t, tau)["estimate"]
            assert reference is not None and abs(reference - est["latest"]) < 1e-12, "latest must equal profile()"
            support = profile(subset, u, s, t, tau)["support"]
            lab = {p: alignment({"estimate": v, "support": support, "dispersion": 0.0}, level) for p, v in est.items()}
            total += 1
            for p, l in lab.items():
                labels[p][l] += 1
            differ["latest_vs_average_if_improved"] += lab["latest"] != lab["average_if_improved"]
            differ["latest_vs_best"] += lab["latest"] != lab["best"]
    return {
        "seed": seed, "students": students, "skills": skills, "level": level, "student_skill_pairs": total,
        "records": len(records),
        "labels": {p: dict(v) for p, v in labels.items()},
        "label_differs": dict(differ),
        "label_differs_share": {k: round(v / total, 4) for k, v in differ.items()},
        "note": "Synthetic scores; dispersion ignored (set to 0) to isolate the attempt rule.",
    }


# --- agreement -----------------------------------------------------------------

def agreement(map_a, map_b, items, skills):
    a = b = both = 0
    n = len(items) * len(skills)
    disagreements = []
    exact = 0
    for item in items:
        sa, sb = set(map_a[item]), set(map_b[item])
        exact += sa == sb
        for s in skills:
            a += s in sa
            b += s in sb
            both += s in sa and s in sb
        if sa != sb:
            disagreements.append({"item": item, "only_first": sorted(sa - sb), "only_second": sorted(sb - sa)})
    observed = (n - a - b + 2 * both) / n
    expected = (a * b + (n - a) * (n - b)) / n**2
    kappa = (observed - expected) / (1 - expected) if expected < 1 else 1.0
    pa = 2 * both / (a + b) if a + b else 1.0
    return {"cells": n, "items": len(items), "positive_first": a, "positive_second": b, "positive_both": both,
            "cohen_kappa": round(kappa, 3), "positive_agreement": round(pa, 3),
            "items_identical": exact, "disagreements": disagreements}


def run(mapping, second):
    entities, skills, edges, map_a = build_graph(HERE / mapping)
    coverage = {c: course_coverage(edges, c) for c in COURSES}
    comparison = {c: {r: role_vs_course(entities, edges, r, coverage[c]) for r in ROLES} for c in COURSES}
    result = {
        "mapping": mapping,
        "graph": {"entities": len(entities), "skills": len(skills), "edges": len(edges),
                  "edges_by_relation": dict(sorted(defaultdict(int, {}).items()))},
        "coverage": coverage,
        "vacancy_comparison": comparison,
        "representational_findings": representational_findings(entities, coverage),
        "policy_experiment": policy_experiment(edges),
    }
    counts = defaultdict(int)
    for _, r, _ in edges:
        counts[r] += 1
    result["graph"]["edges_by_relation"] = dict(sorted(counts.items()))
    if second and (HERE / second).exists():
        map_b = load_mapping(HERE / second)
        items = [k for k, e in entities.items() if e["type"] in MAPPED_TYPES]
        result["agreement"] = {"second": second, **agreement(map_a, map_b, items, sorted(skills))}
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mapping", default="data/mapping.csv")
    p.add_argument("--second", default=None)
    p.add_argument("--output", default="results.json")
    args = p.parse_args()
    result = run(args.mapping, args.second)
    (HERE / args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("graph", "representational_findings")}, indent=1))
    for c in COURSES:
        print(c, {k: v for k, v in result["coverage"][c].items()})
        print(c, {r: result["vacancy_comparison"][c][r]["counts"] for r in ROLES})
    pe = result["policy_experiment"]
    print("policy", pe["label_differs_share"], pe["labels"])
    if "agreement" in result:
        print("agreement", {k: v for k, v in result["agreement"].items() if k != "disagreements"})


if __name__ == "__main__":
    main()
