# IA/backend/app/diagnostics/schemas.py
"""Pydantic validation for diagnostic feedback requests."""

from pydantic import BaseModel, Field, field_validator

FEEDBACK_REASONS = frozenset({"wrong", "unhelpful", "harmful", "other"})
FEEDBACK_FEATURES = frozenset({"ask"})


class DiagnosticFeedbackRequest(BaseModel):
    operation_id: str = Field(min_length=1, max_length=128)
    feature: str = Field(min_length=1, max_length=32)
    reason: str = Field(min_length=1, max_length=32)

    @field_validator("operation_id")
    @classmethod
    def strip_operation_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("operation_id required")
        return cleaned

    @field_validator("feature")
    @classmethod
    def validate_feature(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in FEEDBACK_FEATURES:
            raise ValueError("Unsupported diagnostic feature")
        return cleaned

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in FEEDBACK_REASONS:
            raise ValueError("Unsupported feedback reason")
        return cleaned
