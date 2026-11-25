# Article 1: competency graph and evidence-based profile

Code and data for the paper *Graph Models of Educational and Professional
Relations and an Evidence-Based Dynamic Student Competency Profile*
(Sultan Turan, Astana IT University).

The repository contains a reference implementation of the typed graph and the
profile computation, the checks reported in the paper, and a case study that
loads two public course specifications and three public vacancies into the
graph.

**Scope.** All student evidence is synthetic. Course and vacancy content comes
from public web pages and is stored as short paraphrases and identifiers. The
results verify that the implementation follows its specification and that the
graph can represent public documents. They are not evidence of measurement
validity, learning effects or employment outcomes.

## Requirements
Python 3.10 or later, standard library only. Every script runs in under a
second.

## Reproduce the paper's results

```sh
cd verification
python3 verify_models.py --output reproduced_verification.json
python3 mutation_checks.py
python3 evaluate_audit.py
cd ../case_study
python3 case_study.py --output reproduced_results.json
```

| Script | Paper result | Expected output |
|---|---|---|
| `verification/verify_models.py` | scenario table, property checks | 11/11 scenarios pass; 1,000 property-check iterations pass. The output is identical to `verification_results.json` |
| `verification/mutation_checks.py` | rule-removal check | the faithful re-implementation passes, and all 10 simplified versions are caught |
| `verification/evaluate_audit.py` | SQL cross-check | 2,000/2,000 queries agree (seed 41, 200 ledgers); rewrites `audit_results.json` with identical content |
| `case_study/case_study.py` | case study on public specifications | output is identical to `results.json` (see below) |

## Case study (`case_study/`)
- `data/sources.csv`: the five public sources, with URL, access date and
  the SHA-256 of the page snapshot taken on that date. The snapshots are not
  redistributed because the pages state no license.
- `data/entities.csv`: courses, learning outcomes, assessments, roles and
  requirements (50 entities), each with a locator in its source.
- `data/official_edges.csv`: 71 relations between document parts, taken from
  the sources.
- `data/skills.csv`: the shared vocabulary of 26 skills with scope notes.
- `data/mapping.csv`: the 66 item-to-skill links, assigned under
  `mapping/RATER_PROTOCOL.md` and reviewed and approved by the supervisor.
- `mapping/mapping_form_blank.csv`: a blank form of the 45 items, for remapping.

Main results in `results.json`:
- Sydney COMP5347: the final exam (55%) reaches architecture, performance and
  web security only through the outcomes it covers.
- Berkeley INFO 253B: no public assessment description names the objectives
  on authentication, system design or cloud deployment.
- Of 18 vacancy requirements, Berkeley's assessed skills cover 8 and Sydney's
  cover 2. Three requirements cannot be expressed as stated: an alternative, an
  optional advantage and a personal quality.
- With 1,000 synthetic students (seed 7), Berkeley's average-if-improved
  resubmission rule and the latest-attempt rule assign different labels to 6.6%
  of student–skill pairs. Best attempt and latest attempt differ on 2.7%.

To compare with another mapping of the same items, run
`python3 case_study.py --second path/to/other_mapping.csv`. This adds Cohen's κ.

## License
MIT. See `LICENSE`. Course and vacancy texts belong to their publishers and
are referenced by URL.
