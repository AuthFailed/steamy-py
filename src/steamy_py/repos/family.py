"""Steam Family API endpoints."""

import logging

from ..exceptions import AuthenticationError, SteamAPIError
from ..models.family import FamilyGroupStatusResponse, SteamResponse
from .base import BaseAPI

logger = logging.getLogger(__name__)


class FamilyAPI(BaseAPI):
    """Steam Family API endpoints.

    Endpoints for IFamilyGroupsService
    Note: These endpoints require access_token authentication, not api_key.
    """

    async def cancel_family_group_invite(
        self, family_group_id: int | None = None, steamid_to_cancel: int | None = None
    ):
        """Cancel a pending invite to the specified family group.

        Args:
            family_group_id: Requester's family group id
            steamid_to_cancel: Steamid of user for invite cancellation

        Returns:

        """
        params = {}
        if family_group_id:
            params["family_group_id"] = family_group_id
        if steamid_to_cancel:
            params["steamid_to_cancel"] = steamid_to_cancel

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
            params["steamid"] = steamid
        if invite_id:
            params["invite_id"] = invite_id

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
        family_group_id: int | None = None,
        invite_id: int | None = None,
        nonce: int | None = None,
    ):
        """

        Args:
            family_group_id: Family group id
            invite_id: Invitation id
            nonce:

        Returns:

        """
        params = {}
        if family_group_id:
            params["family_group_id"] = family_group_id
        if invite_id:
            params["invite_id"] = invite_id
        if nonce:
            params["nonce"] = nonce

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
        family_group_id: int | None = None,
        invite_id: int | None = None,
        nonce: int | None = None,
    ):
        """Confirm join of user to family group.

        Args:
            family_group_id: Family group id
            invite_id: Invitation id
            nonce:

        Returns:

        """
        params = {}
        if family_group_id:
            params["family_group_id"] = family_group_id
        if invite_id:
            params["invite_id"] = invite_id
        if nonce:
            params["nonce"] = nonce

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
            params["steamid"] = steamid

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
        family_group_id: int | None = None,
    ):
        """Delete the specified family group.

        Args:
            family_group_id: Family group id

        Returns:

        """
        params = {}
        if family_group_id:
            params["family_group_id"] = family_group_id

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
        family_group_id: int | None = None,
        steamid: int | None = None,
    ):
        """Accepts invite for family group.

        Args:
            family_group_id: Family group id
            steamid: Steamid of user to accept invite

        Returns:

        """
        params = {}
        if family_group_id:
            params["family_group_id"] = family_group_id
        if steamid:
            params["steamid"] = steamid

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

    async def get_change_log(self, family_group_id: int | None = None):
        """Return a log of changes made to this family group.

        **Not finished. Missing Unknown required routing parameter**

        Args:
            family_group_id: Family group id

        Returns:

        """
        params = {}
        if family_group_id:
            params["family_group_id"] = family_group_id

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
        family_group_id: int,
        send_running_apps: bool = False,
    ):
        """Get family group information.

        Use *get_family_group_for_user* to get info about user's current family group

        Args:
            family_group_id: Family group id
            send_running_apps: Whether to include running app information

        Returns:
            Family group data

        Raises:
            AuthenticationError: If access token is not provided
            SteamAPIError: On API errors
        """
        params = {}
        if family_group_id:
            params["family_group_id"] = family_group_id
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
        By default, the method receives the family group of the currently authorized user.

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
            params["steamid"] = steamid

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="GetFamilyGroupForUser",
                version="v1",
                params=params,
                auth_type="access_token",
            )
            print(response_data)
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
        self, family_group_id: int | None = None, steamid: int | None = None
    ):
        """

        Args:
            family_group_id: Requester's family group id
            steamid:

        Returns:

        """
        params = {}
        if family_group_id is not None:
            params["family_group_id"] = family_group_id
        if steamid is not None:
            params["steamid"] = steamid

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

    async def get_playtime_summary(self, family_group_id: int) -> SteamResponse:
        """Get the playtimes in all apps from the shared library
         for the whole family group.

        Args:
            family_group_id: Family group id

        Returns:
            Playtime summary data

        Raises:
            AuthenticationError: If access token is not provided
            SteamAPIError: On API errors
        """
        params = {}
        if family_group_id is not None:
            params["family_groupid"] = family_group_id

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

    async def get_preferred_lenders(self, family_group_id: int | None = None):
        """

        Args:
            family_group_id: Family group id

        Returns:

        """
        params = {}
        if family_group_id is not None:
            params["family_group_id"] = family_group_id

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
        family_group_id: int | None = None,
        include_completed: bool = False,
        rt_include_completed_since: int | None = None,
    ):
        """Get pending purchase requests for the family.

        Args:
            request_ids:
            family_group_id: Requester's family group id
            include_completed:
            rt_include_completed_since:

        Returns:

        """
        params = {}
        if request_ids is not None:
            params["request_ids"] = request_ids
        if family_group_id is not None:
            params["family_group_id"] = family_group_id
        if include_completed is not None:
            params["include_completed"] = include_completed
        if rt_include_completed_since is not None:
            params["rt_include_completed_since"] = rt_include_completed_since

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
        family_group_id: int | None = None,
        include_own: bool = False,
        include_excluded: bool = False,
        include_free: bool = False,
        include_non_games: bool = False,
        language: str = "english",
        max_apps: int | None = None,
        steamid: int | None = None,
    ):
        """Return a list of apps available from other members.

        Args:
            family_group_id: Requester's family group id
            include_own:
            include_excluded:
            include_free:
            include_non_games:
            language:
            max_apps:
            steamid:

        Returns:

        """
        params = {}
        if family_group_id is not None:
            params["family_group_id"] = family_group_id
        if include_own is not None:
            params["include_own"] = include_own
        if include_excluded is not None:
            params["include_excluded"] = include_excluded
        if include_free is not None:
            params["include_free"] = include_free
        if include_non_games is not None:
            params["include_non_games"] = include_non_games
        if language is not None:
            params["language"] = language
        if max_apps is not None:
            params["max_apps"] = max_apps
        if steamid is not None:
            params["steamid"] = steamid

        try:
            response_data = await self._request(
                interface="IFamilyGroupsService",
                method="GetSharedLibraryApps",
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
            logger.error(f"Error getting shared library apps: {e}")
            raise SteamAPIError(f"Failed to get shared library apps: {e}") from e

    async def get_users_sharing_device(
        self,
        family_group_id: int | None = None,
        client_session_id: int | None = None,
        client_instance_id: int | None = None,
    ):
        """Get lenders or borrowers sharing device with.

        Args:
            family_group_id: Requester's family group id
            client_session_id:
            client_instance_id:

        Returns:

        """
        params = {}
        if family_group_id is not None:
            params["family_group_id"] = family_group_id
        if client_session_id is not None:
            params["client_session_id"] = client_session_id
        if client_instance_id is not None:
            params["client_instance_id"] = client_instance_id

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
        family_group_id: int | None = None,
        receiver_steamid: int | None = None,
        receiver_role: int | None = None,
    ):
        """Invites an account to a family group.

        Args:
            family_group_id: Requester's family group id
            receiver_steamid:
            receiver_role: 0 - None, 1 - Adult, 2 - Child, 3 - MAX

        Returns:

        """
        params = {}
        if family_group_id is not None:
            params["family_group_id"] = family_group_id
        if receiver_steamid is not None:
            params["receiver_steamid"] = receiver_steamid
        if receiver_role is not None:
            params["receiver_role"] = receiver_role

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
        self, family_group_id: int | None = None, nonce: int | None = None
    ):
        """Join the specified family group.

        Args:
            family_group_id: Requester's family group id
            nonce:

        Returns:

        """
        params = {}
        if family_group_id is not None:
            params["family_group_id"] = family_group_id
        if nonce is not None:
            params["nonce"] = nonce

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
        self, family_group_id: int | None = None, name: str | None = None
    ):
        """Modify the details of the specified family group.

        Args:
            family_group_id: Requester's family group id
            name: If present, set the family name to the current value

        Returns:

        """
        params = {}
        if family_group_id is not None:
            params["family_group_id"] = family_group_id
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
        self, family_group_id: int | None = None, steamid_to_remove: int | None = None
    ):
        """Remove the specified account from the specified family group.

        Args:
            family_group_id: Requester's family group id
            steamid_to_remove:

        Returns:

        """
        params = {}
        if family_group_id is not None:
            params["family_group_id"] = family_group_id
        if steamid_to_remove is not None:
            params["steamid_to_remove"] = steamid_to_remove

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
        family_group_id: int | None = None,
        gid_shopping_card: int | None = None,
        store_country_code: str | None = None,
        use_account_cart: bool = False,
    ):
        """Request purchase of the specified cart.

        Args:
            family_group_id: Requester's family group id
            gid_shopping_card:
            store_country_code:
            use_account_cart:

        Returns:

        """
        params = {}
        if family_group_id is not None:
            params["family_group_id"] = family_group_id
        if gid_shopping_card is not None:
            params["gid_shopping_card"] = gid_shopping_card
        if store_country_code is not None:
            params["store_country_code"] = store_country_code
        if use_account_cart:
            params["use_account_cart"] = use_account_cart

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
        family_group_id: int | None = None,
        steamid: int | None = None,
    ):
        """

        Args:
            family_group_id: Requester's family group id
            steamid:

        Returns:

        """
        params = {}
        if family_group_id is not None:
            params["family_group_id"] = family_group_id
        if steamid is not None:
            params["steamid"] = steamid

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
        family_group_id: int | None = None,
        purchase_requester_steamid: int | None = None,
        action: int | None = None,
        request_id: int | None = None,
    ):
        """

        Args:
            family_group_id: Requester's family group id
            purchase_requester_steamid:
            action:
            request_id:

        Returns:

        """
        params = {}
        if family_group_id is not None:
            params["family_group_id"] = family_group_id
        if purchase_requester_steamid is not None:
            params["purchase_requester_steamid"] = purchase_requester_steamid
        if action is not None:
            params["action"] = action
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
        self, family_group_id: int | None = None, rtime32_target: int | None = None
    ):
        """

        Args:
            family_group_id: Requester's family group id
            rtime32_target:

        Returns:

        """
        params = {}
        if family_group_id is not None:
            params["family_group_id"] = family_group_id
        if rtime32_target is not None:
            params["rtime32_target"] = rtime32_target

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
        self, family_group_id: int | None = None, cooldown_count: int | None = None
    ):
        """Set the number of times a family group's cooldown time
         should be ignored for joins.

        Args:
            family_group_id: Requester's family group id
            cooldown_count:

        Returns:

        """
        params = {}
        if family_group_id is not None:
            params["family_group_id"] = family_group_id
        if cooldown_count is not None:
            params["cooldown_count"] = cooldown_count

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
        family_group_id: int | None = None,
        appid: int | None = None,
        lender_steamid: int | None = None,
    ):
        """

        Args:
            family_group_id: Requester's family group id
            appid:
            lender_steamid:

        Returns:

        """
        params = {}
        if family_group_id is not None:
            params["family_group_id"] = family_group_id
        if appid is not None:
            params["appid"] = appid
        if lender_steamid is not None:
            params["lender_steamid"] = lender_steamid

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

    async def undelete_family_group(self, family_group_id: int | None = None):
        """

        Args:
            family_group_id: Family group id

        Returns:

        """
        params = {}
        if family_group_id is not None:
            params["family_group_id"] = family_group_id

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
