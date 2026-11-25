"""Independent SQLite selection oracle and synthetic policy counterexamples.

Python 3.10+, standard library. Run without -O: python3 evaluate_audit.py
"""
from dataclasses import astuple, replace
from pathlib import Path
import json
import math
import random
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_models import Evidence, profile


def sql_profile(records, student, skill, t, tau):
    # Separate declarative implementation; does not call canonical() or profile().
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE TABLE e (id, rev, student, skill, assessment, attempt, occurred, recorded, score, weight, status, rubric)')
        db.executemany('INSERT INTO e VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', map(astuple, records))
        rows = db.execute('''
            WITH visible AS (
              SELECT DISTINCT * FROM e WHERE student=? AND skill=? AND occurred<=? AND recorded<=?
            ), revised AS (
              SELECT *, ROW_NUMBER() OVER(PARTITION BY id ORDER BY rev DESC) AS rn FROM visible
            ), attempts AS (
              SELECT *, ROW_NUMBER() OVER(PARTITION BY assessment
                ORDER BY occurred DESC, attempt DESC, id DESC) AS an
              FROM revised WHERE rn=1 AND status='valid'
            ) SELECT id,rev,occurred,score,weight FROM attempts WHERE an=1 ORDER BY id
        ''', (student, skill, t, tau)).fetchall()
    if not rows:
        return dict(estimate=None, support=0.0, dispersion=None, evidence=[], latest_event=None)
    total = sum(r[4] for r in rows)
    mean = sum(r[3]*r[4] for r in rows)/total
    return dict(estimate=mean, support=total,
                dispersion=math.sqrt(sum(r[4]*(r[3]-mean)**2 for r in rows)/total),
                evidence=[[r[0],r[1]] for r in rows], latest_event=max(r[2] for r in rows))


def run():
    rng = random.Random(41)
    queries = revisions = revoked = late = 0
    for case in range(200):
        records = []
        n = rng.randint(5,25)
        times = sorted(rng.randint(0,30) for _ in range(n))  # attempt numbers follow occurrence order
        for i in range(n):
            occurred = times[i]
            recorded = occurred+rng.randint(0,8)
            e = Evidence(f'e{i:03}',1,rng.choice(['u','v']),rng.choice(['python','sql']),
                         f'A{i%4}',i+1,occurred,recorded,rng.random(),rng.uniform(.05,1))
            records.append(e)
            late += recorded > occurred
            for revision in range(2,rng.randint(1,4)+1):
                recorded += rng.randint(1,8)
                e = replace(e,revision=revision,recorded=recorded,score=rng.random(),
                            weight=rng.uniform(.05,1),status=rng.choice(['valid','valid','revoked']))
                records.append(e)
                revisions += 1
                revoked += e.status == 'revoked'
        records.append(records[0])
        rng.shuffle(records)
        for q in range(10):
            student, skill = rng.choice(['u','v']),rng.choice(['python','sql'])
            t,tau = rng.randint(0,50),rng.randint(0,65)
            actual = profile(records,student,skill,t,tau)
            expected = sql_profile(records,student,skill,t,tau)
            for key in ['evidence','latest_event']:
                assert actual[key] == expected[key], (case,q,key)
            for key in ['estimate','support','dispersion']:
                if actual[key] is None:
                    assert expected[key] is None
                else:
                    assert math.isclose(actual[key],expected[key],abs_tol=1e-12,rel_tol=1e-12), (case,q,key)
            queries += 1
    a = Evidence('a',1,'u','python','A',1,1,1,.2)
    fixed = replace(a,revision=2,recorded=5,score=.8)
    withdrawn = replace(a,revision=2,recorded=5,status='revoked')
    retry = Evidence('b',1,'u','python','A',2,3,3,.8)
    def raw_mean(records):
        return sum(e.score*e.weight for e in records)/sum(e.weight for e in records)
    examples = [
        dict(omitted_rule='recording cutoff',expected=profile([a,fixed],'u','python',1,2)['estimate'],simplified=profile([a,fixed],'u','python',1,5)['estimate'],
             consequence='A correction recorded on day 5 leaks into a day-2 reconstruction.'),
        dict(omitted_rule='revision resolution',expected=profile([a,fixed],'u','python',1,5)['estimate'],simplified=raw_mean([a,fixed]),
             consequence='Averaging both revisions counts one observation twice.'),
        dict(omitted_rule='resolve revision before revocation filter',expected=profile([a,withdrawn],'u','python',1,5)['estimate'],simplified=profile([e for e in [a,withdrawn] if e.status=='valid'],'u','python',1,5)['estimate'],
             consequence='Filtering revoked rows first resurrects a withdrawn observation.'),
        dict(omitted_rule='one attempt per assessment',expected=profile([a,retry],'u','python',3,3)['estimate'],simplified=raw_mean([a,retry]),
             consequence='Averaging both attempts changes the declared latest-valid-attempt policy.')]
    for row in examples:
        assert row['expected'] != row['simplified']
    return dict(seed=41,ledgers=200,queries=queries,additional_revisions=revisions,
                revoked_revisions=revoked,late_initial_records=late,sql_agreement=True,
                absolute_and_relative_tolerance=1e-12,counterexamples=examples,
                limitation='Agreement of implementations of one policy is not validation of that policy or of competence measurement.')


if __name__ == '__main__':
    report = run()
    Path(__file__).with_name('audit_results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
