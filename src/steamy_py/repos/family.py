"""Steam Family API endpoints."""

import logging

from ..exceptions import AuthenticationError, SteamAPIError
from ..models.family import (
    FamilyGroupStatusResponse,
    SharedLibraryAppsResponse,
    SteamResponse,
)
from .base import BaseAPI

logger = logging.getLogger(__name__)


class FamilyAPI(BaseAPI):
    """Steam Family API endpoints.

    Endpoints for IFamilyGroupsService
    Note: These endpoints require access_token authentication, not api_key.
    """

    async def cancel_family_group_invite(
        self, family_groupid: int | None = None, steamid_to_cancel: int | None = None
    ):
        """Cancel a pending invite to the specified family group.

        Args:
            family_groupid: Requester's family group id
            steamid_to_cancel: Steamid of user for invite cancellation

        Returns:

        """
        params = {}
        if family_groupid:
            params["family_groupid"] = str(family_groupid)
        if steamid_to_cancel:
            params["steamid_to_cancel"] = str(steamid_to_cancel)

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="CancelFamilyGroupInvite",
                version="v1",
                params=params,
                auth_type="access_token",
                http_method="POST",
            )
            return response_data
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error getting change log: {e}")
            raise SteamAPIError(f"Failed to get change log: {e}") from e

    async def clear_cooldown_skip(
        self, steamid: int | None = None, invite_id: int | None = None
    ):
        """Clear cooldown skip of user.

        Args:
            steamid: Steamid of user to clear cooldown skip
            invite_id: Invitation id

        Returns:

        """
        params = {}
        if steamid:
            params["steamid"] = str(steamid)
        if invite_id:
            params["invite_id"] = str(invite_id)

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="ClearCooldownSkip",
                version="v1",
                params=params,
                auth_type="access_token",
                http_method="POST",
            )
            return response_data
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error getting change log: {e}")
            raise SteamAPIError(f"Failed to get change log: {e}") from e

    async def confirm_invite_to_family_group(
        self,
        family_groupid: int | None = None,
        invite_id: int | None = None,
        nonce: int | None = None,
    ):
        """

        Args:
            family_groupid: Family group id
            invite_id: Invitation id
            nonce:

        Returns:

        """
        params = {}
        if family_groupid:
            params["family_groupid"] = str(family_groupid)
        if invite_id:
            params["invite_id"] = str(invite_id)
        if nonce:
            params["nonce"] = str(nonce)

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="ConfirmInviteToFamilyGroup",
                version="v1",
                params=params,
                auth_type="access_token",
                http_method="POST",
            )
            return response_data
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error getting change log: {e}")
            raise SteamAPIError(f"Failed to get change log: {e}") from e

    async def confirm_join_family_group(
        self,
        family_groupid: int | None = None,
        invite_id: int | None = None,
        nonce: int | None = None,
    ):
        """Confirm join of user to family group.

        Args:
            family_groupid: Family group id
            invite_id: Invitation id
            nonce:

        Returns:

        """
        params = {}
        if family_groupid:
            params["family_groupid"] = str(family_groupid)
        if invite_id:
            params["invite_id"] = str(invite_id)
        if nonce:
            params["nonce"] = str(nonce)

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="ConfirmJoinFamilyGroup",
                version="v1",
                params=params,
                auth_type="access_token",
                http_method="POST",
            )
            return response_data
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error getting change log: {e}")
            raise SteamAPIError(f"Failed to get change log: {e}") from e

    async def create_family_group(self, name: str, steamid: int | None = None):
        """Creates a new family group.

        Args:
            name: Name of new family group
            steamid: (Support only) User to create this family group for
             and add to the group.

        Returns:

        """
        params = {}
        if name:
            params["name"] = name
        if steamid:
            params["steamid"] = str(steamid)

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="CreateFamilyGroup",
                version="v1",
                params=params,
                auth_type="access_token",
                http_method="POST",
            )
            return response_data
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error getting change log: {e}")
            raise SteamAPIError(f"Failed to get change log: {e}") from e

    async def delete_family_group(
        self,
        family_groupid: int | None = None,
    ):
        """Delete the specified family group.

        Args:
            family_groupid: Family group id

        Returns:

        """
        params = {}
        if family_groupid:
            params["family_groupid"] = str(family_groupid)

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="DeleteFamilyGroup",
                version="v1",
                params=params,
                auth_type="access_token",
                http_method="POST",
            )
            return response_data
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error getting change log: {e}")
            raise SteamAPIError(f"Failed to get change log: {e}") from e

    async def force_accept_invite(
        self,
        family_groupid: int | None = None,
        steamid: int | None = None,
    ):
        """Accepts invite for family group.

        Args:
            family_groupid: Family group id
            steamid: Steamid of user to accept invite

        Returns:

        """
        params = {}
        if family_groupid:
            params["family_groupid"] = str(family_groupid)
        if steamid:
            params["steamid"] = str(steamid)

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="ForceAcceptInvite",
                version="v1",
                params=params,
                auth_type="access_token",
                http_method="POST",
            )
            return response_data
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error getting change log: {e}")
            raise SteamAPIError(f"Failed to get change log: {e}") from e

    async def get_change_log(self, family_groupid: int | None = None):
        """Return a log of changes made to this family group.

        **Not finished. Missing Unknown required routing parameter**

        Args:
            family_groupid: Family group id

        Returns:

        """
        params = {}
        if family_groupid:
            params["family_groupid"] = str(family_groupid)

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="GetChangeLog",
                version="v1",
                params=params,
                auth_type="access_token",
            )
            return response_data
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error getting change log: {e}")
            raise SteamAPIError(f"Failed to get change log: {e}") from e

    async def get_family_group(
        self,
        family_groupid: int,
        send_running_apps: bool = False,
    ):
        """Get family group information.

        Use *get_family_group_for_user* to get info about user's current family group

        Args:
            family_groupid: Family group id
            send_running_apps: Whether to include running app information

        Returns:
            Family group data

        Raises:
            AuthenticationError: If access token is not provided
            SteamAPIError: On API errors
        """
        params = {}
        if family_groupid:
            params["family_groupid"] = str(family_groupid)
        if send_running_apps:
            params["send_running_apps"] = "1"

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="GetFamilyGroup",
                version="v1",
                params=params,
                auth_type="access_token",
            )
            return response_data
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error getting family group: {e}")
            raise SteamAPIError(f"Failed to get family group: {e}") from e

    async def get_family_group_for_user(
        self, steamid: int | None = None
    ) -> FamilyGroupStatusResponse:
        """Gets the family group of user.

        **Only SUPPORT/ADMIN accounts can specify steamid.**
        By default, the method receives the family group of the currently
        authorized user.

        Args:
            steamid: Steam ID of user

        Returns:
            Family group data for the user

        Raises:
            AuthenticationError: If access token is not provided
            SteamAPIError: On API errors
        """
        params = {}
        if steamid is not None:
            params["steamid"] = str(steamid)

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="GetFamilyGroupForUser",
                version="v1",
                params=params,
                auth_type="access_token",
            )
            return FamilyGroupStatusResponse.model_validate(response_data)
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error getting family group for user: {e}")
            raise SteamAPIError(f"Failed to get family group for user: {e}") from e

    async def get_invite_check_results(
        self, family_groupid: int | None = None, steamid: int | None = None
    ):
        """

        Args:
            family_groupid: Requester's family group id
            steamid:

        Returns:

        """
        params = {}
        if family_groupid is not None:
            params["family_groupid"] = str(family_groupid)
        if steamid is not None:
            params["steamid"] = str(steamid)

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="GetInviteCheckResults",
                version="v1",
                params=params,
                auth_type="access_token",
            )
            return response_data
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error getting invite check results: {e}")
            raise SteamAPIError(f"Failed to get invite check results: {e}") from e

    async def get_playtime_summary(self, family_groupid: int) -> SteamResponse:
        """Get the playtimes in all apps from the shared library
         for the whole family group.

        Args:
            family_groupid: Family group id

        Returns:
            Playtime summary data

        Raises:
            AuthenticationError: If access token is not provided
            SteamAPIError: On API errors
        """
        params = {}
        if family_groupid is not None:
            params["family_groupid"] = family_groupid

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="GetPlaytimeSummary",
                version="v1",
                params=params,
                auth_type="access_token",
                http_method="POST",
            )
            return SteamResponse.model_validate(response_data)
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error getting playtime summary: {e}")
            raise SteamAPIError(f"Failed to get playtime summary: {e}") from e

    async def get_preferred_lenders(self, family_groupid: int | None = None):
        """

        Args:
            family_groupid: Family group id

        Returns:

        """
        params = {}
        if family_groupid is not None:
            params["family_groupid"] = str(family_groupid)

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="GetPreferredLenders",
                version="v1",
                params=params,
                auth_type="access_token",
            )
            return response_data
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error getting preferred lenders: {e}")
            raise SteamAPIError(f"Failed to get preferred lenders: {e}") from e

    async def get_purchase_requests(
        self,
        request_ids: list[int],
        family_groupid: int | None = None,
        include_completed: bool = False,
        rt_include_completed_since: int | None = None,
    ):
        """Get pending purchase requests for the family.

        Args:
            request_ids:
            family_groupid: Requester's family group id
            include_completed:
            rt_include_completed_since:

        Returns:

        """
        params = {}
        if request_ids is not None:
            params["request_ids"] = ",".join(str(req_id) for req_id in request_ids)
        if family_groupid is not None:
            params["family_groupid"] = str(family_groupid)
        if include_completed is not None:
            params["include_completed"] = int(include_completed)
        if rt_include_completed_since is not None:
            params["rt_include_completed_since"] = str(rt_include_completed_since)

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="GetPurchaseRequests",
                version="v1",
                params=params,
                auth_type="access_token",
            )
            return response_data
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error getting purchase requests: {e}")
            raise SteamAPIError(f"Failed to get purchase requests: {e}") from e

    async def get_shared_library_apps(
        self,
        family_groupid: int,
        include_own: bool = False,
        include_excluded: bool = False,
        include_free: bool = False,
        include_non_games: bool = False,
        language: str = "english",
        max_apps: int | None = None,
        steamid: int | None = None,
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
            SteamAPIError: On API errors
        """
        values = {
            "family_groupid": family_groupid,
            "include_own": include_own,
            "include_excluded": include_excluded,
            "include_free": include_free,
            "include_non_games": include_non_games,
            "language": language,
            "max_apps": max_apps,
            "steamid": steamid,
        }
        params = {
            name: int(value) if isinstance(value, bool) else str(value)
            for name, value in values.items()
            if value is not None
        }

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="GetSharedLibraryApps",
                version="v1",
                params=params,
                auth_type="access_token",
            )
            return SharedLibraryAppsResponse.model_validate(response_data)
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error getting shared library apps: {e}")
            raise SteamAPIError(f"Failed to get shared library apps: {e}") from e

    async def get_users_sharing_device(
        self,
        family_groupid: int | None = None,
        client_session_id: int | None = None,
        client_instance_id: int | None = None,
    ):
        """Get lenders or borrowers sharing device with.

        Args:
            family_groupid: Requester's family group id
            client_session_id:
            client_instance_id:

        Returns:

        """
        params = {}
        if family_groupid is not None:
            params["family_groupid"] = str(family_groupid)
        if client_session_id is not None:
            params["client_session_id"] = str(client_session_id)
        if client_instance_id is not None:
            params["client_instance_id"] = str(client_instance_id)

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="GetUsersSharingDevice",
                version="v1",
                params=params,
                auth_type="access_token",
            )
            return response_data
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error getting users sharing device: {e}")
            raise SteamAPIError(f"Failed to get users sharing device: {e}") from e

    async def invite_to_family_group(
        self,
        family_groupid: int | None = None,
        receiver_steamid: int | None = None,
        receiver_role: int | None = None,
    ):
        """Invites an account to a family group.

        Args:
            family_groupid: Requester's family group id
            receiver_steamid:
            receiver_role: 0 - None, 1 - Adult, 2 - Child, 3 - MAX

        Returns:

        """
        params = {}
        if family_groupid is not None:
            params["family_groupid"] = str(family_groupid)
        if receiver_steamid is not None:
            params["receiver_steamid"] = str(receiver_steamid)
        if receiver_role is not None:
            params["receiver_role"] = str(receiver_role)

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="InviteToFamilyGroup",
                version="v1",
                params=params,
                auth_type="access_token",
                http_method="POST",
            )
            return response_data
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error joining to family group: {e}")
            raise SteamAPIError(f"Failed to join to family group: {e}") from e

    async def join_family_group(
        self, family_groupid: int | None = None, nonce: int | None = None
    ):
        """Join the specified family group.

        Args:
            family_groupid: Requester's family group id
            nonce:

        Returns:

        """
        params = {}
        if family_groupid is not None:
            params["family_groupid"] = str(family_groupid)
        if nonce is not None:
            params["nonce"] = str(nonce)

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="JoinFamilyGroup",
                version="v1",
                params=params,
                auth_type="access_token",
                http_method="POST",
            )
            return response_data
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error getting invite to family group: {e}")
            raise SteamAPIError(f"Failed to get invite to family group: {e}") from e

    async def modify_family_group_details(
        self, family_groupid: int | None = None, name: str | None = None
    ):
        """Modify the details of the specified family group.

        Args:
            family_groupid: Requester's family group id
            name: If present, set the family name to the current value

        Returns:

        """
        params = {}
        if family_groupid is not None:
            params["family_groupid"] = str(family_groupid)
        if name is not None:
            params["name"] = name

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="ModifyFamilyGroupDetails",
                version="v1",
                params=params,
                auth_type="access_token",
                http_method="POST",
            )
            return response_data
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error to remove from family group: {e}")
            raise SteamAPIError(f"Failed to remove from family group: {e}") from e

    async def remove_from_family_group(
        self, family_groupid: int | None = None, steamid_to_remove: int | None = None
    ):
        """Remove the specified account from the specified family group.

        Args:
            family_groupid: Requester's family group id
            steamid_to_remove:

        Returns:

        """
        params = {}
        if family_groupid is not None:
            params["family_groupid"] = str(family_groupid)
        if steamid_to_remove is not None:
            params["steamid_to_remove"] = str(steamid_to_remove)

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="RemoveFromFamilyGroup",
                version="v1",
                params=params,
                auth_type="access_token",
                http_method="POST",
            )
            return response_data
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error to remove from family group: {e}")
            raise SteamAPIError(f"Failed to remove from family group: {e}") from e

    async def request_purchase(
        self,
        family_groupid: int | None = None,
        gid_shopping_card: int | None = None,
        store_country_code: str | None = None,
        use_account_cart: bool = False,
    ):
        """Request purchase of the specified cart.

        Args:
            family_groupid: Requester's family group id
            gid_shopping_card:
            store_country_code:
            use_account_cart:

        Returns:

        """
        params = {}
        if family_groupid is not None:
            params["family_groupid"] = str(family_groupid)
        if gid_shopping_card is not None:
            params["gid_shopping_card"] = str(gid_shopping_card)
        if store_country_code is not None:
            params["store_country_code"] = store_country_code
        if use_account_cart:
            params["use_account_cart"] = int(use_account_cart)

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="RequestPurchase",
                version="v1",
                params=params,
                auth_type="access_token",
                http_method="POST",
            )
            return response_data
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error to request purchase: {e}")
            raise SteamAPIError(f"Failed to request purchase: {e}") from e

    async def resend_invitation_to_family_group(
        self,
        family_groupid: int | None = None,
        steamid: int | None = None,
    ):
        """

        Args:
            family_groupid: Requester's family group id
            steamid:

        Returns:

        """
        params = {}
        if family_groupid is not None:
            params["family_groupid"] = str(family_groupid)
        if steamid is not None:
            params["steamid"] = str(steamid)

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="RespondToRequestedPurchase",
                version="v1",
                params=params,
                auth_type="access_token",
                http_method="POST",
            )
            return response_data
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error to resend invitation to family group: {e}")
            raise SteamAPIError(
                f"Failed to resend invitation to family group: {e}"
            ) from e

    async def respond_to_requested_purchase(
        self,
        family_groupid: int | None = None,
        purchase_requester_steamid: int | None = None,
        action: int | None = None,
        request_id: int | None = None,
    ):
        """

        Args:
            family_groupid: Requester's family group id
            purchase_requester_steamid:
            action:
            request_id:

        Returns:

        """
        params = {}
        if family_groupid is not None:
            params["family_groupid"] = str(family_groupid)
        if purchase_requester_steamid is not None:
            params["purchase_requester_steamid"] = str(purchase_requester_steamid)
        if action is not None:
            params["action"] = str(action)
        if request_id is not None:
            params["request_id"] = request_id

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="RespondToRequestedPurchase",
                version="v1",
                params=params,
                auth_type="access_token",
                http_method="POST",
            )
            return response_data
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error to response to requested purchase: {e}")
            raise SteamAPIError(f"Failed to response to requested purchase: {e}") from e

    async def rollback_family_group(
        self, family_groupid: int | None = None, rtime32_target: int | None = None
    ):
        """

        Args:
            family_groupid: Requester's family group id
            rtime32_target:

        Returns:

        """
        params = {}
        if family_groupid is not None:
            params["family_groupid"] = str(family_groupid)
        if rtime32_target is not None:
            params["rtime32_target"] = str(rtime32_target)

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="SetFamilyCooldownOverrides",
                version="v1",
                params=params,
                auth_type="access_token",
                http_method="POST",
            )
            return response_data
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error to rollback family group: {e}")
            raise SteamAPIError(f"Failed to rollback family group: {e}") from e

    async def set_family_cooldown_overrides(
        self, family_groupid: int | None = None, cooldown_count: int | None = None
    ):
        """Set the number of times a family group's cooldown time
         should be ignored for joins.

        Args:
            family_groupid: Requester's family group id
            cooldown_count:

        Returns:

        """
        params = {}
        if family_groupid is not None:
            params["family_groupid"] = str(family_groupid)
        if cooldown_count is not None:
            params["cooldown_count"] = str(cooldown_count)

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="SetFamilyCooldownOverrides",
                version="v1",
                params=params,
                auth_type="access_token",
                http_method="POST",
            )
            return response_data
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error to set family cooldown overrides: {e}")
            raise SteamAPIError(f"Failed to set family cooldown overrides: {e}") from e

    async def set_preferred_lender(
        self,
        family_groupid: int | None = None,
        appid: int | None = None,
        lender_steamid: int | None = None,
    ):
        """

        Args:
            family_groupid: Requester's family group id
            appid:
            lender_steamid:

        Returns:

        """
        params = {}
        if family_groupid is not None:
            params["family_groupid"] = str(family_groupid)
        if appid is not None:
            params["appid"] = str(appid)
        if lender_steamid is not None:
            params["lender_steamid"] = str(lender_steamid)

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="SetPreferredLender",
                version="v1",
                params=params,
                auth_type="access_token",
                http_method="POST",
            )
            return response_data
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error getting invite to family group: {e}")
            raise SteamAPIError(f"Failed to get invite to family group: {e}") from e

    async def undelete_family_group(self, family_groupid: int | None = None):
        """

        Args:
            family_groupid: Family group id

        Returns:

        """
        params = {}
        if family_groupid is not None:
            params["family_groupid"] = str(family_groupid)

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="UndeleteFamilyGroup",
                version="v1",
                params=params,
                auth_type="access_token",
                http_method="POST",
            )
            return response_data
        except ValueError as e:
            if "Access token is required" in str(e):
                raise AuthenticationError(
                    "Access token is required for Family API endpoints"
                ) from e
            raise
        except Exception as e:
            logger.error(f"Error to undelete family group: {e}")
            raise SteamAPIError(f"Failed to undelete family group: {e}") from e
