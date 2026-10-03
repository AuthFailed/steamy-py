"""Models for IFamilyGroupsService (Steam Families) responses.

Steam service methods serialize protobuf messages to JSON and leave out
every field at its default value (false, 0, "" or an empty list), so every
field here has a default. 64-bit ids (family group ids, Steam IDs, invite
ids) arrive as strings and are kept as strings.
"""

from enum import IntEnum

from pydantic import Field

from .base import SteamModel


class EFamilyGroupRole(IntEnum):
    """Role of a member in a family group."""

    NONE = 0
    ADULT = 1
    CHILD = 2
    MAX = 3


class EProtoAppType(IntEnum):
    """Type of an app (``app_type`` of a shared library app)."""

    INVALID = 0
    GAME = 1
    APPLICATION = 2
    TOOL = 4
    DEMO = 8
    DEPRECATED = 16
    DLC = 32
    GUIDE = 64
    DRIVER = 128
    CONFIG = 256
    HARDWARE = 512
    FRANCHISE = 1024
    VIDEO = 2048
    PLUGIN = 4096
    MUSIC = 8192
    SERIES = 16384
    COMIC = 32768
    BETA = 65536
    SHORTCUT = 1073741824
    DEPOT_ONLY = -2147483648


class EPurchaseRequestAction(IntEnum):
    """Response to a family member's purchase request."""

    NONE = 0
    DECLINE = 1
    PURCHASED = 2
    ABANDONED = 3
    CANCEL = 4


class MembershipHistoryEntry(SteamModel):
    family_groupid: str = Field("", description="Steam family group id")
    rtime_joined: int = Field(0, description="Time of joining this family group")
    rtime_left: int = Field(
        0, description="Time of leaving this family group (0 if still a member)"
    )
    role: int = Field(0, description="Role in this family group (EFamilyGroupRole)")
    participated: bool = Field(
        False, description="Whether the user took part in this family group"
    )


class FamilyGroupPendingInviteForUser(SteamModel):
    """An invitation the user has received to join a family group."""

    family_groupid: str = Field("", description="Inviting family group id")
    role: int = Field(0, description="Role the user is invited as")
    inviter_steamid: str = Field("", description="Steam ID of the inviter")
    awaiting_2fa: bool = Field(
        False, description="Whether the invite awaits two-factor confirmation"
    )
    invite_id: str = Field("", description="Invitation id")


class FamilyGroupMember(SteamModel):
    steamid: str = Field("", description="Steam ID of the member")
    role: int = Field(0, description="Role of the member")
    time_joined: int = Field(0, description="Time the member joined")
    cooldown_seconds_remaining: int = Field(
        0, description="Seconds until the member may join another family group"
    )


class FamilyGroupPendingInvite(SteamModel):
    steamid: str = Field("", description="Steam ID of the invited user")
    role: int = Field(0, description="Role the user is invited as")


class FamilyGroupFormerMember(SteamModel):
    steamid: str = Field("", description="Steam ID of the former member")


class FamilyGroup(SteamModel):
    """A family group, as returned by GetFamilyGroup."""

    name: str = Field("", description="Family group name")
    members: list[FamilyGroupMember] = Field(default_factory=list)
    pending_invites: list[FamilyGroupPendingInvite] = Field(default_factory=list)
    free_spots: int = Field(0, description="Number of free member slots")
    country: str = Field("", description="Country of the family group")
    slot_cooldown_remaining_seconds: int = Field(
        0, description="Seconds until a freed slot can be filled"
    )
    former_members: list[FamilyGroupFormerMember] = Field(default_factory=list)
    slot_cooldown_overrides: int = Field(
        0, description="Number of slot cooldowns that will be skipped"
    )


class FamilyGroupStatus(SteamModel):
    family_groupid: str = Field("", description="Steam family group id")
    is_not_member_of_any_group: bool = Field(
        False, description="True if the user is not in any family group"
    )
    latest_time_joined: int = Field(
        0, description="Time of joining the current family group"
    )
    latest_joined_family_groupid: str = Field(
        "", description="Latest joined family group id of user"
    )
    pending_group_invites: list[FamilyGroupPendingInviteForUser] = Field(
        default_factory=list
    )
    role: int = Field(0, description="Role of user in current family group")
    cooldown_seconds_remaining: int = Field(
        0, description="Cooldown until next available family group change"
    )
    family_group: FamilyGroup | None = Field(
        None,
        description="The full family group, when include_family_group_response "
        "was requested",
    )
    can_undelete_last_joined_family: bool = Field(
        False, description="Whether the last joined family group can be restored"
    )
    membership_history: list[MembershipHistoryEntry] = Field(default_factory=list)


class FamilyGroupStatusResponse(SteamModel):
    response: FamilyGroupStatus = Field(default_factory=FamilyGroupStatus)


class PlaytimeEntry(SteamModel):
    steamid: str = ""
    appid: int = 0
    first_played: int = 0
    latest_played: int = 0
    seconds_played: int = 0


class PlaytimeSummary(SteamModel):
    entries: list[PlaytimeEntry] = Field(default_factory=list)
    entries_by_owner: list[PlaytimeEntry] = Field(default_factory=list)


class PlaytimeSummaryResponse(SteamModel):
    response: PlaytimeSummary = Field(default_factory=PlaytimeSummary)


class SharedLibraryApp(SteamModel):
    appid: int = Field(0, description="Steam app ID")
    owner_steamids: list[str] = Field(
        default_factory=list, description="Steam IDs of users who own this app"
    )
    name: str = Field("", description="App name")
    sort_as: str = Field("", description="Name to sort the app by")
    capsule_filename: str = Field(
        "", description="Filename for the app's capsule image"
    )
    img_icon_hash: str = Field("", description="Hash for the app's icon image")
    exclude_reason: int = Field(
        0, description="Reason for exclusion from family sharing (0 if not excluded)"
    )
    rt_time_acquired: int = Field(0, description="Unix timestamp when app was acquired")
    rt_last_played: int = Field(0, description="Unix timestamp of last play time")
    rt_playtime: int = Field(0, description="Total playtime in seconds")
    app_type: int = Field(0, description="Type of app (an EProtoAppType)")
    content_descriptors: list[int] = Field(
        default_factory=list, description="Content descriptor IDs"
    )


class SharedLibraryAppsData(SteamModel):
    apps: list[SharedLibraryApp] = Field(default_factory=list)
    owner_steamid: str = Field("", description="Steam ID of the requesting user")


class SharedLibraryAppsResponse(SteamModel):
    response: SharedLibraryAppsData = Field(default_factory=SharedLibraryAppsData)


class FamilyGroupResponse(SteamModel):
    """Response of GetFamilyGroup."""

    response: FamilyGroup = Field(default_factory=FamilyGroup)


class FamilyGroupChange(SteamModel):
    """One entry of a family group's change log."""

    timestamp: int = Field(0, description="Unix time of the change")
    actor_steamid: str = Field("", description="Steam ID of who made the change")
    type: int = Field(0, description="EFamilyGroupChangeLogType of the change")
    body: str = Field("", description="Details of the change (JSON text)")
    by_support: bool = Field(False, description="Whether Steam Support made it")


class FamilyGroupChangeLog(SteamModel):
    changes: list[FamilyGroupChange] = Field(default_factory=list)


class FamilyGroupChangeLogResponse(SteamModel):
    """Response of GetChangeLog."""

    response: FamilyGroupChangeLog = Field(default_factory=FamilyGroupChangeLog)


class PreferredLender(SteamModel):
    """A member and the apps they prefer to borrow from them."""

    steamid: str = Field("", description="Steam ID of the member")
    preferred_appids: list[int] = Field(default_factory=list)


class PreferredLenders(SteamModel):
    members: list[PreferredLender] = Field(default_factory=list)


class PreferredLendersResponse(SteamModel):
    """Response of GetPreferredLenders."""

    response: PreferredLenders = Field(default_factory=PreferredLenders)


class PurchaseRequest(SteamModel):
    """A family member's request to have a cart bought for them."""

    requester_steamid: str = Field("", description="Steam ID of the requester")
    gidshoppingcart: str = Field("", description="Shopping cart id")
    time_requested: int = Field(0, description="Unix time of the request")
    time_responded: int = Field(0, description="Unix time of the response")
    responder_steamid: str = Field("", description="Steam ID of the responder")
    response_action: int = Field(0, description="An EPurchaseRequestAction")
    is_completed: bool = Field(False, description="Whether the request is closed")
    request_id: str = Field("", description="Purchase request id")
    requested_packageids: list[int] = Field(default_factory=list)
    purchased_packageids: list[int] = Field(default_factory=list)
    requested_bundleids: list[int] = Field(default_factory=list)
    purchased_bundleids: list[int] = Field(default_factory=list)


class PurchaseRequests(SteamModel):
    requests: list[PurchaseRequest] = Field(default_factory=list)


class PurchaseRequestsResponse(SteamModel):
    """Response of GetPurchaseRequests."""

    response: PurchaseRequests = Field(default_factory=PurchaseRequests)


class InviteCheckResults(SteamModel):
    """Steam's checks on an invitation."""

    wallet_country_matches: bool = Field(
        False, description="Whether the wallet countries match"
    )
    ip_match: bool = Field(False, description="Whether the IP addresses match")
    join_restriction: int = Field(
        0, description="Why the invitee may not join (0 if they may)"
    )


class InviteCheckResultsResponse(SteamModel):
    """Response of GetInviteCheckResults."""

    response: InviteCheckResults = Field(default_factory=InviteCheckResults)


class UsersSharingDevice(SteamModel):
    users: list[str] = Field(default_factory=list, description="Steam IDs of the users")


class UsersSharingDeviceResponse(SteamModel):
    """Response of GetUsersSharingDevice."""

    response: UsersSharingDevice = Field(default_factory=UsersSharingDevice)
