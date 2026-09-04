import discord
from discord.ext import commands
from datetime import datetime, timedelta, timezone
import re
from typing import Optional, Union

SYSTEM_COLOR = 0xcef3f1

RELOJ = "<:RelojEmoji:1544417450852880434>"
RELOJ_ARENA = "<:RelojArenaEmoji:1544417426375053343>"
PLUMA = "<:PlumaEmoji:1544417398113968328>"
LUPA = "<:Lupaemoji:1544417373921218580>"
DENEGADO = "<:DenegadoEmoji:1544417342904078367>"
AVISO = "<:AvisoEmoji:1544417307139244082>"
ACEPTAR = "<:Aceptar:1544417278563586138>"


def parse_time(time_str: str) -> Optional[timedelta]:
    match = re.fullmatch(r"(\d+)([smhdw])", time_str.lower())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    return timedelta(seconds=value * multipliers[unit])


def is_staff_or_admin(member: discord.Member, bot) -> bool:
    config = bot.bot_configs.get(member.guild.id, {})
    staff_roles = set(config.get("staff_roles", []))
    admin_roles = set(config.get("admin_roles", []))
    member_roles = {r.id for r in member.roles}
    return bool(member_roles & (staff_roles | admin_roles)) or member.guild_permissions.administrator


async def send_dm_sanction(user: discord.User, action: str, reason: str, duration: str = None, guild_name: str = None):
    embed = discord.Embed(
        title=f"{AVISO} Sanción recibida",
        color=SYSTEM_COLOR,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="Acción", value=action, inline=True)
    if duration:
        embed.add_field(name="Duración", value=duration, inline=True)
    embed.add_field(name="Razón", value=reason or "No especificada", inline=False)
    if guild_name:
        embed.add_field(name="Servidor", value=guild_name, inline=False)
    embed.set_footer(text="Dead by Bodrios")
    try:
        await user.send(embed=embed)
    except discord.Forbidden:
        pass


async def log_action(bot, guild: discord.Guild, embed: discord.Embed):
    config = bot.bot_configs.get(guild.id, {})
    log_channel_id = config.get("log_channel")
    if log_channel_id:
        channel = guild.get_channel(log_channel_id)
        if channel:
            try:
                await channel.send(embed=embed)
            except Exception:
                pass


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="lock")
    @commands.guild_only()
    async def lock(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        if not is_staff_or_admin(ctx.author, self.bot):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos.", color=SYSTEM_COLOR))
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send(embed=discord.Embed(description=f"{ACEPTAR} Canal {channel.mention} bloqueado.", color=SYSTEM_COLOR))
        log_embed = discord.Embed(title=f"{AVISO} Canal bloqueado", color=SYSTEM_COLOR, timestamp=datetime.now(timezone.utc))
        log_embed.add_field(name="Canal", value=channel.mention, inline=True)
        log_embed.add_field(name="Moderador", value=ctx.author.mention, inline=True)
        log_embed.set_footer(text="Dead by Bodrios")
        await log_action(self.bot, ctx.guild, log_embed)

    @commands.command(name="unlock")
    @commands.guild_only()
    async def unlock(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        if not is_staff_or_admin(ctx.author, self.bot):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos.", color=SYSTEM_COLOR))
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send(embed=discord.Embed(description=f"{ACEPTAR} Canal {channel.mention} desbloqueado.", color=SYSTEM_COLOR))
        log_embed = discord.Embed(title=f"{AVISO} Canal desbloqueado", color=SYSTEM_COLOR, timestamp=datetime.now(timezone.utc))
        log_embed.add_field(name="Canal", value=channel.mention, inline=True)
        log_embed.add_field(name="Moderador", value=ctx.author.mention, inline=True)
        log_embed.set_footer(text="Dead by Bodrios")
        await log_action(self.bot, ctx.guild, log_embed)

    @commands.command(name="ban")
    @commands.guild_only()
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No especificada"):
        if not is_staff_or_admin(ctx.author, self.bot):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos.", color=SYSTEM_COLOR))
        if member.top_role >= ctx.author.top_role and not ctx.author.guild_permissions.administrator:
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No puedes banear a alguien con rol igual o superior.", color=SYSTEM_COLOR))
        await send_dm_sanction(member, "Ban permanente", reason, guild_name=ctx.guild.name)
        await member.ban(reason=f"{ctx.author} | {reason}")
        await ctx.send(embed=discord.Embed(description=f"{ACEPTAR} {member.mention} ha sido baneado.\n**Razón:** {reason}", color=SYSTEM_COLOR))
        log_embed = discord.Embed(title=f"{AVISO} Usuario baneado", color=SYSTEM_COLOR, timestamp=datetime.now(timezone.utc))
        log_embed.add_field(name="Usuario", value=f"{member} (`{member.id}`)", inline=True)
        log_embed.add_field(name="Moderador", value=ctx.author.mention, inline=True)
        log_embed.add_field(name="Razón", value=reason, inline=False)
        log_embed.set_footer(text="Dead by Bodrios")
        await log_action(self.bot, ctx.guild, log_embed)

    @commands.command(name="tempban")
    @commands.guild_only()
    async def tempban(self, ctx: commands.Context, member: discord.Member, time: str, *, reason: str = "No especificada"):
        if not is_staff_or_admin(ctx.author, self.bot):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos.", color=SYSTEM_COLOR))
        duration = parse_time(time)
        if not duration:
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} Formato de tiempo inválido. Usa: `30s`, `5m`, `2h`, `1d`, `1w`", color=SYSTEM_COLOR))
        await send_dm_sanction(member, "Ban temporal", reason, duration=time, guild_name=ctx.guild.name)
        await member.ban(reason=f"{ctx.author} | Tempban {time} | {reason}")
        unban_at = datetime.now(timezone.utc) + duration
        await self.bot.db.tempbans.update_one(
            {"guild_id": ctx.guild.id, "user_id": member.id},
            {"$set": {"unban_at": unban_at, "reason": reason, "moderator_id": ctx.author.id}},
            upsert=True
        )
        await ctx.send(embed=discord.Embed(description=f"{ACEPTAR} {member.mention} ha sido baneado temporalmente por **{time}**.\n**Razón:** {reason}", color=SYSTEM_COLOR))
        log_embed = discord.Embed(title=f"{AVISO} Usuario baneado temporalmente", color=SYSTEM_COLOR, timestamp=datetime.now(timezone.utc))
        log_embed.add_field(name="Usuario", value=f"{member} (`{member.id}`)", inline=True)
        log_embed.add_field(name="Moderador", value=ctx.author.mention, inline=True)
        log_embed.add_field(name="Duración", value=time, inline=True)
        log_embed.add_field(name="Razón", value=reason, inline=False)
        log_embed.set_footer(text="Dead by Bodrios")
        await log_action(self.bot, ctx.guild, log_embed)

    @commands.command(name="unban")
    @commands.guild_only()
    async def unban(self, ctx: commands.Context, user: Union[discord.User, int], *, reason: str = "No especificada"):
        if not is_staff_or_admin(ctx.author, self.bot):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos.", color=SYSTEM_COLOR))
        user_id = user.id if isinstance(user, discord.User) else user
        try:
            await ctx.guild.unban(discord.Object(id=user_id), reason=f"{ctx.author} | {reason}")
        except discord.NotFound:
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} Ese usuario no está baneado.", color=SYSTEM_COLOR))
        await self.bot.db.tempbans.delete_one({"guild_id": ctx.guild.id, "user_id": user_id})
        await ctx.send(embed=discord.Embed(description=f"{ACEPTAR} Usuario `{user_id}` desbaneado.\n**Razón:** {reason}", color=SYSTEM_COLOR))
        log_embed = discord.Embed(title=f"{AVISO} Usuario desbaneado", color=SYSTEM_COLOR, timestamp=datetime.now(timezone.utc))
        log_embed.add_field(name="Usuario ID", value=str(user_id), inline=True)
        log_embed.add_field(name="Moderador", value=ctx.author.mention, inline=True)
        log_embed.add_field(name="Razón", value=reason, inline=False)
        log_embed.set_footer(text="Dead by Bodrios")
        await log_action(self.bot, ctx.guild, log_embed)

    @commands.command(name="kick")
    @commands.guild_only()
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No especificada"):
        if not is_staff_or_admin(ctx.author, self.bot):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos.", color=SYSTEM_COLOR))
        if member.top_role >= ctx.author.top_role and not ctx.author.guild_permissions.administrator:
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No puedes expulsar a alguien con rol igual o superior.", color=SYSTEM_COLOR))
        await send_dm_sanction(member, "Expulsión (Kick)", reason, guild_name=ctx.guild.name)
        await member.kick(reason=f"{ctx.author} | {reason}")
        await ctx.send(embed=discord.Embed(description=f"{ACEPTAR} {member.mention} ha sido expulsado.\n**Razón:** {reason}", color=SYSTEM_COLOR))
        log_embed = discord.Embed(title=f"{AVISO} Usuario expulsado", color=SYSTEM_COLOR, timestamp=datetime.now(timezone.utc))
        log_embed.add_field(name="Usuario", value=f"{member} (`{member.id}`)", inline=True)
        log_embed.add_field(name="Moderador", value=ctx.author.mention, inline=True)
        log_embed.add_field(name="Razón", value=reason, inline=False)
        log_embed.set_footer(text="Dead by Bodrios")
        await log_action(self.bot, ctx.guild, log_embed)

    @commands.command(name="mute", aliases=["timeout"])
    @commands.guild_only()
    async def mute(self, ctx: commands.Context, member: discord.Member, time: str, *, reason: str = "No especificada"):
        if not is_staff_or_admin(ctx.author, self.bot):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos.", color=SYSTEM_COLOR))
        duration = parse_time(time)
        if not duration:
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} Formato de tiempo inválido. Usa: `30s`, `5m`, `2h`, `1d`, `1w`", color=SYSTEM_COLOR))
        if duration.total_seconds() > 28 * 86400:
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} El timeout máximo de Discord es 28 días.", color=SYSTEM_COLOR))
        until = datetime.now(timezone.utc) + duration
        await member.timeout(until, reason=f"{ctx.author} | {reason}")
        await send_dm_sanction(member, "Timeout (Mute)", reason, duration=time, guild_name=ctx.guild.name)
        await ctx.send(embed=discord.Embed(description=f"{ACEPTAR} {member.mention} ha sido silenciado por **{time}**.\n**Razón:** {reason}", color=SYSTEM_COLOR))
        log_embed = discord.Embed(title=f"{AVISO} Usuario silenciado (Timeout)", color=SYSTEM_COLOR, timestamp=datetime.now(timezone.utc))
        log_embed.add_field(name="Usuario", value=f"{member} (`{member.id}`)", inline=True)
        log_embed.add_field(name="Moderador", value=ctx.author.mention, inline=True)
        log_embed.add_field(name="Duración", value=time, inline=True)
        log_embed.add_field(name="Razón", value=reason, inline=False)
        log_embed.set_footer(text="Dead by Bodrios")
        await log_action(self.bot, ctx.guild, log_embed)

    @commands.command(name="unmute")
    @commands.guild_only()
    async def unmute(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No especificada"):
        if not is_staff_or_admin(ctx.author, self.bot):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos.", color=SYSTEM_COLOR))
        await member.timeout(None, reason=f"{ctx.author} | {reason}")
        await send_dm_sanction(member, "Timeout removido", reason, guild_name=ctx.guild.name)
        await ctx.send(embed=discord.Embed(description=f"{ACEPTAR} Se ha removido el timeout de {member.mention}.\n**Razón:** {reason}", color=SYSTEM_COLOR))
        log_embed = discord.Embed(title=f"{AVISO} Timeout removido", color=SYSTEM_COLOR, timestamp=datetime.now(timezone.utc))
        log_embed.add_field(name="Usuario", value=f"{member} (`{member.id}`)", inline=True)
        log_embed.add_field(name="Moderador", value=ctx.author.mention, inline=True)
        log_embed.add_field(name="Razón", value=reason, inline=False)
        log_embed.set_footer(text="Dead by Bodrios")
        await log_action(self.bot, ctx.guild, log_embed)

    @commands.command(name="warn")
    @commands.guild_only()
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No especificada"):
        if not is_staff_or_admin(ctx.author, self.bot):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos.", color=SYSTEM_COLOR))
        warn_data = {
            "reason": reason,
            "moderator_id": ctx.author.id,
            "timestamp": datetime.now(timezone.utc),
            "auto": False
        }
        await self.bot.db.warns.update_one(
            {"guild_id": ctx.guild.id, "user_id": member.id},
            {"$push": {"warns": warn_data}},
            upsert=True
        )
        doc = await self.bot.db.warns.find_one({"guild_id": ctx.guild.id, "user_id": member.id})
        total = len(doc.get("warns", [])) if doc else 1
        await send_dm_sanction(member, f"Advertencia ({total})", reason, guild_name=ctx.guild.name)
        await ctx.send(embed=discord.Embed(description=f"{ACEPTAR} {member.mention} ha recibido una advertencia.\n**Razón:** {reason}\n**Total:** {total}", color=SYSTEM_COLOR))
        log_embed = discord.Embed(title=f"{AVISO} Advertencia aplicada", color=SYSTEM_COLOR, timestamp=datetime.now(timezone.utc))
        log_embed.add_field(name="Usuario", value=f"{member} (`{member.id}`)", inline=True)
        log_embed.add_field(name="Moderador", value=ctx.author.mention, inline=True)
        log_embed.add_field(name="Total warns", value=str(total), inline=True)
        log_embed.add_field(name="Razón", value=reason, inline=False)
        log_embed.set_footer(text="Dead by Bodrios")
        await log_action(self.bot, ctx.guild, log_embed)

    @commands.command(name="warnings", aliases=["warns"])
    @commands.guild_only()
    async def warnings(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        member = member or ctx.author
        if member != ctx.author and not is_staff_or_admin(ctx.author, self.bot):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos.", color=SYSTEM_COLOR))
        doc = await self.bot.db.warns.find_one({"guild_id": ctx.guild.id, "user_id": member.id})
        warns = doc.get("warns", []) if doc else []
        if not warns:
            return await ctx.send(embed=discord.Embed(description=f"{LUPA} {member.mention} no tiene advertencias.", color=SYSTEM_COLOR))
        embed = discord.Embed(title=f"{LUPA} Advertencias de {member}", color=SYSTEM_COLOR, timestamp=datetime.now(timezone.utc))
        for i, w in enumerate(warns, 1):
            mod = ctx.guild.get_member(w["moderator_id"])
            mod_name = mod.mention if mod else f"`{w['moderator_id']}`"
            ts = w["timestamp"]
            ts_str = discord.utils.format_dt(ts, "R") if isinstance(ts, datetime) else "Desconocido"
            auto = " (Automod)" if w.get("auto") else ""
            embed.add_field(name=f"#{i}{auto}", value=f"**Razón:** {w['reason']}\n**Mod:** {mod_name}\n**Fecha:** {ts_str}", inline=False)
        embed.set_footer(text=f"Total: {len(warns)} • Dead by Bodrios")
        await ctx.send(embed=embed)

    @commands.command(name="delwarn")
    @commands.guild_only()
    async def delwarn(self, ctx: commands.Context, member: discord.Member, index: int):
        if not is_staff_or_admin(ctx.author, self.bot):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos.", color=SYSTEM_COLOR))
        doc = await self.bot.db.warns.find_one({"guild_id": ctx.guild.id, "user_id": member.id})
        if not doc or not doc.get("warns"):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} Ese usuario no tiene advertencias.", color=SYSTEM_COLOR))
        warns = doc["warns"]
        if index < 1 or index > len(warns):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} Índice inválido.", color=SYSTEM_COLOR))
        removed = warns.pop(index - 1)
        await self.bot.db.warns.update_one({"guild_id": ctx.guild.id, "user_id": member.id}, {"$set": {"warns": warns}})
        await ctx.send(embed=discord.Embed(description=f"{ACEPTAR} Advertencia #{index} eliminada de {member.mention}.\n**Razón eliminada:** {removed['reason']}", color=SYSTEM_COLOR))

    @commands.command(name="editreason")
    @commands.guild_only()
    async def editreason(self, ctx: commands.Context, member: discord.Member, index: int, *, new_reason: str):
        if not is_staff_or_admin(ctx.author, self.bot):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos.", color=SYSTEM_COLOR))
        doc = await self.bot.db.warns.find_one({"guild_id": ctx.guild.id, "user_id": member.id})
        if not doc or not doc.get("warns"):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} Ese usuario no tiene advertencias.", color=SYSTEM_COLOR))
        warns = doc["warns"]
        if index < 1 or index > len(warns):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} Índice inválido.", color=SYSTEM_COLOR))
        old = warns[index - 1]["reason"]
        warns[index - 1]["reason"] = new_reason
        await self.bot.db.warns.update_one({"guild_id": ctx.guild.id, "user_id": member.id}, {"$set": {"warns": warns}})
        await ctx.send(embed=discord.Embed(description=f"{ACEPTAR} Razón de la advertencia #{index} actualizada.\n**Antes:** {old}\n**Ahora:** {new_reason}", color=SYSTEM_COLOR))

    @commands.command(name="note")
    @commands.guild_only()
    async def note(self, ctx: commands.Context, member: discord.Member, *, content: str):
        if not is_staff_or_admin(ctx.author, self.bot):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos.", color=SYSTEM_COLOR))
        note_data = {"content": content, "moderator_id": ctx.author.id, "timestamp": datetime.now(timezone.utc)}
        await self.bot.db.notes.update_one({"guild_id": ctx.guild.id, "user_id": member.id}, {"$push": {"notes": note_data}}, upsert=True)
        await ctx.send(embed=discord.Embed(description=f"{ACEPTAR} Nota añadida a {member.mention}.", color=SYSTEM_COLOR))

    @commands.command(name="viewnotes", aliases=["notes"])
    @commands.guild_only()
    async def viewnotes(self, ctx: commands.Context, member: discord.Member):
        if not is_staff_or_admin(ctx.author, self.bot):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos.", color=SYSTEM_COLOR))
        doc = await self.bot.db.notes.find_one({"guild_id": ctx.guild.id, "user_id": member.id})
        notes = doc.get("notes", []) if doc else []
        if not notes:
            return await ctx.send(embed=discord.Embed(description=f"{LUPA} {member.mention} no tiene notas.", color=SYSTEM_COLOR))
        embed = discord.Embed(title=f"{PLUMA} Notas de {member}", color=SYSTEM_COLOR)
        for i, n in enumerate(notes, 1):
            mod = ctx.guild.get_member(n["moderator_id"])
            mod_name = mod.mention if mod else f"`{n['moderator_id']}`"
            ts = n["timestamp"]
            ts_str = discord.utils.format_dt(ts, "R") if isinstance(ts, datetime) else "Desconocido"
            embed.add_field(name=f"Nota #{i}", value=f"{n['content']}\n— {mod_name} • {ts_str}", inline=False)
        embed.set_footer(text="Dead by Bodrios")
        await ctx.send(embed=embed)

    @commands.command(name="delnote")
    @commands.guild_only()
    async def delnote(self, ctx: commands.Context, member: discord.Member, index: int):
        if not is_staff_or_admin(ctx.author, self.bot):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos.", color=SYSTEM_COLOR))
        doc = await self.bot.db.notes.find_one({"guild_id": ctx.guild.id, "user_id": member.id})
        if not doc or not doc.get("notes"):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} Ese usuario no tiene notas.", color=SYSTEM_COLOR))
        notes = doc["notes"]
        if index < 1 or index > len(notes):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} Índice inválido.", color=SYSTEM_COLOR))
        notes.pop(index - 1)
        await self.bot.db.notes.update_one({"guild_id": ctx.guild.id, "user_id": member.id}, {"$set": {"notes": notes}})
        await ctx.send(embed=discord.Embed(description=f"{ACEPTAR} Nota #{index} eliminada de {member.mention}.", color=SYSTEM_COLOR))

    @commands.command(name="slowmode")
    @commands.guild_only()
    async def slowmode(self, ctx: commands.Context, seconds: int, channel: Optional[discord.TextChannel] = None):
        if not is_staff_or_admin(ctx.author, self.bot):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos.", color=SYSTEM_COLOR))
        if seconds < 0 or seconds > 21600:
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} El slowmode debe estar entre 0 y 21600 segundos.", color=SYSTEM_COLOR))
        channel = channel or ctx.channel
        await channel.edit(slowmode_delay=seconds)
        await ctx.send(embed=discord.Embed(description=f"{ACEPTAR} Slowmode de {channel.mention} establecido en **{seconds}s**.", color=SYSTEM_COLOR))

    @commands.command(name="clear", aliases=["purge"])
    @commands.guild_only()
    async def clear(self, ctx: commands.Context, amount: int):
        if not is_staff_or_admin(ctx.author, self.bot):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos.", color=SYSTEM_COLOR))
        if amount < 1 or amount > 100:
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} Debes especificar un número entre 1 y 100.", color=SYSTEM_COLOR))
        deleted = await ctx.channel.purge(limit=amount + 1)
        msg = await ctx.send(embed=discord.Embed(description=f"{ACEPTAR} Se eliminaron **{len(deleted)-1}** mensajes.", color=SYSTEM_COLOR))
        await msg.delete(delay=5)


class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="dm")
    @commands.guild_only()
    async def dm(self, ctx: commands.Context, member: discord.Member, *, message: str):
        if not is_staff_or_admin(ctx.author, self.bot):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos.", color=SYSTEM_COLOR))
        embed = discord.Embed(description=message, color=SYSTEM_COLOR, timestamp=datetime.now(timezone.utc))
        embed.set_footer(text="Dead by Bodrios")
        try:
            await member.send(embed=embed)
            await ctx.send(embed=discord.Embed(description=f"{ACEPTAR} Mensaje enviado a {member.mention}.", color=SYSTEM_COLOR))
        except discord.Forbidden:
            await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No pude enviar el DM.", color=SYSTEM_COLOR))

    @commands.command(name="addrole")
    @commands.guild_only()
    async def addrole(self, ctx: commands.Context, member: discord.Member, role: discord.Role):
        if not is_staff_or_admin(ctx.author, self.bot):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos.", color=SYSTEM_COLOR))
        if role >= ctx.author.top_role and not ctx.author.guild_permissions.administrator:
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No puedes asignar un rol igual o superior al tuyo.", color=SYSTEM_COLOR))
        await member.add_roles(role, reason=f"Por {ctx.author}")
        await ctx.send(embed=discord.Embed(description=f"{ACEPTAR} Rol {role.mention} añadido a {member.mention}.", color=SYSTEM_COLOR))

    @commands.command(name="removerole")
    @commands.guild_only()
    async def removerole(self, ctx: commands.Context, member: discord.Member, role: discord.Role):
        if not is_staff_or_admin(ctx.author, self.bot):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos.", color=SYSTEM_COLOR))
        await member.remove_roles(role, reason=f"Por {ctx.author}")
        await ctx.send(embed=discord.Embed(description=f"{ACEPTAR} Rol {role.mention} removido de {member.mention}.", color=SYSTEM_COLOR))

    @commands.command(name="nick", aliases=["nickname"])
    @commands.guild_only()
    async def nick(self, ctx: commands.Context, member: discord.Member, *, nickname: str = None):
        if not is_staff_or_admin(ctx.author, self.bot):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos.", color=SYSTEM_COLOR))
        await member.edit(nick=nickname)
        if nickname:
            await ctx.send(embed=discord.Embed(description=f"{ACEPTAR} Nickname de {member.mention} cambiado a **{nickname}**.", color=SYSTEM_COLOR))
        else:
            await ctx.send(embed=discord.Embed(description=f"{ACEPTAR} Nickname de {member.mention} reseteado.", color=SYSTEM_COLOR))

    @commands.command(name="userinfo", aliases=["ui", "whois"])
    @commands.guild_only()
    async def userinfo(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        member = member or ctx.author
        embed = discord.Embed(title=f"{LUPA} Información de {member}", color=member.color if member.color.value != 0 else SYSTEM_COLOR, timestamp=datetime.now(timezone.utc))
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=f"`{member.id}`", inline=True)
        embed.add_field(name="Nickname", value=member.nick or "Ninguno", inline=True)
        embed.add_field(name="Bot", value="Sí" if member.bot else "No", inline=True)
        embed.add_field(name="Cuenta creada", value=discord.utils.format_dt(member.created_at, "R"), inline=True)
        embed.add_field(name="Se unió", value=discord.utils.format_dt(member.joined_at, "R") if member.joined_at else "Desconocido", inline=True)
        roles = [r.mention for r in member.roles if r != ctx.guild.default_role]
        embed.add_field(name=f"Roles [{len(roles)}]", value=" ".join(roles) if roles else "Ninguno", inline=False)
        embed.set_footer(text="Dead by Bodrios")
        await ctx.send(embed=embed)

    @commands.command(name="cmds", aliases=["commands", "help"])
    async def cmds(self, ctx: commands.Context):
        embed = discord.Embed(title=f"{PLUMA} Comandos de Dead by Bodrios", description="Prefijo: `?` (no distingue mayúsculas)", color=SYSTEM_COLOR)
        embed.add_field(name="Moderación", value="`?lock` `?unlock`\n`?ban` `?tempban` `?unban`\n`?kick`\n`?mute` `?unmute` `?timeout`\n`?warn` `?warnings` `?delwarn` `?editreason`\n`?note` `?viewnotes` `?delnote`\n`?slowmode` `?clear`", inline=True)
        embed.add_field(name="Utilidad", value="`?dm`\n`?addrole` `?removerole`\n`?nick`\n`?userinfo`\n`?cmds`", inline=True)
        embed.add_field(name="Tickets", value="`?adduser` `?removeuser`\n`?close` `?delete`\n`?rename`", inline=True)
        embed.add_field(name="Configuración + Giveaways (Slash)", value="`/welcome-setup` `/bot-setup` `/tickets-setup`\n`/giveaway-create` `/giveaway-end` `/giveaway-reroll` `/giveaway-list`", inline=False)
        embed.set_footer(text="Dead by Bodrios")
        await ctx.send(embed=embed)


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="adduser")
    @commands.guild_only()
    async def adduser(self, ctx: commands.Context, member: discord.Member):
        if not is_staff_or_admin(ctx.author, self.bot):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos.", color=SYSTEM_COLOR))
        ticket = await self.bot.db.tickets.find_one({"channel_id": ctx.channel.id})
        if not ticket:
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} Este canal no es un ticket.", color=SYSTEM_COLOR))
        await ctx.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
        await ctx.send(embed=discord.Embed(description=f"{ACEPTAR} {member.mention} ha sido añadido al ticket.", color=SYSTEM_COLOR))

    @commands.command(name="removeuser")
    @commands.guild_only()
    async def removeuser(self, ctx: commands.Context, member: discord.Member):
        if not is_staff_or_admin(ctx.author, self.bot):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos.", color=SYSTEM_COLOR))
        ticket = await self.bot.db.tickets.find_one({"channel_id": ctx.channel.id})
        if not ticket:
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} Este canal no es un ticket.", color=SYSTEM_COLOR))
        await ctx.channel.set_permissions(member, overwrite=None)
        await ctx.send(embed=discord.Embed(description=f"{ACEPTAR} {member.mention} ha sido removido del ticket.", color=SYSTEM_COLOR))

    @commands.command(name="close")
    @commands.guild_only()
    async def close(self, ctx: commands.Context):
        ticket = await self.bot.db.tickets.find_one({"channel_id": ctx.channel.id})
        if not ticket:
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} Este canal no es un ticket.", color=SYSTEM_COLOR))
        if not is_staff_or_admin(ctx.author, self.bot) and ctx.author.id != ticket.get("user_id"):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos para cerrar este ticket.", color=SYSTEM_COLOR))
        await ctx.channel.set_permissions(ctx.guild.default_role, view_channel=False)
        await ctx.send(embed=discord.Embed(description=f"{ACEPTAR} Ticket cerrado por {ctx.author.mention}. Usa `?delete` para eliminarlo.", color=SYSTEM_COLOR))
        await self.bot.db.tickets.update_one({"channel_id": ctx.channel.id}, {"$set": {"closed": True, "closed_by": ctx.author.id, "closed_at": datetime.now(timezone.utc)}})

    @commands.command(name="delete")
    @commands.guild_only()
    async def delete_ticket(self, ctx: commands.Context):
        if not is_staff_or_admin(ctx.author, self.bot):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos.", color=SYSTEM_COLOR))
        ticket = await self.bot.db.tickets.find_one({"channel_id": ctx.channel.id})
        if not ticket:
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} Este canal no es un ticket.", color=SYSTEM_COLOR))
        await ctx.send(embed=discord.Embed(description=f"{RELOJ_ARENA} Eliminando ticket en 5 segundos...", color=SYSTEM_COLOR))
        await self.bot.db.tickets.delete_one({"channel_id": ctx.channel.id})
        await ctx.channel.delete(reason=f"Ticket eliminado por {ctx.author}")

    @commands.command(name="rename")
    @commands.guild_only()
    async def rename(self, ctx: commands.Context, *, new_name: str):
        if not is_staff_or_admin(ctx.author, self.bot):
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} No tienes permisos.", color=SYSTEM_COLOR))
        ticket = await self.bot.db.tickets.find_one({"channel_id": ctx.channel.id})
        if not ticket:
            return await ctx.send(embed=discord.Embed(description=f"{DENEGADO} Este canal no es un ticket.", color=SYSTEM_COLOR))
        await ctx.channel.edit(name=new_name[:100])
        await ctx.send(embed=discord.Embed(description=f"{ACEPTAR} Ticket renombrado a **{new_name}**.", color=SYSTEM_COLOR))


async def setup(bot):
    await bot.add_cog(Moderation(bot))
    await bot.add_cog(Utility(bot))
    await bot.add_cog(Tickets(bot))
