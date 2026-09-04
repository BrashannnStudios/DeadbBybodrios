import os
import re
import asyncio
import random
import discord
from discord.ext import commands, tasks
from discord import app_commands
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta, timezone
from collections import defaultdict, deque
from flask import Flask
from threading import Thread
from dotenv import load_dotenv
from typing import Optional, List, Dict, Any

load_dotenv()

# ==================== CONSTANTES ====================
SYSTEM_COLOR = 0xcef3f1
RELOJ = "<:RelojEmoji:1544417450852880434>"
RELOJ_ARENA = "<:RelojArenaEmoji:1544417426375053343>"
PLUMA = "<:PlumaEmoji:1544417398113968328>"
LUPA = "<:Lupaemoji:1544417373921218580>"
DENEGADO = "<:DenegadoEmoji:1544417342904078367>"
AVISO = "<:AvisoEmoji:1544417307139244082>"
ACEPTAR = "<:Aceptar:1544417278563586138>"

INVITE_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?(?:discord\.(?:gg|io|me|li)|discordapp\.com/invite|discord\.com/invite)/[a-zA-Z0-9]+",
    re.IGNORECASE
)

# ==================== KEEP-ALIVE ====================
app = Flask("")

@app.route("/")
def home():
    return "Dead by Bodrios is alive"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# ==================== BOT ====================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(
    command_prefix=commands.when_mentioned_or("?"),
    intents=intents,
    case_insensitive=True,
    help_command=None
)

bot.bot_configs: Dict[int, dict] = {}
bot.welcome_configs: Dict[int, dict] = {}
bot.tickets_configs: Dict[int, dict] = {}
bot.flood_tracker: Dict[int, Dict[int, deque]] = defaultdict(lambda: defaultdict(lambda: deque(maxlen=20)))

# ==================== DB ====================
MONGO_URI = os.getenv("MONGO_URI")
client = AsyncIOMotorClient(MONGO_URI)
bot.db = client["deadbybodrios"]

# ==================== HELPERS ====================
def parse_time(time_str: str) -> Optional[timedelta]:
    match = re.fullmatch(r"(\d+)([smhdw])", time_str.lower().strip())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    return timedelta(seconds=value * multipliers[unit])

def replace_vars(text: str, member: discord.Member) -> str:
    if not text:
        return text
    return (
        text.replace("{user}", member.mention)
        .replace("{username}", str(member))
        .replace("{server}", member.guild.name)
        .replace("{membercount}", str(member.guild.member_count))
    )

async def load_all_configs():
    bot.bot_configs.clear()
    bot.welcome_configs.clear()
    bot.tickets_configs.clear()

    async for doc in bot.db.bot_config.find({}):
        bot.bot_configs[doc["guild_id"]] = doc

    async for doc in bot.db.welcome_config.find({}):
        bot.welcome_configs[doc["guild_id"]] = doc

    async for doc in bot.db.tickets_config.find({}):
        bot.tickets_configs[doc["guild_id"]] = doc

async def get_bot_config(guild_id: int) -> dict:
    if guild_id in bot.bot_configs:
        return bot.bot_configs[guild_id]
    doc = await bot.db.bot_config.find_one({"guild_id": guild_id})
    if doc:
        bot.bot_configs[guild_id] = doc
        return doc
    default = {
        "guild_id": guild_id,
        "log_channel": None,
        "staff_roles": [],
        "admin_roles": [],
        "automod": {
            "anti_invite": True,
            "anti_flood": True,
            "flood_limit": 5,
            "flood_seconds": 5
        }
    }
    await bot.db.bot_config.insert_one(default)
    bot.bot_configs[guild_id] = default
    return default

async def get_welcome_config(guild_id: int) -> dict:
    if guild_id in bot.welcome_configs:
        return bot.welcome_configs[guild_id]
    doc = await bot.db.welcome_config.find_one({"guild_id": guild_id})
    if doc:
        bot.welcome_configs[guild_id] = doc
        return doc
    default = {
        "guild_id": guild_id,
        "channel_id": None,
        "message": "¡Bienvenido {user} a **{server}**!\nEres el miembro #{membercount}.",
        "color": SYSTEM_COLOR,
        "footer": "Dead by Bodrios",
        "image": None,
        "recommended_channels": []
    }
    await bot.db.welcome_config.insert_one(default)
    bot.welcome_configs[guild_id] = default
    return default

async def get_tickets_config(guild_id: int) -> dict:
    if guild_id in bot.tickets_configs:
        return bot.tickets_configs[guild_id]
    doc = await bot.db.tickets_config.find_one({"guild_id": guild_id})
    if doc:
        bot.tickets_configs[guild_id] = doc
        return doc
    default = {
        "guild_id": guild_id,
        "category_id": None,
        "panel_channel_id": None,
        "message": "Selecciona una categoría para abrir un ticket.",
        "color": SYSTEM_COLOR,
        "footer": "Dead by Bodrios",
        "image": None,
        "categories": ["Soporte General", "Reportes", "Donaciones"],
        "open_type": "buttons"
    }
    await bot.db.tickets_config.insert_one(default)
    bot.tickets_configs[guild_id] = default
    return default

def is_staff_or_admin(member: discord.Member) -> bool:
    config = bot.bot_configs.get(member.guild.id, {})
    staff = set(config.get("staff_roles", []))
    admin = set(config.get("admin_roles", []))
    roles = {r.id for r in member.roles}
    return bool(roles & (staff | admin)) or member.guild_permissions.administrator

async def send_log(guild: discord.Guild, embed: discord.Embed):
    config = bot.bot_configs.get(guild.id, {})
    channel_id = config.get("log_channel")
    if channel_id:
        channel = guild.get_channel(channel_id)
        if channel:
            try:
                await channel.send(embed=embed)
            except Exception:
                pass

async def add_auto_warn(guild: discord.Guild, member: discord.Member, reason: str):
    warn_data = {
        "reason": reason,
        "moderator_id": bot.user.id,
        "timestamp": datetime.now(timezone.utc),
        "auto": True
    }
    await bot.db.warns.update_one(
        {"guild_id": guild.id, "user_id": member.id},
        {"$push": {"warns": warn_data}},
        upsert=True
    )
    doc = await bot.db.warns.find_one({"guild_id": guild.id, "user_id": member.id})
    total = len(doc.get("warns", [])) if doc else 1

    log_embed = discord.Embed(
        title=f"{AVISO} Advertencia automática",
        color=SYSTEM_COLOR,
        timestamp=datetime.now(timezone.utc)
    )
    log_embed.add_field(name="Usuario", value=f"{member} (`{member.id}`)", inline=True)
    log_embed.add_field(name="Razón", value=reason, inline=True)
    log_embed.add_field(name="Total", value=str(total), inline=True)
    log_embed.set_footer(text="Dead by Bodrios")
    await send_log(guild, log_embed)

    try:
        dm = discord.Embed(
            title=f"{AVISO} Advertencia automática",
            description=f"Has recibido una advertencia automática.\n**Razón:** {reason}\n**Total:** {total}",
            color=SYSTEM_COLOR
        )
        dm.set_footer(text="Dead by Bodrios")
        await member.send(embed=dm)
    except Exception:
        pass

# ==================== GIVEAWAY HELPERS ====================
async def end_giveaway(giveaway: dict, force: bool = False):
    """Finaliza un giveaway y elige ganadores."""
    guild = bot.get_guild(giveaway["guild_id"])
    if not guild:
        await bot.db.giveaways.update_one({"_id": giveaway["_id"]}, {"$set": {"ended": True}})
        return

    channel = guild.get_channel(giveaway["channel_id"])
    if not channel:
        await bot.db.giveaways.update_one({"_id": giveaway["_id"]}, {"$set": {"ended": True}})
        return

    try:
        message = await channel.fetch_message(giveaway["message_id"])
    except Exception:
        await bot.db.giveaways.update_one({"_id": giveaway["_id"]}, {"$set": {"ended": True}})
        return

    entrants = giveaway.get("entrants", [])
    winners_count = giveaway.get("winners_count", 1)
    prize = giveaway.get("prize", "Premio")

    # Filtrar usuarios válidos (aún en el servidor y no bots)
    valid = []
    for uid in entrants:
        member = guild.get_member(uid)
        if member and not member.bot:
            valid.append(member)

    winners = []
    if valid:
        winners = random.sample(valid, min(winners_count, len(valid)))

    # Actualizar embed
    embed = discord.Embed(
        title="🎉 GIVEAWAY FINALIZADO",
        description=f"**Premio:** {prize}\n\n{giveaway.get('description', '')}",
        color=SYSTEM_COLOR,
        timestamp=datetime.now(timezone.utc)
    )
    if winners:
        winners_text = "\n".join(f"• {w.mention} (`{w.id}`)" for w in winners)
        embed.add_field(name="Ganador(es)", value=winners_text, inline=False)
    else:
        embed.add_field(name="Ganador(es)", value="Nadie participó 😢", inline=False)

    embed.add_field(name="Participantes", value=str(len(entrants)), inline=True)
    embed.set_footer(text="Dead by Bodrios")

    try:
        await message.edit(embed=embed, view=None)
    except Exception:
        pass

    # Anuncio
    if winners:
        mentions = ", ".join(w.mention for w in winners)
        await channel.send(f"🎉 Felicidades {mentions}! Ganasteis **{prize}**!")
        for w in winners:
            try:
                dm = discord.Embed(
                    title="🎉 ¡Has ganado un Giveaway!",
                    description=f"**Premio:** {prize}\n**Servidor:** {guild.name}",
                    color=SYSTEM_COLOR
                )
                dm.set_footer(text="Dead by Bodrios")
                await w.send(embed=dm)
            except Exception:
                pass
    else:
        await channel.send("El giveaway terminó sin participantes válidos.")

    await bot.db.giveaways.update_one(
        {"_id": giveaway["_id"]},
        {"$set": {"ended": True, "winners": [w.id for w in winners]}}
    )

# ==================== PRESENCE ====================
@tasks.loop(seconds=10)
async def rotate_presence():
    activities = [
        discord.Activity(type=discord.ActivityType.watching, name="↪Dead by Bodrios"),
        discord.Activity(type=discord.ActivityType.watching, name="↪Dev: Supskevv!"),
    ]
    activity = activities[rotate_presence.current_loop % len(activities)]
    await bot.change_presence(activity=activity, status=discord.Status.online)

# ==================== TEMPBAN + GIVEAWAY CHECKER ====================
@tasks.loop(minutes=1)
async def check_tempbans():
    now = datetime.now(timezone.utc)
    async for doc in bot.db.tempbans.find({"unban_at": {"$lte": now}}):
        guild = bot.get_guild(doc["guild_id"])
        if guild:
            try:
                await guild.unban(discord.Object(id=doc["user_id"]), reason="Tempban expirado")
            except Exception:
                pass
        await bot.db.tempbans.delete_one({"_id": doc["_id"]})

@tasks.loop(seconds=30)
async def check_giveaways():
    now = datetime.now(timezone.utc)
    async for doc in bot.db.giveaways.find({"ended": False, "end_time": {"$lte": now}}):
        await end_giveaway(doc)

# ==================== EVENTS ====================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    await load_all_configs()
    await bot.load_extension("commands")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"Sync error: {e}")
    if not rotate_presence.is_running():
        rotate_presence.start()
    if not check_tempbans.is_running():
        check_tempbans.start()
    if not check_giveaways.is_running():
        check_giveaways.start()
    print("Dead by Bodrios listo.")

@bot.event
async def on_member_join(member: discord.Member):
    config = await get_welcome_config(member.guild.id)
    channel_id = config.get("channel_id")
    if not channel_id:
        return
    channel = member.guild.get_channel(channel_id)
    if not channel:
        return

    description = replace_vars(config.get("message", ""), member)
    color = config.get("color", SYSTEM_COLOR)
    footer = replace_vars(config.get("footer", "Dead by Bodrios"), member)
    image = config.get("image")
    recommended = config.get("recommended_channels", [])

    embed = discord.Embed(description=description, color=color)
    embed.set_thumbnail(url=member.display_avatar.url)
    if footer:
        embed.set_footer(text=footer)
    if image:
        embed.set_image(url=image)
    if recommended:
        rec_text = "\n".join(f"• <#{cid}>" for cid in recommended if member.guild.get_channel(cid))
        if rec_text:
            embed.add_field(name="Canales recomendados", value=rec_text, inline=False)

    try:
        await channel.send(content=member.mention, embed=embed)
    except Exception:
        pass

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        await bot.process_commands(message)
        return

    config = await get_bot_config(message.guild.id)
    automod = config.get("automod", {})

    if automod.get("anti_invite", True) and INVITE_REGEX.search(message.content):
        if not is_staff_or_admin(message.author):
            try:
                await message.delete()
            except Exception:
                pass
            await add_auto_warn(message.guild, message.author, "Envío de invitación de Discord")
            try:
                await message.channel.send(
                    embed=discord.Embed(
                        description=f"{DENEGADO} {message.author.mention} no se permiten invitaciones.",
                        color=SYSTEM_COLOR
                    ),
                    delete_after=8
                )
            except Exception:
                pass
            await bot.process_commands(message)
            return

    if automod.get("anti_flood", True):
        limit = automod.get("flood_limit", 5)
        seconds = automod.get("flood_seconds", 5)
        now = datetime.now(timezone.utc).timestamp()
        tracker = bot.flood_tracker[message.guild.id][message.author.id]
        tracker.append(now)
        while tracker and now - tracker[0] > seconds:
            tracker.popleft()
        if len(tracker) >= limit:
            if not is_staff_or_admin(message.author):
                try:
                    await message.delete()
                except Exception:
                    pass
                try:
                    def check(m):
                        return m.author.id == message.author.id and (datetime.now(timezone.utc).timestamp() - m.created_at.timestamp()) < seconds + 2
                    await message.channel.purge(limit=limit + 2, check=check)
                except Exception:
                    pass
                await add_auto_warn(message.guild, message.author, f"Flood ({limit} mensajes en {seconds}s)")
                try:
                    await message.channel.send(
                        embed=discord.Embed(
                            description=f"{DENEGADO} {message.author.mention} flood detectado.",
                            color=SYSTEM_COLOR
                        ),
                        delete_after=8
                    )
                except Exception:
                    pass
                tracker.clear()

    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            title=f"{AVISO} Uso incorrecto",
            description=f"**Uso correcto:** `?{ctx.command.qualified_name} {ctx.command.signature}`",
            color=SYSTEM_COLOR
        )
        await ctx.send(embed=embed, delete_after=15)
    elif isinstance(error, commands.BadArgument):
        embed = discord.Embed(
            title=f"{AVISO} Argumento inválido",
            description=str(error),
            color=SYSTEM_COLOR
        )
        await ctx.send(embed=embed, delete_after=12)
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(embed=discord.Embed(
            description=f"{RELOJ} Espera {error.retry_after:.1f}s.",
            color=SYSTEM_COLOR
        ), delete_after=8)
    elif isinstance(error, commands.MissingPermissions) or isinstance(error, commands.BotMissingPermissions):
        await ctx.send(embed=discord.Embed(
            description=f"{DENEGADO} Permisos insuficientes.",
            color=SYSTEM_COLOR
        ), delete_after=10)

# ==================== GIVEAWAY VIEW ====================
class GiveawayEnterView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Participar", style=discord.ButtonStyle.primary, emoji="🎉", custom_id="giveaway_enter")
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        giveaway = await bot.db.giveaways.find_one({"message_id": interaction.message.id, "ended": False})
        if not giveaway:
            return await interaction.response.send_message(f"{DENEGADO} Este giveaway ya terminó o no existe.", ephemeral=True)

        if interaction.user.id in giveaway.get("entrants", []):
            return await interaction.response.send_message(f"{AVISO} Ya estás participando.", ephemeral=True)

        await bot.db.giveaways.update_one(
            {"message_id": interaction.message.id},
            {"$addToSet": {"entrants": interaction.user.id}}
        )

        # Actualizar contador en el embed
        new_count = len(giveaway.get("entrants", [])) + 1
        embed = interaction.message.embeds[0]
        # Reconstruir embed simple
        prize = giveaway.get("prize", "Premio")
        description = giveaway.get("description", "")
        end_ts = int(giveaway["end_time"].timestamp())

        new_embed = discord.Embed(
            title="🎉 GIVEAWAY",
            description=f"**Premio:** {prize}\n\n{description}",
            color=SYSTEM_COLOR
        )
        new_embed.add_field(name="Termina", value=f"<t:{end_ts}:R> (<t:{end_ts}:f>)", inline=True)
        new_embed.add_field(name="Ganadores", value=str(giveaway.get("winners_count", 1)), inline=True)
        new_embed.add_field(name="Participantes", value=str(new_count), inline=True)
        new_embed.set_footer(text="Dead by Bodrios")

        try:
            await interaction.message.edit(embed=new_embed, view=self)
        except Exception:
            pass

        await interaction.response.send_message(f"{ACEPTAR} ¡Te has unido al giveaway!", ephemeral=True)

# ==================== WELCOME / BOT / TICKETS (igual que antes) ====================
# (Mantengo todas las clases de WelcomeSetupView, BotSetupView, TicketsSetupView, 
# TicketControlView, create_ticket, etc. exactamente iguales a la versión anterior.
# Por longitud no las repito aquí, pero en el archivo real deben estar completas.)

# ---------- Para que el archivo sea usable, aquí van las partes críticas de giveaway + start ----------

@bot.tree.command(name="giveaway-create", description="Crear un nuevo giveaway")
@app_commands.describe(
    duration="Duración (ej: 30s, 10m, 2h, 1d, 1w)",
    prize="Premio / recompensa",
    winners="Número de ganadores (default 1)",
    description="Descripción opcional del giveaway",
    channel="Canal donde se publicará (default: canal actual)"
)
@app_commands.default_permissions(manage_guild=True)
async def giveaway_create(
    interaction: discord.Interaction,
    duration: str,
    prize: str,
    winners: app_commands.Range[int, 1, 20] = 1,
    description: Optional[str] = None,
    channel: Optional[discord.TextChannel] = None
):
    if not is_staff_or_admin(interaction.user):
        return await interaction.response.send_message(f"{DENEGADO} No tienes permisos.", ephemeral=True)

    delta = parse_time(duration)
    if not delta:
        return await interaction.response.send_message(
            f"{DENEGADO} Formato de tiempo inválido. Usa: `30s`, `5m`, `2h`, `1d`, `1w`",
            ephemeral=True
        )

    target_channel = channel or interaction.channel
    end_time = datetime.now(timezone.utc) + delta
    end_ts = int(end_time.timestamp())

    embed = discord.Embed(
        title="🎉 GIVEAWAY",
        description=f"**Premio:** {prize}\n\n{description or ''}",
        color=SYSTEM_COLOR
    )
    embed.add_field(name="Termina", value=f"<t:{end_ts}:R> (<t:{end_ts}:f>)", inline=True)
    embed.add_field(name="Ganadores", value=str(winners), inline=True)
    embed.add_field(name="Participantes", value="0", inline=True)
    embed.set_footer(text="Dead by Bodrios")

    view = GiveawayEnterView()
    msg = await target_channel.send(embed=embed, view=view)

    await bot.db.giveaways.insert_one({
        "message_id": msg.id,
        "channel_id": target_channel.id,
        "guild_id": interaction.guild.id,
        "prize": prize,
        "description": description or "",
        "winners_count": winners,
        "end_time": end_time,
        "entrants": [],
        "ended": False,
        "host_id": interaction.user.id,
        "created_at": datetime.now(timezone.utc)
    })

    await interaction.response.send_message(
        f"{ACEPTAR} Giveaway creado en {target_channel.mention}",
        ephemeral=True
    )

@bot.tree.command(name="giveaway-end", description="Finalizar un giveaway manualmente")
@app_commands.describe(message_id="ID del mensaje del giveaway")
@app_commands.default_permissions(manage_guild=True)
async def giveaway_end(interaction: discord.Interaction, message_id: str):
    if not is_staff_or_admin(interaction.user):
        return await interaction.response.send_message(f"{DENEGADO} No tienes permisos.", ephemeral=True)

    try:
        mid = int(message_id)
    except ValueError:
        return await interaction.response.send_message(f"{DENEGADO} ID inválido.", ephemeral=True)

    giveaway = await bot.db.giveaways.find_one({"message_id": mid, "guild_id": interaction.guild.id, "ended": False})
    if not giveaway:
        return await interaction.response.send_message(f"{DENEGADO} Giveaway no encontrado o ya finalizado.", ephemeral=True)

    await end_giveaway(giveaway, force=True)
    await interaction.response.send_message(f"{ACEPTAR} Giveaway finalizado.", ephemeral=True)

@bot.tree.command(name="giveaway-reroll", description="Volver a elegir ganadores de un giveaway terminado")
@app_commands.describe(message_id="ID del mensaje del giveaway")
@app_commands.default_permissions(manage_guild=True)
async def giveaway_reroll(interaction: discord.Interaction, message_id: str):
    if not is_staff_or_admin(interaction.user):
        return await interaction.response.send_message(f"{DENEGADO} No tienes permisos.", ephemeral=True)

    try:
        mid = int(message_id)
    except ValueError:
        return await interaction.response.send_message(f"{DENEGADO} ID inválido.", ephemeral=True)

    giveaway = await bot.db.giveaways.find_one({"message_id": mid, "guild_id": interaction.guild.id, "ended": True})
    if not giveaway:
        return await interaction.response.send_message(f"{DENEGADO} Giveaway no encontrado o aún activo.", ephemeral=True)

    # Re-usar la lógica de end (elige de nuevo)
    giveaway["ended"] = False  # temporal
    await end_giveaway(giveaway, force=True)
    await interaction.response.send_message(f"{ACEPTAR} Nuevos ganadores elegidos.", ephemeral=True)

@bot.tree.command(name="giveaway-list", description="Listar giveaways activos del servidor")
@app_commands.default_permissions(manage_guild=True)
async def giveaway_list(interaction: discord.Interaction):
    cursor = bot.db.giveaways.find({"guild_id": interaction.guild.id, "ended": False})
    giveaways = [doc async for doc in cursor]

    if not giveaways:
        return await interaction.response.send_message(f"{LUPA} No hay giveaways activos.", ephemeral=True)

    embed = discord.Embed(title=f"{LUPA} Giveaways activos", color=SYSTEM_COLOR)
    for g in giveaways[:10]:
        end_ts = int(g["end_time"].timestamp())
        embed.add_field(
            name=g["prize"][:50],
            value=f"ID: `{g['message_id']}`\nTermina: <t:{end_ts}:R>\nParticipantes: {len(g.get('entrants', []))}",
            inline=False
        )
    embed.set_footer(text="Dead by Bodrios")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ==================== SETUP HOOK + START ====================
@bot.event
async def setup_hook():
    bot.add_view(GiveawayEnterView())
    bot.add_view(TicketControlView())  # si ya lo tenías

keep_alive()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN no encontrado en variables de entorno")
bot.run(TOKEN)
