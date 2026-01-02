"""Steam Family API endpoints."""

import logging
from typing import Optional

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
            steamid_to_cancel:

        Returns:

        """

    async def clear_cooldown_skip(
        self, steamid: int | None = None, invite_id: int | None = None
    ):
        """

        Args:
            steamid:
            invite_id:

        Returns:

        """

    async def confirm_invite_to_family_group(
        self,
        family_group_id: int | None = None,
        invite_id: int | None = None,
        nonce: int | None = None,
    ):
        """

        Args:
            family_group_id: Requester's family group id
            invite_id:
            nonce:

        Returns:

        """

    async def confirm_join_family_group(
        self,
        family_group_id: int | None = None,
        invite_id: int | None = None,
        nonce: int | None = None,
    ):
        """

        Args:
            family_group_id: Requester's family group id
            invite_id:
            nonce:

        Returns:

        """

    async def create_family_group(
        self, name: str | None = None, steamid: int | None = None
    ):
        """Creates a new family group.

        Args:
            name:
            steamid:

        Returns:

        """

    async def delete_family_group(
        self,
        family_group_id: int | None = None,
    ):
        """Delete the specified family group.

        Args:
            family_group_id: Requester's family group id

        Returns:

        """

    async def force_accept_invite(
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

    async def get_change_log(self, family_group_id: int | None = None):
        """Return a log of changes made to this family group.

        Args:
            family_group_id: Requester's family group id

        Returns:

        """
        ...

    async def get_family_group(
        self,
        family_group_id: int,
        send_running_apps: bool = False,
    ):
        """Get family group information.

        Args:
            family_group_id: Requester's family group id
            send_running_apps: Whether to include running app information

        Returns:
            Family group data

        Raises:
            AuthenticationError: If access token is not provided
            SteamAPIError: On API errors
        """
        params = {}
        if family_group_id is not None:
            params["family_group_id"] = str(family_group_id)
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
        self, steamid: Optional[str] = None
    ) -> FamilyGroupStatusResponse:
        """Gets the family group id for the authenticated user
         or a user specified by a support account.

        Args:
            steamid: Steam ID of user (for support/admin accounts only).
                    If omitted, gets family group for the authenticated user.

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
        self, family_group_id: int | None = None, steamid: int | None = None
    ):
        """

        Args:
            family_group_id: Requester's family group id
            steamid:

        Returns:

        """

    async def get_playtime_summary(
        self, family_group_id: Optional[int] = None
    ) -> SteamResponse:
        """Get the playtimes in all apps from the shared library
         for the whole family group.

        Args:
            family_group_id: Requester's family group id

        Returns:
            Playtime summary data

        Raises:
            AuthenticationError: If access token is not provided
            SteamAPIError: On API errors
        """
        params = {}
        if family_group_id is not None:
            params["family_groupid"] = str(family_group_id)

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
            family_group_id: Requester's family group id

        Returns:

        """

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

    async def join_family_group(
        self, family_group_id: int | None = None, nonce: int | None = None
    ):
        """Join the specified family group.

        Args:
            family_group_id: Requester's family group id
            nonce:

        Returns:

        """

    async def modify_family_group_details(
        self, family_group_id: int | None = None, name: str | None = None
    ):
        """Modify the details of the specified family group.

        Args:
            family_group_id: Requester's family group id
            name: If present, set the family name to the current value

        Returns:

        """

    async def remove_from_family_group(
        self, family_group_id: int | None = None, steamid_to_remove: int | None = None
    ):
        """Remove the specified account from the specified family group.

        Args:
            family_group_id: Requester's family group id
            steamid_to_remove:

        Returns:

        """

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

    async def rollback_family_group(
        self, family_group_id: int | None = None, rtime32_target: int | None = None
    ):
        """

        Args:
            family_group_id: Requester's family group id
            rtime32_target:

        Returns:

        """

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

    async def undelete_family_group(self, family_group_id: int | None = None):
        """

        Args:
            family_group_id: Requester's family group id

        Returns:

        """
