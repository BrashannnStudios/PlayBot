import discord
from discord.ext import commands
from database import db
from utils import (
    success_embed, error_embed, info_embed, warning_embed,
    parse_time, format_duration,
    EMOJI_SUCCESS, EMOJI_ERROR, EMOJI_WARNING, EMOJI_INFO,
    EMOJI_LOCK, EMOJI_ACEPTAR, EMOJI_DENEGADO, EMOJI_AVISO,
    EMOJI_PLUMA, EMOJI_LUPA, EMOJI_RELOJ, EMOJI_RELOJARENA
)
from datetime import datetime, timedelta
import re

class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Helper ────────────────────────────────────────────────────────────
    async def get_member(self, ctx: commands.Context, user: str) -> discord.Member | None:
        """Resuelve mención, ID o nombre."""
        if not user:
            return None
        # Mención
        match = re.search(r"<@!?(\d+)>", user)
        if match:
            return ctx.guild.get_member(int(match.group(1)))
        # ID
        if user.isdigit():
            return ctx.guild.get_member(int(user))
        # Nombre
        return discord.utils.find(
            lambda m: m.name.lower() == user.lower() or m.display_name.lower() == user.lower(),
            ctx.guild.members
        )

    # ── Lock / Unlock ─────────────────────────────────────────────────────
    @commands.command(name="lock")
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"Locked by {ctx.author}")
        await ctx.send(embed=success_embed("Channel Locked", f"{channel.mention} has been locked."))

    @commands.command(name="unlock")
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"Unlocked by {ctx.author}")
        await ctx.send(embed=success_embed("Channel Unlocked", f"{channel.mention} has been unlocked."))

    # ── Slowmode ──────────────────────────────────────────────────────────
    @commands.command(name="slowmode")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx: commands.Context, channel: discord.TextChannel = None, time: str = "0"):
        channel = channel or ctx.channel
        # Si el primer argumento no es canal, es el tiempo
        if isinstance(channel, str):
            time = channel
            channel = ctx.channel

        seconds = parse_time(time)
        if seconds is None:
            return await ctx.send(embed=error_embed("Invalid time", "Use formats like `5s`, `10m`, `1h` or `0` to disable."))
        if seconds > 21600:
            return await ctx.send(embed=error_embed("Too high", "Maximum slowmode is 6 hours (21600s)."))

        await channel.edit(slowmode_delay=seconds, reason=f"Slowmode set by {ctx.author}")
        if seconds == 0:
            await ctx.send(embed=success_embed("Slowmode Disabled", f"Slowmode removed from {channel.mention}."))
        else:
            await ctx.send(embed=success_embed("Slowmode Set", f"Slowmode of **{format_duration(seconds)}** applied to {channel.mention}."))

    # ── Userinfo ──────────────────────────────────────────────────────────
    @commands.command(name="userinfo", aliases=["ui", "whois"])
    async def userinfo(self, ctx: commands.Context, user: str = None):
        member = await self.get_member(ctx, user) if user else ctx.author
        if not member:
            return await ctx.send(embed=error_embed("User not found."))

        roles = [r.mention for r in member.roles if r != ctx.guild.default_role]
        roles_str = " ".join(roles[:15]) + (" ..." if len(roles) > 15 else "") or "None"

        embed = discord.Embed(color=member.color or 0x5865F2, timestamp=datetime.utcnow())
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=f"`{member.id}`", inline=True)
        embed.add_field(name="Nickname", value=member.nick or "None", inline=True)
        embed.add_field(name="Bot", value="Yes" if member.bot else "No", inline=True)
        embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, "R"), inline=True)
        embed.add_field(name="Joined Server", value=discord.utils.format_dt(member.joined_at, "R") if member.joined_at else "Unknown", inline=True)
        embed.add_field(name=f"Roles [{len(roles)}]", value=roles_str, inline=False)
        embed.set_footer(text=f"Requested by {ctx.author}")
        await ctx.send(embed=embed)

    # ── DM ────────────────────────────────────────────────────────────────
    @commands.command(name="dm")
    @commands.has_permissions(manage_messages=True)
    async def dm(self, ctx: commands.Context, user: str, *, message: str):
        member = await self.get_member(ctx, user)
        if not member:
            return await ctx.send(embed=error_embed("User not found."))
        try:
            await member.send(embed=info_embed(f"Message from {ctx.guild.name}", message))
            await ctx.send(embed=success_embed("DM Sent", f"Message delivered to {member.mention}."))
        except discord.Forbidden:
            await ctx.send(embed=error_embed("Could not DM", "User has DMs closed or blocked the bot."))

    # ── Mute / Unmute (timeout nativo) ────────────────────────────────────
    @commands.command(name="mute")
    @commands.has_permissions(moderate_members=True)
    async def mute(self, ctx: commands.Context, user: str, time: str = "1h", *, reason: str = "No reason provided"):
        member = await self.get_member(ctx, user)
        if not member:
            return await ctx.send(embed=error_embed("User not found."))
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send(embed=error_embed("Hierarchy error", "You cannot mute this user."))
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.send(embed=error_embed("Hierarchy error", "I cannot mute this user."))

        seconds = parse_time(time)
        if seconds is None or seconds < 1:
            return await ctx.send(embed=error_embed("Invalid duration", "Use `5m`, `1h`, `1d`, etc. Max 28 days."))
        if seconds > 2419200:  # 28 days
            seconds = 2419200

        until = discord.utils.utcnow() + timedelta(seconds=seconds)
        try:
            await member.timeout(until, reason=f"{reason} | By {ctx.author}")
            await ctx.send(embed=success_embed(
                "User Muted",
                f"{member.mention} has been timed out for **{format_duration(seconds)}**.\nReason: {reason}"
            ))
        except Exception as e:
            await ctx.send(embed=error_embed("Failed to mute", str(e)))

    @commands.command(name="unmute")
    @commands.has_permissions(moderate_members=True)
    async def unmute(self, ctx: commands.Context, user: str):
        member = await self.get_member(ctx, user)
        if not member:
            return await ctx.send(embed=error_embed("User not found."))
        try:
            await member.timeout(None, reason=f"Unmuted by {ctx.author}")
            await ctx.send(embed=success_embed("User Unmuted", f"{member.mention} timeout removed."))
        except Exception as e:
            await ctx.send(embed=error_embed("Failed to unmute", str(e)))

    # ── Ban / Tempban / Unban ─────────────────────────────────────────────
    @commands.command(name="ban")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, user: str, *, reason: str = "No reason provided"):
        member = await self.get_member(ctx, user)
        if not member:
            # Intentar banear por ID aunque no esté en el server
            if user.isdigit():
                try:
                    await ctx.guild.ban(discord.Object(id=int(user)), reason=f"{reason} | By {ctx.author}", delete_message_days=0)
                    return await ctx.send(embed=success_embed("User Banned", f"User `{user}` has been banned.\nReason: {reason}"))
                except Exception:
                    return await ctx.send(embed=error_embed("User not found."))
            return await ctx.send(embed=error_embed("User not found."))

        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send(embed=error_embed("Hierarchy error"))
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.send(embed=error_embed("I cannot ban this user."))

        try:
            await member.ban(reason=f"{reason} | By {ctx.author}", delete_message_days=0)
            await ctx.send(embed=success_embed("User Banned", f"{member} has been banned.\nReason: {reason}"))
        except Exception as e:
            await ctx.send(embed=error_embed("Failed to ban", str(e)))

    @commands.command(name="tempban")
    @commands.has_permissions(ban_members=True)
    async def tempban(self, ctx: commands.Context, user: str, time: str, *, reason: str = "No reason provided"):
        member = await self.get_member(ctx, user)
        if not member and not user.isdigit():
            return await ctx.send(embed=error_embed("User not found."))

        seconds = parse_time(time)
        if seconds is None or seconds < 60:
            return await ctx.send(embed=error_embed("Invalid duration", "Minimum 1 minute. Use `1h`, `1d`, `7d`, etc."))

        user_id = member.id if member else int(user)
        expires = datetime.utcnow() + timedelta(seconds=seconds)

        try:
            if member:
                if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
                    return await ctx.send(embed=error_embed("Hierarchy error"))
                await member.ban(reason=f"[TEMP] {reason} | By {ctx.author} | Expires: {expires}", delete_message_days=0)
            else:
                await ctx.guild.ban(discord.Object(id=user_id), reason=f"[TEMP] {reason} | By {ctx.author}", delete_message_days=0)

            await db.add_tempban(ctx.guild.id, user_id, expires, reason, ctx.author.id)
            await ctx.send(embed=success_embed(
                "Temporary Ban",
                f"User has been banned for **{format_duration(seconds)}**.\nReason: {reason}"
            ))
        except Exception as e:
            await ctx.send(embed=error_embed("Failed to tempban", str(e)))

    @commands.command(name="unban")
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, user_id: str, *, reason: str = "No reason provided"):
        if not user_id.isdigit():
            return await ctx.send(embed=error_embed("Invalid ID", "Provide the numeric user ID."))
        try:
            await ctx.guild.unban(discord.Object(id=int(user_id)), reason=f"{reason} | By {ctx.author}")
            await db.remove_tempban(ctx.guild.id, int(user_id))
            await ctx.send(embed=success_embed("User Unbanned", f"User `{user_id}` has been unbanned."))
        except discord.NotFound:
            await ctx.send(embed=error_embed("User not banned or invalid ID."))
        except Exception as e:
            await ctx.send(embed=error_embed("Failed to unban", str(e)))

    # ── Warn system ───────────────────────────────────────────────────────
    @commands.command(name="warn")
    @commands.has_permissions(moderate_members=True)
    async def warn(self, ctx: commands.Context, user: str, *, reason: str = "No reason provided"):
        member = await self.get_member(ctx, user)
        if not member:
            return await ctx.send(embed=error_embed("User not found."))

        warn_id = await db.add_warning(ctx.guild.id, member.id, ctx.author.id, reason)
        warnings = await db.get_warnings(ctx.guild.id, member.id)

        embed = warning_embed(
            "User Warned",
            f"{member.mention} has been warned.\n**Reason:** {reason}\n**Total warnings:** {len(warnings)}\n**Warn ID:** `{warn_id}`"
        )
        await ctx.send(embed=embed)

        try:
            await member.send(embed=warning_embed(
                f"You were warned in {ctx.guild.name}",
                f"**Reason:** {reason}\n**Moderator:** {ctx.author}"
            ))
        except Exception:
            pass

    @commands.command(name="delwarn", aliases=["removewarn", "unwarn"])
    @commands.has_permissions(moderate_members=True)
    async def delwarn(self, ctx: commands.Context, user: str, warn_id: str):
        member = await self.get_member(ctx, user)
        if not member:
            return await ctx.send(embed=error_embed("User not found."))

        success = await db.remove_warning(ctx.guild.id, warn_id)
        if success:
            await ctx.send(embed=success_embed("Warning Removed", f"Warn `{warn_id}` deleted for {member.mention}."))
        else:
            await ctx.send(embed=error_embed("Warn not found", "Check the warn ID."))

    @commands.command(name="warnings", aliases=["warns"])
    @commands.has_permissions(moderate_members=True)
    async def warnings(self, ctx: commands.Context, user: str):
        member = await self.get_member(ctx, user)
        if not member:
            return await ctx.send(embed=error_embed("User not found."))

        warns = await db.get_warnings(ctx.guild.id, member.id)
        if not warns:
            return await ctx.send(embed=info_embed("No Warnings", f"{member.mention} has no warnings."))

        embed = discord.Embed(
            title=f"{EMOJI_AVISO} Warnings for {member}",
            color=0xFEE75C,
            timestamp=datetime.utcnow()
        )
        for w in warns[:15]:
            mod = ctx.guild.get_member(w["moderator_id"])
            mod_name = mod.mention if mod else f"`{w['moderator_id']}`"
            embed.add_field(
                name=f"ID: `{w['_id']}`",
                value=f"**Reason:** {w['reason']}\n**By:** {mod_name}\n**Date:** {discord.utils.format_dt(w['timestamp'], 'R')}",
                inline=False
            )
        embed.set_footer(text=f"Total: {len(warns)}")
        await ctx.send(embed=embed)

    # ── Notes system ──────────────────────────────────────────────────────
    @commands.command(name="addnote")
    @commands.has_permissions(moderate_members=True)
    async def addnote(self, ctx: commands.Context, user: str, *, note: str):
        member = await self.get_member(ctx, user)
        if not member:
            return await ctx.send(embed=error_embed("User not found."))

        note_id = await db.add_note(ctx.guild.id, member.id, ctx.author.id, note)
        await ctx.send(embed=success_embed("Note Added", f"Note saved for {member.mention}.\n**ID:** `{note_id}`"))

    @commands.command(name="removenote", aliases=["delnote"])
    @commands.has_permissions(moderate_members=True)
    async def removenote(self, ctx: commands.Context, user: str, note_id: str):
        member = await self.get_member(ctx, user)
        if not member:
            return await ctx.send(embed=error_embed("User not found."))

        success = await db.remove_note(ctx.guild.id, note_id)
        if success:
            await ctx.send(embed=success_embed("Note Removed", f"Note `{note_id}` deleted."))
        else:
            await ctx.send(embed=error_embed("Note not found."))

    @commands.command(name="viewnotes", aliases=["notes"])
    @commands.has_permissions(moderate_members=True)
    async def viewnotes(self, ctx: commands.Context, user: str):
        member = await self.get_member(ctx, user)
        if not member:
            return await ctx.send(embed=error_embed("User not found."))

        notes = await db.get_notes(ctx.guild.id, member.id)
        if not notes:
            return await ctx.send(embed=info_embed("No Notes", f"{member.mention} has no notes."))

        embed = discord.Embed(
            title=f"{EMOJI_PLUMA} Notes for {member}",
            color=0x5865F2,
            timestamp=datetime.utcnow()
        )
        for n in notes[:15]:
            mod = ctx.guild.get_member(n["moderator_id"])
            mod_name = mod.mention if mod else f"`{n['moderator_id']}`"
            embed.add_field(
                name=f"ID: `{n['_id']}`",
                value=f"{n['note']}\n**By:** {mod_name} • {discord.utils.format_dt(n['timestamp'], 'R')}",
                inline=False
            )
        embed.set_footer(text=f"Total: {len(notes)}")
        await ctx.send(embed=embed)

    # ── cmds ──────────────────────────────────────────────────────────────
    @commands.command(name="cmds", aliases=["commands", "help"])
    async def cmds(self, ctx: commands.Context):
        embed = discord.Embed(
            title=f"{EMOJI_INFO} Play Big Studios – Commands",
            description="Prefix: `?` (case-insensitive)\nSlash commands also available for setup.",
            color=0x5865F2
        )
        embed.add_field(
            name="Moderation",
            value=(
                "`?lock [channel]`\n"
                "`?unlock [channel]`\n"
                "`?slowmode [channel] <time>`\n"
                "`?mute <user> [time] [reason]`\n"
                "`?unmute <user>`\n"
                "`?ban <user> [reason]`\n"
                "`?tempban <user> <time> [reason]`\n"
                "`?unban <user-id> [reason]`\n"
                "`?warn <user> [reason]`\n"
                "`?delwarn <user> <warn-id>`\n"
                "`?warnings <user>`"
            ),
            inline=True
        )
        embed.add_field(
            name="Utility",
            value=(
                "`?userinfo [user]`\n"
                "`?dm <user> <message>`\n"
                "`?addnote <user> <note>`\n"
                "`?removenote <user> <note-id>`\n"
                "`?viewnotes <user>`\n"
                "`?cmds`"
            ),
            inline=True
        )
        embed.add_field(
            name="Setup (Slash)",
            value=(
                "`/welcome-setup`\n"
                "`/vacants-setup`\n"
                "`/open-vacants`\n"
                "`/close-vacants`"
            ),
            inline=False
        )
        embed.set_footer(text="Play Big Studios")
        await ctx.send(embed=embed)

    # ── Error handler local ───────────────────────────────────────────────
    @lock.error
    @unlock.error
    @slowmode.error
    @mute.error
    @unmute.error
    @ban.error
    @tempban.error
    @unban.error
    @warn.error
    async def mod_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=error_embed("Missing Permissions", "You do not have the required permissions."))
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=error_embed("Missing Argument", f"Missing: `{error.param.name}`"))
        elif isinstance(error, commands.BadArgument):
            await ctx.send(embed=error_embed("Invalid Argument", str(error)))
        else:
            await ctx.send(embed=error_embed("Error", str(error)))

async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
