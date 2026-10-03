"""Steam Family API endpoints (IFamilyGroupsService)."""

from typing import Any

from ..models.family import (
    FamilyGroupStatusResponse,
    PlaytimeSummaryResponse,
    SharedLibraryAppsResponse,
)
from ..steamid import SteamIDLike, validate_steam_id
from .base import BaseAPI

_INTERFACE = "IFamilyGroupsService"

# Family group ids, invite ids, nonces and cart ids are 64-bit; pass them as
# int or as the string Steam returns.
FamilyID = int | str


def _steamid(value: SteamIDLike | None) -> str | None:
    """Validate an optional Steam ID input."""
    return None if value is None else validate_steam_id(value)


class FamilyAPI(BaseAPI):
    """Steam Family API endpoints.

    Every method calls IFamilyGroupsService with the user's access token. A
    method returning a raw body returns Steam's JSON, ``{"response": {...}}``.
    """

    async def _family(
        self,
        method: str,
        operation: str,
        inputs: dict[str, Any],
        http_method: str = "POST",
    ) -> dict[str, Any]:
        """Call an IFamilyGroupsService method and return the raw body."""
        return await self._call_service(
            _INTERFACE,
            method,
            operation,
            inputs,
            http_method=http_method,
            auth_type="access_token",
        )

    async def cancel_family_group_invite(
        self,
        family_groupid: FamilyID | None = None,
        steamid_to_cancel: SteamIDLike | None = None,
    ) -> dict[str, Any]:
        """Cancel a pending invite to the specified family group.

        Args:
            family_groupid: Requester's family group id
            steamid_to_cancel: Steam ID of the user whose invite is cancelled

        Returns:
            The raw response body
        """
        return await self._family(
            "CancelFamilyGroupInvite",
            "cancel family group invite",
            {
                "family_groupid": family_groupid,
                "steamid_to_cancel": _steamid(steamid_to_cancel),
            },
        )

    async def clear_cooldown_skip(
        self, steamid: SteamIDLike | None = None, invite_id: FamilyID | None = None
    ) -> dict[str, Any]:
        """Clear the cooldown skip of a user.

        **Steam Support only:** Steam rejects ordinary user access tokens.

        Args:
            steamid: Steam ID of the user whose cooldown skip is cleared
            invite_id: Invitation id

        Returns:
            The raw response body
        """
        return await self._family(
            "ClearCooldownSkip",
            "clear cooldown skip",
            {"steamid": _steamid(steamid), "invite_id": invite_id},
        )

    async def confirm_invite_to_family_group(
        self,
        family_groupid: FamilyID | None = None,
        invite_id: FamilyID | None = None,
        nonce: FamilyID | None = None,
    ) -> dict[str, Any]:
        """Confirm an invitation sent with *invite_to_family_group*.

        Steam asks for this second step after the inviter confirmed the
        invitation (e.g. by email or the mobile app).

        Args:
            family_groupid: Family group id
            invite_id: Invitation id
            nonce: Nonce from the confirmation

        Returns:
            The raw response body
        """
        return await self._family(
            "ConfirmInviteToFamilyGroup",
            "confirm invite to family group",
            {"family_groupid": family_groupid, "invite_id": invite_id, "nonce": nonce},
        )

    async def confirm_join_family_group(
        self,
        family_groupid: FamilyID | None = None,
        invite_id: FamilyID | None = None,
        nonce: FamilyID | None = None,
    ) -> dict[str, Any]:
        """Confirm joining a family group (after *join_family_group*).

        Args:
            family_groupid: Family group id
            invite_id: Invitation id
            nonce: Nonce from the confirmation

        Returns:
            The raw response body
        """
        return await self._family(
            "ConfirmJoinFamilyGroup",
            "confirm join family group",
            {"family_groupid": family_groupid, "invite_id": invite_id, "nonce": nonce},
        )

    async def create_family_group(
        self, name: str, steamid: SteamIDLike | None = None
    ) -> dict[str, Any]:
        """Create a new family group.

        Args:
            name: Name of the new family group
            steamid: (Steam Support only) User to create this family group for
                and add to the group

        Returns:
            The raw response body (``family_groupid``,
            ``cooldown_skip_granted``)
        """
        return await self._family(
            "CreateFamilyGroup",
            "create family group",
            {"name": name, "steamid": _steamid(steamid)},
        )

    async def delete_family_group(
        self, family_groupid: FamilyID | None = None
    ) -> dict[str, Any]:
        """Delete the specified family group.

        Args:
            family_groupid: Family group id

        Returns:
            The raw response body
        """
        return await self._family(
            "DeleteFamilyGroup",
            "delete family group",
            {"family_groupid": family_groupid},
        )

    async def force_accept_invite(
        self,
        family_groupid: FamilyID | None = None,
        steamid: SteamIDLike | None = None,
    ) -> dict[str, Any]:
        """Accept a family group invite on behalf of a user.

        **Steam Support only:** Steam rejects ordinary user access tokens.

        Args:
            family_groupid: Family group id
            steamid: Steam ID of the user whose invite is accepted

        Returns:
            The raw response body
        """
        return await self._family(
            "ForceAcceptInvite",
            "force accept invite",
            {"family_groupid": family_groupid, "steamid": _steamid(steamid)},
        )

    async def get_change_log(
        self, family_groupid: FamilyID | None = None
    ) -> dict[str, Any]:
        """Return a log of changes made to this family group.

        Args:
            family_groupid: Family group id

        Returns:
            The raw response body (``changes``)
        """
        return await self._family(
            "GetChangeLog", "get change log", {"family_groupid": family_groupid}
        )

    async def get_family_group(
        self, family_groupid: FamilyID, send_running_apps: bool = False
    ) -> dict[str, Any]:
        """Get family group information.

        Use *get_family_group_for_user* to get the current user's family group.

        Args:
            family_groupid: Family group id
            send_running_apps: Whether to include running app information

        Returns:
            The raw response body

        Raises:
            AuthenticationError: If access token is not provided
            SteamAPIError: On API errors
        """
        return await self._family(
            "GetFamilyGroup",
            "get family group",
            {
                "family_groupid": family_groupid,
                "send_running_apps": send_running_apps or None,
            },
            http_method="GET",
        )

    async def get_family_group_for_user(
        self,
        steamid: SteamIDLike | None = None,
        include_family_group_response: bool = False,
    ) -> FamilyGroupStatusResponse:
        """Get the family group of a user.

        **Only SUPPORT/ADMIN accounts can specify steamid.**
        By default, the method returns the family group of the currently
        authorized user.

        Args:
            steamid: Steam ID of user
            include_family_group_response: Also return the full family group
                (as from *get_family_group*) in ``family_group``

        Returns:
            Family group data for the user

        Raises:
            AuthenticationError: If access token is not provided
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        return await self._call_service(
            _INTERFACE,
            "GetFamilyGroupForUser",
            "get family group for user",
            {
                "steamid": _steamid(steamid),
                "include_family_group_response": include_family_group_response or None,
            },
            model=FamilyGroupStatusResponse,
            auth_type="access_token",
        )

    async def get_invite_check_results(
        self,
        family_groupid: FamilyID | None = None,
        steamid: SteamIDLike | None = None,
    ) -> dict[str, Any]:
        """Get the results of Steam's checks on an invitation.

        Args:
            family_groupid: Requester's family group id
            steamid: Steam ID of the invited user

        Returns:
            The raw response body (e.g. ``wallet_country_matches``,
            ``ip_match``)
        """
        return await self._family(
            "GetInviteCheckResults",
            "get invite check results",
            {"family_groupid": family_groupid, "steamid": _steamid(steamid)},
            http_method="GET",
        )

    async def get_playtime_summary(
        self, family_groupid: FamilyID
    ) -> PlaytimeSummaryResponse:
        """Get the playtime in every shared-library app for the whole family.

        Args:
            family_groupid: Family group id

        Returns:
            Playtime summary data

        Raises:
            AuthenticationError: If access token is not provided
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        return await self._call_service(
            _INTERFACE,
            "GetPlaytimeSummary",
            "get playtime summary",
            {"family_groupid": family_groupid},
            model=PlaytimeSummaryResponse,
            http_method="POST",
            auth_type="access_token",
        )

    async def get_preferred_lenders(
        self, family_groupid: FamilyID | None = None
    ) -> dict[str, Any]:
        """Get the members' preferred lenders, per app.

        Args:
            family_groupid: Family group id

        Returns:
            The raw response body (``members``)
        """
        return await self._family(
            "GetPreferredLenders",
            "get preferred lenders",
            {"family_groupid": family_groupid},
            http_method="GET",
        )

    async def get_purchase_requests(
        self,
        request_ids: list[FamilyID] | None = None,
        family_groupid: FamilyID | None = None,
        include_completed: bool = False,
        rt_include_completed_since: int | None = None,
    ) -> dict[str, Any]:
        """Get pending purchase requests for the family.

        Args:
            request_ids: Only return these requests (all requests if omitted)
            family_groupid: Requester's family group id
            include_completed: Also return completed requests (may no longer
                be honored by Steam; use *rt_include_completed_since*)
            rt_include_completed_since: Return requests completed since this
                Unix time

        Returns:
            The raw response body (``requests``)
        """
        return await self._family(
            "GetPurchaseRequests",
            "get purchase requests",
            {
                "request_ids": request_ids,
                "family_groupid": family_groupid,
                "include_completed": include_completed,
                "rt_include_completed_since": rt_include_completed_since,
            },
            http_method="GET",
        )

    async def get_shared_library_apps(
        self,
        family_groupid: FamilyID,
        include_own: bool = False,
        include_excluded: bool = False,
        include_free: bool = False,
        include_non_games: bool = False,
        language: str = "english",
        max_apps: int | None = None,
        steamid: SteamIDLike | None = None,
    ) -> SharedLibraryAppsResponse:
        """Return a list of apps available from other members.

        Args:
            family_groupid: Requester's family group id
            include_own: Include apps owned by the user
            include_excluded: Include excluded apps
            include_free: Include free to play apps
            include_non_games: Include non-game apps
            language: Language for app names
            max_apps: Maximum number of apps to return
            steamid: Steam ID of user to query

        Returns:
            Shared library apps data

        Raises:
            AuthenticationError: If access token is not provided
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        return await self._call_service(
            _INTERFACE,
            "GetSharedLibraryApps",
            "get shared library apps",
            {
                "family_groupid": family_groupid,
                "include_own": include_own,
                "include_excluded": include_excluded,
                "include_free": include_free,
                "include_non_games": include_non_games,
                "language": language,
                "max_apps": max_apps,
                "steamid": _steamid(steamid),
            },
            model=SharedLibraryAppsResponse,
            auth_type="access_token",
        )

    async def get_users_sharing_device(
        self,
        family_groupid: FamilyID | None = None,
        client_session_id: int | None = None,
        client_instance_id: int | None = None,
    ) -> dict[str, Any]:
        """Get the lenders or borrowers sharing a device with the user.

        Args:
            family_groupid: Requester's family group id
            client_session_id: Session id of the Steam client
            client_instance_id: Instance id of the Steam client

        Returns:
            The raw response body (``users``)
        """
        return await self._family(
            "GetUsersSharingDevice",
            "get users sharing device",
            {
                "family_groupid": family_groupid,
                "client_session_id": client_session_id,
                "client_instance_id": client_instance_id,
            },
            http_method="GET",
        )

    async def invite_to_family_group(
        self,
        family_groupid: FamilyID | None = None,
        receiver_steamid: SteamIDLike | None = None,
        receiver_role: int | None = None,
    ) -> dict[str, Any]:
        """Invite an account to a family group.

        Args:
            family_groupid: Requester's family group id
            receiver_steamid: Steam ID of the account to invite
            receiver_role: An ``EFamilyGroupRole``: 1 Adult, 2 Child

        Returns:
            The raw response body (``invite_id``, ``two_factor_method``)
        """
        return await self._family(
            "InviteToFamilyGroup",
            "invite to family group",
            {
                "family_groupid": family_groupid,
                "receiver_steamid": _steamid(receiver_steamid),
                "receiver_role": receiver_role,
            },
        )

    async def join_family_group(
        self, family_groupid: FamilyID | None = None, nonce: FamilyID | None = None
    ) -> dict[str, Any]:
        """Join the specified family group.

        Args:
            family_groupid: Family group id
            nonce: Nonce from the invitation

        Returns:
            The raw response body (``two_factor_method``)
        """
        return await self._family(
            "JoinFamilyGroup",
            "join family group",
            {"family_groupid": family_groupid, "nonce": nonce},
        )

    async def modify_family_group_details(
        self, family_groupid: FamilyID | None = None, name: str | None = None
    ) -> dict[str, Any]:
        """Modify the details of the specified family group.

        Args:
            family_groupid: Requester's family group id
            name: New family group name (unchanged when None)

        Returns:
            The raw response body
        """
        return await self._family(
            "ModifyFamilyGroupDetails",
            "modify family group details",
            {"family_groupid": family_groupid, "name": name},
        )

    async def remove_from_family_group(
        self,
        family_groupid: FamilyID | None = None,
        steamid_to_remove: SteamIDLike | None = None,
    ) -> dict[str, Any]:
        """Remove the specified account from the specified family group.

        Args:
            family_groupid: Requester's family group id
            steamid_to_remove: Steam ID of the member to remove

        Returns:
            The raw response body
        """
        return await self._family(
            "RemoveFromFamilyGroup",
            "remove from family group",
            {
                "family_groupid": family_groupid,
                "steamid_to_remove": _steamid(steamid_to_remove),
            },
        )

    async def request_purchase(
        self,
        family_groupid: FamilyID | None = None,
        gid_shopping_cart: FamilyID | None = None,
        store_country_code: str | None = None,
        use_account_cart: bool = False,
    ) -> dict[str, Any]:
        """Ask the family's adults to buy the specified cart.

        Args:
            family_groupid: Requester's family group id
            gid_shopping_cart: Shopping cart id, sent as ``gidshoppingcart``
            store_country_code: Store country code, e.g. ``"US"``
            use_account_cart: Request the account's cart instead

        Returns:
            The raw response body (``gidshoppingcart``, ``request_id``)
        """
        return await self._family(
            "RequestPurchase",
            "request purchase",
            {
                "family_groupid": family_groupid,
                "gidshoppingcart": gid_shopping_cart,
                "store_country_code": store_country_code,
                "use_account_cart": use_account_cart or None,
            },
        )

    async def resend_invitation_to_family_group(
        self,
        family_groupid: FamilyID | None = None,
        steamid: SteamIDLike | None = None,
    ) -> dict[str, Any]:
        """Resend a pending invitation to the specified family group.

        Args:
            family_groupid: Requester's family group id
            steamid: Steam ID of the invited user

        Returns:
            The raw response body
        """
        return await self._family(
            "ResendInvitationToFamilyGroup",
            "resend invitation to family group",
            {"family_groupid": family_groupid, "steamid": _steamid(steamid)},
        )

    async def respond_to_requested_purchase(
        self,
        family_groupid: FamilyID | None = None,
        purchase_requester_steamid: SteamIDLike | None = None,
        action: int | None = None,
        request_id: FamilyID | None = None,
    ) -> dict[str, Any]:
        """Respond to a purchase request from a family member.

        Args:
            family_groupid: Requester's family group id
            purchase_requester_steamid: Steam ID of the member who asked
            action: An ``EPurchaseRequestAction``: 1 Decline, 2 Purchased,
                3 Abandoned, 4 Cancel
            request_id: Purchase request id

        Returns:
            The raw response body
        """
        return await self._family(
            "RespondToRequestedPurchase",
            "respond to requested purchase",
            {
                "family_groupid": family_groupid,
                "purchase_requester_steamid": _steamid(purchase_requester_steamid),
                "action": action,
                "request_id": request_id,
            },
        )

    async def rollback_family_group(
        self, family_groupid: FamilyID | None = None, rtime32_target: int | None = None
    ) -> dict[str, Any]:
        """Roll the family group back to its state at a point in time.

        **Steam Support only:** Steam rejects ordinary user access tokens.

        Args:
            family_groupid: Family group id
            rtime32_target: Unix time to roll back to

        Returns:
            The raw response body
        """
        return await self._family(
            "RollbackFamilyGroup",
            "rollback family group",
            {"family_groupid": family_groupid, "rtime32_target": rtime32_target},
        )

    async def set_family_cooldown_overrides(
        self, family_groupid: FamilyID | None = None, cooldown_count: int | None = None
    ) -> dict[str, Any]:
        """Set how many times the family's join cooldown is skipped.

        **Steam Support only:** Steam rejects ordinary user access tokens.

        Args:
            family_groupid: Requester's family group id
            cooldown_count: Number of joins that skip the cooldown

        Returns:
            The raw response body
        """
        return await self._family(
            "SetFamilyCooldownOverrides",
            "set family cooldown overrides",
            {"family_groupid": family_groupid, "cooldown_count": cooldown_count},
        )

    async def set_preferred_lender(
        self,
        family_groupid: FamilyID | None = None,
        appid: int | None = None,
        lender_steamid: SteamIDLike | None = None,
    ) -> dict[str, Any]:
        """Choose which member's copy of an app the user borrows.

        Args:
            family_groupid: Requester's family group id
            appid: App id
            lender_steamid: Steam ID of the member to borrow the app from

        Returns:
            The raw response body
        """
        return await self._family(
            "SetPreferredLender",
            "set preferred lender",
            {
                "family_groupid": family_groupid,
                "appid": appid,
                "lender_steamid": _steamid(lender_steamid),
            },
        )

    async def undelete_family_group(
        self, family_groupid: FamilyID | None = None
    ) -> dict[str, Any]:
        """Restore a deleted family group.

        **Steam Support only:** Steam rejects ordinary user access tokens.

        Args:
            family_groupid: Family group id

        Returns:
            The raw response body
        """
        return await self._family(
            "UndeleteFamilyGroup",
            "undelete family group",
            {"family_groupid": family_groupid},
        )
