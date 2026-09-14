from datetime import datetime, timezone

import discord
from discord.ext import commands

from config import COLOR_ERROR, COLOR_INFO, COLOR_SUCCESS, EMOJI_ACCEPT, EMOJI_DENIED, EMOJI_PEN, FOOTER_TEXT
from database import get_next_id, notes_collection


def base_embed(title: str, description: str, color: int) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=FOOTER_TEXT)
    embed.timestamp = datetime.now(timezone.utc)
    return embed


class Notes(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="addnote")
    @commands.has_permissions(moderate_members=True)
    async def addnote(self, ctx: commands.Context, user: discord.Member, *, note: str):
        note_id = await get_next_id(ctx.guild.id, "note")
        await notes_collection.insert_one(
            {
                "guild_id": ctx.guild.id,
                "user_id": user.id,
                "note_id": note_id,
                "content": note,
                "author_id": ctx.author.id,
                "created_at": datetime.now(timezone.utc),
            }
        )
        await ctx.send(
            embed=base_embed(
                f"{EMOJI_PEN} Note Added",
                f"Note `{note_id}` added for {user.mention}.",
                COLOR_SUCCESS,
            )
        )

    @commands.command(name="removenote")
    @commands.has_permissions(moderate_members=True)
    async def removenote(self, ctx: commands.Context, user: discord.Member, note_id: int):
        result = await notes_collection.delete_one(
            {"guild_id": ctx.guild.id, "user_id": user.id, "note_id": note_id}
        )
        if result.deleted_count:
            await ctx.send(
                embed=base_embed(
                    f"{EMOJI_ACCEPT} Note Removed",
                    f"Note `{note_id}` for {user.mention} has been deleted.",
                    COLOR_SUCCESS,
                )
            )
        else:
            await ctx.send(
                embed=base_embed(
                    f"{EMOJI_DENIED} Note Not Found",
                    f"No note with ID `{note_id}` was found for {user.mention}.",
                    COLOR_ERROR,
                )
            )

    @commands.command(name="viewnotes")
    @commands.has_permissions(moderate_members=True)
    async def viewnotes(self, ctx: commands.Context, user: discord.Member):
        cursor = notes_collection.find({"guild_id": ctx.guild.id, "user_id": user.id})
        entries = [n async for n in cursor]
        if not entries:
            await ctx.send(
                embed=base_embed(
                    f"{EMOJI_PEN} No Notes",
                    f"{user.mention} has no notes.",
                    COLOR_INFO,
                )
            )
            return
        embed = base_embed(f"{EMOJI_PEN} Notes for {user}", f"Total: **{len(entries)}**", COLOR_INFO)
        for n in entries[:25]:
            embed.add_field(
                name=f"Note ID: {n['note_id']}",
                value=f"{n['content']}\n**Author:** <@{n['author_id']}>",
                inline=False,
            )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Notes(bot))
