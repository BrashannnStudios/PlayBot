import asyncio
import itertools
import logging

import discord
from discord.ext import commands, tasks

from config import PREFIX, TOKEN
from keep_alive import keep_alive

logging.basicConfig(level=logging.INFO)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, case_insensitive=True, help_command=None)

EXTENSIONS = ["welcome", "vacants", "moderation", "warns", "notes"]

PRESENCE_MESSAGES = itertools.cycle(["› Play big Studios", "› Dev: Supskevv!"])


@tasks.loop(seconds=10)
async def rotate_presence():
    text = next(PRESENCE_MESSAGES)
    await bot.change_presence(activity=discord.CustomActivity(name=text))


@rotate_presence.before_loop
async def before_rotate_presence():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s).")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")
    if not rotate_presence.is_running():
        rotate_presence.start()


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have permission to use this command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing argument: `{error.param.name}`.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("I couldn't find that member.")
    elif isinstance(error, commands.CommandNotFound):
        return
    else:
        await ctx.send("An unexpected error occurred while running that command.")
        raise error


async def main():
    async with bot:
        for ext in EXTENSIONS:
            await bot.load_extension(ext)
        await bot.start(TOKEN)


if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())
