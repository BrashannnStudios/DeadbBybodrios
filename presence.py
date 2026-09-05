import discord
from discord.ext import commands, tasks

class Presence(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @tasks.loop(seconds=10)
    async def rotate_presence(self):
        activities = [
            discord.Activity(type=discord.ActivityType.watching, name="↪ Dead by bodrios"),
            discord.Activity(type=discord.ActivityType.watching, name="↪ Dev: Supskevv"),
        ]
        activity = activities[self.rotate_presence.current_loop % len(activities)]
        await self.bot.change_presence(activity=activity, status=discord.Status.online)

    @rotate_presence.before_loop
    async def before_presence(self):
        await self.bot.wait_until_ready()

    async def cog_load(self):
        self.rotate_presence.start()

    async def cog_unload(self):
        self.rotate_presence.cancel()


async def setup(bot):
    await bot.add_cog(Presence(bot))
