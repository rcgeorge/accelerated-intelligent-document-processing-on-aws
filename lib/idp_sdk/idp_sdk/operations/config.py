# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Configuration operations for IDP SDK."""

from typing import Optional

from idp_sdk.models import ConfigCreateResult, ConfigDownloadResult, ConfigUploadResult, ConfigValidationResult


class ConfigOperation:
    """Configuration management operations."""

    def __init__(self, client):
        self._client = client

    def create(self, features: str = "min", pattern: str = "pattern-2", output: Optional[str] = None, **kwargs) -> ConfigCreateResult:
        """Generate configuration template."""
        return self._client.config_create(features=features, pattern=pattern, output=output, **kwargs)

    def validate(self, config_file: str, pattern: str = "pattern-2", **kwargs) -> ConfigValidationResult:
        """Validate configuration file."""
        return self._client.config_validate(config_file=config_file, pattern=pattern, **kwargs)

    def download(self, stack_name: Optional[str] = None, output: Optional[str] = None, **kwargs) -> ConfigDownloadResult:
        """Download configuration from stack."""
        return self._client.config_download(stack_name=stack_name, output=output, **kwargs)

    def upload(self, config_file: str, stack_name: Optional[str] = None, **kwargs) -> ConfigUploadResult:
        """Upload configuration to stack."""
        return self._client.config_upload(config_file=config_file, stack_name=stack_name, **kwargs)
