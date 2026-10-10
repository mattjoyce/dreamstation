"""Errors raised while reading a card.

Every error names the file and, where there is one, the session, so a problem on a card of
1,300 sessions can be found again.
"""

from __future__ import annotations


class FormatError(ValueError):
    """The bytes do not fit the format this library knows.

    Raised for a short or corrupt chunk, a failed checksum or CRC, and for any code the format
    note does not describe. The last case is deliberate: a new code needs a decision, not a guess,
    so the reader stops rather than skip it.
    """

    def __init__(self, message: str, *, path: str | None = None, session: int | None = None):
        where = []
        if path:
            where.append(str(path))
        if session is not None:
            where.append(f"session {session:#x}")
        prefix = f"{' '.join(where)}: " if where else ""
        super().__init__(prefix + message)
        self.path = path
        self.session = session


class UnsupportedDeviceError(FormatError):
    """The card is from a device family or version this library does not decode."""
