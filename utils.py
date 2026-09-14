import discord
from typing import Optional
from datetime import datetime, timedelta

# ── Custom Emojis ─────────────────────────────────────────────────────────
EMOJI_RELOJ      = "<:RelojEmoji:1549130376537051176>"
EMOJI_RELOJARENA = "<:RelojArenaEmoji:1549130360011493426>"
EMOJI_PLUMA      = "<:PlumaEmoji:1549130341610950706>"
EMOJI_LUPA       = "<:Lupaemoji:1549130325488046251>"
EMOJI_DENEGADO   = "<:DenegadoEmoji:1549130308883058699>"
EMOJI_AVISO      = "<:AvisoEmoji:1549130289153052762>"
EMOJI_ACEPTAR    = "<:Aceptar:1549130267426300044>"

# Aliases útiles
EMOJI_SUCCESS = EMOJI_ACEPTAR
EMOJI_ERROR   = EMOJI_DENEGADO
EMOJI_WARNING = EMOJI_AVISO
EMOJI_INFO    = EMOJI_LUPA
EMOJI_LOADING = EMOJI_RELOJARENA
EMOJI_TIME    = EMOJI_RELOJ
EMOJI_NOTE    = EMOJI_PLUMA

def success_embed(title: str, description: str = None) -> discord.Embed:
    e = discord.Embed(title=f"{EMOJI_SUCCESS} {title}", color=0x57F287)
    if description:
        e.description = description
    return e

def error_embed(title: str, description: str = None) -> discord.Embed:
    e = discord.Embed(title=f"{EMOJI_ERROR} {title}", color=0xED4245)
    if description:
        e.description = description
    return e

def info_embed(title: str, description: str = None) -> discord.Embed:
    e = discord.Embed(title=f"{EMOJI_INFO} {title}", color=0x5865F2)
    if description:
        e.description = description
    return e

def warning_embed(title: str, description: str = None) -> discord.Embed:
    e = discord.Embed(title=f"{EMOJI_WARNING} {title}", color=0xFEE75C)
    if description:
        e.description = description
    return e

def parse_time(time_str: str) -> Optional[int]:
    """'30s', '5m', '2h', '1d', '1w' → segundos. None si inválido."""
    time_str = time_str.lower().strip()
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    if len(time_str) < 2:
        return None
    unit = time_str[-1]
    num = time_str[:-1]
    if unit in units and num.isdigit():
        return int(num) * units[unit]
    if time_str.isdigit():
        return int(time_str)
    return None

def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"

def safe_color(value) -> int:
    """Acepta hex string o int y devuelve int válido para Embed."""
    try:
        if isinstance(value, str):
            value = value.strip().lstrip("#")
            return int(value, 16)
        return int(value)
    except Exception:
        return 0x5865F2
