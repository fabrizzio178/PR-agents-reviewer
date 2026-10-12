"""Domain errors: failures a review branch can degrade on instead of aborting."""

from __future__ import annotations


class ReviewError(Exception):
    """A reviewer branch could not produce a result."""


class LLMError(ReviewError):
    """The LLM call failed or returned output that does not match the schema."""


class StaticAnalysisError(ReviewError):
    """The static analyzer could not run or returned unreadable output."""
