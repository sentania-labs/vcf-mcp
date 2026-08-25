"""Typed dispatcher failures safe to expose to callers."""

from __future__ import annotations


class DispatchError(Exception):
    """A normalized failure raised before a handler result exists."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
