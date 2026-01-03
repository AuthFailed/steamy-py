import asyncio

from steamy_py import Steam


async def main():
    """The example shows obtaining a family group of user, authorized by access_token of that user."""
    async with Steam(access_token="YOUR_ACCESS_TOKEN") as steam:
        family = await steam.family.get_family_group_for_user()

        # print(family.response.family_groupid)

        family_test = await steam.family.get_family_group(
            family_group_id=family.response.family_groupid
        )
        print(family_test)


if __name__ == "__main__":
    asyncio.run(main())
