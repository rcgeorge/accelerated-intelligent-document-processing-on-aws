# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Manifest operations for IDP SDK."""

from typing import Optional

from idp_sdk.models import ManifestResult, ValidationResult


class ManifestOperation:
    """Manifest file operations."""

    def __init__(self, client):
        self._client = client

    def generate(self, directory: Optional[str] = None, s3_uri: Optional[str] = None, output: Optional[str] = None, **kwargs) -> ManifestResult:
        """Generate manifest file."""
        return self._client.generate_manifest(directory=directory, s3_uri=s3_uri, output=output, **kwargs)

    def validate(self, manifest_path: str) -> ValidationResult:
        """Validate manifest file."""
        return self._client.validate_manifest(manifest_path=manifest_path)
