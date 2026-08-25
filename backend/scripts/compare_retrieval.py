"""
Show what the SQL filter changes, without asking a model anything.

    python -m scripts.compare_retrieval

The eval questions mostly name a scheme, which makes retrieval easy for
both configurations, so they do not really show the difference the
project is built on. This does, and it costs nothing to run because no
language model is involved.

It takes a student profile and asks the same question two ways:

  naive   embed "which scholarships can I get" and take the closest
          chunks from the whole corpus
  hybrid  ask Postgres who this student qualifies for, then search only
          inside those

Then it counts how many schemes the naive version put in front of the
model that the student is not actually eligible for. Every one of those
is a scheme a language model can be talked into recommending, because
it was handed the page and nothing told it the student does not qualify.
"""

from app import config, eligibility, embeddings, vector_store

QUESTION = "which scholarships can I get with my marks and family income"

PROFILES = [
    {
        "label": "SC girl, UG, 72%, income 1.8 lakh, Telangana",
        "profile": {
            "percentage": 72, "cgpa": None, "income": 180000, "age": 19,
            "category": "SC", "gender": "FEMALE", "course_level": "UG", "state": "Telangana",
        },
    },
    {
        "label": "General boy, Class 10, income 90,000, Goa",
        "profile": {
            "percentage": 68, "cgpa": None, "income": 90000, "age": 15,
            "category": "GEN", "gender": "MALE", "course_level": "SCHOOL", "state": "Goa",
        },
    },
    {
        "label": "Minority PG student, 65%, income 4 lakh, West Bengal",
        "profile": {
            "percentage": 65, "cgpa": None, "income": 400000, "age": 24,
            "category": "MINORITY", "gender": "FEMALE", "course_level": "PG", "state": "West Bengal",
        },
    },
]


def run(label, profile):
    eligible = {scheme["id"] for scheme in eligibility.find_matches(profile)}

    query_vector = embeddings.embed_query(QUESTION)

    naive_hits = vector_store.search(query_vector, limit=config.CANDIDATE_CHUNKS)
    naive_schemes = {hit["scheme_id"] for hit in naive_hits}

    hybrid_hits = vector_store.search(
        query_vector, limit=config.CANDIDATE_CHUNKS, scheme_ids=list(eligible)
    )
    hybrid_schemes = {hit["scheme_id"] for hit in hybrid_hits}

    wrong = naive_schemes - eligible
    missed = eligible - naive_schemes

    print(f"\n{label}")
    print(f"  actually eligible for            {len(eligible)} schemes")
    print(f"  naive search put in front of it  {len(naive_schemes)} schemes")
    print(f"    of those, NOT eligible for     {len(wrong)}")
    print(f"  hybrid search                    {len(hybrid_schemes)} schemes, all eligible")
    print(f"  eligible schemes naive never saw {len(missed)}")

    return len(eligible), len(naive_schemes), len(wrong), len(missed)


def main():
    print("Same question, same student, two ways of choosing what to read.")
    print(f'Question: "{QUESTION}"')

    totals = [0, 0, 0, 0]
    for case in PROFILES:
        result = run(case["label"], case["profile"])
        totals = [running + new for running, new in zip(totals, result)]

    eligible, seen, wrong, missed = totals

    print("\n--- across the three profiles ---")
    print(f"  schemes naive handed the model:        {seen}")
    print(f"  of those the student cannot get:       {wrong}")
    if seen:
        print(f"  so {wrong / seen:.0%} of what plain retrieval reads is ineligible")
    print(f"  eligible schemes plain retrieval missed: {missed}")
    print(
        "\nThis is the argument for filtering first. Anything in that ineligible\n"
        "count is a scheme the model was shown with nothing to tell it the\n"
        "student does not qualify, and a scheme it never saw cannot be suggested\n"
        "however good the reranking is."
    )


if __name__ == "__main__":
    main()
