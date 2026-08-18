"""Exceptions raised while talking to the python-vm sandbox."""

from __future__ import annotations


class SandboxError(Exception):
    """Infrastructure failure while working with the sandbox."""


class SandboxSessionNotFound(SandboxError):
    """The session no longer exists — python-vm's reaper has collected it."""


class SandboxCapacityError(SandboxError):
    """The sandbox has run out of session slots."""


class SandboxUnavailable(SandboxError):
    """The sandbox could not be reached at all."""
