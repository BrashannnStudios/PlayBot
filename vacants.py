import discord
from discord import app_commands
from discord.ext import commands
from database import db
from utils import (
    success_embed, error_embed, info_embed, warning_embed, safe_color,
    EMOJI_SUCCESS, EMOJI_ERROR, EMOJI_INFO, EMOJI_PLUMA, EMOJI_LUPA,
    EMOJI_ACEPTAR, EMOJI_DENEGADO, EMOJI_AVISO, EMOJI_RELOJARENA
)
import asyncio
from datetime import datetime

# ── Application Flow (DM questions) ───────────────────────────────────────
class ApplicationSession:
    def __init__(self, bot, user: discord.User, guild: discord.Guild, position: dict):
        self.bot = bot
        self.user = user
        self.guild = guild
        self.position = position
        self.answers = []
        self.questions = position.get("questions") or [
            "Why do you want this position?",
            "What relevant experience do you have?",
            "How many hours per week can you dedicate?"
        ]

    async def start(self):
        try:
            await self.user.send(
                embed=info_embed(
                    f"Application – {self.position['label']}",
                    f"You are applying for **{self.position['label']}** in **{self.guild.name}**.\n"
                    f"I will ask you {len(self.questions)} questions. Answer one by one."
                )
            )
        except discord.Forbidden:
            return False

        for i, question in enumerate(self.questions, 1):
            await self.user.send(embed=info_embed(f"Question {i}/{len(self.questions)}", question))
            try:
                msg = await self.bot.wait_for(
                    "message",
                    check=lambda m: m.author.id == self.user.id and isinstance(m.channel, discord.DMChannel),
                    timeout=600
                )
                self.answers.append(msg.content)
            except asyncio.TimeoutError:
                await self.user.send(embed=error_embed("Application timed out. Please try again later."))
                return False

        # Enviar al canal de vacantes
        config = await db.get_guild_config(self.guild.id)
        channel_id = config["vacants"].get("channel_id")
        channel = self.guild.get_channel(channel_id) if channel_id else None
        if not channel:
            await self.user.send(embed=error_embed("Application channel not configured. Contact staff."))
            return False

        embed = discord.Embed(
            title=f"{EMOJI_PLUMA} New Application – {self.position['label']}",
            color=0x5865F2,
            timestamp=datetime.utcnow()
        )
        embed.set_author(name=str(self.user), icon_url=self.user.display_avatar.url)
        embed.add_field(name="User", value=f"{self.user.mention} (`{self.user.id}`)", inline=False)
        for i, (q, a) in enumerate(zip(self.questions, self.answers), 1):
            embed.add_field(name=f"Q{i}: {q[:200]}", value=a[:1024] or "—", inline=False)
        embed.set_footer(text=f"Position ID: {self.position['id']}")

        view = ApplicationReviewView(self.user.id, self.position["id"])
        msg = await channel.send(embed=embed, view=view)

        # Guardar en DB
        await db.create_application({
            "guild_id": self.guild.id,
            "user_id": self.user.id,
            "position": self.position["id"],
            "position_label": self.position["label"],
            "answers": self.answers,
            "questions": self.questions,
            "status": "pending",
            "message_id": msg.id,
            "channel_id": channel.id,
            "timestamp": datetime.utcnow()
        })

        await self.user.send(embed=success_embed("Application submitted!", "Staff will review it soon."))
        return True

class ApplicationReviewView(discord.ui.View):
    def __init__(self, applicant_id: int, position_id: str):
        super().__init__(timeout=None)  # persistent
        self.applicant_id = applicant_id
        self.position_id = position_id

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.secondary, emoji=EMOJI_ACEPTAR, custom_id="vacant_accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._resolve(interaction, "accepted")

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.secondary, emoji=EMOJI_DENEGADO, custom_id="vacant_deny")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._resolve(interaction, "denied")

    async def _resolve(self, interaction: discord.Interaction, status: str):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(
                embed=error_embed("You need Manage Server permission."), ephemeral=True
            )

        # Deshabilitar botones
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

        applicant = interaction.client.get_user(self.applicant_id) or await interaction.client.fetch_user(self.applicant_id)
        color = 0x57F287 if status == "accepted" else 0xED4245
        emoji = EMOJI_ACEPTAR if status == "accepted" else EMOJI_DENEGADO

        embed = interaction.message.embeds[0]
        embed.color = color
        embed.title = f"{emoji} Application {status.upper()} – {embed.title.split('–')[-1].strip()}"
        embed.add_field(name="Reviewed by", value=interaction.user.mention, inline=False)
        await interaction.message.edit(embed=embed, view=self)

        # Notificar al usuario
        try:
            if status == "accepted":
                await applicant.send(embed=success_embed(
                    "Application Accepted!",
                    f"Your application for the position has been **accepted** in **{interaction.guild.name}**.\nStaff will contact you soon."
                ))
            else:
                await applicant.send(embed=error_embed(
                    "Application Denied",
                    f"Your application has been **denied** in **{interaction.guild.name}**.\nYou may apply again later if positions remain open."
                ))
        except Exception:
            pass

        await interaction.response.send_message(
            embed=success_embed(f"Application {status}."), ephemeral=True
        )

# ── Setup Views ───────────────────────────────────────────────────────────
class VacantsSetupView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=600)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(embed=error_embed("Only the author can use this."), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Set Review Channel", style=discord.ButtonStyle.secondary, emoji=EMOJI_LUPA)
    async def set_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=info_embed("Mention the channel where applications will be sent."), ephemeral=True)
        try:
            msg = await interaction.client.wait_for(
                "message",
                check=lambda m: m.author.id == self.author_id and m.channel.id == interaction.channel.id,
                timeout=60
            )
            channel = msg.channel_mentions[0] if msg.channel_mentions else interaction.guild.get_channel(int(msg.content.strip()))
            if not channel:
                return await msg.reply(embed=error_embed("Invalid channel."))
            config = await db.get_guild_config(interaction.guild.id)
            config["vacants"]["channel_id"] = channel.id
            await db.update_guild_config(interaction.guild.id, {"vacants": config["vacants"]})
            await msg.reply(embed=success_embed("Review channel set!", channel.mention))
        except Exception:
            await interaction.followup.send(embed=error_embed("Timed out."), ephemeral=True)

    @discord.ui.button(label="Manage Positions", style=discord.ButtonStyle.secondary, emoji=EMOJI_PLUMA)
    async def manage_positions(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await db.get_guild_config(interaction.guild.id)
        positions = config["vacants"].get("positions", [])
        desc = "\n".join(f"• **{p['label']}** (`{p['id']}`) – {len(p.get('questions', []))} questions" for p in positions) or "No positions yet."
        embed = info_embed("Positions", desc + "\n\nUse the buttons to add or remove.")
        view = PositionManageView(self.author_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Set Embed Title/Desc", style=discord.ButtonStyle.secondary)
    async def set_embed_text(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=info_embed("Send the embed **title** first, then the **description** in a second message."),
            ephemeral=True
        )
        try:
            title_msg = await interaction.client.wait_for(
                "message", check=lambda m: m.author.id == self.author_id and m.channel.id == interaction.channel.id, timeout=60
            )
            await title_msg.reply(embed=info_embed("Now send the description."))
            desc_msg = await interaction.client.wait_for(
                "message", check=lambda m: m.author.id == self.author_id and m.channel.id == interaction.channel.id, timeout=120
            )
            config = await db.get_guild_config(interaction.guild.id)
            config["vacants"]["embed"]["title"] = title_msg.content
            config["vacants"]["embed"]["description"] = desc_msg.content
            await db.update_guild_config(interaction.guild.id, {"vacants": config["vacants"]})
            await desc_msg.reply(embed=success_embed("Embed text updated!"))
        except Exception:
            await interaction.followup.send(embed=error_embed("Timed out."), ephemeral=True)

    @discord.ui.button(label="Set Embed Color/Image", style=discord.ButtonStyle.secondary)
    async def set_embed_style(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=info_embed("Send hex color, then image URL (or `none`)."), ephemeral=True
        )
        try:
            color_msg = await interaction.client.wait_for(
                "message", check=lambda m: m.author.id == self.author_id and m.channel.id == interaction.channel.id, timeout=60
            )
            color = safe_color(color_msg.content)
            await color_msg.reply(embed=info_embed("Now send image URL or `none`."))
            img_msg = await interaction.client.wait_for(
                "message", check=lambda m: m.author.id == self.author_id and m.channel.id == interaction.channel.id, timeout=60
            )
            img = None if img_msg.content.lower().strip() == "none" else img_msg.content.strip()
            config = await db.get_guild_config(interaction.guild.id)
            config["vacants"]["embed"]["color"] = color
            config["vacants"]["embed"]["image_url"] = img
            await db.update_guild_config(interaction.guild.id, {"vacants": config["vacants"]})
            await img_msg.reply(embed=success_embed("Embed style updated!"))
        except Exception:
            await interaction.followup.send(embed=error_embed("Timed out."), ephemeral=True)

class PositionManageView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=300)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    @discord.ui.button(label="Add Position", style=discord.ButtonStyle.secondary, emoji=EMOJI_ACEPTAR)
    async def add_position(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=info_embed(
                "Add Position",
                "Send in this format (one message):\n"
                "`id | Label | emoji(optional)`\n"
                "Example: `mod | Moderator | 🛡️`\n\n"
                "Then I will ask for the questions (one per line)."
            ),
            ephemeral=True
        )
        try:
            msg = await interaction.client.wait_for(
                "message", check=lambda m: m.author.id == self.author_id and m.channel.id == interaction.channel.id, timeout=90
            )
            parts = [p.strip() for p in msg.content.split("|")]
            if len(parts) < 2:
                return await msg.reply(embed=error_embed("Invalid format."))
            pos_id = parts[0].lower().replace(" ", "_")
            label = parts[1]
            emoji = parts[2] if len(parts) > 2 else None

            await msg.reply(embed=info_embed("Now send the questions, one per line."))
            q_msg = await interaction.client.wait_for(
                "message", check=lambda m: m.author.id == self.author_id and m.channel.id == interaction.channel.id, timeout=180
            )
            questions = [q.strip() for q in q_msg.content.splitlines() if q.strip()]

            config = await db.get_guild_config(interaction.guild.id)
            positions = config["vacants"].get("positions", [])
            # evitar duplicados
            positions = [p for p in positions if p["id"] != pos_id]
            positions.append({
                "id": pos_id,
                "label": label,
                "emoji": emoji,
                "questions": questions
            })
            config["vacants"]["positions"] = positions
            await db.update_guild_config(interaction.guild.id, {"vacants": config["vacants"]})
            await q_msg.reply(embed=success_embed(f"Position **{label}** added with {len(questions)} questions."))
        except Exception:
            await interaction.followup.send(embed=error_embed("Timed out or error."), ephemeral=True)

    @discord.ui.button(label="Remove Position", style=discord.ButtonStyle.secondary, emoji=EMOJI_DENEGADO)
    async def remove_position(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await db.get_guild_config(interaction.guild.id)
        positions = config["vacants"].get("positions", [])
        if not positions:
            return await interaction.response.send_message(embed=error_embed("No positions to remove."), ephemeral=True)

        options = [discord.SelectOption(label=p["label"], value=p["id"]) for p in positions]
        select = discord.ui.Select(placeholder="Select position to remove", options=options)

        async def select_callback(inter: discord.Interaction):
            pos_id = select.values[0]
            config = await db.get_guild_config(inter.guild.id)
            config["vacants"]["positions"] = [p for p in config["vacants"]["positions"] if p["id"] != pos_id]
            await db.update_guild_config(inter.guild.id, {"vacants": config["vacants"]})
            await inter.response.send_message(embed=success_embed("Position removed."), ephemeral=True)

        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message(embed=info_embed("Select the position to remove:"), view=view, ephemeral=True)

# ── Open Vacants View (botones dinámicos) ─────────────────────────────────
class OpenVacantsView(discord.ui.View):
    def __init__(self, positions: list):
        super().__init__(timeout=None)
        for pos in positions:
            button = discord.ui.Button(
                label=pos["label"],
                style=discord.ButtonStyle.secondary,
                emoji=pos.get("emoji"),
                custom_id=f"apply_{pos['id']}"
            )
            button.callback = self.make_callback(pos)
            self.add_item(button)

    def make_callback(self, position: dict):
        async def callback(interaction: discord.Interaction):
            config = await db.get_guild_config(interaction.guild.id)
            if not config["vacants"].get("open", False):
                return await interaction.response.send_message(
                    embed=error_embed("Applications are currently closed."), ephemeral=True
                )
            await interaction.response.defer(ephemeral=True)
            session = ApplicationSession(interaction.client, interaction.user, interaction.guild, position)
            success = await session.start()
            if not success:
                await interaction.followup.send(
                    embed=error_embed("Could not start application. Make sure your DMs are open."),
                    ephemeral=True
                )
            else:
                await interaction.followup.send(embed=success_embed("Check your DMs to continue the application."), ephemeral=True)
        return callback

class Vacants(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Registrar views persistentes al iniciar
        bot.add_view(ApplicationReviewView(0, ""))  # dummy para persistent

    @app_commands.command(name="vacants-setup", description="Configure the job application system")
    @app_commands.checks.has_permissions(administrator=True)
    async def vacants_setup(self, interaction: discord.Interaction):
        config = await db.get_guild_config(interaction.guild.id)
        v = config["vacants"]
        channel = f"<#{v['channel_id']}>" if v.get("channel_id") else "Not set"
        positions = v.get("positions", [])
        pos_text = "\n".join(f"• {p['label']}" for p in positions) or "None"

        embed = discord.Embed(
            title=f"{EMOJI_INFO} Vacants System Setup",
            color=0x5865F2
        )
        embed.add_field(name="Review Channel", value=channel, inline=True)
        embed.add_field(name="Currently Open", value="Yes" if v.get("open") else "No", inline=True)
        embed.add_field(name="Positions", value=pos_text, inline=False)

        view = VacantsSetupView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="open-vacants", description="Open applications and post the panel")
    @app_commands.checks.has_permissions(administrator=True)
    async def open_vacants(self, interaction: discord.Interaction):
        config = await db.get_guild_config(interaction.guild.id)
        v = config["vacants"]
        if not v.get("channel_id"):
            return await interaction.response.send_message(embed=error_embed("Set the review channel first with `/vacants-setup`."), ephemeral=True)
        if not v.get("positions"):
            return await interaction.response.send_message(embed=error_embed("Add at least one position first."), ephemeral=True)

        v["open"] = True
        await db.update_guild_config(interaction.guild.id, {"vacants": v})

        emb_data = v.get("embed", {})
        embed = discord.Embed(
            title=emb_data.get("title", "Open Positions"),
            description=emb_data.get("description", "Click a button below to apply."),
            color=emb_data.get("color", 0x5865F2)
        )
        if emb_data.get("image_url"):
            embed.set_image(url=emb_data["image_url"])
        embed.set_footer(text=emb_data.get("footer", "Play Big Studios"))

        # Listar posiciones
        for p in v["positions"]:
            embed.add_field(name=f"{p.get('emoji', '')} {p['label']}", value="Click the button to apply", inline=True)

        view = OpenVacantsView(v["positions"])
        await interaction.response.send_message(embed=success_embed("Vacants opened!"), ephemeral=True)
        await interaction.channel.send(embed=embed, view=view)

    @app_commands.command(name="close-vacants", description="Close applications")
    @app_commands.checks.has_permissions(administrator=True)
    async def close_vacants(self, interaction: discord.Interaction):
        config = await db.get_guild_config(interaction.guild.id)
        config["vacants"]["open"] = False
        await db.update_guild_config(interaction.guild.id, {"vacants": config["vacants"]})
        await interaction.response.send_message(embed=success_embed("Applications are now closed."), ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Vacants(bot))
