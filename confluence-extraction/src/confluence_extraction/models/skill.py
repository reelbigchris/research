"""Models for skill documents and Phase 2 outputs."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class QuestionType(str, Enum):
    """Type of open question."""

    CONTRADICTION = "contradiction"
    GAP = "gap"
    STALENESS = "staleness"
    AMBIGUITY = "ambiguity"


class OpenQuestion(BaseModel):
    """An unresolved issue discovered during synthesis."""

    question_type: QuestionType
    description: str = Field(..., description="What is unclear or contradictory")
    source_pages: list[str] = Field(default_factory=list, description="Page IDs involved")
    evidence: Optional[str] = Field(None, description="Relevant quotes or evidence")
    resolution: Optional[str] = Field(None, description="Resolution if answered")
    resolved: bool = Field(False, description="Whether this has been resolved")
    resolved_by: Optional[str] = Field(None, description="Who resolved it")
    resolved_at: Optional[datetime] = Field(None, description="When it was resolved")


class SourceReference(BaseModel):
    """Reference to source material."""

    source_type: str = Field(..., description="Type: confluence, interview, code, etc.")
    source_id: str = Field(..., description="ID or identifier")
    title: Optional[str] = Field(None, description="Human-readable title")
    url: Optional[str] = Field(None, description="URL if applicable")


class SkillMetadata(BaseModel):
    """Metadata for a skill document."""

    skill_id: str = Field(..., description="Unique identifier")
    title: str = Field(..., description="Skill title")
    category: str = Field(..., description="Category this skill belongs to")
    sources: list[SourceReference] = Field(default_factory=list, description="Source materials")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_reviewed: Optional[datetime] = Field(None, description="Last human review date")
    reviewed_by: Optional[str] = Field(None, description="Who reviewed it")
    open_questions_count: int = Field(0, description="Number of unresolved questions")
    confidence_score: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Confidence in accuracy (0-1)"
    )


class SkillDocument(BaseModel):
    """A synthesized skill document."""

    metadata: SkillMetadata
    content: str = Field(..., description="Markdown content of the skill")
    open_questions: list[OpenQuestion] = Field(
        default_factory=list,
        description="Unresolved questions"
    )
    key_concepts: list[str] = Field(
        default_factory=list,
        description="Key concepts covered"
    )
    related_skills: list[str] = Field(
        default_factory=list,
        description="Related skill IDs"
    )
    code_locations: list[str] = Field(
        default_factory=list,
        description="Related code paths"
    )
    synthesis_notes: Optional[str] = Field(
        None,
        description="Notes from the synthesis process"
    )


class ValidationNote(BaseModel):
    """A validation note from human review."""

    skill_id: str
    reviewer: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    corrections: list[str] = Field(default_factory=list, description="What was corrected")
    missing_info: list[str] = Field(default_factory=list, description="What's missing")
    questions_answered: list[str] = Field(
        default_factory=list,
        description="Question IDs that were answered"
    )
    additional_notes: Optional[str] = None
    approved: bool = Field(False, description="Whether the skill is approved")


class SynthesisResult(BaseModel):
    """Result of synthesizing pages into a skill."""

    skill: SkillDocument
    pages_synthesized: list[str] = Field(default_factory=list, description="Page IDs used")
    synthesis_confidence: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Confidence in synthesis"
    )
    warnings: list[str] = Field(default_factory=list, description="Warnings during synthesis")
