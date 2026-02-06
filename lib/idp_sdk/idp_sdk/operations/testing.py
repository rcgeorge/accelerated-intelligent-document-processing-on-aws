# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Testing operations for IDP SDK."""

from typing import Optional

from idp_sdk.models import LoadTestResult


class TestingOperation:
    """Load testing and workflow control operations."""

    def __init__(self, client):
        self._client = client

    def load_test(self, source_file: str, stack_name: Optional[str] = None, rate: int = 100, duration: int = 1, **kwargs) -> LoadTestResult:
        """Run load test."""
        return self._client.load_test(source_file=source_file, stack_name=stack_name, rate=rate, duration=duration, **kwargs)
