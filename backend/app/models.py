"""
What goes in and out of the API.

These are Pydantic models, so FastAPI checks the request before any of
my code runs. A student who types "abc" into the CGPA box gets a clear
422 from the framework instead of a confusing crash inside a SQL query.

Every profile field is optional on purpose. A student filling in half
the form should still get useful results, with the rules that could not
be checked reported honestly rather than quietly treated as passed.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class Profile(BaseModel):
    """The student. Everything is optional."""

    cgpa: Optional[float] = Field(default=None, ge=0, le=10)
    percentage: Optional[float] = Field(default=None, ge=0, le=100)
    income: Optional[float] = Field(default=None, ge=0, description="Annual family income in rupees")
    age: Optional[int] = Field(default=None, ge=5, le=100)
    category: Optional[str] = Field(default=None, description="SC, ST, OBC, EWS, GEN or MINORITY")
    gender: Optional[str] = Field(default=None, description="MALE, FEMALE or OTHER")
    course_level: Optional[str] = Field(default=None, description="SCHOOL, DIPLOMA, UG, PG or PHD")
    state: Optional[str] = Field(default=None)


class EligibilityRequest(BaseModel):
    profile: Profile


class SchemeMatch(BaseModel):
    id: int
    name: str
    provider: str
    description: str
    amount_text: Optional[str]
    deadline: Optional[str]
    source_url: str
    match_reasons: List[str]
    unchecked_rules: List[str]
    unverified_fields: List[str]
    extraction_confidence: float


class NearMiss(BaseModel):
    id: int
    name: str
    provider: str
    amount_text: Optional[str]
    source_url: str
    missed_by: str


class EligibilityResponse(BaseModel):
    matches: List[SchemeMatch]
    near_misses: List[NearMiss]
    total_schemes: int


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    profile: Optional[Profile] = None
    # "hybrid" is the real system. "naive" is the baseline, exposed so
    # the comparison in the README can be reproduced from the API
    # rather than only from the eval script.
    mode: str = Field(default="hybrid", pattern="^(hybrid|naive)$")
    use_reranker: bool = True


class Citation(BaseModel):
    number: int
    scheme_id: int
    scheme_name: str
    section: str
    source_url: str
    source_page: Optional[int] = None


class AskResponse(BaseModel):
    answer: str
    abstained: bool
    abstain_reason: Optional[str]
    citations: List[Citation]
    warnings: List[str]
    grounded: Optional[bool]
    near_misses: List[NearMiss] = []
    eligible_count: Optional[int]
    top_score: float
    latency_ms: int
    tokens: int
