# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Stack operations for IDP SDK."""

from typing import Dict, Optional, Union

from idp_sdk.models import DeletionResult, DeploymentResult, Pattern, StackResources


class StackOperation:
    """Stack deployment and management operations."""

    def __init__(self, client):
        self._client = client

    def deploy(
        self,
        stack_name: Optional[str] = None,
        pattern: Optional[Union[str, Pattern]] = None,
        admin_email: Optional[str] = None,
        **kwargs
    ) -> DeploymentResult:
        """Deploy IDP stack."""
        return self._client.deploy(stack_name=stack_name, pattern=pattern, admin_email=admin_email, **kwargs)

    def delete(self, stack_name: Optional[str] = None, **kwargs) -> DeletionResult:
        """Delete IDP stack."""
        return self._client.delete(stack_name=stack_name, **kwargs)

    def get_resources(self, stack_name: Optional[str] = None) -> StackResources:
        """Get stack resources."""
        return self._client.get_resources(stack_name=stack_name)
