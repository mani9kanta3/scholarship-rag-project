"""
Thirty questions that nothing has been tuned on.

**Why this file exists.**

The forty questions in questions.py did their job, and then I used them
for something they cannot do. config.MIN_SIMILARITY was set to 0.75 by
looking at the scores those forty questions produced, which means the
abstention numbers measured on them are optimistic by an unknown amount.
A threshold chosen on a set and then scored on the same set is not
measured, it is fitted. The README says so, and saying so is not the
same as fixing it.

The reranker has the same problem from the other side. Its effect was
measured twice on those forty questions and came out opposite both
times, so the honest conclusion was "inside the noise". Forty questions,
eight of them traps, cannot separate a small effect from chance.

So this is a second set, and the whole value of it is in the rules I
followed while writing it.

**The rules.**

1. Written before looking at a single score from it. Not one question
   here was kept, dropped or reworded because of how the system did on
   it. The moment that happens this file becomes questions.py again.

2. Drawn from schemes the original forty never touch. Those twenty
   schemes are spoken for. These thirty questions use the other
   twenty four, so the two sets do not share ground truth.

3. Ground truth read off **the scheme documents**, never off the
   criteria table. This rule is in its stronger form because the first
   draft broke it and I did not notice until the numbers came back.

   I wrote the first version of questions 8 to 16 from the
   eligibility_criteria columns, which was fast and wrong. That table
   flattens rules that vary by course level into one value, which is
   the limitation the README already calls the largest correctness gap
   in the project. So the National Overseas scheme, which sets 35 years
   for a Master's, 40 for a PhD and 45 for post-doctoral study, appears
   in the table as a single max_age of 45. I read 45, wrote a question
   about a 45 year old Master's applicant, and called it eligible. The
   document says they are not.

   Three questions were wrong that way, and every one of them was wrong
   in the direction that agreed with the system. That is the part worth
   understanding: the system reads the flattened column, I read the
   flattened column, we agreed, and the judge marked it correct. A
   held-out set built from a derived table is not held out from the
   system that reads that table. It inherits its blind spot.

   Everything below is now derived from the stored chunk text. Where a
   rule depends on something the profile cannot record, such as which
   year of MBBS or which level a student is applying for, the question
   says so in words.

4. Nothing is tuned on this. Not the similarity floor, not the
   confidence floor, not the reranker. If a number here is
   disappointing, the number is the finding.

**The split**, which follows the original so the two are comparable:

  eligibility  8   a categorical rule decides it, clearly in or out
  threshold   10   five pairs, each sitting either side of a cutoff
  detail       6   documents, amounts and deadlines, no arithmetic
  trap         6   no answer in the corpus, so refusing is correct

The traps are deliberately harder than the original ones. Four name
something real I did not collect, which is the same idea as before. The
other two name a scheme that **is** in the corpus and ask for a fact
that is not in its document. Those are the ones I expect to be failed,
because every retrieval signal points confidently at the right scheme
and the answer still is not there.
"""


def profile(**changes):
    """Same helper as the main set, so profiles read the same way."""
    base = {
        "percentage": None,
        "cgpa": None,
        "income": None,
        "age": None,
        "category": None,
        "gender": None,
        "course_level": None,
        "state": None,
    }
    base.update(changes)
    return base


HOLDOUT_QUESTIONS = [
    # ---------------------------------------------------------------
    # eligibility: one categorical rule decides it
    # ---------------------------------------------------------------
    {
        "id": 1,
        "type": "eligibility",
        "question": "Am I eligible for the Begum Hazrat Mahal National Scholarship?",
        "profile": profile(gender="FEMALE", category="MINORITY", course_level="SCHOOL",
                           percentage=60, income=150000),
        "expected_scheme_ids": [4],
        "expected_abstain": False,
        "expected_answer": "Yes. It is for minority girl students in school with a family income under INR 2,00,000 who scored at least 50%, and this student meets all of those.",
        "why": "The clean pass for this scheme. Everything is comfortably inside, so a failure here is a broken filter rather than a hard question.",
    },
    {
        "id": 2,
        "type": "eligibility",
        "question": "Am I eligible for the Begum Hazrat Mahal National Scholarship?",
        "profile": profile(gender="MALE", category="MINORITY", course_level="SCHOOL",
                           percentage=60, income=150000),
        "expected_scheme_ids": [4],
        "expected_abstain": False,
        "expected_answer": "No. The scholarship is only for girl students, and this student is male.",
        "why": "One field changed from question 1. Isolates gender with the marks and income held constant, so nothing else can explain a wrong answer.",
    },
    {
        "id": 3,
        "type": "eligibility",
        "question": "Am I eligible for the MOMA Pre-Matric Scholarship for Minorities?",
        "profile": profile(category="GEN", course_level="SCHOOL", percentage=85, income=60000),
        "expected_scheme_ids": [17],
        "expected_abstain": False,
        "expected_answer": "No. The scheme is for students from minority communities, and this student is in the general category.",
        "why": "Strong marks and a very low income, so every number says yes and only the category says no. This is the shape of question a system that reads numbers well and categories badly gets wrong.",
    },
    {
        "id": 4,
        "type": "eligibility",
        "question": "Am I eligible for the Post-Graduate Indira Gandhi Scholarship for Single Girl Child?",
        "profile": profile(gender="MALE", course_level="PG", age=24),
        "expected_scheme_ids": [12],
        "expected_abstain": False,
        "expected_answer": "No. The scholarship is for a single girl child doing a postgraduate course, and this student is male.",
        "why": "The course level is right and the age is right, so the only failing rule is the one the scheme name states outright.",
    },
    {
        "id": 5,
        "type": "eligibility",
        "question": "Am I eligible for the Pre-Matric Scholarship for SC Students (Class 9 and 10), Delhi?",
        "profile": profile(category="SC", course_level="SCHOOL", income=120000, state="Haryana"),
        "expected_scheme_ids": [33],
        "expected_abstain": False,
        "expected_answer": "No. That scheme is for students domiciled in Delhi, and this student is from Haryana.",
        "why": "Category, course level and income all pass. Only the state fails, and the corpus holds a near identical Chandigarh scheme, so a system searching by meaning has an attractive wrong neighbour.",
    },
    {
        "id": 6,
        "type": "eligibility",
        "question": "Am I eligible for the Post-Matric Scholarship (PMS) for SC/ST/BC/Disabled Category, Telangana?",
        "profile": profile(category="OBC", state="Telangana", course_level="UG", income=140000),
        "expected_scheme_ids": [41],
        "expected_abstain": False,
        "expected_answer": "Yes. The scheme covers SC, ST and OBC students in Telangana, and this student is OBC and from Telangana.",
        "why": "A pass that needs the category list to be read as a list rather than as one value. OBC sits in the middle of it.",
    },
    {
        "id": 7,
        "type": "eligibility",
        "question": "Am I eligible for the Prime Minister's Fellowship Scheme for Doctoral Research?",
        "profile": profile(course_level="UG", percentage=92, income=250000),
        "expected_scheme_ids": [26],
        "expected_abstain": False,
        "expected_answer": "No. The fellowship is for doctoral research, and this student is an undergraduate.",
        "why": "Excellent marks on a scheme where marks are irrelevant. Tests that course level is actually checked rather than inferred from how strong the student looks.",
    },
    {
        "id": 8,
        "type": "eligibility",
        "question": "Am I eligible for the Swami Vivekananda Merit Cum Means Scholarship Scheme?",
        "profile": profile(category="MINORITY", state="West Bengal", course_level="UG",
                           percentage=60, income=200000),
        "expected_scheme_ids": [40],
        "expected_abstain": False,
        "expected_answer": "Yes. It is for minority students in West Bengal, and at graduation level the scheme asks for 60%. This student has 60% with a family income of 2,00,000, under the 2,50,000 limit.",
        "why": "A pass that has to clear several rules at once, and the one that matters is the marks. The document sets 60% for graduation level, 53% for postgraduate and 55% for engineering at graduation. The criteria table keeps only 53, so anyone writing ground truth from the table instead of the document gets this wrong. I did exactly that on the first draft.",
    },

    # ---------------------------------------------------------------
    # threshold: five pairs, each a hair either side of a cutoff
    # ---------------------------------------------------------------
    {
        "id": 9,
        "type": "threshold",
        "question": "I am a 3rd year MBBS student with 71% in my last university exam. Am I eligible for the Vivek Medical Students Scholarship Program?",
        "profile": profile(percentage=71, course_level="UG", income=200000),
        "expected_scheme_ids": [44],
        "expected_abstain": False,
        "expected_answer": "Yes. For a 2nd, 3rd or 4th year MBBS student the scheme asks for over 70% in the last university exam, and this student has 71% with a family income inside the INR 3,00,000 limit.",
        "why": "The year is stated in the question because the profile has nowhere to put it, and it matters: the document sets 85% for 1st year students and over 70% from 2nd year on. This is the clear pass just above a strict inequality, and it pairs with question 10 sitting exactly on it.",
    },
    {
        "id": 10,
        "type": "threshold",
        "question": "I am a 3rd year MBBS student with exactly 70% in my last university exam. Am I eligible for the Vivek Medical Students Scholarship Program?",
        "profile": profile(percentage=70, course_level="UG", income=200000),
        "expected_scheme_ids": [44],
        "expected_abstain": False,
        "expected_answer": "No. The scheme asks for over 70% and this student has exactly 70%, which is not over it.",
        "table_disagrees": "The table stores min_percentage 70 and the filter uses >=, so it says yes.",
        "why": "A strict inequality, which the criteria table cannot express. It stores a single min_percentage of 70 and the filter compares with greater-than-or-equal, so exactly 70 is let through and the answer comes out yes. I expect this one to fail. It is here because the failure is a true finding about how faithfully the rules were extracted, not a mistake in the question.",
    },
    {
        "id": 11,
        "type": "threshold",
        "question": "I am 35 and applying for a Master's degree abroad. Am I eligible for the National Overseas Scholarship Scheme for SC Students?",
        "profile": profile(category="SC", course_level="PG", age=35, percentage=65, income=500000),
        "expected_scheme_ids": [22],
        "expected_abstain": False,
        "expected_answer": "Yes. For a Master's the age limit is 35 years or less and this student is 35, with SC category, 65% in the Bachelor's degree and a family income under INR 8,00,000.",
        "why": "An age cutoff rather than a marks cutoff, landed on exactly. The level is stated in the question because the document sets three different limits by level and the profile cannot carry that.",
    },
    {
        "id": 12,
        "type": "threshold",
        "question": "I am 36 and applying for a Master's degree abroad. Am I eligible for the National Overseas Scholarship Scheme for SC Students?",
        "profile": profile(category="SC", course_level="PG", age=36, percentage=65, income=500000),
        "expected_scheme_ids": [22],
        "expected_abstain": False,
        "expected_answer": "No. For a Master's the age limit is 35 years and this student is 36.",
        "table_disagrees": "The table stores a single max_age of 45, the post-doctoral limit, so it says yes.",
        "why": "One year over question 11. The criteria table stores a single max_age of 45, which is the post-doctoral limit, so a system reading that column passes this student happily. Like question 10, I expect this to fail, and the failure is the schema limitation showing itself rather than a bad question.",
    },
    {
        "id": 13,
        "type": "threshold",
        "question": "Am I eligible for the National Means-cum-Merit Scholarship Scheme?",
        "profile": profile(category="GEN", course_level="SCHOOL", income=350000, percentage=60),
        "expected_scheme_ids": [21],
        "expected_abstain": False,
        "expected_answer": "Yes. The income limit is INR 3,50,000 and this family is at exactly 3,50,000, with the category, course level and marks all inside the rules.",
        "why": "An income limit landed on exactly. Income is where Indian number formatting bites, because 3,50,000 is three and a half lakh and not three hundred and fifty thousand to a naive parser.",
    },
    {
        "id": 14,
        "type": "threshold",
        "question": "Am I eligible for the National Means-cum-Merit Scholarship Scheme?",
        "profile": profile(category="GEN", course_level="SCHOOL", income=360000, percentage=60),
        "expected_scheme_ids": [21],
        "expected_abstain": False,
        "expected_answer": "No. The family income limit is INR 3,50,000 and this family earns 3,60,000.",
        "why": "Ten thousand rupees over question 13. Small enough that the two profiles read identically, large enough that the rule is unambiguous.",
    },
    {
        "id": 15,
        "type": "threshold",
        "question": "I have been admitted to a full time PhD and scored 55% in my postgraduate degree. Am I eligible for the National Fellowship and Scholarship for Higher Education of ST Students?",
        "profile": profile(category="ST", course_level="PHD", percentage=55, income=400000, age=30),
        "expected_scheme_ids": [20],
        "expected_abstain": False,
        "expected_answer": "Yes. The fellowship asks for a maximum age of 36, admission to a full time MPhil or PhD, and at least 55% in the postgraduate degree. This student is 30, admitted to a PhD, and has exactly 55%.",
        "why": "On the line at 55%. The admission condition is stated in the question because the profile has nowhere to record it, and without it the question is ambiguous: a student still doing a Master's has no postgraduate degree to be marked on yet.",
    },
    {
        "id": 16,
        "type": "threshold",
        "question": "I have been admitted to a full time PhD and scored 54.5% in my postgraduate degree. Am I eligible for the National Fellowship and Scholarship for Higher Education of ST Students?",
        "profile": profile(category="ST", course_level="PHD", percentage=54.5, income=400000, age=30),
        "expected_scheme_ids": [20],
        "expected_abstain": False,
        "expected_answer": "No. The fellowship asks for at least 55% in the postgraduate degree and this student has 54.5%.",
        "why": "Half a percent under question 15. The age and the admission both still pass, so the answer turns entirely on the one rule that does not.",
    },
    {
        "id": 17,
        "type": "threshold",
        "question": "Am I eligible for the Reliance Foundation Undergraduate Scholarships?",
        "profile": profile(percentage=60, course_level="UG", income=400000),
        "expected_scheme_ids": [35],
        "expected_abstain": False,
        "expected_answer": "Yes. It needs at least 60% for an undergraduate course with a family income under INR 15,00,000, and this student has exactly 60% and earns well under the limit.",
        "why": "A very high income ceiling with a marks cutoff landed on exactly. The generous income limit is there so that nothing but the marks can decide it.",
    },
    {
        "id": 18,
        "type": "threshold",
        "question": "Am I eligible for the Reliance Foundation Undergraduate Scholarships?",
        "profile": profile(percentage=59.5, course_level="UG", income=400000),
        "expected_scheme_ids": [35],
        "expected_abstain": False,
        "expected_answer": "No. The scheme needs at least 60% and this student has 59.5%.",
        "why": "The fifth and last pair, and the plainest one. If the four before it passed and this fails, the problem is the scheme rather than the arithmetic.",
    },

    # ---------------------------------------------------------------
    # detail: look it up and copy it out
    # ---------------------------------------------------------------
    {
        "id": 19,
        "type": "detail",
        "question": "How much money does the Begum Hazrat Mahal National Scholarship give?",
        "profile": None,
        "expected_scheme_ids": [4],
        "expected_abstain": False,
        "expected_answer": "INR 10,000 a year for Classes 9 and 10, and INR 12,000 a year for Classes 11 and 12, released in instalments.",
        "why": "Two amounts in one answer, which is the case where a system tends to quote one of them and drop the other. Also a direct test of grounding, since both figures must trace back to the source.",
    },
    {
        "id": 20,
        "type": "detail",
        "question": "What is the scholarship amount for the National Means-cum-Merit Scholarship Scheme?",
        "profile": None,
        "expected_scheme_ids": [21],
        "expected_abstain": False,
        "expected_answer": "INR 1,000 per month for a year.",
        "why": "A single clean figure. If this is wrong, nothing about the amounts in this corpus can be trusted.",
    },
    {
        "id": 21,
        "type": "detail",
        "question": "What documents do I need for the Vivek Medical Students Scholarship Program?",
        "profile": None,
        "expected_scheme_ids": [44],
        "expected_abstain": False,
        "expected_answer": "Aadhaar card, academic transcripts, proof of admission, family income proof and a passport size picture.",
        "why": "A short list, so an answer that pads it out with the documents other schemes ask for is immediately visible. Document lists are where corpora bleed into each other.",
    },
    {
        "id": 22,
        "type": "detail",
        "question": "What is the deadline for the Reliance Foundation Undergraduate Scholarships?",
        "profile": None,
        "expected_scheme_ids": [35],
        "expected_abstain": False,
        "expected_answer": "October 7, 2025.",
        "why": "A date rather than a number, which goes through a different half of the grounding check. The corpus is full of other deadlines for the search to confuse it with.",
    },
    {
        "id": 23,
        "type": "detail",
        "question": "Is the Post-Graduate Indira Gandhi Scholarship for Single Girl Child still open?",
        "profile": None,
        "expected_scheme_ids": [12],
        "expected_abstain": False,
        "expected_answer": "No. It is closed. The closing date was 31st December 2022.",
        "why": "The document says closed, so the honest answer is a no with a date attached. A system that treats every scheme as live will tell a student to apply to something that shut years ago.",
    },
    {
        "id": 24,
        "type": "detail",
        "question": "What does the National Overseas Scholarship Scheme for SC Students pay for maintenance?",
        "profile": None,
        "expected_scheme_ids": [22],
        "expected_abstain": False,
        "expected_answer": "An annual maintenance allowance of USD 15,400 for countries other than the UK, or GBP 9,900 for the UK.",
        "why": "Two currencies and two figures that only make sense as a pair. Quoting one without its condition is wrong in a way that looks right.",
    },

    # ---------------------------------------------------------------
    # trap: refusing is the only correct answer
    # ---------------------------------------------------------------
    {
        "id": 25,
        "type": "trap",
        "question": "What is the eligibility for the INSPIRE Scholarship for Higher Education?",
        "profile": None,
        "expected_scheme_ids": [],
        "expected_abstain": True,
        "expected_answer": "INSPIRE is not in this corpus, so the system should say it does not have it.",
        "why": "A real and well known Indian science scholarship that I did not collect. Checked: the word appears nowhere in the corpus. The corpus is full of merit scholarships for it to answer from instead.",
    },
    {
        "id": 26,
        "type": "trap",
        "question": "How do I apply for the KVPY fellowship?",
        "profile": None,
        "expected_scheme_ids": [],
        "expected_abstain": True,
        "expected_answer": "KVPY is not in this corpus, so the system should say so.",
        "why": "Another real Indian scheme that is absent, asked as a how-to. The corpus has many application processes, and they all look alike, so the pull towards answering is strong.",
    },
    {
        "id": 27,
        "type": "trap",
        "question": "What is the income limit for the Tamil Nadu Post-Matric Scholarship?",
        "profile": None,
        "expected_scheme_ids": [],
        "expected_abstain": True,
        "expected_answer": "The corpus holds no Tamil Nadu scheme, so the system should say so.",
        "why": "The corpus has post-matric scholarships for Assam, Bihar, Sikkim, Telangana and Uttar Pradesh. Every one of them has an income limit, and quoting the wrong state's figure is the worst available failure.",
    },
    {
        "id": 28,
        "type": "trap",
        "question": "Am I eligible for the Chevening Scholarship?",
        "profile": profile(course_level="PG", percentage=80, income=500000),
        "expected_scheme_ids": [],
        "expected_abstain": True,
        "expected_answer": "Chevening is not in this corpus, so the system should say so.",
        "why": "A foreign scholarship asked with a full profile, so the filter will return schemes this student does qualify for and the model has a tempting set of real matches to answer from.",
    },
    {
        "id": 29,
        "type": "trap",
        "question": "What is the interview date for the National Means-cum-Merit Scholarship Scheme?",
        "profile": None,
        "expected_scheme_ids": [21],
        "expected_abstain": True,
        "expected_answer": "The document does not mention an interview, so the system should say it cannot find that rather than offer the application deadline instead.",
        "why": "The harder kind of trap, and the one I expect to fail. The scheme is real and in the corpus, so routing, filtering and retrieval all point confidently at the right page. The fact simply is not on it, and the page does carry a date, which is exactly the wrong thing to reach for.",
    },
    {
        "id": 30,
        "type": "trap",
        "question": "What is the helpline number for the Reliance Foundation Undergraduate Scholarships?",
        "profile": None,
        "expected_scheme_ids": [35],
        "expected_abstain": True,
        "expected_answer": "No phone number appears in the document, so the system should say it does not have one.",
        "why": "The same shape as question 29 on a different scheme. Checked: the word helpline appears nowhere in the corpus. A retrieval score cannot catch either of these, because the right page really was found. Only the grounding check can.",
    },
]
