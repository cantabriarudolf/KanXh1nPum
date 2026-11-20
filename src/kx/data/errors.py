"""Domain errors. Every message names the fix, not just the failure."""

from __future__ import annotations


class KxError(Exception):
    """Base class for errors this project raises on purpose."""


class DataError(KxError):
    """Something is wrong with the data itself."""


class DataNotCached(DataError):
    """The requested series is not on disk."""


class DataAlignmentError(DataError):
    """Series cannot be joined without inventing values or leaking the future."""


class DataSourceError(DataError):
    """A remote source refused, changed shape, or returned nothing."""
