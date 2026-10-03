"""Models for ISteamWebAPIUtil responses.

These are legacy (non-protobuf) methods: Steam always sends every field
below except the descriptions, so only those have defaults. A body missing
any other field raises ``ResponseParsingError`` instead of parsing as empty.
"""

from pydantic import Field

from .base import SteamModel


class ServerInfo(SteamModel):
    """Response of GetServerInfo: the Web API server's clock."""

    servertime: int = Field(description="Server time (Unix timestamp)")
    servertimestring: str = Field(
        description=(
            "The same time as text in Steam's local time, not UTC, "
            "e.g. 'Sat Oct  3 07:57:07 2026'"
        )
    )


class APIParameter(SteamModel):
    """A parameter of a Web API method."""

    name: str = Field(description="Parameter name, e.g. 'steamid'")
    type: str = Field(
        description="Parameter type, e.g. 'uint32', 'string', '{message}', '{enum}'"
    )
    optional: bool = Field(description="Whether the parameter may be left out")
    description: str | None = Field(
        default=None, description="What the parameter is for, if Steam says"
    )


class APIMethod(SteamModel):
    """One version of a Web API method."""

    name: str = Field(description="Method name, e.g. 'GetServerInfo'")
    version: int = Field(description="Method version, e.g. 1 for v1")
    httpmethod: str = Field(description="HTTP verb, 'GET' or 'POST'")
    description: str | None = Field(
        default=None, description="What the method does, if Steam says"
    )
    parameters: list[APIParameter] = Field(description="The method's parameters")


class APIInterface(SteamModel):
    """A Web API interface and its methods."""

    name: str = Field(description="Interface name, e.g. 'ISteamWebAPIUtil'")
    methods: list[APIMethod] = Field(
        description="The interface's methods, one entry per version"
    )


class SupportedAPIList(SteamModel):
    """The Web API interfaces and methods Steam lists."""

    interfaces: list[APIInterface] = Field(description="The listed interfaces")


class SupportedAPIListResponse(SteamModel):
    """Response of GetSupportedAPIList."""

    apilist: SupportedAPIList
