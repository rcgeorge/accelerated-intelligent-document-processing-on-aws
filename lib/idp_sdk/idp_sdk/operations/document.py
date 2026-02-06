# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Document operations for IDP SDK."""

from typing import Optional

from idp_sdk.models import BatchStatusResult, DocumentDeletionResult


class DocumentOperation:
    """Single document operations."""

    def __init__(self, client):
        self._client = client

    def get_status(self, document_id: str, stack_name: Optional[str] = None) -> BatchStatusResult:
        """Get document status."""
        return self._client.get_status(document_id=document_id, stack_name=stack_name)

    def delete(self, document_id: str, stack_name: Optional[str] = None, **kwargs) -> DocumentDeletionResult:
        """Delete single document."""
        return self._client.delete_documents(document_ids=[document_id], stack_name=stack_name, **kwargs)
