"""Models for game server endpoints: IGameServersService and ISteamApps.

IGameServersService/GetServerList serializes ``CGameServers_GetServerList_
Response`` (ValvePython/steam protobufs/steammessages_gameservers.proto) and
may leave out any field at its default value, so every field has a default.
A server's Steam ID is 64-bit and arrives as a string.

ISteamApps/UpToDateCheck is an older JSON endpoint: ``success`` is always
sent, and the version fields only when they apply.
"""

from pydantic import Field

from .base import SteamModel


class GameServer(SteamModel):
    """A game server known to Steam's master server."""

    addr: str = Field(default="", description='IP address and query port, "ip:port"')
    gameport: int = Field(default=0, description="Port players connect to")
    specport: int = Field(default=0, description="Spectator (SourceTV) port, if any")
    steamid: str = Field(default="", description="Steam ID of the server (64-bit)")
    name: str = Field(default="", description="Server name")
    appid: int = Field(default=0, description="App ID of the game")
    gamedir: str = Field(default="", description='Game directory, e.g. "tf"')
    version: str = Field(default="", description="Game version")
    product: str = Field(default="", description="Product name")
    region: int = Field(
        default=0,
        description="Master server region: 0 US East, 1 US West, 2 South "
        "America, 3 Europe, 4 Asia, 5 Australia, 6 Middle East, 7 Africa, 255 "
        "rest of the world (-1 also seen)",
    )
    players: int = Field(default=0, description="Players on the server")
    max_players: int = Field(default=0, description="Player slots")
    bots: int = Field(default=0, description="Bots on the server")
    map: str = Field(default="", description="Current map")
    secure: bool = Field(default=False, description="Whether VAC protects it")
    dedicated: bool = Field(default=False, description="Whether it is dedicated")
    os: str = Field(default="", description='Server OS: "l" Linux, "w" Windows')
    gametype: str = Field(default="", description="Server tags, comma separated")


class ServerList(SteamModel):
    """IGameServersService/GetServerList response body."""

    servers: list[GameServer] = Field(
        default_factory=list, description="Servers matching the filter"
    )


class ServerListResponse(SteamModel):
    """Response wrapper for IGameServersService/GetServerList."""

    response: ServerList = Field(default_factory=ServerList)


class UpToDateCheck(SteamModel):
    """Whether a game version is current (ISteamApps/UpToDateCheck)."""

    success: bool = Field(description="Whether Steam has version data for the app")
    up_to_date: bool = Field(
        default=False, description="Whether the given version is current"
    )
    version_is_listable: bool = Field(
        default=False, description="Whether the given version may be listed"
    )
    required_version: int | None = Field(
        default=None,
        description="Current version; sent only when the given one is out of date",
    )
    message: str = Field(
        default="", description='e.g. "Your server is out of date, please upgrade"'
    )
    error: str = Field(default="", description="Steam's reason when not successful")


class UpToDateCheckResponse(SteamModel):
    """Response wrapper for ISteamApps/UpToDateCheck."""

    response: UpToDateCheck
