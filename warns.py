from datetime import datetime, timezone

import discord
from discord.ext import commands

from config import COLOR_ERROR, COLOR_INFO, COLOR_SUCCESS, COLOR_WARNING, EMOJI_ACCEPT, EMOJI_DENIED, EMOJI_WARNING, FOOTER_TEXT
from database import get_next_id, warns_collection


def base_embed(title: str, description: str, color: int) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=FOOTER_TEXT)
    embed.timestamp = datetime.now(timezone.utc)
    return embed


class Warns(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="warn")
    @commands.has_permissions(moderate_members=True)
    async def warn(self, ctx: commands.Context, user: discord.Member, *, reason: str = "No reason provided"):
        warn_id = await get_next_id(ctx.guild.id, "warn")
        await warns_collection.insert_one(
            {
                "guild_id": ctx.guild.id,
                "user_id": user.id,
                "warn_id": warn_id,
                "reason": reason,
                "moderator_id": ctx.author.id,
                "created_at": datetime.now(timezone.utc),
            }
        )
        await ctx.send(
            embed=base_embed(
                f"{EMOJI_WARNING} Member Warned",
                f"{user.mention} has been warned. **Warn ID:** `{warn_id}`\n**Reason:** {reason}",
                COLOR_WARNING,
            )
        )
        try:
            await user.send(
                embed=base_embed(
                    f"{EMOJI_WARNING} You Have Been Warned",
                    f"You received a warning in **{ctx.guild.name}**.\n**Reason:** {reason}",
                    COLOR_WARNING,
                )
            )
        except discord.Forbidden:
            pass

    @commands.command(name="delwarn")
    @commands.has_permissions(moderate_members=True)
    async def delwarn(self, ctx: commands.Context, user: discord.Member, warn_id: int):
        result = await warns_collection.delete_one(
            {"guild_id": ctx.guild.id, "user_id": user.id, "warn_id": warn_id}
        )
        if result.deleted_count:
            await ctx.send(
                embed=base_embed(
                    f"{EMOJI_ACCEPT} Warning Removed",
                    f"Warn `{warn_id}` for {user.mention} has been deleted.",
                    COLOR_SUCCESS,
                )
            )
        else:
            await ctx.send(
                embed=base_embed(
                    f"{EMOJI_DENIED} Warning Not Found",
                    f"No warning with ID `{warn_id}` was found for {user.mention}.",
                    COLOR_ERROR,
                )
            )

    @commands.command(name="warnings")
    async def warnings(self, ctx: commands.Context, user: discord.Member):
        cursor = warns_collection.find({"guild_id": ctx.guild.id, "user_id": user.id})
        entries = [w async for w in cursor]
        if not entries:
            await ctx.send(
                embed=base_embed(
                    f"{EMOJI_ACCEPT} No Warnings",
                    f"{user.mention} has no warnings.",
                    COLOR_SUCCESS,
                )
            )
            return
        embed = base_embed(
            f"{EMOJI_WARNING} Warnings for {user}",
            f"Total: **{len(entries)}**",
            COLOR_WARNING,
        )
        for w in entries[:25]:
            embed.add_field(
                name=f"Warn ID: {w['warn_id']}",
                value=f"**Reason:** {w['reason']}\n**Moderator:** <@{w['moderator_id']}>",
                inline=False,
            )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Warns(bot))
