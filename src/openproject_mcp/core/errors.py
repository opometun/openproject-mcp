class ScopeDeniedError(PermissionError):
    """Raised when a caller lacks required OAuth scopes for a tool."""


__all__ = ["ScopeDeniedError"]
