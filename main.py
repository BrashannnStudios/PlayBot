import os
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
from database import db
from keep_alive import keep_alive
from datetime import datetime
import asyncio

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.moderation = True

bot = commands.Bot(
    command_prefix="?",
    intents=intents,
    case_insensitive=True,
    help_command=None
)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"Connected to {len(bot.guilds)} guilds")
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="Play Big Studios")
    )
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"Slash sync failed: {e}")
    if not check_tempbans.is_running():
        check_tempbans.start()

@tasks.loop(minutes=1)
async def check_tempbans():
    try:
        expired = await db.get_expired_tempbans()
        for ban in expired:
            guild = bot.get_guild(ban["guild_id"])
            if guild:
                try:
                    await guild.unban(
                        discord.Object(id=ban["user_id"]),
                        reason="Temporary ban expired"
                    )
                    print(f"Unbanned {ban['user_id']} from {guild.name}")
                except Exception as e:
                    print(f"Failed to unban {ban['user_id']}: {e}")
            await db.remove_tempban(ban["guild_id"], ban["user_id"])
    except Exception as e:
        print(f"Tempban check error: {e}")

@check_tempbans.before_loop
async def before_tempbans():
    await bot.wait_until_ready()

async def main():
    await db.connect()
    print("MongoDB connected")

    extensions = ["welcome", "vacants", "moderation"]
    for ext in extensions:
        try:
            await bot.load_extension(ext)
            print(f"Loaded extension: {ext}")
        except Exception as e:
            print(f"Failed to load {ext}: {e}")

    keep_alive()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("DISCORD_TOKEN environment variable is missing")
    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
