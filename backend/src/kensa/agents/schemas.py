"""Structured output the diagnosis model must return.

Field order is deliberate: the model writes its citations and explanation before it commits to a
category. Only simple JSON-schema constraints are used, because Ollama turns the schema into a
grammar; semantic checks (do the citations exist?) are the verifier's job.
"""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from kensa.analysis.categories import Category

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class CitationDraft(BaseModel):
    evidence_id: str = Field(description="Evidence block id, e.g. E1", max_length=8)
    line: int = Field(description="The L-number of the cited line", ge=1)
    quote: str = Field(description="Exact text copied from that line", max_length=300)


class DiagnosisDraft(BaseModel):
    citations: list[CitationDraft] = Field(max_length=6)
    root_cause: str = Field(max_length=1500)
    summary: str = Field(max_length=600)
    category: Category
    confidence: float = Field(ge=0, le=1)
    recommended_fixes: list[ShortText] = Field(max_length=5)
    uncertainty: str = Field(max_length=800)


# Ollama's schema grammar cuts text off at max_length, so an edit that reaches it is treated as
# truncated and dropped (kensa.agents.remediation).
EDIT_TEXT_MAX = 400


class EditDraft(BaseModel):
    """One minimal text replacement in a repository file shown as evidence. Kensa checks it
    against the file and computes the diff itself; the model never writes a diff."""

    evidence_id: str = Field(description="Evidence block id of a repository file", max_length=8)
    find: str = Field(description="Exact text currently in that file", max_length=EDIT_TEXT_MAX)
    replace: str = Field(description="The text to put in its place", max_length=EDIT_TEXT_MAX)
    explanation: str = Field(max_length=300)


class RemediationDraft(BaseModel):
    edits: list[EditDraft] = Field(max_length=2)
    risks: list[ShortText] = Field(max_length=3)
    validation_steps: list[ShortText] = Field(max_length=3)
