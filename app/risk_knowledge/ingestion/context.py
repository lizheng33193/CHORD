"""Input context for one M2D-6 ingestion attempt."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.knowledge_base.schemas import SourceType


class IngestionContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kb_id: str = Field(..., min_length=1)
    doc_id: str = Field(..., min_length=1)
    version_id: str = Field(..., min_length=1)
    job_id: str = Field(..., min_length=1)
    file_path: str = Field(..., min_length=1)
    doc_name: str = Field(..., min_length=1)
    source_type: SourceType
    parser_name: str = "swxy"
