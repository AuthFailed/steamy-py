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
