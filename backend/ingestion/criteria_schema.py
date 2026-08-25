"""
The shape the model has to return, and the words it is allowed to use.

This is the first of the three defences from section 5 of the guide.
The model is told to answer in exactly this shape, so a number field cannot
come back as "around 2.5 lakh" and a category cannot come back as
"backward caste people". If it does not fit the shape, the call fails
loudly instead of putting rubbish in my database.

Every field is paired with a *_quote field. The model must copy the
sentence it read the value from. That quote is what verify.py checks,
and it is the cheapest hallucination catcher in the whole project.

One change from the guide. Its course_levels list is UG, PG, PHD and
DIPLOMA. My corpus has a lot of pre-matric and post-matric school
schemes, Class 9 to Class 12, and calling those UG would be wrong. So I
added SCHOOL. Leaving them out would have made a third of the corpus
unmatchable by course level.
"""

from typing import List, Optional

from pydantic import BaseModel, Field

# The only values allowed in the array columns. Written here rather than
# left to the model, because "SC", "Sc", "Scheduled Caste" and "sc" in
# four different rows would break every filter that compares them.
CATEGORIES = ["SC", "ST", "OBC", "EWS", "GEN", "MINORITY"]
GENDERS = ["MALE", "FEMALE", "OTHER"]
COURSE_LEVELS = ["SCHOOL", "DIPLOMA", "UG", "PG", "PHD"]


class ExtractedCriteria(BaseModel):
    """
    Everything read out of one scheme document.

    A field is None when the scheme sets no limit there. That is a real
    answer, not a missing one. "I could not read it" is a different
    state and it comes out of verify.py, not from here.
    """

    summary: str = Field(
        description="One or two sentences describing what this scheme is."
    )
    amount_text: Optional[str] = Field(
        default=None,
        description="The award amount, copied as written. Free text, amounts are messy.",
    )

    min_cgpa: Optional[float] = Field(
        default=None, description="Lowest CGPA on a 10 point scale that qualifies."
    )
    min_cgpa_quote: Optional[str] = Field(
        default=None, description="The exact sentence min_cgpa was read from."
    )

    min_percentage: Optional[float] = Field(
        default=None, description="Lowest percentage of marks that qualifies."
    )
    min_percentage_quote: Optional[str] = Field(
        default=None, description="The exact sentence min_percentage was read from."
    )

    max_family_income: Optional[float] = Field(
        default=None,
        description="Highest annual family income that qualifies, in rupees as a plain number.",
    )
    max_family_income_quote: Optional[str] = Field(
        default=None, description="The exact sentence max_family_income was read from."
    )

    categories: Optional[List[str]] = Field(
        default=None, description=f"Any of {CATEGORIES}. None means open to all."
    )
    categories_quote: Optional[str] = Field(
        default=None, description="The exact sentence categories was read from."
    )

    genders: Optional[List[str]] = Field(
        default=None, description=f"Any of {GENDERS}. None means open to all."
    )
    genders_quote: Optional[str] = Field(
        default=None, description="The exact sentence genders was read from."
    )

    course_levels: Optional[List[str]] = Field(
        default=None, description=f"Any of {COURSE_LEVELS}. None means open to all."
    )
    course_levels_quote: Optional[str] = Field(
        default=None, description="The exact sentence course_levels was read from."
    )

    states: Optional[List[str]] = Field(
        default=None,
        description="Indian states or union territories the student must belong to. None means all India.",
    )
    states_quote: Optional[str] = Field(
        default=None, description="The exact sentence states was read from."
    )

    min_age: Optional[int] = Field(default=None, description="Lowest age that qualifies.")
    min_age_quote: Optional[str] = Field(
        default=None, description="The exact sentence min_age was read from."
    )

    max_age: Optional[int] = Field(
        default=None, description="Highest age that qualifies."
    )
    max_age_quote: Optional[str] = Field(
        default=None, description="The exact sentence max_age was read from."
    )

    deadline: Optional[str] = Field(
        default=None,
        description="Application deadline as YYYY-MM-DD. None if the scheme has no fixed date or the page does not say.",
    )
    deadline_quote: Optional[str] = Field(
        default=None, description="The exact sentence deadline was read from."
    )


# The fields that hold a single number, and are checked by looking for
# that number inside the quote.
NUMERIC_FIELDS = [
    "min_cgpa",
    "min_percentage",
    "max_family_income",
    "min_age",
    "max_age",
]

# The fields that hold a list, and are checked by looking for a word
# that means each value inside the quote.
LIST_FIELDS = ["categories", "genders", "course_levels", "states"]

# What each allowed value can look like in a real sentence. A document
# almost never writes "SC", it writes "Scheduled Caste category", so a
# plain substring check on the value itself would fail nearly always.
VALUE_WORDS = {
    "SC": ["sc", "scheduled caste"],
    "ST": ["st", "scheduled tribe", "tribal"],
    "OBC": ["obc", "other backward", "backward class", "bc "],
    "EWS": ["ews", "economically weaker", "economically backward", "ebc"],
    "GEN": ["general", "any community", "all categories"],
    "MINORITY": [
        "minority",
        "minorities",
        "muslim",
        "christian",
        "sikh",
        "buddhist",
        "jain",
        "parsi",
        "zoroastrian",
    ],
    "MALE": ["male", "boy", "men"],
    "FEMALE": ["female", "girl", "woman", "women", "kanya"],
    "OTHER": ["transgender", "other gender"],
    "SCHOOL": [
        "class 9",
        "class 10",
        "class 11",
        "class 12",
        "classes 9",
        "classes 1",
        "school",
        "pre-matric",
        "prematric",
        "intermediate",
        "higher secondary",
        "matriculation",
    ],
    "DIPLOMA": ["diploma", "polytechnic", "iti"],
    "UG": [
        "undergraduate",
        "under graduate",
        "ug",
        "bachelor",
        "graduation",
        "degree",
        "b.tech",
        "b.e",
        "mbbs",
        "first year",
    ],
    "PG": [
        "postgraduate",
        "post graduate",
        "post-graduate",
        "pg",
        "master",
        "m.tech",
        "m.phil",
        "postgraduation",
        "post-graduation",
        # Indian documents almost never write "postgraduate". They name
        # the degree. Leaving these out made the check reject a correct
        # extraction from "must hold an M.D. or M.S.", which taught me
        # that a check tuned too tight is as bad as no check, because it
        # throws away good rows and tempts you to switch it off.
        "m.d",
        "m.s",
        "m.sc",
        "m.a.",
        "m.com",
        "mba",
        "med",
        "llm",
    ],
    "PHD": ["ph.d", "phd", "doctoral", "doctorate", "m.phil", "research fellow"],
}

# The short forms Indian documents use for states. Without these, the
# check rejected "Madhya Pradesh" because the sentence it was quoted
# from said "MP", and the column went NULL. NULL means "no constraint",
# so a Madhya Pradesh only scheme started matching a student in
# Telangana. That is exactly the failure the guide warns about, and it
# is why a check that is too strict is not the safe side of the trade.
STATE_WORDS = {
    "Madhya Pradesh": ["mp"],
    "Uttar Pradesh": ["up"],
    "Andhra Pradesh": ["ap"],
    "Tamil Nadu": ["tn"],
    "West Bengal": ["wb"],
    "Himachal Pradesh": ["hp"],
    "Jammu and Kashmir": ["j&k", "jammu", "kashmir"],
    "Delhi": ["nct", "new delhi"],
    "Andaman and Nicobar": ["andaman", "nicobar"],
    "Arunachal Pradesh": ["arunachal"],
    "Chhattisgarh": ["cg"],
    "Odisha": ["orissa"],
    "Uttarakhand": ["uk"],
}
