"""Mutation check: each selection rule, when removed from profile(), must fail the
property checks. A faithful re-implementation is the control and must pass.

Run from this folder: python3 mutation_checks.py
"""
import math, random, sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import verify_models as vm
orig = vm.profile
def make(no_tau=False, revoke_first=False, all_attempts=False, no_resolution=False, empty=False,
         earliest=False, best_score=False, no_fallback=False, no_filter=False, unweighted=False):
    def p(records, student, skill, t, tau):
        vis = [e for e in vm.canonical(records) if (no_filter or (e.student == student and e.skill == skill))
               and e.occurred <= t and (no_tau or e.recorded <= tau)]
        if revoke_first: vis = [e for e in vis if e.status == "valid"]
        if no_resolution: versions = {(e.evidence_id, e.revision): e for e in vis}
        else:
            versions = {}
            for e in vis:
                if e.evidence_id not in versions or e.revision > versions[e.evidence_id].revision:
                    versions[e.evidence_id] = e
        sel = {}
        def rank(e):
            if earliest: return (-e.occurred, -e.attempt, e.evidence_id)
            if best_score: return (e.score, e.evidence_id)
            return (e.occurred, e.attempt, e.evidence_id)
        for k, e in versions.items():
            if e.status != "valid" and not no_fallback: continue
            key = k if all_attempts else e.assessment
            if key not in sel or rank(e) > rank(sel[key]): sel[key] = e
        obs = sorted((e for e in sel.values() if e.status == "valid"), key=lambda e: (e.evidence_id, e.revision))
        if empty: obs = []
        if not obs: return {"estimate": None, "support": 0.0, "dispersion": None, "evidence": [], "latest_event": None}
        wt = (lambda e: 1.0) if unweighted else (lambda e: e.weight)
        W = math.fsum(e.weight for e in obs); m = math.fsum(wt(e)*e.score for e in obs)/math.fsum(wt(e) for e in obs)
        D = math.sqrt(math.fsum(e.weight*(e.score-m)**2 for e in obs)/W)
        return {"estimate": m, "support": W, "dispersion": D, "evidence": [[e.evidence_id, e.revision] for e in obs],
                "latest_event": max(e.occurred for e in obs)}
    return p
cases = {"faithful re-implementation": {}, "no recording cutoff": {"no_tau": True},
         "revocation filtered before revision choice": {"revoke_first": True},
         "all attempts contribute": {"all_attempts": True}, "no revision resolution": {"no_resolution": True},
         "always empty (unassessed)": {"empty": True}, "earliest attempt per assessment": {"earliest": True},
         "best-scoring attempt per assessment": {"best_score": True},
         "no fallback after a revoked latest attempt": {"no_fallback": True},
         "ignores the student/skill filter": {"no_filter": True}, "unweighted mean": {"unweighted": True}}
for name, kw in cases.items():
    vm.profile = make(**kw)
    try:
        vm.property_checks(random.Random(7), 1000); print(f"{name:45s} -> passes")
    except (AssertionError, ValueError):
        print(f"{name:45s} -> CAUGHT")
vm.profile = orig
