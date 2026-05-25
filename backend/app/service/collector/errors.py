from __future__ import annotations


class ChannelError(RuntimeError):
    """Raised when a collector channel cannot produce observations."""


class ChannelNotRegisteredError(ChannelError):
    """Raised when channel lookup misses a registered action."""


class RobotsBlocked(ChannelError):
    """Raised when robots.txt disallows a fetch target."""


class FetchTimeout(ChannelError):
    """Raised when upstream fetch exceeds timeout budget."""


class RateLimited(ChannelError):
    """Raised when a channel cannot acquire rate-limit tokens in time."""
