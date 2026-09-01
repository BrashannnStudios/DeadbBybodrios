import os
import re
import asyncio
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

# Caches
bot.bot_configs: Dict[int, dict] = {}
bot.welcome_configs: Dict[int, dict] = {}
bot.tickets_configs: Dict[int, dict] = {}
bot.flood_tracker: Dict[int, Dict[int, deque]] = defaultdict(lambda: defaultdict(lambda: deque(maxlen=20)))

# ==================== DB ====================
MONGO_URI = os.getenv("MONGO_URI")
client = AsyncIOMotorClient(MONGO_URI)
bot.db = client["deadbybodrios"]

# ==================== HELPERS ====================
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
        "footer": "Sistema de Tickets • Dead by Bodrios",
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

    if total >= 3:
        # Convertir a warn normal ya está hecho; opcionalmente aplicar sanción extra
        pass

    log_embed = discord.Embed(
        title=f"{AVISO} Advertencia automática",
        color=SYSTEM_COLOR,
        timestamp=datetime.now(timezone.utc)
    )
    log_embed.add_field(name="Usuario", value=f"{member} (`{member.id}`)", inline=True)
    log_embed.add_field(name="Razón", value=reason, inline=True)
    log_embed.add_field(name="Total", value=str(total), inline=True)
    await send_log(guild, log_embed)

    try:
        dm = discord.Embed(
            title=f"{AVISO} Advertencia automática",
            description=f"Has recibido una advertencia automática.\n**Razón:** {reason}\n**Total:** {total}",
            color=SYSTEM_COLOR
        )
        dm.set_footer(text="Staff Team • Dead by Bodrios")
        await member.send(embed=dm)
    except Exception:
        pass

# ==================== PRESENCE ====================
@tasks.loop(seconds=10)
async def rotate_presence():
    activities = [
        discord.Activity(type=discord.ActivityType.watching, name="Dead by Bodrios"),
        discord.Activity(type=discord.ActivityType.listening, name="tickets y moderación"),
        discord.Game(name="?cmds | /welcome-setup"),
        discord.Activity(type=discord.ActivityType.competing, name=f"{len(bot.guilds)} servidores"),
        discord.Activity(type=discord.ActivityType.watching, name="el servidor"),
    ]
    activity = activities[rotate_presence.current_loop % len(activities)]
    await bot.change_presence(activity=activity, status=discord.Status.online)

# ==================== TEMPBAN CHECKER ====================
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
    footer = replace_vars(config.get("footer", ""), member)
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

    # Anti-invite
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

    # Anti-flood
    if automod.get("anti_flood", True):
        limit = automod.get("flood_limit", 5)
        seconds = automod.get("flood_seconds", 5)
        now = datetime.now(timezone.utc).timestamp()
        tracker = bot.flood_tracker[message.guild.id][message.author.id]
        tracker.append(now)
        # Limpiar antiguos
        while tracker and now - tracker[0] > seconds:
            tracker.popleft()
        if len(tracker) >= limit:
            if not is_staff_or_admin(message.author):
                try:
                    await message.delete()
                except Exception:
                    pass
                # Borrar los últimos mensajes del usuario (simple)
                try:
                    def check(m):
                        return m.author.id == message.author.id and (datetime.now(timezone.utc).timestamp() - m.created_at.timestamp()) < seconds + 2
                    deleted = await message.channel.purge(limit=limit + 2, check=check)
                except Exception:
                    deleted = []
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
    else:
        # Silenciar otros errores comunes
        pass

# ==================== WELCOME SETUP ====================
class WelcomeMessageModal(discord.ui.Modal, title="Mensaje de bienvenida"):
    def __init__(self, view: "WelcomeSetupView"):
        super().__init__()
        self.view = view
        self.message_input = discord.ui.TextInput(
            label="Mensaje del embed",
            style=discord.TextStyle.paragraph,
            default=view.config.get("message", ""),
            max_length=2000,
            required=True
        )
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.view.config["message"] = self.message_input.value
        await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)

class WelcomeFooterModal(discord.ui.Modal, title="Footer"):
    def __init__(self, view: "WelcomeSetupView"):
        super().__init__()
        self.view = view
        self.footer_input = discord.ui.TextInput(
            label="Footer (soporta variables)",
            default=view.config.get("footer", ""),
            max_length=2048,
            required=False
        )
        self.add_item(self.footer_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.view.config["footer"] = self.footer_input.value
        await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)

class WelcomeColorModal(discord.ui.Modal, title="Color del embed"):
    def __init__(self, view: "WelcomeSetupView"):
        super().__init__()
        self.view = view
        self.color_input = discord.ui.TextInput(
            label="Color HEX (ej: #cef3f1)",
            default=f"#{view.config.get('color', SYSTEM_COLOR):06x}",
            max_length=7,
            required=True
        )
        self.add_item(self.color_input)

    async def on_submit(self, interaction: discord.Interaction):
        value = self.color_input.value.strip().lstrip("#")
        try:
            color = int(value, 16)
            self.view.config["color"] = color
            await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)
        except ValueError:
            await interaction.response.send_message(f"{DENEGADO} Color inválido.", ephemeral=True)

class WelcomeImageModal(discord.ui.Modal, title="Imagen del embed"):
    def __init__(self, view: "WelcomeSetupView"):
        super().__init__()
        self.view = view
        self.image_input = discord.ui.TextInput(
            label="URL de la imagen (vacío = quitar)",
            default=view.config.get("image") or "",
            required=False
        )
        self.add_item(self.image_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.view.config["image"] = self.image_input.value.strip() or None
        await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)

class WelcomeSetupView(discord.ui.View):
    def __init__(self, author_id: int, config: dict):
        super().__init__(timeout=600)
        self.author_id = author_id
        self.config = config.copy()

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"{PLUMA} Configuración de Bienvenidas",
            color=SYSTEM_COLOR
        )
        ch = f"<#{self.config['channel_id']}>" if self.config.get("channel_id") else "*No configurado*"
        embed.add_field(name="Canal", value=ch, inline=True)
        embed.add_field(name="Color", value=f"`#{self.config.get('color', SYSTEM_COLOR):06x}`", inline=True)
        embed.add_field(name="Imagen", value="Sí" if self.config.get("image") else "No", inline=True)
        embed.add_field(name="Mensaje", value=self.config.get("message", "")[:200] + ("..." if len(self.config.get("message", "")) > 200 else ""), inline=False)
        embed.add_field(name="Footer", value=self.config.get("footer") or "*Ninguno*", inline=False)
        rec = self.config.get("recommended_channels", [])
        rec_text = "\n".join(f"• <#{c}>" for c in rec) if rec else "*Ninguno*"
        embed.add_field(name="Canales recomendados", value=rec_text, inline=False)
        embed.set_footer(text="Los cambios se guardan al pulsar Guardar")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(f"{DENEGADO} Solo quien ejecutó el comando puede usar este panel.", ephemeral=True)
            return False
        return True

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Seleccionar canal de bienvenida", channel_types=[discord.ChannelType.text], row=0)
    async def channel_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        self.config["channel_id"] = select.values[0].id
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Mensaje", style=discord.ButtonStyle.primary, row=1)
    async def btn_message(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WelcomeMessageModal(self))

    @discord.ui.button(label="Color", style=discord.ButtonStyle.primary, row=1)
    async def btn_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WelcomeColorModal(self))

    @discord.ui.button(label="Footer", style=discord.ButtonStyle.primary, row=1)
    async def btn_footer(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WelcomeFooterModal(self))

    @discord.ui.button(label="Imagen", style=discord.ButtonStyle.primary, row=1)
    async def btn_image(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WelcomeImageModal(self))

    @discord.ui.button(label="Añadir canal recomendado", style=discord.ButtonStyle.secondary, row=2)
    async def btn_add_rec(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Usamos un select temporal
        view = discord.ui.View(timeout=60)
        select = discord.ui.ChannelSelect(placeholder="Canal recomendado", channel_types=[discord.ChannelType.text])

        async def callback(inter: discord.Interaction):
            cid = select.values[0].id
            rec = self.config.setdefault("recommended_channels", [])
            if cid not in rec:
                rec.append(cid)
            await inter.response.edit_message(embed=self.build_embed(), view=self)

        select.callback = callback
        view.add_item(select)
        await interaction.response.send_message("Selecciona el canal recomendado:", view=view, ephemeral=True)

    @discord.ui.button(label="Limpiar recomendados", style=discord.ButtonStyle.secondary, row=2)
    async def btn_clear_rec(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.config["recommended_channels"] = []
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Vista previa", style=discord.ButtonStyle.secondary, row=3)
    async def btn_preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        description = replace_vars(self.config.get("message", ""), member)
        embed = discord.Embed(description=description, color=self.config.get("color", SYSTEM_COLOR))
        embed.set_thumbnail(url=member.display_avatar.url)
        footer = replace_vars(self.config.get("footer", ""), member)
        if footer:
            embed.set_footer(text=footer)
        if self.config.get("image"):
            embed.set_image(url=self.config["image"])
        rec = self.config.get("recommended_channels", [])
        if rec:
            rec_text = "\n".join(f"• <#{c}>" for c in rec)
            embed.add_field(name="Canales recomendados", value=rec_text, inline=False)
        await interaction.response.send_message(content="**Vista previa:**", embed=embed, ephemeral=True)

    @discord.ui.button(label="Guardar", style=discord.ButtonStyle.success, emoji=ACEPTAR, row=3)
    async def btn_save(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.config["guild_id"] = interaction.guild.id
        await bot.db.welcome_config.update_one(
            {"guild_id": interaction.guild.id},
            {"$set": self.config},
            upsert=True
        )
        bot.welcome_configs[interaction.guild.id] = self.config
        await interaction.response.edit_message(
            embed=discord.Embed(description=f"{ACEPTAR} Configuración de bienvenidas guardada.", color=SYSTEM_COLOR),
            view=None
        )
        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.danger, emoji=DENEGADO, row=3)
    async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=discord.Embed(description=f"{DENEGADO} Configuración cancelada.", color=SYSTEM_COLOR),
            view=None
        )
        self.stop()

@bot.tree.command(name="welcome-setup", description="Configurar el sistema de bienvenidas")
@app_commands.default_permissions(administrator=True)
async def welcome_setup(interaction: discord.Interaction):
    config = await get_welcome_config(interaction.guild.id)
    view = WelcomeSetupView(interaction.user.id, config)
    await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

# ==================== BOT SETUP ====================
class BotSetupView(discord.ui.View):
    def __init__(self, author_id: int, config: dict):
        super().__init__(timeout=600)
        self.author_id = author_id
        self.config = config.copy()
        if "automod" not in self.config:
            self.config["automod"] = {"anti_invite": True, "anti_flood": True, "flood_limit": 5, "flood_seconds": 5}

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(title=f"{PLUMA} Configuración del Bot", color=SYSTEM_COLOR)
        log = f"<#{self.config['log_channel']}>" if self.config.get("log_channel") else "*No configurado*"
        embed.add_field(name="Canal de Logs", value=log, inline=False)

        staff = self.config.get("staff_roles", [])
        staff_text = " ".join(f"<@&{r}>" for r in staff) if staff else "*Ninguno*"
        embed.add_field(name="Roles de Staff", value=staff_text, inline=False)

        admin = self.config.get("admin_roles", [])
        admin_text = " ".join(f"<@&{r}>" for r in admin) if admin else "*Ninguno*"
        embed.add_field(name="Roles de Admin/Owner", value=admin_text, inline=False)

        am = self.config["automod"]
        embed.add_field(
            name="Automod",
            value=(
                f"Anti-invite: `{'ON' if am.get('anti_invite') else 'OFF'}`\n"
                f"Anti-flood: `{'ON' if am.get('anti_flood') else 'OFF'}`\n"
                f"Flood: `{am.get('flood_limit', 5)}` msgs / `{am.get('flood_seconds', 5)}`s"
            ),
            inline=False
        )
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(f"{DENEGADO} Solo quien ejecutó el comando puede usar este panel.", ephemeral=True)
            return False
        return True

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Canal de logs", channel_types=[discord.ChannelType.text], row=0)
    async def log_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        self.config["log_channel"] = select.values[0].id
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Roles de Staff (múltiples)", min_values=0, max_values=10, row=1)
    async def staff_select(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        self.config["staff_roles"] = [r.id for r in select.values]
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Roles de Admin/Owner (múltiples)", min_values=0, max_values=10, row=2)
    async def admin_select(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        self.config["admin_roles"] = [r.id for r in select.values]
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Toggle Anti-Invite", style=discord.ButtonStyle.secondary, row=3)
    async def toggle_invite(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.config["automod"]["anti_invite"] = not self.config["automod"].get("anti_invite", True)
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Toggle Anti-Flood", style=discord.ButtonStyle.secondary, row=3)
    async def toggle_flood(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.config["automod"]["anti_flood"] = not self.config["automod"].get("anti_flood", True)
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Config Flood", style=discord.ButtonStyle.primary, row=3)
    async def config_flood(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = FloodConfigModal(self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Guardar", style=discord.ButtonStyle.success, emoji=ACEPTAR, row=4)
    async def btn_save(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.config["guild_id"] = interaction.guild.id
        await bot.db.bot_config.update_one(
            {"guild_id": interaction.guild.id},
            {"$set": self.config},
            upsert=True
        )
        bot.bot_configs[interaction.guild.id] = self.config
        await interaction.response.edit_message(
            embed=discord.Embed(description=f"{ACEPTAR} Configuración del bot guardada.", color=SYSTEM_COLOR),
            view=None
        )
        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.danger, emoji=DENEGADO, row=4)
    async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=discord.Embed(description=f"{DENEGADO} Cancelado.", color=SYSTEM_COLOR),
            view=None
        )
        self.stop()

class FloodConfigModal(discord.ui.Modal, title="Configuración de Flood"):
    def __init__(self, view: BotSetupView):
        super().__init__()
        self.view = view
        am = view.config["automod"]
        self.limit_input = discord.ui.TextInput(label="Límite de mensajes", default=str(am.get("flood_limit", 5)), max_length=3)
        self.seconds_input = discord.ui.TextInput(label="Segundos", default=str(am.get("flood_seconds", 5)), max_length=3)
        self.add_item(self.limit_input)
        self.add_item(self.seconds_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            limit = int(self.limit_input.value)
            seconds = int(self.seconds_input.value)
            if limit < 2 or limit > 20 or seconds < 1 or seconds > 30:
                raise ValueError
            self.view.config["automod"]["flood_limit"] = limit
            self.view.config["automod"]["flood_seconds"] = seconds
            await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)
        except ValueError:
            await interaction.response.send_message(f"{DENEGADO} Valores inválidos (msgs 2-20, segs 1-30).", ephemeral=True)

@bot.tree.command(name="bot-setup", description="Configurar logs, roles y automod")
@app_commands.default_permissions(administrator=True)
async def bot_setup(interaction: discord.Interaction):
    config = await get_bot_config(interaction.guild.id)
    view = BotSetupView(interaction.user.id, config)
    await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

# ==================== TICKETS SETUP + RUNTIME ====================
class TicketMessageModal(discord.ui.Modal, title="Mensaje del panel"):
    def __init__(self, view: "TicketsSetupView"):
        super().__init__()
        self.view = view
        self.msg = discord.ui.TextInput(label="Mensaje", style=discord.TextStyle.paragraph, default=view.config.get("message", ""), max_length=2000)
        self.add_item(self.msg)

    async def on_submit(self, interaction: discord.Interaction):
        self.view.config["message"] = self.msg.value
        await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)

class TicketFooterModal(discord.ui.Modal, title="Footer"):
    def __init__(self, view: "TicketsSetupView"):
        super().__init__()
        self.view = view
        self.footer = discord.ui.TextInput(label="Footer", default=view.config.get("footer", ""), required=False)
        self.add_item(self.footer)

    async def on_submit(self, interaction: discord.Interaction):
        self.view.config["footer"] = self.footer.value
        await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)

class TicketColorModal(discord.ui.Modal, title="Color"):
    def __init__(self, view: "TicketsSetupView"):
        super().__init__()
        self.view = view
        self.color = discord.ui.TextInput(label="HEX", default=f"#{view.config.get('color', SYSTEM_COLOR):06x}")
        self.add_item(self.color)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            self.view.config["color"] = int(self.color.value.strip().lstrip("#"), 16)
            await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)
        except ValueError:
            await interaction.response.send_message(f"{DENEGADO} Color inválido.", ephemeral=True)

class TicketImageModal(discord.ui.Modal, title="Imagen"):
    def __init__(self, view: "TicketsSetupView"):
        super().__init__()
        self.view = view
        self.image = discord.ui.TextInput(label="URL (vacío = quitar)", default=view.config.get("image") or "", required=False)
        self.add_item(self.image)

    async def on_submit(self, interaction: discord.Interaction):
        self.view.config["image"] = self.image.value.strip() or None
        await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)

class TicketCategoriesModal(discord.ui.Modal, title="Categorías de ticket"):
    def __init__(self, view: "TicketsSetupView"):
        super().__init__()
        self.view = view
        current = ", ".join(view.config.get("categories", []))
        self.cats = discord.ui.TextInput(
            label="Categorías separadas por coma",
            style=discord.TextStyle.paragraph,
            default=current,
            placeholder="Soporte General, Reportes, Donaciones"
        )
        self.add_item(self.cats)

    async def on_submit(self, interaction: discord.Interaction):
        cats = [c.strip() for c in self.cats.value.split(",") if c.strip()]
        if not cats:
            await interaction.response.send_message(f"{DENEGADO} Debes poner al menos una categoría.", ephemeral=True)
            return
        self.view.config["categories"] = cats[:10]
        await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)

class TicketsSetupView(discord.ui.View):
    def __init__(self, author_id: int, config: dict):
        super().__init__(timeout=600)
        self.author_id = author_id
        self.config = config.copy()

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(title=f"{PLUMA} Configuración de Tickets", color=SYSTEM_COLOR)
        cat = f"<#{self.config['category_id']}>" if self.config.get("category_id") else "*No configurado*"
        panel = f"<#{self.config['panel_channel_id']}>" if self.config.get("panel_channel_id") else "*No configurado*"
        embed.add_field(name="Categoría de tickets", value=cat, inline=True)
        embed.add_field(name="Canal del panel", value=panel, inline=True)
        embed.add_field(name="Tipo de apertura", value=self.config.get("open_type", "buttons").upper(), inline=True)
        embed.add_field(name="Mensaje", value=self.config.get("message", "")[:150], inline=False)
        embed.add_field(name="Categorías", value=", ".join(self.config.get("categories", [])), inline=False)
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(f"{DENEGADO} Solo quien ejecutó el comando puede usar este panel.", ephemeral=True)
            return False
        return True

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Categoría donde se crean los tickets", channel_types=[discord.ChannelType.category], row=0)
    async def category_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        self.config["category_id"] = select.values[0].id
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Canal donde se enviará el panel", channel_types=[discord.ChannelType.text], row=1)
    async def panel_channel_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        self.config["panel_channel_id"] = select.values[0].id
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Mensaje", style=discord.ButtonStyle.primary, row=2)
    async def btn_msg(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketMessageModal(self))

    @discord.ui.button(label="Color", style=discord.ButtonStyle.primary, row=2)
    async def btn_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketColorModal(self))

    @discord.ui.button(label="Footer", style=discord.ButtonStyle.primary, row=2)
    async def btn_footer(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketFooterModal(self))

    @discord.ui.button(label="Imagen", style=discord.ButtonStyle.primary, row=2)
    async def btn_image(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketImageModal(self))

    @discord.ui.button(label="Categorías", style=discord.ButtonStyle.secondary, row=3)
    async def btn_cats(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketCategoriesModal(self))

    @discord.ui.button(label="Tipo: Botones", style=discord.ButtonStyle.secondary, row=3)
    async def btn_type_buttons(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.config["open_type"] = "buttons"
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Tipo: Select", style=discord.ButtonStyle.secondary, row=3)
    async def btn_type_select(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.config["open_type"] = "select"
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Vista previa + Guardar & Enviar", style=discord.ButtonStyle.success, emoji=ACEPTAR, row=4)
    async def btn_save(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.config.get("category_id") or not self.config.get("panel_channel_id"):
            await interaction.response.send_message(f"{DENEGADO} Debes configurar categoría y canal del panel.", ephemeral=True)
            return

        self.config["guild_id"] = interaction.guild.id
        await bot.db.tickets_config.update_one(
            {"guild_id": interaction.guild.id},
            {"$set": self.config},
            upsert=True
        )
        bot.tickets_configs[interaction.guild.id] = self.config

        # Enviar panel
        channel = interaction.guild.get_channel(self.config["panel_channel_id"])
        if not channel:
            await interaction.response.send_message(f"{DENEGADO} Canal del panel no encontrado.", ephemeral=True)
            return

        embed = discord.Embed(
            description=self.config.get("message", ""),
            color=self.config.get("color", SYSTEM_COLOR)
        )
        if self.config.get("footer"):
            embed.set_footer(text=self.config["footer"])
        if self.config.get("image"):
            embed.set_image(url=self.config["image"])

        if self.config.get("open_type") == "select":
            view = TicketSelectView(self.config["categories"])
        else:
            view = TicketButtonsView(self.config["categories"])

        await channel.send(embed=embed, view=view)
        await interaction.response.edit_message(
            embed=discord.Embed(description=f"{ACEPTAR} Configuración guardada y panel enviado a {channel.mention}.", color=SYSTEM_COLOR),
            view=None
        )
        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.danger, emoji=DENEGADO, row=4)
    async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=discord.Embed(description=f"{DENEGADO} Cancelado.", color=SYSTEM_COLOR),
            view=None
        )
        self.stop()

# Views de apertura de tickets
class TicketButtonsView(discord.ui.View):
    def __init__(self, categories: List[str]):
        super().__init__(timeout=None)
        for i, cat in enumerate(categories[:5]):  # máx 5 botones
            button = discord.ui.Button(label=cat, style=discord.ButtonStyle.primary, custom_id=f"ticket_btn:{cat}")
            button.callback = self.make_callback(cat)
            self.add_item(button)

    def make_callback(self, category: str):
        async def callback(interaction: discord.Interaction):
            await create_ticket(interaction, category)
        return callback

class TicketSelectView(discord.ui.View):
    def __init__(self, categories: List[str]):
        super().__init__(timeout=None)
        options = [discord.SelectOption(label=c, value=c) for c in categories[:25]]
        select = discord.ui.Select(placeholder="Selecciona una categoría", options=options, custom_id="ticket_select")
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        category = interaction.data["values"][0]
        await create_ticket(interaction, category)

async def create_ticket(interaction: discord.Interaction, category: str):
    config = await get_tickets_config(interaction.guild.id)
    category_id = config.get("category_id")
    if not category_id:
        await interaction.response.send_message(f"{DENEGADO} Sistema de tickets no configurado.", ephemeral=True)
        return

    # Evitar tickets duplicados abiertos
    existing = await bot.db.tickets.find_one({
        "guild_id": interaction.guild.id,
        "user_id": interaction.user.id,
        "closed": {"$ne": True}
    })
    if existing:
        ch = interaction.guild.get_channel(existing["channel_id"])
        if ch:
            await interaction.response.send_message(f"{AVISO} Ya tienes un ticket abierto: {ch.mention}", ephemeral=True)
            return

    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True),
        interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
    }

    # Añadir staff roles
    bot_config = await get_bot_config(interaction.guild.id)
    for rid in bot_config.get("staff_roles", []) + bot_config.get("admin_roles", []):
        role = interaction.guild.get_role(rid)
        if role:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

    name = f"ticket-{interaction.user.name}"[:100]
    try:
        channel = await interaction.guild.create_text_channel(
            name=name,
            category=interaction.guild.get_channel(category_id),
            overwrites=overwrites,
            reason=f"Ticket de {interaction.user}"
        )
    except Exception as e:
        await interaction.response.send_message(f"{DENEGADO} Error al crear el ticket: {e}", ephemeral=True)
        return

    await bot.db.tickets.insert_one({
        "channel_id": channel.id,
        "guild_id": interaction.guild.id,
        "user_id": interaction.user.id,
        "category": category,
        "claimed_by": None,
        "closed": False,
        "created_at": datetime.now(timezone.utc)
    })

    embed = discord.Embed(
        title=f"Ticket • {category}",
        description=f"Hola {interaction.user.mention}, describe tu problema.\nUn miembro del staff te atenderá pronto.",
        color=SYSTEM_COLOR
    )
    embed.set_footer(text="Dead by Bodrios")
    view = TicketControlView()
    await channel.send(content=interaction.user.mention, embed=embed, view=view)
    await interaction.response.send_message(f"{ACEPTAR} Ticket creado: {channel.mention}", ephemeral=True)

class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Reclamar", style=discord.ButtonStyle.primary, custom_id="ticket_claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_or_admin(interaction.user):
            await interaction.response.send_message(f"{DENEGADO} Solo staff puede reclamar.", ephemeral=True)
            return
        ticket = await bot.db.tickets.find_one({"channel_id": interaction.channel.id})
        if not ticket:
            await interaction.response.send_message(f"{DENEGADO} No es un ticket.", ephemeral=True)
            return
        if ticket.get("claimed_by"):
            await interaction.response.send_message(f"{AVISO} Ya reclamado por <@{ticket['claimed_by']}>.", ephemeral=True)
            return

        await bot.db.tickets.update_one(
            {"channel_id": interaction.channel.id},
            {"$set": {"claimed_by": interaction.user.id}}
        )
        await interaction.channel.send(embed=discord.Embed(
            description=f"{ACEPTAR} Ticket reclamado por {interaction.user.mention}.",
            color=SYSTEM_COLOR
        ))
        await interaction.response.defer()

    @discord.ui.button(label="Cerrar", style=discord.ButtonStyle.secondary, custom_id="ticket_close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = await bot.db.tickets.find_one({"channel_id": interaction.channel.id})
        if not ticket:
            await interaction.response.send_message(f"{DENEGADO} No es un ticket.", ephemeral=True)
            return
        if not is_staff_or_admin(interaction.user) and interaction.user.id != ticket.get("user_id"):
            await interaction.response.send_message(f"{DENEGADO} No puedes cerrar este ticket.", ephemeral=True)
            return

        await bot.db.tickets.update_one(
            {"channel_id": interaction.channel.id},
            {"$set": {"closed": True, "closed_by": interaction.user.id, "closed_at": datetime.now(timezone.utc)}}
        )
        await interaction.channel.set_permissions(interaction.guild.default_role, view_channel=False)
        await interaction.response.send_message(embed=discord.Embed(
            description=f"{ACEPTAR} Ticket cerrado por {interaction.user.mention}. Usa el botón **Eliminar** o `?delete`.",
            color=SYSTEM_COLOR
        ))

    @discord.ui.button(label="Eliminar Ticket", style=discord.ButtonStyle.danger, custom_id="ticket_delete")
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_or_admin(interaction.user):
            await interaction.response.send_message(f"{DENEGADO} Solo staff puede eliminar.", ephemeral=True)
            return
        ticket = await bot.db.tickets.find_one({"channel_id": interaction.channel.id})
        if not ticket:
            await interaction.response.send_message(f"{DENEGADO} No es un ticket.", ephemeral=True)
            return

        await interaction.response.send_message(embed=discord.Embed(
            description=f"{RELOJ_ARENA} Eliminando en 5 segundos...",
            color=SYSTEM_COLOR
        ))
        await bot.db.tickets.delete_one({"channel_id": interaction.channel.id})
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Eliminado por {interaction.user}")
        except Exception:
            pass

@bot.tree.command(name="tickets-setup", description="Configurar el sistema de tickets")
@app_commands.default_permissions(administrator=True)
async def tickets_setup(interaction: discord.Interaction):
    config = await get_tickets_config(interaction.guild.id)
    view = TicketsSetupView(interaction.user.id, config)
    await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

# ==================== PERSISTENT VIEWS ====================
@bot.event
async def setup_hook():
    bot.add_view(TicketControlView())
    # Las views de apertura se re-crean al enviar el panel; los custom_id permiten persistencia parcial

# ==================== START ====================
keep_alive()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN no encontrado en variables de entorno")
bot.run(TOKEN)
