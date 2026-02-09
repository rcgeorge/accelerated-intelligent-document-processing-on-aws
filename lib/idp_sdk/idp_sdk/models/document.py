# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Document-related models."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .base import DocumentState


class DocumentStatus(BaseModel):
    """Status information for a single document."""

    document_id: str = Field(description="Document identifier (S3 key)")
    status: DocumentState = Field(description="Current processing status")
    start_time: Optional[datetime] = Field(
        default=None, description="Processing start time"
    )
    end_time: Optional[datetime] = Field(
        default=None, description="Processing end time"
    )
    duration_seconds: Optional[float] = Field(
        default=None, description="Processing duration in seconds"
    )
    num_pages: Optional[int] = Field(default=None, description="Number of pages")
    num_sections: Optional[int] = Field(
        default=None, description="Number of extracted sections"
    )
    error: Optional[str] = Field(default=None, description="Error message if failed")


class DocumentDeletionResult(BaseModel):
    """Result of deleting a single document."""

    success: bool = Field(description="Whether deletion succeeded")
    object_key: str = Field(description="Document object key (S3 path)")
    deleted: Dict[str, Any] = Field(
        default_factory=dict,
        description="Details of deleted items (input_file, output_files, list_entries, document_record)",
    )
    errors: List[str] = Field(default_factory=list, description="Error messages if any")
