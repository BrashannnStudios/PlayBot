import discord
from discord import app_commands
from discord.ext import commands

from config import COLOR_DEFAULT, EMOJI_ACCEPT, EMOJI_DENIED, EMOJI_PEN, FOOTER_TEXT
from database import get_vacants_config, set_vacants_config

DEFAULT_TITLE = "Vacancies Open!"
DEFAULT_MESSAGE = "We are currently looking for new team members. Apply now!"


def hex_to_int(value: str) -> int | None:
    value = value.strip().lstrip("#")
    try:
        return int(value, 16)
    except ValueError:
        return None


def build_vacants_embed(guild: discord.Guild, cfg: dict) -> discord.Embed:
    cfg = cfg or {}
    title = cfg.get("title", DEFAULT_TITLE)
    message = cfg.get("message", DEFAULT_MESSAGE)
    color = cfg.get("color", COLOR_DEFAULT)

    embed = discord.Embed(title=title, description=message, color=color)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    image = cfg.get("image")
    if image:
        embed.set_image(url=image)

    embed.set_footer(text=FOOTER_TEXT)
    return embed


def build_vacants_view(cfg: dict) -> discord.ui.View | None:
    links = (cfg or {}).get("links", [])
    if not links:
        return None
    view = discord.ui.View(timeout=None)
    for link in links:
        view.add_item(
            discord.ui.Button(
                label=link["label"],
                url=link["url"],
                style=discord.ButtonStyle.link,
            )
        )
    return view


# ---------------------- MODALS ----------------------

class TitleModal(discord.ui.Modal, title="Set Embed Title"):
    title_input = discord.ui.TextInput(
        label="Embed title",
        placeholder="Vacancies Open!",
        max_length=256,
        required=True,
    )

    def __init__(self, panel: "VacantsSetupView"):
        super().__init__()
        self.panel = panel

    async def on_submit(self, interaction: discord.Interaction):
        await set_vacants_config(interaction.guild_id, {"title": str(self.title_input)})
        await self.panel.refresh(interaction, "Embed title updated.")


class MessageModal(discord.ui.Modal, title="Set Embed Message"):
    message = discord.ui.TextInput(
        label="Embed message",
        style=discord.TextStyle.paragraph,
        placeholder="Describe the open positions and how to apply.",
        max_length=1000,
        required=True,
    )

    def __init__(self, panel: "VacantsSetupView"):
        super().__init__()
        self.panel = panel

    async def on_submit(self, interaction: discord.Interaction):
        await set_vacants_config(interaction.guild_id, {"message": str(self.message)})
        await self.panel.refresh(interaction, "Embed message updated.")


class ColorModal(discord.ui.Modal, title="Set Embed Color"):
    color = discord.ui.TextInput(
        label="Hex color (e.g. #5865F2)",
        placeholder="#5865F2",
        max_length=7,
        required=True,
    )

    def __init__(self, panel: "VacantsSetupView"):
        super().__init__()
        self.panel = panel

    async def on_submit(self, interaction: discord.Interaction):
        parsed = hex_to_int(str(self.color))
        if parsed is None:
            await interaction.response.send_message(
                "That is not a valid hex color.", ephemeral=True
            )
            return
        await set_vacants_config(interaction.guild_id, {"color": parsed})
        await self.panel.refresh(interaction, "Embed color updated.")


class ImageModal(discord.ui.Modal, title="Set Image"):
    url = discord.ui.TextInput(
        label="Image or GIF URL",
        placeholder="https://example.com/banner.png",
        max_length=300,
        required=True,
    )

    def __init__(self, panel: "VacantsSetupView"):
        super().__init__()
        self.panel = panel

    async def on_submit(self, interaction: discord.Interaction):
        await set_vacants_config(interaction.guild_id, {"image": str(self.url)})
        await self.panel.refresh(interaction, "Embed image updated.")


class LinkModal(discord.ui.Modal, title="Add Button Link"):
    label = discord.ui.TextInput(label="Button label", max_length=80, required=True)
    url = discord.ui.TextInput(
        label="URL", placeholder="https://forms.gle/...", max_length=300, required=True
    )

    def __init__(self, panel: "VacantsSetupView"):
        super().__init__()
        self.panel = panel

    async def on_submit(self, interaction: discord.Interaction):
        if not str(self.url).startswith(("http://", "https://")):
            await interaction.response.send_message(
                "The URL must start with http:// or https://", ephemeral=True
            )
            return
        cfg = await get_vacants_config(interaction.guild_id) or {}
        links = cfg.get("links", [])
        links.append({"label": str(self.label), "url": str(self.url)})
        await set_vacants_config(interaction.guild_id, {"links": links})
        await self.panel.refresh(interaction, "Link button added.")


# ---------------------- SELECT ----------------------

class VacantsChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, panel: "VacantsSetupView"):
        super().__init__(
            placeholder="Select the vacancies announcement channel",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
        )
        self.panel = panel

    async def callback(self, interaction: discord.Interaction):
        await set_vacants_config(
            interaction.guild_id, {"channel_id": self.values[0].id}
        )
        await self.panel.refresh(
            interaction, f"Vacancies channel set to {self.values[0].mention}."
        )


# ---------------------- MAIN PANEL VIEW ----------------------

class VacantsSetupView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild_id: int):
        super().__init__(timeout=600)
        self.bot = bot
        self.guild_id = guild_id
        self.add_item(VacantsChannelSelect(self))

    async def refresh(self, interaction: discord.Interaction, note: str):
        cfg = await get_vacants_config(self.guild_id) or {}
        embed = self.build_panel_embed(cfg, note)
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    def build_panel_embed(self, cfg: dict, note: str | None = None) -> discord.Embed:
        embed = discord.Embed(
            title=f"{EMOJI_PEN} Vacancies System Configuration",
            description="Use the buttons and menu below to configure the vacancies announcement.",
            color=COLOR_DEFAULT,
        )
        channel = f"<#{cfg['channel_id']}>" if cfg.get("channel_id") else "Not set"
        embed.add_field(name="Channel", value=channel, inline=True)
        embed.add_field(
            name="Color", value=f"#{cfg.get('color', COLOR_DEFAULT):06X}", inline=True
        )
        embed.add_field(
            name="Image", value="Set" if cfg.get("image") else "Not set", inline=True
        )
        embed.add_field(
            name="Title", value=cfg.get("title", DEFAULT_TITLE), inline=False
        )
        embed.add_field(
            name="Message",
            value=(cfg.get("message", DEFAULT_MESSAGE))[:200],
            inline=False,
        )
        links = cfg.get("links", [])
        embed.add_field(
            name="Link Buttons",
            value=", ".join(l["label"] for l in links) if links else "None",
            inline=False,
        )
        if note:
            embed.set_footer(text=f"{EMOJI_ACCEPT} {note}")
        else:
            embed.set_footer(text=FOOTER_TEXT)
        return embed

    @discord.ui.button(label="Set Title", style=discord.ButtonStyle.primary, row=2)
    async def set_title(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TitleModal(self))

    @discord.ui.button(label="Set Message", style=discord.ButtonStyle.primary, row=2)
    async def set_message(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MessageModal(self))

    @discord.ui.button(label="Set Color", style=discord.ButtonStyle.secondary, row=2)
    async def set_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ColorModal(self))

    @discord.ui.button(label="Set Image", style=discord.ButtonStyle.secondary, row=3)
    async def set_image(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ImageModal(self))

    @discord.ui.button(label="Add Link Button", style=discord.ButtonStyle.secondary, row=3)
    async def add_link(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LinkModal(self))

    @discord.ui.button(label="Clear Links", style=discord.ButtonStyle.danger, row=3)
    async def clear_links(self, interaction: discord.Interaction, button: discord.ui.Button):
        await set_vacants_config(self.guild_id, {"links": []})
        await self.refresh(interaction, "Link buttons cleared.")

    @discord.ui.button(label="Preview", style=discord.ButtonStyle.success, row=4)
    async def preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await get_vacants_config(self.guild_id) or {}
        embed = build_vacants_embed(interaction.guild, cfg)
        view = build_vacants_view(cfg)
        await interaction.response.send_message(
            content="**Preview:**", embed=embed, view=view, ephemeral=True
        )

    @discord.ui.button(label="Done", style=discord.ButtonStyle.success, row=4)
    async def done(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        embed = self.build_panel_embed(await get_vacants_config(self.guild_id) or {})
        embed.title = f"{EMOJI_ACCEPT} Vacancies System Configuration (Saved)"
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()


# ---------------------- COG ----------------------

class Vacants(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="vacants-setup", description="Configure the vacancies announcement system."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def vacants_setup(self, interaction: discord.Interaction):
        cfg = await get_vacants_config(interaction.guild_id) or {}
        view = VacantsSetupView(self.bot, interaction.guild_id)
        embed = view.build_panel_embed(cfg)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(
        name="open-vacants", description="Announce open vacancies in the configured channel."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def open_vacants(self, interaction: discord.Interaction):
        cfg = await get_vacants_config(interaction.guild_id)
        if not cfg or not cfg.get("channel_id"):
            await interaction.response.send_message(
                f"{EMOJI_DENIED} The vacancies channel hasn't been configured yet. "
                "Run `/vacants-setup` first.",
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(cfg["channel_id"])
        if channel is None:
            await interaction.response.send_message(
                f"{EMOJI_DENIED} The configured vacancies channel no longer exists. "
                "Run `/vacants-setup` to set a new one.",
                ephemeral=True,
            )
            return

        embed = build_vacants_embed(interaction.guild, cfg)
        view = build_vacants_view(cfg)
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(
            f"{EMOJI_ACCEPT} Vacancies announcement sent to {channel.mention}.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Vacants(bot))
