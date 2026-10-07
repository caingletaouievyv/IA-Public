# IA/backend/app/context.py
"""Generic context item passed from context sources to AI prompts."""

from typing import Any

from pydantic import BaseModel, Field


class ContextItem(BaseModel):
    source: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
