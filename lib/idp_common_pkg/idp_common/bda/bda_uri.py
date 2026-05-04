# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Helpers for sanitizing S3 object keys so they are accepted by the
Bedrock Data Automation (BDA) InvokeDataAutomationAsync API.

Background
----------
BDA enforces a stricter S3 URI regex than S3 itself. Keys that S3 accepts
happily (tildes, spaces, some punctuation) are rejected by BDA with a
``ValidationException`` of the form::

    Value at 'inputConfiguration.s3Uri' failed to satisfy constraint:
    Member must satisfy regular expression pattern:
    s3://[a-z0-9][\\.\\-a-z0-9]{1,61}[a-z0-9](/[^\\x00-\\x1F\\x7F\\{^}%`\\]\\">\\[~<#|]*)?

Rather than chase the exact disallow list (which has historically been
broader in practice than what the error message advertises), we take
the conservative route: we preserve only characters from a known-safe
allowlist and map everything else into an underscore. The resulting key
stays human-readable, keeps the directory structure intact, and is
stable (same input always maps to the same output).

When the sanitized key would collide with another input (because two
different raw keys map to the same safe string), callers are
responsible for disambiguating -- typically by using
:func:`sanitize_key_with_hash` which appends a short hash of the
original key.
"""

from __future__ import annotations

import hashlib
import re

# Characters that are always safe in an S3 URI path component across
# AWS services we care about (S3, BDA, Textract, etc.). Anything outside
# this set is replaced.
#
# Allowed:
#   - lowercase/uppercase letters and digits
#   - forward slash (path separator)
#   - dot, underscore, hyphen
#
# Deliberately disallowed (replaced):
#   - tilde (BDA rejects)
#   - space (URL-unsafe; some AWS consumers require encoding)
#   - any punctuation not on the whitelist
_BDA_SAFE_CHAR = re.compile(r"[^A-Za-z0-9/._-]")


def is_bda_safe(key: str) -> bool:
    """Return True if ``key`` contains only BDA-safe characters."""
    return _BDA_SAFE_CHAR.search(key) is None


def sanitize_key(key: str) -> str:
    """Replace every non-safe character in ``key`` with an underscore.

    Empty path segments (e.g., produced by a leading or double slash)
    are left untouched -- we don't modify the shape of the path, only
    the characters inside it.
    """
    return _BDA_SAFE_CHAR.sub("_", key)


def sanitize_key_with_hash(key: str, hash_len: int = 8) -> str:
    """Sanitize ``key`` and append a short hash of the original.

    Useful when the sanitized form could collide with another input
    (e.g., ``a~b.pdf`` and ``a_b.pdf`` both map to ``a_b.pdf``).
    The hash suffix ensures the sanitized key round-trips 1:1 back to
    the original via DynamoDB lookup.

    The hash is derived from the full original key, inserted just
    before the final extension so the result still looks like a file.
    """
    safe = sanitize_key(key)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:hash_len]

    # Split on the last dot to preserve extension; if no extension,
    # just append the digest.
    if "/" in safe:
        dir_part, _, file_part = safe.rpartition("/")
        prefix = dir_part + "/"
    else:
        prefix = ""
        file_part = safe

    if "." in file_part:
        stem, _, ext = file_part.rpartition(".")
        return f"{prefix}{stem}__{digest}.{ext}"
    return f"{prefix}{file_part}__{digest}"
