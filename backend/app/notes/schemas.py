# IA/backend/app/notes/schemas.py
"""Pydantic models: NoteCreate (full), NoteUpdate (partial); tag validation."""

from pydantic import BaseModel, Field, validator
from typing import List

class NoteBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    category: str = Field(..., min_length=1, max_length=50)
    content: str = Field(default="")
    tags: List[str] = Field(default_factory=list)

    @validator("tags", each_item=True)
    def tags_must_be_non_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Tags must be non-empty strings")
        return v.strip()

class NoteCreate(NoteBase):
    pass

class NoteUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=100)
    category: str | None = Field(None, min_length=1, max_length=50)
    content: str | None = Field(None, min_length=1)
    tags: List[str] | None = None

    @validator("tags", each_item=True)
    def tags_must_be_non_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Tags must be non-empty strings")
        return v.strip()
