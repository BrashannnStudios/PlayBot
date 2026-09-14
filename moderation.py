import re
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks

from config import (
    COLOR_ERROR,
    COLOR_INFO,
    COLOR_SUCCESS,
    COLOR_WARNING,
    EMOJI_ACCEPT,
    EMOJI_CLOCK,
    EMOJI_DENIED,
    EMOJI_SEARCH,
    EMOJI_WARNING,
    FOOTER_TEXT,
)
from database import tempbans_collection

TIME_REGEX = re.compile(r"^(\d+)([smhdw])$")
TIME_UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days", "w": "weeks"}


def parse_duration(value: str) -> timedelta | None:
    match = TIME_REGEX.match(value.lower())
    if not match:
        return None
    amount, unit = match.groups()
    return timedelta(**{TIME_UNITS[unit]: int(amount)})


def base_embed(title: str, description: str, color: int) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=FOOTER_TEXT)
    embed.timestamp = datetime.now(timezone.utc)
    return embed


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_tempbans.start()

    def cog_unload(self):
        self.check_tempbans.cancel()

    # ---------- CHANNEL COMMANDS ----------

    @commands.command(name="lock")
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send(
            embed=base_embed(
                f"{EMOJI_DENIED} Channel Locked",
                f"{channel.mention} has been locked.",
                COLOR_ERROR,
            )
        )

    @commands.command(name="unlock")
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send(
            embed=base_embed(
                f"{EMOJI_ACCEPT} Channel Unlocked",
                f"{channel.mention} has been unlocked.",
                COLOR_SUCCESS,
            )
        )

    @commands.command(name="slowmode")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx: commands.Context, channel: discord.TextChannel, time: int):
        await channel.edit(slowmode_delay=time)
        await ctx.send(
            embed=base_embed(
                f"{EMOJI_CLOCK} Slowmode Updated",
                f"Slowmode in {channel.mention} set to **{time}** seconds.",
                COLOR_INFO,
            )
        )

    # ---------- USER INFO / DM ----------

    @commands.command(name="userinfo")
    async def userinfo(self, ctx: commands.Context, user: discord.Member = None):
        user = user or ctx.author
        embed = base_embed(f"{EMOJI_SEARCH} User Information", "", COLOR_INFO)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Username", value=str(user), inline=True)
        embed.add_field(name="ID", value=user.id, inline=True)
        embed.add_field(
            name="Joined Server",
            value=discord.utils.format_dt(user.joined_at, "R") if user.joined_at else "Unknown",
            inline=True,
        )
        embed.add_field(
            name="Account Created",
            value=discord.utils.format_dt(user.created_at, "R"),
            inline=True,
        )
        roles = [r.mention for r in user.roles if r.name != "@everyone"]
        embed.add_field(
            name=f"Roles ({len(roles)})",
            value=" ".join(roles) if roles else "None",
            inline=False,
        )
        await ctx.send(embed=embed)

    @commands.command(name="dm")
    @commands.has_permissions(manage_messages=True)
    async def dm(self, ctx: commands.Context, user: discord.Member, *, message: str):
        try:
            embed = base_embed(
                f"Message from {ctx.guild.name}", message, COLOR_INFO
            )
            await user.send(embed=embed)
            await ctx.send(
                embed=base_embed(
                    f"{EMOJI_ACCEPT} Message Sent",
                    f"Your message was delivered to {user.mention}.",
                    COLOR_SUCCESS,
                )
            )
        except discord.Forbidden:
            await ctx.send(
                embed=base_embed(
                    f"{EMOJI_DENIED} Delivery Failed",
                    f"Could not DM {user.mention}. They may have DMs disabled.",
                    COLOR_ERROR,
                )
            )

    # ---------- MUTE / UNMUTE ----------

    @commands.command(name="mute")
    @commands.has_permissions(moderate_members=True)
    async def mute(self, ctx: commands.Context, user: discord.Member, *, reason: str = "No reason provided"):
        duration = timedelta(hours=1)
        await user.timeout(duration, reason=reason)
        await ctx.send(
            embed=base_embed(
                f"{EMOJI_WARNING} Member Muted",
                f"{user.mention} has been muted.\n**Reason:** {reason}",
                COLOR_WARNING,
            )
        )

    @commands.command(name="unmute")
    @commands.has_permissions(moderate_members=True)
    async def unmute(self, ctx: commands.Context, user: discord.Member):
        await user.timeout(None)
        await ctx.send(
            embed=base_embed(
                f"{EMOJI_ACCEPT} Member Unmuted",
                f"{user.mention} has been unmuted.",
                COLOR_SUCCESS,
            )
        )

    # ---------- BAN / TEMPBAN / UNBAN ----------

    @commands.command(name="ban")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, user: discord.Member, *, reason: str = "No reason provided"):
        await user.ban(reason=reason)
        await ctx.send(
            embed=base_embed(
                f"{EMOJI_DENIED} Member Banned",
                f"{user.mention} has been banned.\n**Reason:** {reason}",
                COLOR_ERROR,
            )
        )

    @commands.command(name="tempban")
    @commands.has_permissions(ban_members=True)
    async def tempban(
        self,
        ctx: commands.Context,
        user: discord.Member,
        duration: str,
        *,
        reason: str = "No reason provided",
    ):
        delta = parse_duration(duration)
        if delta is None:
            await ctx.send(
                embed=base_embed(
                    f"{EMOJI_DENIED} Invalid Duration",
                    "Use a format like `10m`, `2h`, `1d` or `1w`.",
                    COLOR_ERROR,
                )
            )
            return
        unban_at = datetime.now(timezone.utc) + delta
        await user.ban(reason=f"[Tempban] {reason}")
        await tempbans_collection.insert_one(
            {
                "guild_id": ctx.guild.id,
                "user_id": user.id,
                "unban_at": unban_at,
                "reason": reason,
            }
        )
        await ctx.send(
            embed=base_embed(
                f"{EMOJI_CLOCK} Member Temp-Banned",
                f"{user.mention} has been banned for **{duration}**.\n**Reason:** {reason}",
                COLOR_WARNING,
            )
        )

    @commands.command(name="unban")
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, user_id: int, *, reason: str = "No reason provided"):
        try:
            user = await self.bot.fetch_user(user_id)
            await ctx.guild.unban(user, reason=reason)
            await ctx.send(
                embed=base_embed(
                    f"{EMOJI_ACCEPT} Member Unbanned",
                    f"{user.mention} has been unbanned.\n**Reason:** {reason}",
                    COLOR_SUCCESS,
                )
            )
        except discord.NotFound:
            await ctx.send(
                embed=base_embed(
                    f"{EMOJI_DENIED} User Not Found",
                    "That user is not currently banned.",
                    COLOR_ERROR,
                )
            )

    @tasks.loop(minutes=1)
    async def check_tempbans(self):
        now = datetime.now(timezone.utc)
        async for entry in tempbans_collection.find({"unban_at": {"$lte": now}}):
            guild = self.bot.get_guild(entry["guild_id"])
            if guild is not None:
                try:
                    user = discord.Object(id=entry["user_id"])
                    await guild.unban(user, reason="Tempban expired")
                except discord.HTTPException:
                    pass
            await tempbans_collection.delete_one({"_id": entry["_id"]})

    @check_tempbans.before_loop
    async def before_check_tempbans(self):
        await self.bot.wait_until_ready()

    # ---------- HELP ----------

    @commands.command(name="cmds")
    async def cmds(self, ctx: commands.Context):
        embed = base_embed(
            f"{EMOJI_SEARCH} Command List",
            "Prefix: `?` (case-insensitive)",
            COLOR_INFO,
        )
        embed.add_field(
            name="Channel Management",
            value=(
                "`?lock {channel}`\n`?unlock {channel}`\n`?slowmode {channel} {time}`"
            ),
            inline=False,
        )
        embed.add_field(
            name="Member Management",
            value=(
                "`?userinfo {user}`\n`?dm {user} {message}`\n"
                "`?mute {user} {reason}`\n`?unmute {user}`\n"
                "`?ban {user} {reason}`\n`?tempban {user} {duration} {reason}`\n"
                "`?unban {user-id} {reason}`"
            ),
            inline=False,
        )
        embed.add_field(
            name="Warnings",
            value=(
                "`?warn {user} {reason}`\n`?delwarn {user} {warn-id}`\n`?warnings {user}`"
            ),
            inline=False,
        )
        embed.add_field(
            name="Notes",
            value=(
                "`?addnote {user} {note}`\n`?removenote {user} {note-id}`\n`?viewnotes {user}`"
            ),
            inline=False,
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
