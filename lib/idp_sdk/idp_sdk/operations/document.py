# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Document operations for IDP SDK."""

from typing import Optional

from idp_sdk.models import BatchDeletionResult, DocumentStatus


class DocumentOperation:
    """Single document operations."""

    def __init__(self, client):
        self._client = client

    def get_status(
        self, document_id: str, stack_name: Optional[str] = None
    ) -> DocumentStatus:
        """Get single document status."""
        batch_status = self._client.batch.get_status(
            document_id=document_id, stack_name=stack_name
        )
        if batch_status.documents:
            return batch_status.documents[0]
        from idp_sdk.exceptions import IDPResourceNotFoundError

        raise IDPResourceNotFoundError(f"Document not found: {document_id}")

    def delete(
        self, document_id: str, stack_name: Optional[str] = None, **kwargs
    ) -> BatchDeletionResult:
        """Delete single document."""
        return self._client.batch.delete_documents(
            document_ids=[document_id], stack_name=stack_name, **kwargs
        )
