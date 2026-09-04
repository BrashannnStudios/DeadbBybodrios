import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
from typing import Optional

SYSTEM_COLOR = 0xcef3f1
PLUMA = "<:PlumaEmoji:1544417398113968328>"
DENEGADO = "<:DenegadoEmoji:1544417342904078367>"
ACEPTAR = "<:Aceptar:1544417278563586138>"


def replace_vars(text: str, member: discord.Member) -> str:
    if not text:
        return text
    return (
        text.replace("{user}", member.mention)
        .replace("{username}", str(member))
        .replace("{server}", member.guild.name)
        .replace("{membercount}", str(member.guild.member_count))
    )


class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_welcome_config(self, guild_id: int) -> dict:
        if guild_id in self.bot.welcome_configs:
            return self.bot.welcome_configs[guild_id]
        doc = await self.bot.db.welcome_config.find_one({"guild_id": guild_id})
        if doc:
            self.bot.welcome_configs[guild_id] = doc
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
        await self.bot.db.welcome_config.insert_one(default)
        self.bot.welcome_configs[guild_id] = default
        return default

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        config = await self.get_welcome_config(member.guild.id)
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

    # ==================== SETUP PANEL ====================
    class WelcomeMessageModal(discord.ui.Modal, title="Mensaje de bienvenida"):
        def __init__(self, view):
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
        def __init__(self, view):
            super().__init__()
            self.view = view
            self.footer_input = discord.ui.TextInput(
                label="Footer (soporta variables)",
                default=view.config.get("footer", "Dead by Bodrios"),
                max_length=2048,
                required=False
            )
            self.add_item(self.footer_input)

        async def on_submit(self, interaction: discord.Interaction):
            self.view.config["footer"] = self.footer_input.value
            await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)

    class WelcomeColorModal(discord.ui.Modal, title="Color del embed"):
        def __init__(self, view):
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
        def __init__(self, view):
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
        def __init__(self, bot, author_id: int, config: dict):
            super().__init__(timeout=600)
            self.bot = bot
            self.author_id = author_id
            self.config = config.copy()

        def build_embed(self) -> discord.Embed:
            embed = discord.Embed(title=f"{PLUMA} Configuración de Bienvenidas", color=SYSTEM_COLOR)
            ch = f"<#{self.config['channel_id']}>" if self.config.get("channel_id") else "*No configurado*"
            embed.add_field(name="Canal", value=ch, inline=True)
            embed.add_field(name="Color", value=f"`#{self.config.get('color', SYSTEM_COLOR):06x}`", inline=True)
            embed.add_field(name="Imagen", value="Sí" if self.config.get("image") else "No", inline=True)
            embed.add_field(name="Mensaje", value=self.config.get("message", "")[:200] + ("..." if len(self.config.get("message", "")) > 200 else ""), inline=False)
            embed.add_field(name="Footer", value=self.config.get("footer") or "*Ninguno*", inline=False)
            rec = self.config.get("recommended_channels", [])
            rec_text = "\n".join(f"• <#{c}>" for c in rec) if rec else "*Ninguno*"
            embed.add_field(name="Canales recomendados", value=rec_text, inline=False)
            embed.set_footer(text="Dead by Bodrios")
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
            await interaction.response.send_modal(Welcome.WelcomeMessageModal(self))

        @discord.ui.button(label="Color", style=discord.ButtonStyle.primary, row=1)
        async def btn_color(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_modal(Welcome.WelcomeColorModal(self))

        @discord.ui.button(label="Footer", style=discord.ButtonStyle.primary, row=1)
        async def btn_footer(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_modal(Welcome.WelcomeFooterModal(self))

        @discord.ui.button(label="Imagen", style=discord.ButtonStyle.primary, row=1)
        async def btn_image(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_modal(Welcome.WelcomeImageModal(self))

        @discord.ui.button(label="Añadir canal recomendado", style=discord.ButtonStyle.secondary, row=2)
        async def btn_add_rec(self, interaction: discord.Interaction, button: discord.ui.Button):
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
            footer = replace_vars(self.config.get("footer", "Dead by Bodrios"), member)
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
            await self.bot.db.welcome_config.update_one(
                {"guild_id": interaction.guild.id},
                {"$set": self.config},
                upsert=True
            )
            self.bot.welcome_configs[interaction.guild.id] = self.config
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

    @app_commands.command(name="welcome-setup", description="Configurar el sistema de bienvenidas")
    @app_commands.default_permissions(administrator=True)
    async def welcome_setup(self, interaction: discord.Interaction):
        config = await self.get_welcome_config(interaction.guild.id)
        view = self.WelcomeSetupView(self.bot, interaction.user.id, config)
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Welcome(bot))
