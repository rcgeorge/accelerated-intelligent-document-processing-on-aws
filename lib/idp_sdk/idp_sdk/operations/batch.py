# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Batch operations for IDP SDK."""

from typing import List, Optional

from idp_sdk.core.batch_processor import BatchProcessor
from idp_sdk.core.progress_monitor import ProgressMonitor
from idp_sdk.core.rerun_processor import RerunProcessor
from idp_sdk.models import BatchInfo, BatchResult, BatchStatusResult, RerunResult


class BatchOperation:
    """Batch document processing operations."""

    def __init__(self, client):
        self._client = client

    def run(
        self,
        source: Optional[str] = None,
        manifest: Optional[str] = None,
        directory: Optional[str] = None,
        s3_uri: Optional[str] = None,
        batch_id: Optional[str] = None,
        batch_prefix: str = "sdk-batch",
        **kwargs
    ) -> BatchResult:
        """Run batch processing."""
        return self._client.run_inference(
            source=source,
            manifest=manifest,
            directory=directory,
            s3_uri=s3_uri,
            batch_id=batch_id,
            batch_prefix=batch_prefix,
            **kwargs
        )

    def get_status(self, batch_id: str, stack_name: Optional[str] = None) -> BatchStatusResult:
        """Get batch status."""
        return self._client.get_status(batch_id=batch_id, stack_name=stack_name)

    def list(self, limit: int = 10, stack_name: Optional[str] = None) -> List[BatchInfo]:
        """List recent batches."""
        return self._client.list_batches(limit=limit, stack_name=stack_name)

    def download(self, batch_id: str, output_dir: str, file_types: Optional[List[str]] = None, stack_name: Optional[str] = None):
        """Download batch results."""
        return self._client.download_results(batch_id=batch_id, output_dir=output_dir, file_types=file_types, stack_name=stack_name)

    def rerun(self, step: str, document_ids: Optional[List[str]] = None, batch_id: Optional[str] = None, stack_name: Optional[str] = None) -> RerunResult:
        """Rerun batch from specific step."""
        return self._client.rerun_inference(step=step, document_ids=document_ids, batch_id=batch_id, stack_name=stack_name)

    def delete_documents(self, batch_id: str, status_filter: Optional[str] = None, stack_name: Optional[str] = None, **kwargs):
        """Delete documents in batch."""
        return self._client.delete_documents(batch_id=batch_id, status_filter=status_filter, stack_name=stack_name, **kwargs)

    def stop_workflows(self, stack_name: Optional[str] = None, **kwargs):
        """Stop all running workflows."""
        return self._client.stop_workflows(stack_name=stack_name, **kwargs)
