"""Player/User related data models for Steam API."""

import base64
from datetime import datetime
from enum import IntEnum

from pydantic import Field

from .base import SteamModel, SteamResponse


class PersonaState(IntEnum):
    """Steam persona state enumeration."""

    OFFLINE = 0
    ONLINE = 1
    BUSY = 2
    AWAY = 3
    SNOOZE = 4
    LOOKING_TO_TRADE = 5
    LOOKING_TO_PLAY = 6


class CommunityVisibilityState(IntEnum):
    """Steam community visibility state."""

    PRIVATE = 1
    FRIENDS_ONLY = 2
    PUBLIC = 3


class PlayerSummary(SteamModel):
    """Steam player summary information."""

    steamid: str = Field(description="Steam ID of the player")
    personaname: str = Field(description="Player's display name")
    profileurl: str = Field(description="URL to player's Steam profile")
    avatar: str = Field(description="32x32 pixel avatar URL")
    avatarmedium: str = Field(description="64x64 pixel avatar URL")
    avatarfull: str = Field(description="184x184 pixel avatar URL")

    personastate: PersonaState = Field(description="Current online status")
    communityvisibilitystate: CommunityVisibilityState = Field(
        description="Profile visibility"
    )
    profilestate: int | None = Field(default=None, description="Profile setup state")

    lastlogoff: int | None = Field(
        default=None, description="Last logoff time (Unix timestamp)"
    )
    commentpermission: int | None = Field(
        default=None, description="Comment permission setting"
    )

    realname: str | None = Field(
        default=None, description="Player's real name (if public)"
    )
    primaryclanid: str | None = Field(default=None, description="Primary clan/group ID")
    timecreated: int | None = Field(
        default=None, description="Account creation time (Unix timestamp)"
    )

    gameid: str | None = Field(default=None, description="Currently playing game ID")
    gameserverip: str | None = Field(
        default=None, description="Game server IP if in-game"
    )
    gameextrainfo: str | None = Field(
        default=None, description="Rich presence game info"
    )

    cityid: int | None = Field(default=None, description="City ID")
    loccountrycode: str | None = Field(default=None, description="Country code")
    locstatecode: str | None = Field(default=None, description="State code")
    loccityid: int | None = Field(default=None, description="City ID")

    @property
    def is_online(self) -> bool:
        """Check if player is currently online."""
        return self.personastate != PersonaState.OFFLINE

    @property
    def is_in_game(self) -> bool:
        """Check if player is currently in a game."""
        return self.gameid is not None

    @property
    def is_public(self) -> bool:
        """Check if profile is public."""
        return self.communityvisibilitystate == CommunityVisibilityState.PUBLIC


class Friend(SteamModel):
    """Steam friend information."""

    steamid: str = Field(description="Steam ID of the friend")
    relationship: str = Field(description="Relationship type (usually 'friend')")
    friend_since: int | None = Field(
        default=None, description="Unix timestamp when friendship started"
    )

    @property
    def friend_since_datetime(self) -> datetime | None:
        """Get friendship start date as datetime object."""
        return datetime.fromtimestamp(self.friend_since) if self.friend_since else None


class PlayerBan(SteamModel):
    """Steam player ban information."""

    steamid: str = Field(alias="SteamId", description="Steam ID of the player")
    community_banned: bool = Field(
        alias="CommunityBanned", description="Community ban status"
    )
    vac_banned: bool = Field(alias="VACBanned", description="VAC ban status")
    number_of_vac_bans: int = Field(
        alias="NumberOfVACBans", description="Number of VAC bans"
    )
    days_since_last_ban: int = Field(
        alias="DaysSinceLastBan", description="Days since last ban"
    )
    number_of_game_bans: int = Field(
        alias="NumberOfGameBans", description="Number of game bans"
    )
    economy_ban: str = Field(alias="EconomyBan", description="Economy ban status")

    @property
    def is_banned(self) -> bool:
        """Check if player has any active bans."""
        return self.community_banned or self.vac_banned or self.number_of_game_bans > 0

    @property
    def has_economy_ban(self) -> bool:
        """Check if player has economy restrictions."""
        return self.economy_ban != "none"


class VanityURLResolution(SteamModel):
    """Vanity URL resolution result."""

    steamid: str | None = Field(default=None, description="Resolved Steam ID")
    success: int = Field(description="Success code (1 = success)")

    @property
    def is_success(self) -> bool:
        """Check if resolution was successful."""
        return self.success == 1


# Response wrapper models
class PlayerSummariesResponse(SteamResponse):
    """Response wrapper for GetPlayerSummaries."""

    players: list[PlayerSummary] = Field(description="List of player summaries")


class FriendsListResponse(SteamResponse):
    """Response wrapper for GetFriendList."""

    friends: list[Friend] = Field(default_factory=list, description="List of friends")


class PlayerBansResponse(SteamResponse):
    """Response wrapper for GetPlayerBans."""

    players: list[PlayerBan] = Field(description="List of player ban information")


class ResolveVanityURLResponse(SteamResponse):
    """Response wrapper for ResolveVanityURL."""

    response: VanityURLResolution = Field(description="Vanity URL resolution result")


# IPlayerService/GetBadges and GetSteamLevel. Like every IPlayerService
# method, these leave out what Steam does not share, so every field has a
# default.
class Badge(SteamModel):
    """A badge the user owns (IPlayerService/GetBadges)."""

    badgeid: int = Field(
        default=0, description="Badge id; a game or event badge is told by appid"
    )
    level: int = Field(default=0, description="Badge level")
    completion_time: int = Field(
        default=0, description="Time the badge was earned (Unix timestamp)"
    )
    xp: int = Field(default=0, description="XP the badge is worth")
    scarcity: int = Field(default=0, description="Number of users with this badge")
    appid: int = Field(
        default=0, description="App of a game or event badge (0 for other badges)"
    )
    communityitemid: str = Field(
        default="", description="Community item id of a game or event badge"
    )
    border_color: int = Field(
        default=0, description="1 for a foil trading card badge, else 0"
    )


class PlayerBadges(SteamModel):
    """A user's badges and Steam level progress (IPlayerService/GetBadges)."""

    badges: list[Badge] = Field(default_factory=list, description="Owned badges")
    player_xp: int = Field(default=0, description="Total XP")
    player_level: int = Field(default=0, description="Steam level")
    player_xp_needed_to_level_up: int = Field(
        default=0, description="XP still needed for the next level"
    )
    player_xp_needed_current_level: int = Field(
        default=0, description="Total XP needed to reach the current level"
    )


class BadgesResponse(SteamModel):
    """Response wrapper for IPlayerService/GetBadges."""

    response: PlayerBadges = Field(default_factory=PlayerBadges)


class SteamLevel(SteamModel):
    """A user's Steam level (IPlayerService/GetSteamLevel)."""

    player_level: int = Field(default=0, description="Steam level")


class SteamLevelResponse(SteamModel):
    """Response wrapper for IPlayerService/GetSteamLevel."""

    response: SteamLevel = Field(default_factory=SteamLevel)


# IPlayerService/GetCommunityBadgeProgress
class CommunityBadgeQuest(SteamModel):
    """One quest of a community badge.

    ``CPlayer_GetCommunityBadgeProgress_Response.Quest``.
    """

    questid: int = Field(default=0, description="Quest id")
    completed: bool = Field(
        default=False, description="Whether the user has completed the quest"
    )


class CommunityBadgeProgress(SteamModel):
    """Body of ``CPlayer_GetCommunityBadgeProgress_Response``."""

    quests: list[CommunityBadgeQuest] = Field(default_factory=list)


class CommunityBadgeProgressResponse(SteamModel):
    """Response wrapper for IPlayerService/GetCommunityBadgeProgress."""

    response: CommunityBadgeProgress = Field(default_factory=CommunityBadgeProgress)


# IPlayerService/GetPlayerLinkDetails
_AVATAR_URL = "https://avatars.steamstatic.com/{}_full.jpg"
# Steam's avatar digest is a SHA-1 (20 bytes). An all-zero digest stands for
# "no avatar set", which Steam shows as this default avatar (node-steam-user
# maps it the same way for persona state data).
_SHA1_SIZE = 20
_NO_AVATAR_HASH = "0" * 40
_DEFAULT_AVATAR_HASH = "fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb"


class PlayerLinkPublicData(SteamModel):
    """Public profile data of an account.

    ``CPlayer_GetPlayerLinkDetails_Response.PlayerLinkDetails.AccountPublicData``.
    """

    steamid: str = Field(default="", description="SteamID64 of the account")
    visibility_state: int = Field(
        default=0,
        description="Profile visibility (CommunityVisibilityState: 1 private, "
        "2 friends only, 3 public)",
    )
    privacy_state: int = Field(
        default=0, description="Privacy state, as Steam sends it"
    )
    profile_state: int = Field(
        default=0, description="1 if the user has set up a community profile"
    )
    ban_expires_time: int = Field(
        default=0, description="When a community ban ends (Unix timestamp)"
    )
    account_flags: int = Field(default=0, description="Account flags bit field")
    sha_digest_avatar: str = Field(
        default="", description="SHA-1 of the avatar, base64-encoded"
    )
    persona_name: str = Field(default="", description="Display name")
    profile_url: str = Field(
        default="",
        description="Custom profile URL name (the part after /id/), if any",
    )
    content_country_restricted: bool = False

    @property
    def avatar_hash(self) -> str:
        """The avatar hash as hex, as ``PlayerSummary.avatarhash`` has it.

        Empty when Steam sent no avatar digest, or one that is not a
        base64-encoded SHA-1 (20 bytes).
        """
        try:
            digest = base64.b64decode(self.sha_digest_avatar, validate=True)
        except ValueError:  # includes binascii.Error
            return ""
        return digest.hex() if len(digest) == _SHA1_SIZE else ""

    @property
    def avatar_url(self) -> str | None:
        """URL of the full-size (184x184) avatar, or None without an avatar hash.

        An all-zero hash (no avatar set) gives Steam's default avatar. Use
        ``.jpg`` or ``_medium.jpg`` instead of ``_full.jpg`` for the 32x32
        and 64x64 sizes.
        """
        avatar_hash = self.avatar_hash
        if not avatar_hash:
            return None
        if avatar_hash == _NO_AVATAR_HASH:
            avatar_hash = _DEFAULT_AVATAR_HASH
        return _AVATAR_URL.format(avatar_hash)


class PlayerLinkPrivateData(SteamModel):
    """Presence data of an account.

    ``CPlayer_GetPlayerLinkDetails_Response.PlayerLinkDetails.AccountPrivateData``.

    Which fields Steam fills depends on the caller (unverified which);
    published clients that call the method with an API key read only
    ``time_created``, ``last_logoff_time`` and ``last_seen_online``.
    """

    persona_state: int = Field(default=0, description="Online status (PersonaState)")
    persona_state_flags: int = Field(default=0, description="Persona state flags")
    time_created: int = Field(
        default=0, description="Account creation time (Unix timestamp)"
    )
    game_id: str = Field(default="", description="Game being played (64-bit game id)")
    game_server_steam_id: str = Field(
        default="", description="Steam ID of the game server (64-bit)"
    )
    game_server_ip_address: int = Field(
        default=0, description="IPv4 address of the game server, as an integer"
    )
    game_server_port: int = 0
    game_extra_info: str = Field(
        default="", description="Name of the game, e.g. for a non-Steam game"
    )
    account_name: str = ""
    lobby_steam_id: str = Field(
        default="", description="Steam ID of the lobby (64-bit)"
    )
    rich_presence_kv: str = Field(default="", description="Rich presence, as text")
    broadcast_session_id: str = Field(default="", description="Broadcast id (64-bit)")
    watching_broadcast_accountid: int = 0
    watching_broadcast_appid: int = 0
    watching_broadcast_viewers: int = 0
    watching_broadcast_title: str = ""
    last_logoff_time: int = Field(default=0, description="Last logoff (Unix timestamp)")
    last_seen_online: int = Field(
        default=0, description="Last time seen online (Unix timestamp)"
    )
    game_os_type: int = 0
    game_device_type: int = 0
    game_device_name: str = ""
    game_is_private: bool = False


class PlayerLinkDetails(SteamModel):
    """One account of IPlayerService/GetPlayerLinkDetails."""

    public_data: PlayerLinkPublicData = Field(default_factory=PlayerLinkPublicData)
    private_data: PlayerLinkPrivateData = Field(default_factory=PlayerLinkPrivateData)


class PlayerLinkDetailsList(SteamModel):
    """Body of ``CPlayer_GetPlayerLinkDetails_Response``."""

    accounts: list[PlayerLinkDetails] = Field(default_factory=list)


class PlayerLinkDetailsResponse(SteamModel):
    """Response wrapper for IPlayerService/GetPlayerLinkDetails."""

    response: PlayerLinkDetailsList = Field(default_factory=PlayerLinkDetailsList)


# IPlayerService/GetProfileItemsEquipped
class ProfileItemColor(SteamModel):
    """A color a profile modifier sets (``ProfileItem.ProfileColor``)."""

    style_name: str = Field(default="", description='e.g. "backgroundgradient_left"')
    color: str = Field(default="", description='CSS color, e.g. "rgba(0, 0, 0, 1)"')


class ProfileItem(SteamModel):
    """A profile item: background, avatar frame, animated avatar, ... (``ProfileItem``).

    Image and movie fields are paths relative to the community image CDN
    (``https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/``
    in published clients). An item with an empty ``communityitemid`` means
    nothing is equipped in that slot.
    """

    communityitemid: str = Field(default="", description="Community item id (64-bit)")
    image_small: str = Field(default="", description="Small image path")
    image_large: str = Field(default="", description="Large image path")
    name: str = Field(default="", description="Item name")
    item_title: str = Field(default="", description="Item title")
    item_description: str = Field(default="", description="Item description")
    appid: int = Field(default=0, description="App the item belongs to")
    item_type: int = Field(default=0, description="Item type")
    item_class: int = Field(default=0, description="Item class (ECommunityItemClass)")
    movie_webm: str = Field(default="", description="WebM movie path")
    movie_mp4: str = Field(default="", description="MP4 movie path")
    movie_webm_small: str = Field(default="", description="Small WebM movie path")
    movie_mp4_small: str = Field(default="", description="Small MP4 movie path")
    equipped_flags: int = Field(default=0, description="Equipped flags bit field")
    profile_colors: list[ProfileItemColor] = Field(
        default_factory=list, description="Colors of a profile modifier"
    )
    tiled: bool = Field(default=False, description="Whether the background is tiled")


class ProfileItemsEquipped(SteamModel):
    """The profile items a user has equipped.

    ``CPlayer_GetProfileItemsEquipped_Response``. A slot with nothing
    equipped is an empty ``ProfileItem``.
    """

    profile_background: ProfileItem = Field(default_factory=ProfileItem)
    mini_profile_background: ProfileItem = Field(default_factory=ProfileItem)
    avatar_frame: ProfileItem = Field(default_factory=ProfileItem)
    animated_avatar: ProfileItem = Field(default_factory=ProfileItem)
    profile_modifier: ProfileItem = Field(default_factory=ProfileItem)
    steam_deck_keyboard_skin: ProfileItem = Field(default_factory=ProfileItem)


class ProfileItemsEquippedResponse(SteamModel):
    """Response wrapper for IPlayerService/GetProfileItemsEquipped."""

    response: ProfileItemsEquipped = Field(default_factory=ProfileItemsEquipped)


# IPlayerService/GetSteamLevelDistribution
class SteamLevelDistribution(SteamModel):
    """Body of ``CPlayer_GetSteamLevelDistribution_Response``."""

    player_level_percentile: float = Field(
        default=0.0, description="Percentile of the level among Steam users (0-100)"
    )


class SteamLevelDistributionResponse(SteamModel):
    """Response wrapper for IPlayerService/GetSteamLevelDistribution."""

    response: SteamLevelDistribution = Field(default_factory=SteamLevelDistribution)


# ISteamUser/GetUserGroupList: an older method with plain JSON, not protobuf.
class UserGroup(SteamModel):
    """A Steam group a user is a member of."""

    gid: str = Field(description="Account id of the group (32-bit), as a string")


class UserGroupList(SteamModel):
    """``response`` of ISteamUser/GetUserGroupList."""

    success: bool = Field(default=False, description="Whether Steam found the groups")
    groups: list[UserGroup] = Field(default_factory=list)
    error: str = Field(default="", description="Reason for a failure, if given")
    message: str = Field(default="", description="Reason for a failure, if given")


class UserGroupListResponse(SteamModel):
    """Response wrapper for ISteamUser/GetUserGroupList."""

    response: UserGroupList
