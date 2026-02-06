# IDP SDK Documentation

The IDP SDK provides programmatic Python access to all IDP Accelerator capabilities with a clean, namespaced API.

## Installation

```bash
# Install from local development
pip install -e ./lib/idp_sdk

# Or with uv
uv pip install -e ./lib/idp_sdk
```

## Quick Start

```python
from idp_sdk import IDPClient

# Create client with stack configuration
client = IDPClient(stack_name="my-idp-stack", region="us-west-2")

# Process documents using namespaced API
result = client.batch.run(source="./documents/")
print(f"Batch: {result.batch_id}, Queued: {result.documents_queued}")

# Check status
status = client.batch.get_status(batch_id=result.batch_id)
print(f"Progress: {status.completed}/{status.total}")
```

## Architecture

The SDK follows a namespaced operation pattern for better organization:

```python
client = IDPClient(stack_name="my-stack")

# Stack operations
client.stack.deploy(...)
client.stack.delete()
client.stack.get_resources()

# Batch operations
client.batch.run(...)
client.batch.get_status(...)
client.batch.list()
client.batch.download(...)
client.batch.delete_documents(...)
client.batch.rerun(...)
client.batch.stop_workflows()

# Document operations
client.document.get_status(...)
client.document.delete(...)

# Configuration operations
client.config.create(...)
client.config.validate(...)
client.config.upload(...)
client.config.download(...)

# Manifest operations
client.manifest.generate(...)
client.manifest.validate(...)

# Testing operations
client.testing.load_test(...)
```

## Client Initialization

```python
from idp_sdk import IDPClient

# With stack name (for stack-dependent operations)
client = IDPClient(stack_name="my-stack", region="us-west-2")

# Without stack (for stack-independent operations)
client = IDPClient()

# Stack can be set later
client._stack_name = "new-stack"
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `stack_name` | str | No | CloudFormation stack name |
| `region` | str | No | AWS region (defaults to boto3 default) |

---

## Stack Operations

Operations for deploying and managing IDP stacks.

### stack.deploy()

Deploy or update an IDP stack.

```python
from idp_sdk import Pattern

result = client.stack.deploy(
    stack_name="my-new-stack",
    pattern=Pattern.PATTERN_2,
    admin_email="admin@example.com",
    max_concurrent=100,
    wait=True
)

if result.success:
    print(f"Stack deployed: {result.stack_name}")
    print(f"Outputs: {result.outputs}")
```

### stack.delete()

Delete an IDP stack.

```python
result = client.stack.delete(
    empty_buckets=True,
    force_delete_all=False,
    wait=True
)

print(f"Status: {result.status}")
```

### stack.get_resources()

Get stack resource information.

```python
resources = client.stack.get_resources()

print(f"Input Bucket: {resources.input_bucket}")
print(f"Output Bucket: {resources.output_bucket}")
print(f"Queue URL: {resources.document_queue_url}")
```

---

## Batch Operations

Operations for processing multiple documents.

### batch.run()

Process documents through the IDP pipeline.

```python
# From directory
result = client.batch.run(source="./documents/")

# From manifest
result = client.batch.run(source="./manifest.csv")

# From S3
result = client.batch.run(source="s3://bucket/path/")

# With options
result = client.batch.run(
    source="./documents/",
    batch_prefix="my-batch",
    file_pattern="*.pdf",
    recursive=True,
    number_of_files=10,
    config_path="./config.yaml"
)

print(f"Batch ID: {result.batch_id}")
print(f"Documents queued: {result.documents_queued}")
```

### batch.get_status()

Get processing status for a batch.

```python
status = client.batch.get_status(batch_id="batch-20250123-123456")

print(f"Total: {status.total}")
print(f"Completed: {status.completed}")
print(f"Failed: {status.failed}")
print(f"Success Rate: {status.success_rate:.1%}")

for doc in status.documents:
    print(f"  {doc.document_id}: {doc.status.value}")
```

### batch.list()

List recent batch processing jobs.

```python
batches = client.batch.list(limit=10)

for batch in batches:
    print(f"{batch.batch_id}: {batch.queued} docs")
```

### batch.download()

Download processing results.

```python
result = client.batch.download(
    batch_id="batch-20250123-123456",
    output_dir="./results",
    file_types=["summary", "sections"]
)

print(f"Downloaded {result.files_downloaded} files")
```

### batch.delete_documents()

Delete documents and all associated data.

```python
# Delete by batch ID
result = client.batch.delete_documents(batch_id="batch-123")

# Delete specific documents
result = client.batch.delete_documents(
    document_ids=["batch-123/doc1.pdf", "batch-123/doc2.pdf"]
)

# Delete with status filter
result = client.batch.delete_documents(
    batch_id="batch-123",
    status_filter="FAILED"
)

# Dry run
result = client.batch.delete_documents(
    batch_id="batch-123",
    dry_run=True
)

print(f"Deleted: {result.deleted_count}/{result.total_count}")
```

### batch.rerun()

Rerun processing from a specific step.

```python
from idp_sdk import RerunStep

# Rerun batch
result = client.batch.rerun(
    step=RerunStep.EXTRACTION,
    batch_id="batch-20250123-123456"
)

# Rerun specific documents
result = client.batch.rerun(
    step="classification",
    document_ids=["batch/doc1.pdf", "batch/doc2.pdf"]
)

print(f"Queued: {result.documents_queued}")
```

### batch.stop_workflows()

Stop all running workflows.

```python
result = client.batch.stop_workflows()

print(f"Queue purged: {result.queue_purged}")
print(f"Executions stopped: {result.executions_stopped}")
```

---

## Document Operations

Operations for individual documents.

### document.get_status()

Get status for a single document.

```python
status = client.document.get_status(
    document_id="batch-123/invoice.pdf"
)

print(f"Status: {status.status.value}")
print(f"Progress: {status.progress}")
```

### document.delete()

Delete a single document and its data.

```python
result = client.document.delete(
    document_id="batch-123/invoice.pdf"
)

print(f"Success: {result.success}")
```

---

## Configuration Operations

Operations for managing IDP configurations.

### config.create()

Generate an IDP configuration template.

```python
result = client.config.create(
    features="min",           # min, core, all, or comma-separated
    pattern="pattern-2",
    output="config.yaml",
    include_prompts=False,
    include_comments=True
)

print(result.yaml_content)
```

### config.validate()

Validate a configuration file.

```python
result = client.config.validate(
    config_file="./config.yaml",
    pattern="pattern-2"
)

if result.valid:
    print("Configuration is valid")
else:
    for error in result.errors:
        print(f"Error: {error}")
```

### config.upload()

Upload configuration to a deployed stack.

```python
result = client.config.upload(
    config_file="./my-config.yaml",
    validate=True
)

if result.success:
    print("Configuration uploaded")
```

### config.download()

Download configuration from a deployed stack.

```python
result = client.config.download(
    output="downloaded-config.yaml",
    format="minimal"  # "full" or "minimal"
)

print(result.yaml_content)
```

---

## Manifest Operations

Operations for manifest generation and validation.

### manifest.generate()

Generate a manifest file from a directory or S3 URI.

```python
result = client.manifest.generate(
    directory="./documents/",
    baseline_dir="./baselines/",
    output="manifest.csv",
    file_pattern="*.pdf",
    recursive=True
)

print(f"Documents: {result.document_count}")
print(f"Baselines matched: {result.baselines_matched}")
```

### manifest.validate()

Validate a manifest file.

```python
result = client.manifest.validate(manifest_path="./manifest.csv")

if result.valid:
    print(f"Valid manifest with {result.document_count} documents")
else:
    print(f"Invalid: {result.error}")
```

---

## Testing Operations

Operations for load testing and performance validation.

### testing.load_test()

Run load testing.

```python
result = client.testing.load_test(
    source_file="./sample.pdf",
    rate=100,              # Files per minute
    duration=5,            # Duration in minutes
    dest_prefix="load-test"
)

print(f"Total files: {result.total_files}")
```

---

## Response Models

All operations return typed Pydantic models:

```python
from idp_sdk import (
    # Results
    BatchResult,
    BatchStatusResult,
    DeploymentResult,
    DeletionResult,
    DocumentDeletionResult,
    RerunResult,
    DownloadResult,
    ManifestResult,
    ValidationResult,
    ConfigCreateResult,
    ConfigValidationResult,
    ConfigUploadResult,
    ConfigDownloadResult,
    LoadTestResult,
    StopWorkflowsResult,
    
    # Enums
    DocumentStatus,
    Pattern,
    RerunStep,
    StackStatus,
    
    # Exceptions
    IDPError,
    IDPConfigurationError,
    IDPStackError,
    IDPProcessingError,
    IDPValidationError,
)
```

### Common Result Fields

Most result models include:
- `success: bool` - Operation success status
- `error: Optional[str]` - Error message if failed
- Additional operation-specific fields

### Document Status Enum

```python
from idp_sdk import DocumentStatus

DocumentStatus.QUEUED
DocumentStatus.PROCESSING
DocumentStatus.COMPLETED
DocumentStatus.FAILED
DocumentStatus.ABORTED
```

---

## Error Handling

```python
from idp_sdk import IDPError, IDPStackError, IDPValidationError

try:
    result = client.batch.run(source="./documents/")
except IDPStackError as e:
    print(f"Stack error: {e}")
except IDPValidationError as e:
    print(f"Validation error: {e}")
except IDPError as e:
    print(f"General error: {e}")
```

---

## Advanced Usage

### Custom Configuration

```python
# Create and upload custom config
config_result = client.config.create(
    features="classification,extraction",
    pattern="pattern-2",
    output="custom-config.yaml"
)

# Validate before upload
validation = client.config.validate(config_file="custom-config.yaml")
if validation.valid:
    client.config.upload(config_file="custom-config.yaml")
```

### Batch Processing with Monitoring

```python
# Start batch
result = client.batch.run(source="./documents/")
batch_id = result.batch_id

# Monitor progress
import time
while True:
    status = client.batch.get_status(batch_id=batch_id)
    print(f"Progress: {status.completed}/{status.total}")
    
    if status.all_complete:
        break
    time.sleep(5)

# Download results
client.batch.download(batch_id=batch_id, output_dir="./results")
```

### Reprocessing Failed Documents

```python
# Get batch status
status = client.batch.get_status(batch_id="batch-123")

# Find failed documents
failed_docs = [
    doc.document_id 
    for doc in status.documents 
    if doc.status == DocumentStatus.FAILED
]

# Rerun from classification
if failed_docs:
    client.batch.rerun(
        step=RerunStep.CLASSIFICATION,
        document_ids=failed_docs
    )
```

---

## Migration from Old API

The SDK now uses namespaced operations. Old flat methods still work but are deprecated:

```python
# Old (deprecated)
client.run_inference(source="./docs/")
client.get_status(batch_id="batch-123")
client.deploy(stack_name="my-stack", ...)

# New (recommended)
client.batch.run(source="./docs/")
client.batch.get_status(batch_id="batch-123")
client.stack.deploy(stack_name="my-stack", ...)
```

---

## Examples

### Complete Workflow

```python
from idp_sdk import IDPClient, Pattern

# Initialize
client = IDPClient(stack_name="my-idp-stack")

# Deploy stack (if needed)
# client.stack.deploy(
#     pattern=Pattern.PATTERN_2,
#     admin_email="admin@example.com"
# )

# Generate manifest
manifest = client.manifest.generate(
    directory="./documents/",
    output="manifest.csv"
)

# Validate manifest
validation = client.manifest.validate(manifest_path="manifest.csv")
if not validation.valid:
    raise ValueError(f"Invalid manifest: {validation.error}")

# Process documents
result = client.batch.run(source="manifest.csv")
print(f"Batch started: {result.batch_id}")

# Monitor progress
import time
while True:
    status = client.batch.get_status(batch_id=result.batch_id)
    print(f"Progress: {status.completed}/{status.total}")
    
    if status.all_complete:
        break
    time.sleep(10)

# Download results
client.batch.download(
    batch_id=result.batch_id,
    output_dir="./results"
)

print(f"Success rate: {status.success_rate:.1%}")
```

---

## API Reference

For detailed API documentation, see the inline docstrings:

```python
from idp_sdk import IDPClient
help(IDPClient.batch.run)
help(IDPClient.stack.deploy)
```
