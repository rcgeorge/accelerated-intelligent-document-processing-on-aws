# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Batch operations for IDP SDK."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from idp_sdk.exceptions import (
    IDPConfigurationError,
    IDPProcessingError,
    IDPResourceNotFoundError,
)
from idp_sdk.models import (
    BatchDeletionResult,
    BatchDownloadResult,
    BatchInfo,
    BatchRerunResult,
    BatchResult,
    BatchStatus,
    DocumentDeletionResult,
    DocumentStatus,
    RerunStep,
    StopWorkflowsResult,
)


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
        test_set: Optional[str] = None,
        stack_name: Optional[str] = None,
        batch_id: Optional[str] = None,
        batch_prefix: str = "sdk-batch",
        file_pattern: str = "*.pdf",
        recursive: bool = True,
        number_of_files: Optional[int] = None,
        config_path: Optional[str] = None,
        context: Optional[str] = None,
    ) -> BatchResult:
        """Run inference on a batch of documents."""
        from idp_sdk.core.batch_processor import BatchProcessor

        name = self._client._require_stack(stack_name)

        if source:
            import os

            if source.startswith("s3://"):
                s3_uri = source
            elif os.path.isdir(source):
                directory = source
            elif os.path.isfile(source):
                manifest = source
            else:
                raise IDPConfigurationError(
                    f"Source '{source}' not found or unrecognized format"
                )

        sources = [manifest, directory, s3_uri, test_set]
        if sum(1 for s in sources if s) != 1:
            raise IDPConfigurationError(
                "Specify exactly one source: manifest, directory, s3_uri, or test_set"
            )

        try:
            processor = BatchProcessor(
                stack_name=name, config_path=config_path, region=self._client._region
            )

            if test_set:
                result = self._process_test_set(
                    processor, test_set, context, number_of_files
                )
            elif manifest:
                result = processor.process_batch(
                    manifest_path=manifest,
                    output_prefix=batch_prefix,
                    batch_id=batch_id,
                    number_of_files=number_of_files,
                )
            elif directory:
                result = processor.process_batch_from_directory(
                    dir_path=directory,
                    file_pattern=file_pattern,
                    recursive=recursive,
                    output_prefix=batch_prefix,
                    batch_id=batch_id,
                    number_of_files=number_of_files,
                )
            else:
                result = processor.process_batch_from_s3_uri(
                    s3_uri=s3_uri,
                    file_pattern=file_pattern,
                    recursive=recursive,
                    output_prefix=batch_prefix,
                    batch_id=batch_id,
                )

            return BatchResult(
                batch_id=result["batch_id"],
                document_ids=result["document_ids"],
                queued=result.get("queued", 0),
                uploaded=result.get("uploaded", 0),
                failed=result.get("failed", 0),
                baselines_uploaded=result.get("baselines_uploaded", 0),
                source=result.get("source", ""),
                output_prefix=result.get("output_prefix", batch_prefix),
                timestamp=datetime.fromisoformat(
                    result.get("timestamp", datetime.now(timezone.utc).isoformat())
                ),
            )
        except Exception as e:
            raise IDPProcessingError(f"Batch processing failed: {e}") from e

    def _process_test_set(
        self,
        processor,
        test_set: str,
        context: Optional[str],
        number_of_files: Optional[int],
    ) -> Dict[str, Any]:
        """Process a test set (internal helper)."""
        import json

        import boto3

        lambda_client = boto3.client("lambda", region_name=self._client._region)
        all_functions = []
        paginator = lambda_client.get_paginator("list_functions")
        for page in paginator.paginate():
            all_functions.extend(page["Functions"])

        stack_name = self._client._require_stack()
        test_runner_function = next(
            (
                f["FunctionName"]
                for f in all_functions
                if stack_name in f["FunctionName"]
                and "TestRunnerFunction" in f["FunctionName"]
            ),
            None,
        )

        if not test_runner_function:
            raise IDPResourceNotFoundError(
                f"TestRunnerFunction not found for stack {stack_name}"
            )

        payload = {"arguments": {"input": {"testSetId": test_set}}}
        if context:
            payload["arguments"]["input"]["context"] = context
        if number_of_files:
            payload["arguments"]["input"]["numberOfFiles"] = number_of_files

        response = lambda_client.invoke(
            FunctionName=test_runner_function, Payload=json.dumps(payload)
        )
        result = json.loads(response["Payload"].read())

        resources = processor.resources
        test_set_bucket = resources.get("TestSetBucket")
        s3_client = boto3.client("s3", region_name=self._client._region)

        document_ids = []
        response = s3_client.list_objects_v2(
            Bucket=test_set_bucket, Prefix=f"{test_set}/input/"
        )

        if "Contents" in response:
            batch_id = result["testRunId"]
            for obj in response["Contents"]:
                key = obj["Key"]
                if not key.endswith("/"):
                    filename = key.split("/")[-1]
                    document_ids.append(f"{batch_id}/{filename}")

        return {
            "batch_id": result["testRunId"],
            "document_ids": document_ids,
            "queued": result.get("filesCount", len(document_ids)),
            "uploaded": 0,
            "failed": 0,
            "source": f"test-set:{test_set}",
            "output_prefix": test_set,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def rerun(
        self,
        step: Union[str, RerunStep],
        document_ids: Optional[List[str]] = None,
        batch_id: Optional[str] = None,
        stack_name: Optional[str] = None,
    ) -> BatchRerunResult:
        """Rerun processing for existing documents from a specific step."""
        from idp_sdk.core.rerun_processor import RerunProcessor

        name = self._client._require_stack(stack_name)
        step_str = step.value if isinstance(step, RerunStep) else step

        if not document_ids and not batch_id:
            raise IDPConfigurationError("Must specify either document_ids or batch_id")

        try:
            processor = RerunProcessor(stack_name=name, region=self._client._region)

            if batch_id and not document_ids:
                document_ids = processor.get_batch_document_ids(batch_id)

            result = processor.rerun_documents(
                document_ids=document_ids, step=step_str, monitor=False
            )

            return BatchRerunResult(
                documents_queued=result.get("documents_queued", 0),
                documents_failed=result.get("documents_failed", 0),
                failed_documents=result.get("failed_documents", []),
                step=RerunStep(step_str),
            )
        except Exception as e:
            raise IDPProcessingError(f"Rerun failed: {e}") from e

    def get_status(
        self,
        batch_id: Optional[str] = None,
        document_id: Optional[str] = None,
        stack_name: Optional[str] = None,
    ) -> BatchStatus:
        """Get status of a batch or single document."""
        from idp_sdk.core.batch_processor import BatchProcessor
        from idp_sdk.core.progress_monitor import ProgressMonitor

        name = self._client._require_stack(stack_name)

        if not batch_id and not document_id:
            raise IDPConfigurationError("Must specify either batch_id or document_id")

        processor = BatchProcessor(stack_name=name, region=self._client._region)

        if batch_id:
            batch_info = processor.get_batch_info(batch_id)
            if not batch_info:
                raise IDPResourceNotFoundError(f"Batch not found: {batch_id}")
            document_ids = batch_info["document_ids"]
            identifier = batch_id
        else:
            document_ids = [document_id]
            identifier = document_id

        monitor = ProgressMonitor(
            stack_name=name, resources=processor.resources, region=self._client._region
        )
        status_data = monitor.get_batch_status(document_ids)
        stats = monitor.calculate_statistics(status_data)

        documents = []
        for category in ["completed", "running", "queued", "failed"]:
            for doc in status_data.get(category, []):
                start_time = doc.get("start_time") or None
                end_time = doc.get("end_time") or None
                documents.append(
                    DocumentStatus(
                        document_id=doc.get("document_id", ""),
                        status=doc.get("status", "UNKNOWN"),
                        start_time=start_time,
                        end_time=end_time,
                        duration_seconds=doc.get("duration"),
                        num_pages=doc.get("num_pages"),
                        num_sections=doc.get("num_sections"),
                        error=doc.get("error"),
                    )
                )

        return BatchStatus(
            batch_id=identifier,
            documents=documents,
            total=stats.get("total", len(documents)),
            completed=stats.get("completed", 0),
            failed=stats.get("failed", 0),
            in_progress=stats.get("running", 0),
            queued=stats.get("queued", 0),
            success_rate=stats.get("success_rate", 0.0) / 100.0,
            all_complete=stats.get("all_complete", False),
        )

    def list(
        self,
        limit: int = 10,
        stack_name: Optional[str] = None,
    ) -> List[BatchInfo]:
        """List recent batch processing jobs."""
        from idp_sdk.core.batch_processor import BatchProcessor

        name = self._client._require_stack(stack_name)
        processor = BatchProcessor(stack_name=name, region=self._client._region)
        batches = processor.list_batches(limit=limit)

        return [
            BatchInfo(
                batch_id=b["batch_id"],
                document_ids=b["document_ids"],
                queued=b.get("queued", 0),
                failed=b.get("failed", 0),
                timestamp=b.get("timestamp", ""),
            )
            for b in batches
        ]

    def download(
        self,
        batch_id: str,
        output_dir: str,
        file_types: Optional[List[str]] = None,
        stack_name: Optional[str] = None,
    ) -> BatchDownloadResult:
        """Download processing results from OutputBucket."""
        from idp_sdk.core.batch_processor import BatchProcessor

        name = self._client._require_stack(stack_name)
        processor = BatchProcessor(stack_name=name, region=self._client._region)

        types_list = file_types or ["all"]
        if "all" in types_list:
            types_list = ["pages", "sections", "summary", "evaluation"]

        result = processor.download_batch_results(
            batch_id=batch_id, output_dir=output_dir, file_types=types_list
        )

        return BatchDownloadResult(
            files_downloaded=result.get("files_downloaded", 0),
            documents_downloaded=result.get("documents_downloaded", 0),
            output_dir=result.get("output_dir", output_dir),
        )

    def delete_documents(
        self,
        document_ids: Optional[List[str]] = None,
        batch_id: Optional[str] = None,
        status_filter: Optional[str] = None,
        stack_name: Optional[str] = None,
        dry_run: bool = False,
        continue_on_error: bool = True,
    ) -> BatchDeletionResult:
        """Permanently delete documents and all their associated data."""
        import boto3
        from idp_common.delete_documents import delete_documents, get_documents_by_batch

        name = self._client._require_stack(stack_name)

        if not document_ids and not batch_id:
            raise IDPConfigurationError("Must specify either document_ids or batch_id")

        if document_ids and batch_id:
            raise IDPConfigurationError(
                "Specify only one of document_ids or batch_id, not both"
            )

        resources = self._client._get_stack_resources(name)
        input_bucket = resources.get("InputBucket")
        output_bucket = resources.get("OutputBucket")
        documents_table_name = resources.get("DocumentsTable")

        if not input_bucket or not output_bucket or not documents_table_name:
            raise IDPResourceNotFoundError(
                "Required resources not found: InputBucket, OutputBucket, or DocumentsTable"
            )

        dynamodb = boto3.resource("dynamodb", region_name=self._client._region)
        tracking_table = dynamodb.Table(documents_table_name)
        s3_client = boto3.client("s3", region_name=self._client._region)

        try:
            if batch_id:
                document_ids = get_documents_by_batch(
                    tracking_table=tracking_table,
                    batch_id=batch_id,
                    status_filter=status_filter,
                )

                if not document_ids:
                    return BatchDeletionResult(
                        success=True,
                        deleted_count=0,
                        failed_count=0,
                        total_count=0,
                        dry_run=dry_run,
                        results=[],
                    )

            result = delete_documents(
                object_keys=document_ids,
                tracking_table=tracking_table,
                s3_client=s3_client,
                input_bucket=input_bucket,
                output_bucket=output_bucket,
                dry_run=dry_run,
                continue_on_error=continue_on_error,
            )

            single_results = [
                DocumentDeletionResult(
                    success=r.get("success", False),
                    object_key=r.get("object_key", ""),
                    deleted=r.get("deleted", {}),
                    errors=r.get("errors", []),
                )
                for r in result.get("results", [])
            ]

            return BatchDeletionResult(
                success=result.get("success", False),
                deleted_count=result.get("deleted_count", 0),
                failed_count=result.get("failed_count", 0),
                total_count=result.get("total_count", 0),
                dry_run=result.get("dry_run", dry_run),
                results=single_results,
            )
        except Exception as e:
            raise IDPProcessingError(f"Document deletion failed: {e}") from e

    def stop_workflows(
        self,
        stack_name: Optional[str] = None,
        skip_purge: bool = False,
        skip_stop: bool = False,
    ) -> StopWorkflowsResult:
        """Stop all running workflows for a stack."""
        from idp_sdk.core.stop_workflows import WorkflowStopper

        name = self._client._require_stack(stack_name)
        stopper = WorkflowStopper(stack_name=name, region=self._client._region)
        results = stopper.stop_all(skip_purge=skip_purge, skip_stop=skip_stop)

        return StopWorkflowsResult(
            executions_stopped=results.get("executions_stopped"),
            documents_aborted=results.get("documents_aborted"),
            queue_purged=not skip_purge,
        )
