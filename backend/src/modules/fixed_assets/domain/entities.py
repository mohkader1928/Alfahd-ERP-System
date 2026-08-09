"""Domain exceptions for Fixed Assets (P0-5)."""


class AssetAlreadyDisposedError(ValueError):
    """Raised when depreciation or disposal is attempted against a fixed
    asset that already has a disposed_at date."""
