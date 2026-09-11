"""Pydantic Schemas for LLM-as-Judge Evaluation.

Defines validated data models for:
1. Response Quality Judge Rubric (Correctness, Groundedness, Helpfulness, Relevance, Action Appropriateness)
2. Evidence Grounding Judge (Claim-level evidence support, binary support flag, support score 0-5)
"""

from typing import List
from pydantic import BaseModel, Field, field_validator


class ResponseJudgeScore(BaseModel):
    """Structured evaluation score across the 5 response quality dimensions."""

    correctness: int = Field(
        ...,
        ge=1,
        le=5,
        description="1-5 rating: Does the response address the customer issue without unsupported claims?",
    )
    groundedness: int = Field(
        ...,
        ge=1,
        le=5,
        description="1-5 rating: Are concrete claims/actions supported ONLY by provided evidence?",
    )
    helpfulness: int = Field(
        ...,
        ge=1,
        le=5,
        description="1-5 rating: Would this response meaningfully help the customer move toward resolution?",
    )
    relevance: int = Field(
        ...,
        ge=1,
        le=5,
        description="1-5 rating: Does the response directly address the issue without unnecessary content?",
    )
    action_appropriateness: int = Field(
        ...,
        ge=1,
        le=5,
        description="1-5 rating: Is the response appropriate for the selected action (auto_handle, clarify, escalate)?",
    )
    overall_score: float = Field(
        ...,
        ge=1.0,
        le=5.0,
        description="Overall composite score between 1.0 and 5.0 (typically mean or weighted score).",
    )
    brief_reason: str = Field(
        ...,
        min_length=5,
        description="Concise rationale explaining the evaluation scores.",
    )

    @field_validator("overall_score", mode="before")
    @classmethod
    def round_overall(cls, v: float) -> float:
        return round(float(v), 2)


class EvidenceJudgeScore(BaseModel):
    """Structured evaluation score for factual evidence grounding and claim support."""

    evidence_supported: bool = Field(
        ...,
        description="Binary determination whether important concrete claims/actions are adequately supported.",
    )
    support_score: int = Field(
        ...,
        ge=0,
        le=5,
        description="0-5 rating: Level of evidence support for concrete claims and troubleshooting actions.",
    )
    supported_claims: List[str] = Field(
        default_factory=list,
        description="Concrete troubleshooting actions or factual claims directly supported by evidence.",
    )
    unsupported_claims: List[str] = Field(
        default_factory=list,
        description="Concrete troubleshooting actions or factual claims not supported by evidence.",
    )
    reason: str = Field(
        ...,
        min_length=5,
        description="Rationale explaining evidence grounding or identifying missing support.",
    )
