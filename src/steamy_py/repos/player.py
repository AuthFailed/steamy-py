"""Deprecated module: the player endpoints moved to ``steamy_py.repos.users``."""

from .users import UsersAPI

# ``PlayerAPI`` is the pre-2.0 name of ``UsersAPI``.
PlayerAPI = UsersAPI

__all__ = ["PlayerAPI"]
