from pydantic import BaseModel, Field


class MembershipHistoryEntry(BaseModel):
    family_groupid: str = Field(..., description="Steam family group id")
    rtime_joined: int = Field(..., description="Time of joining this family group")
    rtime_left: int = Field(..., description="Time of leaving this family group")
    role: int = Field(..., description="Role of user in this family group")
    participated: bool = Field(..., description="")


class FamilyGroupStatus(BaseModel):
    family_groupid: str = Field(..., description="Steam family group id")
    is_not_member_of_any_group: bool = Field(
        ..., description="Is current user member of any group?"
    )
    latest_time_joined: int = Field(..., description="Time of joining this family grou")
    latest_joined_family_groupid: str = Field(
        ..., description="Latest joined family group id of user"
    )
    role: int = Field(..., description="Role of user in current family group")
    cooldown_seconds_remaining: int = Field(
        ..., description="Cooldown until next available family group change"
    )
    can_undelete_last_joined_family: bool = Field(..., description="")
    membership_history: list[MembershipHistoryEntry]


class FamilyGroupStatusResponse(BaseModel):
    response: FamilyGroupStatus

    def __getattr__(self, item):
        try:
            return getattr(self.response, item)
        except AttributeError:
            raise AttributeError(
                f"{self.__class__.__name__!r} object has no attribute {item!r}"
            )


class Entry(BaseModel):
    steamid: str
    appid: int
    first_played: int
    latest_played: int
    seconds_played: int


class ResponseData(BaseModel):
    entries: list[Entry]


class SteamResponse(BaseModel):
    response: ResponseData
