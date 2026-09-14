import asyncio
import logging

import discord
from discord.ext import commands

from config import PREFIX, TOKEN
from keep_alive import keep_alive

logging.basicConfig(level=logging.INFO)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, case_insensitive=True, help_command=None)

EXTENSIONS = ["welcome", "moderation", "warns", "notes"]


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s).")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")


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
