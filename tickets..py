import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
from typing import List, Optional
import asyncio

SYSTEM_COLOR = 0xcef3f1
PLUMA = "<:PlumaEmoji:1544417398113968328>"
DENEGADO = "<:DenegadoEmoji:1544417342904078367>"
ACEPTAR = "<:Aceptar:1544417278563586138>"
AVISO = "<:AvisoEmoji:1544417307139244082>"
RELOJ_ARENA = "<:RelojArenaEmoji:1544417426375053343>"


def is_staff_or_admin(member: discord.Member, bot) -> bool:
    config = bot.bot_configs.get(member.guild.id, {})
    staff = set(config.get("staff_roles", []))
    admin = set(config.get("admin_roles", []))
    roles = {r.id for r in member.roles}
    return bool(roles & (staff | admin)) or member.guild_permissions.administrator


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_tickets_config(self, guild_id: int) -> dict:
        if guild_id in self.bot.tickets_configs:
            return self.bot.tickets_configs[guild_id]
        doc = await self.bot.db.tickets_config.find_one({"guild_id": guild_id})
        if doc:
            self.bot.tickets_configs[guild_id] = doc
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
        await self.bot.db.tickets_config.insert_one(default)
        self.bot.tickets_configs[guild_id] = default
        return default

    # ==================== SETUP ====================
    class TicketMessageModal(discord.ui.Modal, title="Mensaje del panel"):
        def __init__(self, view):
            super().__init__()
            self.view = view
            self.msg = discord.ui.TextInput(label="Mensaje", style=discord.TextStyle.paragraph, default=view.config.get("message", ""), max_length=2000)
            self.add_item(self.msg)

        async def on_submit(self, interaction: discord.Interaction):
            self.view.config["message"] = self.msg.value
            await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)

    class TicketFooterModal(discord.ui.Modal, title="Footer"):
        def __init__(self, view):
            super().__init__()
            self.view = view
            self.footer = discord.ui.TextInput(label="Footer", default=view.config.get("footer", "Dead by Bodrios"), required=False)
            self.add_item(self.footer)

        async def on_submit(self, interaction: discord.Interaction):
            self.view.config["footer"] = self.footer.value
            await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)

    class TicketColorModal(discord.ui.Modal, title="Color"):
        def __init__(self, view):
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
        def __init__(self, view):
            super().__init__()
            self.view = view
            self.image = discord.ui.TextInput(label="URL (vacío = quitar)", default=view.config.get("image") or "", required=False)
            self.add_item(self.image)

        async def on_submit(self, interaction: discord.Interaction):
            self.view.config["image"] = self.image.value.strip() or None
            await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)

    class TicketCategoriesModal(discord.ui.Modal, title="Categorías de ticket"):
        def __init__(self, view):
            super().__init__()
            self.view = view
            current = ", ".join(view.config.get("categories", []))
            self.cats = discord.ui.TextInput(label="Categorías separadas por coma", style=discord.TextStyle.paragraph, default=current, placeholder="Soporte General, Reportes, Donaciones")
            self.add_item(self.cats)

        async def on_submit(self, interaction: discord.Interaction):
            cats = [c.strip() for c in self.cats.value.split(",") if c.strip()]
            if not cats:
                await interaction.response.send_message(f"{DENEGADO} Debes poner al menos una categoría.", ephemeral=True)
                return
            self.view.config["categories"] = cats[:10]
            await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)

    class TicketsSetupView(discord.ui.View):
        def __init__(self, bot, author_id: int, config: dict):
            super().__init__(timeout=600)
            self.bot = bot
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
            embed.set_footer(text="Dead by Bodrios")
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
            await interaction.response.send_modal(Tickets.TicketMessageModal(self))

        @discord.ui.button(label="Color", style=discord.ButtonStyle.primary, row=2)
        async def btn_color(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_modal(Tickets.TicketColorModal(self))

        @discord.ui.button(label="Footer", style=discord.ButtonStyle.primary, row=2)
        async def btn_footer(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_modal(Tickets.TicketFooterModal(self))

        @discord.ui.button(label="Imagen", style=discord.ButtonStyle.primary, row=2)
        async def btn_image(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_modal(Tickets.TicketImageModal(self))

        @discord.ui.button(label="Categorías", style=discord.ButtonStyle.secondary, row=3)
        async def btn_cats(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_modal(Tickets.TicketCategoriesModal(self))

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
            await self.bot.db.tickets_config.update_one({"guild_id": interaction.guild.id}, {"$set": self.config}, upsert=True)
            self.bot.tickets_configs[interaction.guild.id] = self.config

            channel = interaction.guild.get_channel(self.config["panel_channel_id"])
            if not channel:
                await interaction.response.send_message(f"{DENEGADO} Canal del panel no encontrado.", ephemeral=True)
                return

            embed = discord.Embed(description=self.config.get("message", ""), color=self.config.get("color", SYSTEM_COLOR))
            if self.config.get("footer"):
                embed.set_footer(text=self.config["footer"])
            if self.config.get("image"):
                embed.set_image(url=self.config["image"])

            if self.config.get("open_type") == "select":
                view = TicketSelectView(self.config["categories"])
            else:
                view = TicketButtonsView(self.config["categories"])

            await channel.send(embed=embed, view=view)
            await interaction.response.edit_message(embed=discord.Embed(description=f"{ACEPTAR} Configuración guardada y panel enviado a {channel.mention}.", color=SYSTEM_COLOR), view=None)
            self.stop()

        @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.danger, emoji=DENEGADO, row=4)
        async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.edit_message(embed=discord.Embed(description=f"{DENEGADO} Cancelado.", color=SYSTEM_COLOR), view=None)
            self.stop()

    @app_commands.command(name="tickets-setup", description="Configurar el sistema de tickets")
    @app_commands.default_permissions(administrator=True)
    async def tickets_setup(self, interaction: discord.Interaction):
        config = await self.get_tickets_config(interaction.guild.id)
        view = self.TicketsSetupView(self.bot, interaction.user.id, config)
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)


class TicketButtonsView(discord.ui.View):
    def __init__(self, categories: List[str]):
        super().__init__(timeout=None)
        for cat in categories[:5]:
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
    bot = interaction.client
    config = await bot.get_cog("Tickets").get_tickets_config(interaction.guild.id) if bot.get_cog("Tickets") else {}
    # Fallback simple
    if not config:
        config = await bot.db.tickets_config.find_one({"guild_id": interaction.guild.id}) or {}

    category_id = config.get("category_id")
    if not category_id:
        await interaction.response.send_message(f"{DENEGADO} Sistema de tickets no configurado.", ephemeral=True)
        return

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

    bot_config = bot.bot_configs.get(interaction.guild.id, {})
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
        if not is_staff_or_admin(interaction.user, interaction.client):
            await interaction.response.send_message(f"{DENEGADO} Solo staff puede reclamar.", ephemeral=True)
            return
        ticket = await interaction.client.db.tickets.find_one({"channel_id": interaction.channel.id})
        if not ticket:
            await interaction.response.send_message(f"{DENEGADO} No es un ticket.", ephemeral=True)
            return
        if ticket.get("claimed_by"):
            await interaction.response.send_message(f"{AVISO} Ya reclamado por <@{ticket['claimed_by']}>.", ephemeral=True)
            return
        await interaction.client.db.tickets.update_one({"channel_id": interaction.channel.id}, {"$set": {"claimed_by": interaction.user.id}})
        await interaction.channel.send(embed=discord.Embed(description=f"{ACEPTAR} Ticket reclamado por {interaction.user.mention}.", color=SYSTEM_COLOR))
        await interaction.response.defer()

    @discord.ui.button(label="Cerrar", style=discord.ButtonStyle.secondary, custom_id="ticket_close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = await interaction.client.db.tickets.find_one({"channel_id": interaction.channel.id})
        if not ticket:
            await interaction.response.send_message(f"{DENEGADO} No es un ticket.", ephemeral=True)
            return
        if not is_staff_or_admin(interaction.user, interaction.client) and interaction.user.id != ticket.get("user_id"):
            await interaction.response.send_message(f"{DENEGADO} No puedes cerrar este ticket.", ephemeral=True)
            return
        await interaction.client.db.tickets.update_one({"channel_id": interaction.channel.id}, {"$set": {"closed": True, "closed_by": interaction.user.id, "closed_at": datetime.now(timezone.utc)}})
        await interaction.channel.set_permissions(interaction.guild.default_role, view_channel=False)
        await interaction.response.send_message(embed=discord.Embed(description=f"{ACEPTAR} Ticket cerrado por {interaction.user.mention}. Usa el botón **Eliminar** o `?delete`.", color=SYSTEM_COLOR))

    @discord.ui.button(label="Eliminar Ticket", style=discord.ButtonStyle.danger, custom_id="ticket_delete")
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_or_admin(interaction.user, interaction.client):
            await interaction.response.send_message(f"{DENEGADO} Solo staff puede eliminar.", ephemeral=True)
            return
        ticket = await interaction.client.db.tickets.find_one({"channel_id": interaction.channel.id})
        if not ticket:
            await interaction.response.send_message(f"{DENEGADO} No es un ticket.", ephemeral=True)
            return
        await interaction.response.send_message(embed=discord.Embed(description=f"{RELOJ_ARENA} Eliminando en 5 segundos...", color=SYSTEM_COLOR))
        await interaction.client.db.tickets.delete_one({"channel_id": interaction.channel.id})
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Eliminado por {interaction.user}")
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(Tickets(bot))
    bot.add_view(TicketControlView())
