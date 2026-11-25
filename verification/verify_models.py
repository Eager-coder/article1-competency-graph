"""Synthetic verification of the models described in the accompanying manuscript.

Python 3.10+, standard library only. No student or vacancy data are used.
Run: python verify_models.py --output verification_results.json
"""
from __future__ import annotations
from dataclasses import dataclass, replace, asdict
from collections import defaultdict
from typing import Optional
import argparse
import json
import math
import random


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    revision: int
    student: str
    skill: str
    assessment: str
    attempt: int
    occurred: int
    recorded: int
    score: float
    weight: float = 1.0
    status: str = "valid"
    rubric: str = "rubric-v1"


@dataclass(frozen=True)
class RequirementVersion:
    """One version of a role requirement: in force from valid_from (event time)
    until valid_to (exclusive, optional), known from recorded (recording time)."""
    requirement: str
    version: int
    skill: str
    level: float
    valid_from: int
    recorded: int
    valid_to: Optional[int] = None
    source: str = "synthetic-spec-v1"


@dataclass(frozen=True)
class RubricVersion:
    """A rubric version declared for an assessment and its validity interval."""
    assessment: str
    rubric: str
    valid_from: int
    valid_to: Optional[int] = None


def canonical(records):
    """An evidence ID denotes one student/skill/assessment/attempt observation."""
    unique = {}
    by_id = defaultdict(list)
    for e in records:
        if not 0 <= e.score <= 1 or not 0 < e.weight <= 1:
            raise ValueError("score must be in [0,1] and weight in (0,1]")
        if e.status not in {"valid", "revoked"} or e.revision < 1:
            raise ValueError("invalid status or revision")
        if e.recorded < e.occurred or e.attempt < 1 or not e.rubric:
            raise ValueError("invalid timestamps, attempt or rubric")
        key = (e.evidence_id, e.revision)
        if key in unique and unique[key] != e:
            raise ValueError("conflicting duplicate revision")
        unique[key] = e
    for e in unique.values():
        by_id[e.evidence_id].append(e)
    for group in by_id.values():
        ordered = sorted(group, key=lambda x: x.revision)
        identities = {(e.student, e.skill, e.assessment, e.attempt, e.occurred, e.rubric) for e in group}
        if len(identities) != 1:
            raise ValueError("a revision cannot change observation identity")
        if any(a.recorded >= b.recorded for a, b in zip(ordered, ordered[1:])):
            raise ValueError("revision recording times must increase strictly")
    # One observation per (student, skill, assessment, attempt); attempt numbers
    # must not contradict occurrence order.
    attempts = defaultdict(dict)
    for group in by_id.values():
        e = group[0]
        slot = attempts[(e.student, e.skill, e.assessment)]
        if e.attempt in slot and slot[e.attempt].evidence_id != e.evidence_id:
            raise ValueError("two observations for the same attempt")
        slot[e.attempt] = e
    for slot in attempts.values():
        ordered = [slot[k] for k in sorted(slot)]
        if any(a.occurred > b.occurred for a, b in zip(ordered, ordered[1:])):
            raise ValueError("attempt numbers contradict occurrence order")
    return list(unique.values())


def profile(records, student, skill, t, tau):
    """State at event time t using only records known by recording cutoff tau.

    The latest visible revision is chosen BEFORE revocation filtering. A revoked
    latest attempt is excluded; a previous valid attempt can then contribute.
    Only the most recent valid attempt per assessment and skill contributes.
    """
    versions = {}
    for e in canonical(records):
        if e.student != student or e.skill != skill or e.occurred > t or e.recorded > tau:
            continue
        if e.evidence_id not in versions or e.revision > versions[e.evidence_id].revision:
            versions[e.evidence_id] = e
    selected = {}
    for e in versions.values():
        if e.status != "valid":
            continue
        key = e.assessment
        rank = (e.occurred, e.attempt, e.evidence_id)
        if key not in selected or rank > (selected[key].occurred, selected[key].attempt, selected[key].evidence_id):
            selected[key] = e
    observations = sorted(selected.values(), key=lambda e: e.evidence_id)
    if not observations:
        return {"estimate": None, "support": 0.0, "dispersion": None, "evidence": [], "latest_event": None}
    support = math.fsum(e.weight for e in observations)
    estimate = math.fsum(e.weight * e.score for e in observations) / support
    dispersion = math.sqrt(math.fsum(e.weight * (e.score-estimate)**2 for e in observations) / support)
    return {"estimate": estimate, "support": support, "dispersion": dispersion,
            "evidence": [[e.evidence_id, e.revision] for e in observations],
            "latest_event": max(e.occurred for e in observations)}


def alignment(state, required, disagreement=0.35, min_support=1.0):
    """Illustrative policy; thresholds have not been empirically calibrated.
    Dispersion is informative only with two or more contributions (it is 0 for one)."""
    if state["estimate"] is None:
        return "unassessed"
    if state["support"] < min_support:
        return "insufficient evidence"
    if state["dispersion"] > disagreement:
        return "review"
    return "meets configured threshold" if state["estimate"] >= required else "below configured threshold"


ALLOWED = {("Course", "targets", "LearningOutcome"),
           ("LearningOutcome", "addresses", "Skill"),
           ("Assessment", "assesses", "Skill"),
           ("Course", "contains", "Assessment"),
           ("Assessment", "covers", "LearningOutcome"),
           ("Role", "has_requirement", "Requirement"),
           ("Requirement", "requires", "Skill"),
           ("Evidence", "observed_for", "Student"),
           ("Evidence", "generated_by", "Assessment"),
           ("Evidence", "concerns", "Skill")}


def check_requirements(versions):
    """Versions of one requirement keep their skill, have distinct numbers, and are
    recorded in version order; levels lie in [0, 1]."""
    by_requirement = defaultdict(list)
    for v in versions:
        if not 0 <= v.level <= 1 or not v.source or v.version < 1:
            raise ValueError("invalid requirement version")
        if v.valid_to is not None and v.valid_to <= v.valid_from:
            raise ValueError("empty validity interval")
        by_requirement[v.requirement].append(v)
    for group in by_requirement.values():
        ordered = sorted(group, key=lambda v: v.version)
        if len({v.skill for v in group}) != 1 or len({v.version for v in group}) != len(group):
            raise ValueError("a requirement version cannot change its skill or repeat a number")
        if any(a.recorded >= b.recorded for a, b in zip(ordered, ordered[1:])):
            raise ValueError("requirement versions must be recorded in version order")
    return True


def requirement_at(versions, requirement, t, tau):
    """The latest version recorded by tau whose validity has started by t;
    None if no such version exists or the selected version has expired at t."""
    check_requirements(versions)
    known = [v for v in versions if v.requirement == requirement and v.recorded <= tau and v.valid_from <= t]
    if not known:
        return None
    chosen = max(known, key=lambda v: v.version)
    if chosen.valid_to is not None and t >= chosen.valid_to:
        return None
    return chosen


def check_rubrics(records, rubrics):
    """Each record must name a rubric version declared for its assessment and in force when it occurred."""
    for e in records:
        if not any(r.assessment == e.assessment and r.rubric == e.rubric and r.valid_from <= e.occurred
                   and (r.valid_to is None or e.occurred < r.valid_to) for r in rubrics):
            raise ValueError(f"rubric {e.rubric} is not in force for {e.assessment} at {e.occurred}")
    return True


def validate_edge(source_type, relation, target_type, source_reference):
    if (source_type, relation, target_type) not in ALLOWED or not source_reference:
        raise ValueError("invalid edge signature or absent provenance")
    return True


def graph_example():
    nodes = {"C1": "Course", "C2": "Course", "L1": "LearningOutcome", "L2": "LearningOutcome",
             "L3": "LearningOutcome", "python": "Skill", "sql": "Skill", "docker": "Skill",
             "A": "Assessment", "B": "Assessment", "D": "Assessment", "R": "Role",
             "RP": "Requirement", "RD": "Requirement"}
    edges = [("C1", "targets", "L1"), ("C1", "targets", "L2"), ("C2", "targets", "L3"),
             ("L1", "addresses", "python"), ("L2", "addresses", "docker"), ("L3", "addresses", "sql"),
             ("C1", "contains", "A"), ("C1", "contains", "B"), ("C2", "contains", "D"),
             ("A", "assesses", "python"), ("B", "assesses", "python"), ("D", "assesses", "sql"),
             ("R", "has_requirement", "RP"), ("R", "has_requirement", "RD"),
             ("RP", "requires", "python"), ("RD", "requires", "docker")]
    for u, relation, v in edges:
        validate_edge(nodes[u], relation, nodes[v], "synthetic-spec-v1")
    def adjacent(node, relation):
        return {v for u, r, v in edges if u == node and r == relation}
    targeted = {s for lo in adjacent("C1", "targets") for s in adjacent(lo, "addresses")}
    assessed = {s for assessment in adjacent("C1", "contains") for s in adjacent(assessment, "assesses")}
    required = {s for requirement in adjacent("R", "has_requirement") for s in adjacent(requirement, "requires")}
    assert targeted == {"python", "docker"} and assessed == {"python"}
    assert required == {"python", "docker"}
    assert targeted - assessed == {"docker"}
    return {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges),
            "C1_targeted_skills": sorted(targeted), "C1_assessed_skills": sorted(assessed),
            "R_required_skills": sorted(required), "C1_missing_assessment_coverage": sorted(targeted-assessed)}


def check_mapping(records, edges):
    """Evidence about skill s from assessment A is admissible only if A assesses s in the graph."""
    assessed = {(u, v) for u, r, v in edges if r == "assesses"}
    for e in records:
        if (e.assessment, e.skill) not in assessed:
            raise ValueError(f"assessment {e.assessment} is not mapped to skill {e.skill}")
    return True


def role_trace(edges, records, student, role, requirements, rubrics, t, tau):
    """Role -> requirement version in force -> skill -> assessments -> selected evidence -> label."""
    check_mapping(records, edges)
    check_rubrics(records, rubrics)
    def adjacent(node, relation):
        return sorted(v for u, r, v in edges if u == node and r == relation)
    trace = []
    for requirement in adjacent(role, "has_requirement"):
        version = requirement_at(requirements, requirement, t, tau)
        for skill in adjacent(requirement, "requires"):
            if version is None:
                trace.append({"requirement": requirement, "version": None, "level": None, "skill": skill,
                              "assessments": [], "evidence": [], "estimate": None, "label": "not in force"})
                continue
            if version.skill != skill:
                raise ValueError("requirement version and graph disagree on the skill")
            assessments = sorted(u for u, r, v in edges if r == "assesses" and v == skill)
            state = profile(records, student, skill, t, tau)
            label = alignment(state, version.level) if assessments else "unassessed: no assessment mapping"
            trace.append({"requirement": requirement, "version": version.version, "level": version.level,
                          "skill": skill, "assessments": assessments, "evidence": state["evidence"],
                          "estimate": state["estimate"], "label": label})
    return trace


STUDENTS, SKILLS = ("u", "v"), ("s", "k")


def random_ledger(rng):
    """Observations for two students and two skills, with 0-3 later revisions
    (corrections or revocations) and late recording."""
    records = []
    n = rng.randint(1, 20)
    times = sorted(rng.randint(0, 20) for _ in range(n))  # later attempts never occur earlier
    for i in range(n):
        occurred = times[i]
        recorded = occurred + rng.randint(0, 5)
        e = Evidence(f"r{i:02}", 1, rng.choice(STUDENTS), rng.choice(SKILLS), f"A{i % 4}", i // 4 + 1,
                     occurred, recorded, rng.random(), rng.uniform(0.05, 1.0))
        records.append(e)
        for revision in range(2, rng.randint(1, 4) + 1):
            recorded += rng.randint(1, 6)
            e = replace(e, revision=revision, recorded=recorded, score=rng.random(),
                        weight=rng.uniform(0.05, 1.0), status=rng.choice(["valid", "valid", "revoked"]))
            records.append(e)
    return records


def expected_selection(records, student, skill, t, tau):
    """The selection rules written directly from the specification, for the property checks."""
    latest = {}
    for e in set(records):
        if e.student == student and e.skill == skill and e.occurred <= t and e.recorded <= tau:
            if e.evidence_id not in latest or e.revision > latest[e.evidence_id].revision:
                latest[e.evidence_id] = e
    best = {}
    for e in latest.values():
        if e.status == "valid":
            rank = (e.occurred, e.attempt, e.evidence_id)
            if e.assessment not in best or rank > best[e.assessment][0]:
                best[e.assessment] = (rank, e)
    return latest, [e for _, e in best.values()]


def property_checks(rng, iterations):
    """P1-P4, exact selection and aggregates on random ledgers with two students,
    two skills, revisions, revocations and separate cutoffs t and tau."""
    counts = {"iterations": iterations, "revisions": 0, "revocations": 0, "late_initial_records": 0,
              "queries_with_t_ne_tau": 0, "nonempty_states": 0, "fallback_after_revoked_attempt": 0,
              "future_revisions_injected": 0}
    for _ in range(iterations):
        records = random_ledger(rng)
        student, skill = rng.choice(STUDENTS), rng.choice(SKILLS)
        t, tau = rng.randint(0, 25), rng.randint(0, 35)
        counts["revisions"] += sum(e.revision > 1 for e in records)
        counts["revocations"] += sum(e.status == "revoked" for e in records)
        counts["late_initial_records"] += sum(e.revision == 1 and e.recorded > e.occurred for e in records)
        counts["queries_with_t_ne_tau"] += t != tau
        state = profile(records, student, skill, t, tau)

        # P4 replay invariance: order and identical duplicate delivery do not matter.
        shuffled = records[:]
        rng.shuffle(shuffled)
        assert profile(shuffled + [rng.choice(records)], student, skill, t, tau) == state

        # P1 boundedness and P2 preserved missingness.
        if state["estimate"] is None:
            assert state["support"] == 0 and state["evidence"] == []
        else:
            counts["nonempty_states"] += 1
            assert -1e-12 <= state["estimate"] <= 1 + 1e-12
            assert state["support"] > 0 and state["dispersion"] >= 0

        # Selection: exactly the evidence the rules prescribe (soundness and completeness).
        latest, expected = expected_selection(records, student, skill, t, tau)
        assert sorted(map(tuple, state["evidence"])) == sorted((e.evidence_id, e.revision) for e in expected)
        revoked_assessments = {e.assessment for e in latest.values() if e.status == "revoked"}
        counts["fallback_after_revoked_attempt"] += any(e.assessment in revoked_assessments for e in expected)

        # Aggregates: m, W and D recomputed from the prescribed selection.
        if expected:
            W = sum(e.weight for e in expected)
            m = sum(e.weight * e.score for e in expected) / W
            D = math.sqrt(sum(e.weight * (e.score - m) ** 2 for e in expected) / W)
            assert abs(state["support"] - W) < 1e-12 and abs(state["estimate"] - m) < 1e-12
            assert abs(state["dispersion"] - D) < 1e-12
            assert state["latest_event"] == max(e.occurred for e in expected)

        # P3 cutoff consistency: revisions recorded after tau cannot change the state at tau.
        future = []
        for e in latest.values():
            later = max(r.recorded for r in records if r.evidence_id == e.evidence_id)
            top = max(r.revision for r in records if r.evidence_id == e.evidence_id)
            future.append(replace(e, revision=top + 1, recorded=max(later, tau) + 1,
                                  score=rng.random(), status=rng.choice(["valid", "revoked"])))
        counts["future_revisions_injected"] += len(future)
        assert profile(records + future, student, skill, t, tau) == state
    return counts


def run():
    results = []
    a = Evidence("a1", 1, "u", "python", "A", 1, 1, 1, 0.8)
    b = Evidence("b1", 1, "u", "python", "B", 1, 2, 2, 0.4, 0.5)
    a2 = Evidence("a2", 1, "u", "python", "A", 2, 3, 3, 0.6)
    corrected = replace(a2, revision=2, recorded=5, score=0.9)
    revoked = replace(b, revision=2, recorded=6, status="revoked")
    all_records = [a, b, a2, corrected, revoked]

    def record(name, actual, explanation):
        results.append({"scenario": name, "status": "passed", "observed": actual, "meaning": explanation})

    state = profile([], "u", "python", 1, 1)
    assert state["estimate"] is None and state["support"] == 0
    # Passive viewing is represented in the event layer, not in Evidence.
    passive_events = [{"event_id": "view-1", "verb": "viewed", "student": "u"}]
    assert passive_events and profile([], "u", "python", 1, 1) == state
    record("S1 missing evidence and passive activity", state, "A view event does not create assessed evidence.")

    zero = profile([Evidence("z", 1, "v", "sql", "Z", 1, 1, 1, 0.0)], "v", "sql", 1, 1)
    assert zero["estimate"] == 0.0 and zero["support"] == 1.0
    record("S2 observed zero", zero, "Observed zero is distinguishable from unassessed.")

    combined = profile([a, b], "u", "python", 2, 2)
    assert math.isclose(combined["estimate"], 2/3) and combined["support"] == 1.5
    record("S3 two assessments", combined, "Configured weights combine scores without a probability claim.")

    repeated = profile([a, b, a2], "u", "python", 3, 4)
    assert math.isclose(repeated["estimate"], 8/15) and len(repeated["evidence"]) == 2
    record("S4 repeated assessment", repeated, "A second attempt replaces the first contribution from assessment A.")

    before = profile(all_records, "u", "python", 3, 4)
    after = profile(all_records, "u", "python", 3, 5)
    earlier = profile(all_records, "u", "python", 2, 6)
    assert math.isclose(before["estimate"], 8/15) and math.isclose(after["estimate"], 11/15)
    # At tau=6 the revocation of B is known, even when asking about event day 2.
    assert earlier["estimate"] == 0.8
    record("S5 correction and two time cutoffs", {"before": before, "after": after, "earlier_as_known_day6": earlier},
           "A day-5 correction changes reconstruction but cannot enter a day-4 knowledge snapshot.")

    removed = profile(all_records, "u", "python", 3, 6)
    assert removed["estimate"] == 0.9 and removed["evidence"] == [["a2", 2]]
    record("S6 revocation", removed, "Revoking B removes its contribution while retaining the ledger history.")

    conflict = profile([replace(a, score=1.0), replace(b, score=0.0, weight=1.0)], "u", "python", 2, 2)
    assert conflict["estimate"] == 0.5 and conflict["dispersion"] == 0.5
    assert alignment(conflict, 0.4) == "review"
    record("S7 divergent assessment scores", conflict, "Dispersion triggers review under the illustrative threshold 0.35.")

    rp1 = RequirementVersion("RP", 1, "python", 0.7, valid_from=0, recorded=0)
    rp2 = RequirementVersion("RP", 2, "python", 0.6, valid_from=4, recorded=4)
    versions = [rp1, rp2]
    queries = {"t3_tau3": (3, 3), "t4_tau4": (4, 4), "t4_tau3": (4, 3)}
    chosen = {k: requirement_at(versions, "RP", *q) for k, q in queries.items()}
    assert chosen["t3_tau3"] == rp1 and chosen["t4_tau4"] == rp2 and chosen["t4_tau3"] == rp1
    labels = {k: alignment(profile([a, b], "u", "python", *queries[k]), v.level) for k, v in chosen.items()}
    assert labels == {"t3_tau3": "below configured threshold", "t4_tau4": "meets configured threshold",
                      "t4_tau3": "below configured threshold"}
    assert all(profile([a, b], "u", "python", *q)["estimate"] == combined["estimate"] for q in queries.values())
    expired = RequirementVersion("RX", 1, "python", 0.5, valid_from=0, recorded=0, valid_to=3)
    assert requirement_at([expired], "RX", 2, 2) == expired and requirement_at([expired], "RX", 3, 3) is None
    assert requirement_at(versions, "RP", 3, 6) == rp1  # v2 is known but not yet in force at t=3
    record("S8 requirement versions", {"state": combined["estimate"],
                                       "selected_version": {k: v.version for k, v in chosen.items()},
                                       "level": {k: v.level for k, v in chosen.items()}, "alignment": labels},
           "The requirement version is selected with the same two cutoffs; a new level changes the "
           "comparison, not the student's estimate, and is not applied before it is recorded.")

    assert profile(all_records + [a, corrected], "u", "python", 3, 6) == removed
    assert profile(list(reversed(all_records)), "u", "python", 3, 6) == removed
    record("S9 duplicates and replay order", removed, "Identical duplicate records and replay order leave the state unchanged.")

    assert validate_edge("Assessment", "assesses", "Skill", "rubric-v1")
    rejected = 0
    for args in [("Course", "assesses", "Student", "x"), ("Assessment", "assesses", "Skill", "")]:
        try:
            validate_edge(*args)
        except ValueError:
            rejected += 1
    for bad in ([a, replace(a, score=0.1)],                                    # conflicting duplicate revision
                [a, Evidence("a1x", 1, "u", "python", "A", 1, 1, 2, 0.5)],      # second record for one attempt
                [replace(a2, occurred=0, recorded=0), a]):                       # attempt 2 occurs before attempt 1
        try:
            canonical(bad)
        except ValueError:
            rejected += 1
    for bad in ([RequirementVersion("RP", 1, "python", 0.7, 0, 0), RequirementVersion("RP", 2, "docker", 0.6, 4, 4)],
                [RequirementVersion("RP", 1, "python", 0.7, 0, 5), RequirementVersion("RP", 2, "python", 0.6, 4, 4)]):
        try:
            check_requirements(bad)
        except ValueError:
            rejected += 1
    assert rejected == 7
    record("S10 invalid input rejection", {"rejected_invalid_inputs": rejected},
           "Wrong edge types, missing source references, conflicting duplicate revisions, a second record for one "
           "attempt, attempt numbers against occurrence order, a requirement version that changes its skill and "
           "versions recorded out of order are rejected.")

    graph = graph_example()
    requirements = [RequirementVersion("RP", 1, "python", 0.7, 0, 0), RequirementVersion("RD", 1, "docker", 0.7, 0, 0)]
    rubrics = [RubricVersion("A", "rubric-v1", 0), RubricVersion("B", "rubric-v1", 0)]
    trace = role_trace(graph["edges"], all_records, "u", "R", requirements, rubrics, 3, 6)
    assert [(x["skill"], x["assessments"], x["evidence"], x["label"]) for x in trace] == [
        ("docker", [], [], "unassessed: no assessment mapping"),
        ("python", ["A", "B"], [["a2", 2]], "meets configured threshold")]
    unmapped = 0
    try:
        check_mapping([Evidence("d1", 1, "u", "docker", "A", 1, 1, 1, 0.9)], graph["edges"])
    except ValueError:
        unmapped = 1
    assert unmapped == 1
    record("S11 role trace and mapping constraint", {"trace": trace, "rejected_unmapped_evidence": unmapped},
           "Role R traces through requirements, skills and assessments to selected evidence; "
           "evidence for docker from A is rejected because A does not assess docker.")

    # S12 rubric versions: A switches to rubric-v2 from day 4.
    rubrics_v2 = [RubricVersion("A", "rubric-v1", 0, valid_to=4), RubricVersion("A", "rubric-v2", 4),
                  RubricVersion("B", "rubric-v1", 0)]
    a3 = Evidence("a3", 1, "u", "python", "A", 3, 5, 5, 0.7, rubric="rubric-v2")
    assert check_rubrics(all_records + [a3], rubrics_v2)
    rubric_rejected = 0
    for bad in (replace(a3, evidence_id="a3x", occurred=3, recorded=3, attempt=2),   # v2 before it is in force
                replace(a3, evidence_id="a3y", rubric="rubric-v9"),                   # undeclared version
                Evidence("a4", 1, "u", "python", "A", 4, 6, 6, 0.7)):                 # v1 after it expired
        try:
            check_rubrics([bad], rubrics_v2)
        except ValueError:
            rubric_rejected += 1
    assert rubric_rejected == 3
    with_v2 = profile(all_records + [a3], "u", "python", 5, 6)
    assert with_v2["evidence"] == [["a3", 1]] and with_v2["estimate"] == 0.7
    record("S12 rubric versions", {"accepted": "a3 under rubric-v2", "rejected": rubric_rejected, "state": with_v2},
           "A record must name a rubric version declared for its assessment and in force when it occurred; "
           "re-scoring under a new rubric is a new attempt or a revocation plus a new observation.")

    # S13 minimum support: a single half-weight observation is not enough for a label.
    thin = profile([b], "u", "python", 2, 2)
    assert thin["support"] == 0.5 and thin["dispersion"] == 0.0
    assert alignment(thin, 0.3) == "insufficient evidence"
    assert alignment(combined, 0.6) == "meets configured threshold"
    record("S13 minimum support", {"state": thin, "label": alignment(thin, 0.3), "min_support": 1.0},
           "Support below the configured minimum gives 'insufficient evidence' instead of meets/below; "
           "D is 0 for one contribution, so dispersion is informative only with two or more.")

    properties = property_checks(random.Random(7), 1000)
    return {"data_status": "entirely synthetic; no participants, real curricula or scraped vacancies",
            "seed": 7, "scenario_count": len(results), "scenarios_passed": len(results),
            "property_check_iterations": properties["iterations"], "property_checks_passed": True,
            "property_check_inputs": properties,
            "thresholds": {"disagreement": 0.35, "min_support": 1.0, "role_v1": 0.7, "role_v2": 0.6},
            "graph_example": graph, "fixture": [asdict(e) for e in all_records], "scenarios": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="verification_results.json")
    args = parser.parse_args()
    report = run()
    with open(args.output, "w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
    print(json.dumps({k: report[k] for k in ("scenario_count", "scenarios_passed", "property_check_iterations", "property_checks_passed")}))
