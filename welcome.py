import discord
from discord import app_commands
from discord.ext import commands

from config import COLOR_DEFAULT, COLOR_SUCCESS, EMOJI_ACCEPT, EMOJI_PEN, FOOTER_TEXT
from database import get_welcome_config, set_welcome_config

DEFAULT_MESSAGE = "Welcome to **{server}**, {mention}! We're glad to have you here."


def hex_to_int(value: str) -> int | None:
    value = value.strip().lstrip("#")
    try:
        return int(value, 16)
    except ValueError:
        return None


def build_welcome_embed(member: discord.Member, cfg: dict) -> discord.Embed:
    message = (cfg or {}).get("message", DEFAULT_MESSAGE)
    message = message.replace("{mention}", member.mention).replace(
        "{user}", str(member)
    ).replace("{server}", member.guild.name).replace(
        "{member_count}", str(member.guild.member_count)
    )

    color = (cfg or {}).get("color", COLOR_DEFAULT)
    embed = discord.Embed(description=message, color=color)
    embed.set_author(
        name=f"Welcome to {member.guild.name}!",
        icon_url=member.guild.icon.url if member.guild.icon else discord.Embed.Empty,
    )
    embed.set_thumbnail(url=member.display_avatar.url)

    image = (cfg or {}).get("image")
    if image:
        embed.set_image(url=image)

    recommended = (cfg or {}).get("recommended_channels", [])
    if recommended:
        mentions = " ".join(f"<#{cid}>" for cid in recommended)
        embed.add_field(name="Recommended Channels", value=mentions, inline=False)

    embed.set_footer(text=FOOTER_TEXT)
    return embed


def build_welcome_view(cfg: dict) -> discord.ui.View | None:
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

class MessageModal(discord.ui.Modal, title="Set Welcome Message"):
    message = discord.ui.TextInput(
        label="Welcome message",
        style=discord.TextStyle.paragraph,
        placeholder="Use {mention}, {user}, {server}, {member_count}",
        max_length=1000,
        required=True,
    )

    def __init__(self, panel: "WelcomeSetupView"):
        super().__init__()
        self.panel = panel

    async def on_submit(self, interaction: discord.Interaction):
        await set_welcome_config(interaction.guild_id, {"message": str(self.message)})
        await self.panel.refresh(interaction, "Welcome message updated.")


class ColorModal(discord.ui.Modal, title="Set Embed Color"):
    color = discord.ui.TextInput(
        label="Hex color (e.g. #5865F2)",
        placeholder="#5865F2",
        max_length=7,
        required=True,
    )

    def __init__(self, panel: "WelcomeSetupView"):
        super().__init__()
        self.panel = panel

    async def on_submit(self, interaction: discord.Interaction):
        parsed = hex_to_int(str(self.color))
        if parsed is None:
            await interaction.response.send_message(
                "That is not a valid hex color.", ephemeral=True
            )
            return
        await set_welcome_config(interaction.guild_id, {"color": parsed})
        await self.panel.refresh(interaction, "Embed color updated.")


class ImageModal(discord.ui.Modal, title="Set Image / GIF"):
    url = discord.ui.TextInput(
        label="Image or GIF URL",
        placeholder="https://example.com/banner.gif",
        max_length=300,
        required=True,
    )

    def __init__(self, panel: "WelcomeSetupView"):
        super().__init__()
        self.panel = panel

    async def on_submit(self, interaction: discord.Interaction):
        await set_welcome_config(interaction.guild_id, {"image": str(self.url)})
        await self.panel.refresh(interaction, "Welcome image updated.")


class LinkModal(discord.ui.Modal, title="Add Button Link"):
    label = discord.ui.TextInput(label="Button label", max_length=80, required=True)
    url = discord.ui.TextInput(
        label="URL", placeholder="https://discord.gg/...", max_length=300, required=True
    )

    def __init__(self, panel: "WelcomeSetupView"):
        super().__init__()
        self.panel = panel

    async def on_submit(self, interaction: discord.Interaction):
        if not str(self.url).startswith(("http://", "https://")):
            await interaction.response.send_message(
                "The URL must start with http:// or https://", ephemeral=True
            )
            return
        cfg = await get_welcome_config(interaction.guild_id) or {}
        links = cfg.get("links", [])
        links.append({"label": str(self.label), "url": str(self.url)})
        await set_welcome_config(interaction.guild_id, {"links": links})
        await self.panel.refresh(interaction, "Link button added.")


# ---------------------- SELECTS ----------------------

class WelcomeChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, panel: "WelcomeSetupView"):
        super().__init__(
            placeholder="Select the welcome channel",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
        )
        self.panel = panel

    async def callback(self, interaction: discord.Interaction):
        await set_welcome_config(
            interaction.guild_id, {"channel_id": self.values[0].id}
        )
        await self.panel.refresh(interaction, f"Welcome channel set to {self.values[0].mention}.")


class RecommendedChannelsSelect(discord.ui.ChannelSelect):
    def __init__(self, panel: "WelcomeSetupView"):
        super().__init__(
            placeholder="Select up to 5 recommended channels",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=5,
        )
        self.panel = panel

    async def callback(self, interaction: discord.Interaction):
        ids = [c.id for c in self.values]
        await set_welcome_config(interaction.guild_id, {"recommended_channels": ids})
        await self.panel.refresh(interaction, "Recommended channels updated.")


# ---------------------- MAIN PANEL VIEW ----------------------

class WelcomeSetupView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild_id: int):
        super().__init__(timeout=600)
        self.bot = bot
        self.guild_id = guild_id
        self.add_item(WelcomeChannelSelect(self))
        self.add_item(RecommendedChannelsSelect(self))

    async def refresh(self, interaction: discord.Interaction, note: str):
        cfg = await get_welcome_config(self.guild_id) or {}
        embed = self.build_panel_embed(cfg, note)
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    def build_panel_embed(self, cfg: dict, note: str | None = None) -> discord.Embed:
        embed = discord.Embed(
            title=f"{EMOJI_PEN} Welcome System Configuration",
            description="Use the buttons and menus below to configure the welcome system.",
            color=COLOR_DEFAULT,
        )
        channel = f"<#{cfg['channel_id']}>" if cfg.get("channel_id") else "Not set"
        embed.add_field(name="Channel", value=channel, inline=True)
        embed.add_field(
            name="Color", value=f"#{cfg.get('color', COLOR_DEFAULT):06X}", inline=True
        )
        embed.add_field(
            name="Image / GIF", value="Set" if cfg.get("image") else "Not set", inline=True
        )
        embed.add_field(
            name="Message",
            value=(cfg.get("message", DEFAULT_MESSAGE))[:200],
            inline=False,
        )
        recommended = cfg.get("recommended_channels", [])
        embed.add_field(
            name="Recommended Channels",
            value=" ".join(f"<#{c}>" for c in recommended) if recommended else "None",
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

    @discord.ui.button(label="Set Message", style=discord.ButtonStyle.primary, row=2)
    async def set_message(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MessageModal(self))

    @discord.ui.button(label="Set Color", style=discord.ButtonStyle.primary, row=2)
    async def set_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ColorModal(self))

    @discord.ui.button(label="Set Image/GIF", style=discord.ButtonStyle.secondary, row=2)
    async def set_image(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ImageModal(self))

    @discord.ui.button(label="Add Link Button", style=discord.ButtonStyle.secondary, row=3)
    async def add_link(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LinkModal(self))

    @discord.ui.button(label="Clear Links", style=discord.ButtonStyle.danger, row=3)
    async def clear_links(self, interaction: discord.Interaction, button: discord.ui.Button):
        await set_welcome_config(self.guild_id, {"links": []})
        await self.refresh(interaction, "Link buttons cleared.")

    @discord.ui.button(label="Preview", style=discord.ButtonStyle.success, row=4)
    async def preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await get_welcome_config(self.guild_id) or {}
        embed = build_welcome_embed(interaction.user, cfg)
        view = build_welcome_view(cfg)
        await interaction.response.send_message(
            content="**Preview:**", embed=embed, view=view, ephemeral=True
        )

    @discord.ui.button(label="Done", style=discord.ButtonStyle.success, row=4)
    async def done(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        embed = self.build_panel_embed(await get_welcome_config(self.guild_id) or {})
        embed.title = f"{EMOJI_ACCEPT} Welcome System Configuration (Saved)"
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()


# ---------------------- COG ----------------------

class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="welcome-setup", description="Configure the server's welcome system."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def welcome_setup(self, interaction: discord.Interaction):
        cfg = await get_welcome_config(interaction.guild_id) or {}
        view = WelcomeSetupView(self.bot, interaction.guild_id)
        embed = view.build_panel_embed(cfg)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = await get_welcome_config(member.guild.id)
        if not cfg or not cfg.get("channel_id"):
            return
        channel = member.guild.get_channel(cfg["channel_id"])
        if channel is None:
            return
        embed = build_welcome_embed(member, cfg)
        view = build_welcome_view(cfg)
        await channel.send(content=member.mention, embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
