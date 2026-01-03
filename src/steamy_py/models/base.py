"""Base model classes for Steam API responses."""

from pydantic import BaseModel, ConfigDict


class SteamModel(BaseModel):
    """Base class for all Steam API response models."""

    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
        validate_assignment=True,
        use_enum_values=True,
        populate_by_name=True,
    )


class SteamResponse(SteamModel):
    """Base response wrapper for Steam API responses."""

    success: bool = True
    message: str | None = None


class PaginatedResponse(SteamModel):
    """Base for paginated API responses."""

    total: int | None = None
    has_more: bool = False
    next_cursor: str | None = None


class ErrorResponse(SteamModel):
    """Steam API error response model."""

    success: bool = False
    error: str | None = None
    error_code: int | None = None
    error_msg: str | None = None
