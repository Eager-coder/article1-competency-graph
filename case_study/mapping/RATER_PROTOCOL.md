# Mapping protocol: items → skills

A rater works alone and does not look at any other mapping of the same items
before finishing.

**Input:** `data/skills.csv` (26 skill IDs with scope notes) and
`mapping/mapping_form_blank.csv` (45 items: learning outcomes, assessments and
vacancy requirements, each with a short paraphrase of its source text).

**Task:** for each item, write in the `skills` column the IDs of every skill
the item *explicitly* names or clearly denotes. Separate IDs with `;`. If no
skill fits, leave the column empty.

**Rules**
1. Use only the item text and the skill scope notes. Don't infer from what a
   course "probably" teaches. For example, an exam described only as "final
   exam" gets no skills.
2. A named technology counts for the skill whose scope note lists it (Flask →
   `server_framework`; PostgreSQL → `relational_db`; Celery/rq → `async_tasks`).
3. A requirement offering alternatives ("PHP, Python or Node.js") is mapped to
   every skill it names. The `alternatives` flag tells the analysis script to
   treat these as OR, not AND.
4. Personal qualities (responsibility, punctuality) and skills outside the
   vocabulary stay unmapped. Write a note in `comment` if a vocabulary skill is
   missing.
5. When unsure, leave the skill out and add a comment.

**Review.** The supervisor reviewed the complete mapping against these rules and
approved it. The approved mapping is `data/mapping.csv`. If a second independent
mapping of the same items is supplied, `case_study.py --second` reports Cohen's κ
over all item × skill cells.
