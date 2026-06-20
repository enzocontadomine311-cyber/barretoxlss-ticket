import os
import asyncio
import discord
from discord import app_commands
from dotenv import load_dotenv

import storage

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
TICKET_CATEGORY_ID = os.getenv("TICKET_CATEGORY_ID") or None
STAFF_ROLE_ID = os.getenv("STAFF_ROLE_ID") or None

if not DISCORD_TOKEN:
    raise SystemExit("Defina DISCORD_TOKEN no arquivo .env antes de rodar o bot.")

intents = discord.Intents.default()


class TicketBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # Registra as views persistentes (precisa rodar dentro do event loop,
        # por isso fica aqui dentro e não solto no final do arquivo)
        self.add_view(OpenTicketView())
        self.add_view(CloseTicketView())

        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"Comandos sincronizados no servidor {GUILD_ID}.")
        else:
            await self.tree.sync()
            print("Comandos sincronizados globalmente (pode levar até 1h pra propagar).")


client = TicketBot()


@client.event
async def on_ready():
    print(f"Bot online como {client.user}")


# ---------------------------------------------------------------------------
# Views (botões persistentes)
# ---------------------------------------------------------------------------
class OpenTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Abrir Ticket",
        emoji="🎫",
        style=discord.ButtonStyle.success,
        custom_id="ticket_open",
    )
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_open_ticket(interaction)


class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Fechar Ticket",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="ticket_close",
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_close_ticket(interaction)


# ---------------------------------------------------------------------------
# Painel de configuração (botões) — substitui o antigo /setup com parâmetros
# ---------------------------------------------------------------------------
class TituloModal(discord.ui.Modal, title="Título do painel"):
    def __init__(self, config_view: "ConfigPanelView"):
        super().__init__()
        self.config_view = config_view
        self.titulo = discord.ui.TextInput(
            label="Título",
            placeholder="Ex: Suporte",
            max_length=256,
            default=config_view.draft.get("title", ""),
        )
        self.add_item(self.titulo)

    async def on_submit(self, interaction: discord.Interaction):
        self.config_view.draft["title"] = self.titulo.value
        await self.config_view.refresh(interaction)


class DescricaoModal(discord.ui.Modal, title="Descrição do painel"):
    def __init__(self, config_view: "ConfigPanelView"):
        super().__init__()
        self.config_view = config_view
        self.descricao = discord.ui.TextInput(
            label="Descrição",
            style=discord.TextStyle.paragraph,
            placeholder="Ex: Clique no botão abaixo para abrir um ticket",
            max_length=4000,
            default=config_view.draft.get("description", ""),
        )
        self.add_item(self.descricao)

    async def on_submit(self, interaction: discord.Interaction):
        self.config_view.draft["description"] = self.descricao.value
        await self.config_view.refresh(interaction)


class ImagemModal(discord.ui.Modal, title="Imagem do painel"):
    def __init__(self, config_view: "ConfigPanelView"):
        super().__init__()
        self.config_view = config_view
        self.url = discord.ui.TextInput(
            label="URL da imagem (opcional)",
            placeholder="https://exemplo.com/imagem.png",
            required=False,
            default=config_view.draft.get("image") or "",
        )
        self.add_item(self.url)

    async def on_submit(self, interaction: discord.Interaction):
        self.config_view.draft["image"] = self.url.value or None
        await self.config_view.refresh(interaction)


class CanalSelect(discord.ui.ChannelSelect):
    def __init__(self, config_view: "ConfigPanelView"):
        self.config_view = config_view
        super().__init__(
            placeholder="Escolha o canal onde o painel será enviado",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        self.config_view.draft["channel_id"] = self.values[0].id
        await self.config_view.refresh(interaction)


class ConfigPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)
        self.draft = {"title": None, "description": None, "image": None, "channel_id": None}
        self.add_item(CanalSelect(self))

    def build_embed(self) -> discord.Embed:
        titulo = self.draft.get("title") or "*(não definido)*"
        descricao = self.draft.get("description") or "*(não definida)*"
        canal_id = self.draft.get("channel_id")
        canal_txt = f"<#{canal_id}>" if canal_id else "*(não selecionado)*"

        embed = discord.Embed(
            title="⚙️ Configuração do painel de tickets",
            description=(
                f"**Título:** {titulo}\n"
                f"**Descrição:** {descricao}\n"
                f"**Canal:** {canal_txt}\n"
                f"**Imagem:** {'definida' if self.draft.get('image') else 'nenhuma'}"
            ),
            color=0x5865F2,
        )
        if self.draft.get("image"):
            embed.set_image(url=self.draft["image"])
        embed.set_footer(text="Preencha os campos e clique em Publicar")
        return embed

    async def refresh(self, interaction: discord.Interaction):
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=self.build_embed(), view=self)
        else:
            await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Título", emoji="📝", style=discord.ButtonStyle.secondary, row=1)
    async def set_title(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TituloModal(self))

    @discord.ui.button(label="Descrição", emoji="🧾", style=discord.ButtonStyle.secondary, row=1)
    async def set_description(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DescricaoModal(self))

    @discord.ui.button(label="Imagem", emoji="🖼️", style=discord.ButtonStyle.secondary, row=1)
    async def set_image(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ImagemModal(self))

    @discord.ui.button(label="Publicar", emoji="✅", style=discord.ButtonStyle.success, row=2)
    async def publish(self, interaction: discord.Interaction, button: discord.ui.Button):
        faltando = []
        if not self.draft.get("title"):
            faltando.append("Título")
        if not self.draft.get("description"):
            faltando.append("Descrição")
        if not self.draft.get("channel_id"):
            faltando.append("Canal")

        if faltando:
            await interaction.response.send_message(
                f"Faltando preencher: **{', '.join(faltando)}**.",
                ephemeral=True,
            )
            return

        canal = interaction.guild.get_channel(self.draft["channel_id"])
        if canal is None:
            await interaction.response.send_message(
                "Não consegui encontrar o canal selecionado. Tente selecionar novamente.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=self.draft["title"],
            description=self.draft["description"],
            color=0x5865F2,
        )
        embed.set_footer(text="Clique no botão abaixo para abrir um ticket")
        if self.draft.get("image"):
            embed.set_image(url=self.draft["image"])

        ticket_view = OpenTicketView()
        sent_message = await canal.send(embed=embed, view=ticket_view)

        storage.set_guild_config(
            interaction.guild_id,
            {
                "title": self.draft["title"],
                "description": self.draft["description"],
                "image": self.draft.get("image"),
                "channel_id": canal.id,
                "message_id": sent_message.id,
            },
        )

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="✅ Painel publicado",
                description=f"Painel de tickets configurado com sucesso em {canal.mention}.",
                color=0x57F287,
            ),
            view=self,
        )

    @discord.ui.button(label="Cancelar", emoji="✖️", style=discord.ButtonStyle.danger, row=2)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Configuração cancelada",
                color=0xED4245,
            ),
            view=self,
        )
        self.stop()


@client.tree.command(name="painel", description="Abre o painel de configuração do sistema de tickets")
async def painel(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "Você precisa da permissão **Gerenciar Servidor** para usar esse comando.",
            ephemeral=True,
        )
        return

    view = ConfigPanelView()
    await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)


# ---------------------------------------------------------------------------
# Abrir ticket
# ---------------------------------------------------------------------------
async def handle_open_ticket(interaction: discord.Interaction):
    guild = interaction.guild
    user = interaction.user

    if storage.user_has_open_ticket(guild.id, user.id):
        await interaction.response.send_message(
            "Você já tem um ticket aberto. Feche-o antes de abrir outro.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_channels=True,
            read_message_history=True,
        ),
    }

    if STAFF_ROLE_ID:
        staff_role = guild.get_role(int(STAFF_ROLE_ID))
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )

    category = None
    if TICKET_CATEGORY_ID:
        category = guild.get_channel(int(TICKET_CATEGORY_ID))

    channel_name = f"ticket-{user.name}".lower()[:90]

    ticket_channel = await guild.create_text_channel(
        name=channel_name,
        overwrites=overwrites,
        category=category,
    )

    storage.add_ticket(
        ticket_channel.id,
        {"guild_id": guild.id, "user_id": user.id, "opened_at": discord.utils.utcnow().isoformat()},
    )

    embed = discord.Embed(
        title="Ticket aberto",
        description=(
            f"Olá {user.mention}, obrigado por abrir um ticket!\n"
            "Descreva seu problema/dúvida e aguarde o atendimento da equipe."
        ),
        color=0x57F287,
    )

    mention_text = user.mention
    if STAFF_ROLE_ID:
        mention_text += f" <@&{STAFF_ROLE_ID}>"

    view = CloseTicketView()
    await ticket_channel.send(content=mention_text, embed=embed, view=view)

    await interaction.followup.send(
        f"Seu ticket foi criado: {ticket_channel.mention}", ephemeral=True
    )


# ---------------------------------------------------------------------------
# Fechar ticket
# ---------------------------------------------------------------------------
async def handle_close_ticket(interaction: discord.Interaction):
    ticket = storage.get_ticket(interaction.channel_id)

    if not ticket:
        await interaction.response.send_message(
            "Este canal não está registrado como um ticket válido.",
            ephemeral=True,
        )
        return

    is_owner = ticket["user_id"] == interaction.user.id
    is_staff = (
        STAFF_ROLE_ID is not None
        and any(role.id == int(STAFF_ROLE_ID) for role in interaction.user.roles)
    )
    is_manager = interaction.user.guild_permissions.manage_channels

    if not (is_owner or is_staff or is_manager):
        await interaction.response.send_message(
            "Você não tem permissão para fechar este ticket.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message("Fechando o ticket em 5 segundos...")

    storage.remove_ticket(interaction.channel_id)

    async def delete_later():
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except discord.HTTPException as e:
            print(f"Erro ao deletar canal de ticket: {e}")

    asyncio.create_task(delete_later())


client.run(DISCORD_TOKEN)
