import asyncio

from steamy_py import Steam


async def main():
    """The example shows obtaining a family group of user, authorized by access_token of that user."""
    async with Steam(access_token="YOUR_ACCESS_TOKEN") as steam:
        family = await steam.family.get_family_group_for_user()

        print(family.response.family_groupid)
        # or (family.family_groupid)

        playtime = await steam.family.get_playtime_summary(
            family_groupid=family.response.family_groupid
        )
        for entry in playtime.response.entries:
            # or playtime.entries
            print(
                f"{entry.steamid}: {entry.appid} - {entry.latest_played} {entry.seconds_played}"
            )


if __name__ == "__main__":
    asyncio.run(main())
