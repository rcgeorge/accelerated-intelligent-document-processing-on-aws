# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
IDP SDK Client

Main client class for programmatic access to IDP Accelerator capabilities.
"""

from typing import Dict, Optional

from .exceptions import IDPConfigurationError, IDPStackError


class IDPClient:
    """
    Python SDK client for IDP Accelerator.

    Provides programmatic access to all IDP capabilities through operation namespaces:
    - client.stack: Stack deployment and management
    - client.batch: Batch document processing
    - client.document: Single document operations
    - client.config: Configuration management
    - client.manifest: Manifest file operations
    - client.testing: Load testing operations

    Examples:
        # Stack operations
        >>> client = IDPClient()
        >>> client.stack.deploy(stack_name="my-stack", pattern="pattern-2")
        >>> resources = client.stack.get_resources()

        # Batch operations
        >>> client = IDPClient(stack_name="my-stack", region="us-west-2")
        >>> result = client.batch.run(source="./documents/")
        >>> status = client.batch.get_status(batch_id=result.batch_id)

        # Config operations (no stack required)
        >>> client = IDPClient()
        >>> client.config.create(features="min", output="config.yaml")
        >>> client.config.validate("config.yaml")

        # Manifest operations (no stack required)
        >>> client.manifest.generate(directory="./docs/", output="manifest.csv")
    """

    def __init__(
        self,
        stack_name: Optional[str] = None,
        region: Optional[str] = None,
    ):
        """
        Initialize IDP SDK client.

        Args:
            stack_name: CloudFormation stack name (optional, can be passed per-operation)
            region: AWS region (optional, defaults to boto3 default)
        """
        self._stack_name = stack_name
        self._region = region
        self._resources_cache: Optional[Dict[str, str]] = None

        # Initialize operation namespaces
        from idp_sdk.operations import (
            BatchOperation,
            ConfigOperation,
            DocumentOperation,
            ManifestOperation,
            StackOperation,
            TestingOperation,
        )

        self.stack = StackOperation(self)
        self.batch = BatchOperation(self)
        self.document = DocumentOperation(self)
        self.config = ConfigOperation(self)
        self.manifest = ManifestOperation(self)
        self.testing = TestingOperation(self)

    @property
    def stack_name(self) -> Optional[str]:
        """Current default stack name."""
        return self._stack_name

    @stack_name.setter
    def stack_name(self, value: str):
        """Set default stack name and clear resource cache."""
        self._stack_name = value
        self._resources_cache = None

    @property
    def region(self) -> Optional[str]:
        """Current AWS region."""
        return self._region

    def _require_stack(self, stack_name: Optional[str] = None) -> str:
        """
        Ensure stack_name is available.

        Args:
            stack_name: Override stack name

        Returns:
            Stack name to use

        Raises:
            IDPConfigurationError: If no stack name available
        """
        name = stack_name or self._stack_name
        if not name:
            raise IDPConfigurationError(
                "stack_name is required for this operation. "
                "Either pass it to the method or set it when creating IDPClient."
            )
        return name

    def _get_stack_resources(self, stack_name: Optional[str] = None) -> Dict[str, str]:
        """Get stack resources with caching."""
        from idp_sdk.core.stack_info import StackInfo

        name = self._require_stack(stack_name)

        # Use cache if available and stack name matches
        if self._resources_cache and stack_name is None:
            return self._resources_cache

        stack_info = StackInfo(name, self._region)
        if not stack_info.validate_stack():
            raise IDPStackError(
                f"Stack '{name}' is not in a valid state for operations"
            )

        resources = stack_info.get_resources()

        # Cache only if using default stack
        if stack_name is None:
            self._resources_cache = resources

        return resources
