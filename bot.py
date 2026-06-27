import os
import asyncio
import discord
from discord import app_commands
from dotenv import load_dotenv

import storage

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

if not DISCORD_TOKEN:
    raise SystemExit("Defina DISCORD_TOKEN no arquivo .env antes de rodar o bot.")


intents = discord.Intents.default()
intents.members = True


class TicketBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        self.add_view(AbrirTicketView())
        self.add_view(FecharTicketView())

        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"Comandos sincronizados no servidor {GUILD_ID}.")
        else:
            await self.tree.sync()
            print("Comandos sincronizados globalmente.")


client = TicketBot()


@client.event
async def on_ready():
    print(f"Bot online como {client.user}")


# ---------------------------------------------------------------------------
# View: Botão de abrir ticket (publicado no canal de suporte)
# ---------------------------------------------------------------------------

class AbrirTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Abrir Ticket",
        emoji="🎫",
        style=discord.ButtonStyle.primary,
        custom_id="abrir_ticket",
    )
    async def abrir_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user

        # Checar se usuário já tem ticket aberto
        cfg = storage.get_guild_setup(guild.id)
        if not cfg:
            await interaction.response.send_message(
                "❌ Bot não configurado. Um administrador deve usar `/setup`.", ephemeral=True
            )
            return

        # Checar ticket duplicado
        existing = discord.utils.get(guild.text_channels, name=f"ticket-{user.name}".lower()[:90])
        if existing:
            await interaction.response.send_message(
                f"❌ Você já tem um ticket aberto: {existing.mention}", ephemeral=True
            )
            return

        # Criar canal do ticket
        ticket_channel = await criar_canal_ticket(guild, user, cfg)

        # Embed dentro do ticket
        embed = discord.Embed(
            title="🎫 Ticket de Suporte",
            description=(
                f"Olá {user.mention}! 👋\n\n"
                "Nossa equipe irá te atender em breve.\n"
                "Descreva seu problema ou dúvida abaixo."
            ),
            color=0x5865F2,
        )
        embed.set_footer(text="Clique em Fechar Ticket quando o atendimento terminar.")

        staff_role_id = cfg.get("staff_role_id")
        mention = f"<@&{staff_role_id}>" if staff_role_id else ""

        await ticket_channel.send(
            content=f"{user.mention} {mention}",
            embed=embed,
            view=FecharTicketView(),
        )

        await interaction.response.send_message(
            f"✅ Ticket criado: {ticket_channel.mention}", ephemeral=True
        )


# ---------------------------------------------------------------------------
# View: Fechar ticket
# ---------------------------------------------------------------------------

class FecharTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Fechar Ticket",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="fechar_ticket",
    )
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        cfg = storage.get_guild_setup(guild.id)

        staff_role_id = cfg.get("staff_role_id") if cfg else None
        is_staff = (
            staff_role_id is not None
            and any(str(role.id) == str(staff_role_id) for role in interaction.user.roles)
        )
        is_manager = interaction.user.guild_permissions.manage_channels

        # Dono do ticket também pode fechar
        is_owner = interaction.channel.name.replace("ticket-", "") == interaction.user.name.lower()[:87]

        if not (is_staff or is_manager or is_owner):
            await interaction.response.send_message(
                "❌ Você não tem permissão para fechar este ticket.", ephemeral=True
            )
            return

        await interaction.response.send_message("🔒 Fechando ticket em 5 segundos...")

        async def deletar():
            await asyncio.sleep(5)
            try:
                await interaction.channel.delete()
            except discord.HTTPException as e:
                print(f"Erro ao deletar canal: {e}")

        asyncio.create_task(deletar())


# ---------------------------------------------------------------------------
# Criar canal de ticket
# ---------------------------------------------------------------------------

async def criar_canal_ticket(guild: discord.Guild, member: discord.Member, cfg: dict) -> discord.TextChannel:
    staff_role_id = cfg.get("staff_role_id")
    category_id = cfg.get("category_id")

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True, read_message_history=True
        ),
    }

    if staff_role_id:
        staff_role = guild.get_role(int(staff_role_id))
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )

    category = guild.get_channel(int(category_id)) if category_id else None
    channel_name = f"ticket-{member.name}".lower()[:90]

    return await guild.create_text_channel(
        name=channel_name,
        overwrites=overwrites,
        category=category,
    )


# ---------------------------------------------------------------------------
# Painel de setup do bot
# ---------------------------------------------------------------------------

class SetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)
        self.draft = {
            "channel_id": None,
            "staff_role_id": None,
            "category_id": None,
            "titulo": "Suporte",
            "descricao": "Clique no botão abaixo para abrir um ticket com nossa equipe.",
        }
        self.add_item(CanalSuporteSelect(self))
        self.add_item(CargoStaffSelect(self))
        self.add_item(CategoriaSelect(self))

    def build_embed(self) -> discord.Embed:
        canal_id = self.draft.get("channel_id")
        role_id = self.draft.get("staff_role_id")
        cat_id = self.draft.get("category_id")

        embed = discord.Embed(
            title="⚙️ Configuração do Bot de Suporte",
            description=(
                f"**Canal de suporte:** {'<#' + str(canal_id) + '>' if canal_id else '*(não selecionado)*'}\n"
                f"**Cargo de staff:** {'<@&' + str(role_id) + '>' if role_id else '*(nenhum)*'}\n"
                f"**Categoria dos tickets:** {'<#' + str(cat_id) + '>' if cat_id else '*(nenhuma)*'}\n"
                f"**Título do embed:** {self.draft.get('titulo')}\n"
                f"**Descrição:** {self.draft.get('descricao')}\n"
            ),
            color=0x5865F2,
        )
        embed.set_footer(text="Preencha e clique em Publicar")
        return embed

    async def refresh(self, interaction: discord.Interaction):
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=self.build_embed(), view=self)
        else:
            await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Título", emoji="📝", style=discord.ButtonStyle.secondary, row=3)
    async def set_titulo(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TituloModal(self))

    @discord.ui.button(label="Descrição", emoji="🧾", style=discord.ButtonStyle.secondary, row=3)
    async def set_descricao(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DescricaoModal(self))

    @discord.ui.button(label="Publicar", emoji="✅", style=discord.ButtonStyle.success, row=4)
    async def publicar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.draft.get("channel_id"):
            await interaction.response.send_message(
                "❌ Selecione o canal de suporte antes de publicar.", ephemeral=True
            )
            return

        canal = interaction.guild.get_channel(self.draft["channel_id"])
        if not canal:
            await interaction.response.send_message(
                "❌ Canal não encontrado. Selecione novamente.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"🎫 {self.draft['titulo']}",
            description=self.draft["descricao"],
            color=0x5865F2,
        )
        embed.set_footer(text="Clique no botão abaixo para abrir um ticket")

        await canal.send(embed=embed, view=AbrirTicketView())

        # Salvar config
        storage.set_guild_setup(interaction.guild_id, {
            "channel_id": self.draft["channel_id"],
            "staff_role_id": self.draft.get("staff_role_id"),
            "category_id": self.draft.get("category_id"),
        })

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="✅ Bot de suporte publicado!",
                description=f"Painel publicado em <#{canal.id}>.",
                color=0x57F287,
            ),
            view=self,
        )

    @discord.ui.button(label="Cancelar", emoji="✖️", style=discord.ButtonStyle.danger, row=4)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            embed=discord.Embed(title="Configuração cancelada.", color=0xED4245),
            view=self,
        )
        self.stop()


# ---------------------------------------------------------------------------
# Selects do setup
# ---------------------------------------------------------------------------

class CanalSuporteSelect(discord.ui.ChannelSelect):
    def __init__(self, setup_view: "SetupView"):
        self.setup_view = setup_view
        super().__init__(
            placeholder="Canal onde o painel de tickets será publicado",
            channel_types=[discord.ChannelType.text],
            min_values=1, max_values=1, row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        self.setup_view.draft["channel_id"] = self.values[0].id
        await self.setup_view.refresh(interaction)


class CargoStaffSelect(discord.ui.RoleSelect):
    def __init__(self, setup_view: "SetupView"):
        self.setup_view = setup_view
        super().__init__(
            placeholder="Cargo de staff que verá os tickets (opcional)",
            min_values=0, max_values=1, row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        self.setup_view.draft["staff_role_id"] = self.values[0].id if self.values else None
        await self.setup_view.refresh(interaction)


class CategoriaSelect(discord.ui.ChannelSelect):
    def __init__(self, setup_view: "SetupView"):
        self.setup_view = setup_view
        super().__init__(
            placeholder="Categoria onde os tickets serão criados (opcional)",
            channel_types=[discord.ChannelType.category],
            min_values=0, max_values=1, row=2,
        )

    async def callback(self, interaction: discord.Interaction):
        self.setup_view.draft["category_id"] = self.values[0].id if self.values else None
        await self.setup_view.refresh(interaction)


# ---------------------------------------------------------------------------
# Modais de texto do setup
# ---------------------------------------------------------------------------

class TituloModal(discord.ui.Modal, title="Título do painel"):
    def __init__(self, setup_view: "SetupView"):
        super().__init__()
        self.setup_view = setup_view
        self.titulo = discord.ui.TextInput(
            label="Título",
            placeholder="Ex: Suporte ao Cliente",
            max_length=256,
            default=setup_view.draft.get("titulo", ""),
        )
        self.add_item(self.titulo)

    async def on_submit(self, interaction: discord.Interaction):
        self.setup_view.draft["titulo"] = self.titulo.value
        await self.setup_view.refresh(interaction)


class DescricaoModal(discord.ui.Modal, title="Descrição do painel"):
    def __init__(self, setup_view: "SetupView"):
        super().__init__()
        self.setup_view = setup_view
        self.descricao = discord.ui.TextInput(
            label="Descrição",
            style=discord.TextStyle.paragraph,
            placeholder="Ex: Clique abaixo para abrir um ticket com nossa equipe.",
            max_length=2000,
            default=setup_view.draft.get("descricao", ""),
        )
        self.add_item(self.descricao)

    async def on_submit(self, interaction: discord.Interaction):
        self.setup_view.draft["descricao"] = self.descricao.value
        await self.setup_view.refresh(interaction)


# ---------------------------------------------------------------------------
# Comandos slash
# ---------------------------------------------------------------------------

@client.tree.command(name="setup", description="Configura e publica o painel de tickets de suporte")
async def setup(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "❌ Você precisa da permissão **Gerenciar Servidor** para usar esse comando.",
            ephemeral=True,
        )
        return

    view = SetupView()
    await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)


@client.tree.command(name="fechar", description="Fecha o ticket atual")
async def fechar(interaction: discord.Interaction):
    if not interaction.channel.name.startswith("ticket-"):
        await interaction.response.send_message(
            "❌ Este comando só pode ser usado dentro de um ticket.", ephemeral=True
        )
        return

    cfg = storage.get_guild_setup(interaction.guild_id)
    staff_role_id = cfg.get("staff_role_id") if cfg else None
    is_staff = (
        staff_role_id is not None
        and any(str(role.id) == str(staff_role_id) for role in interaction.user.roles)
    )
    is_manager = interaction.user.guild_permissions.manage_channels
    is_owner = interaction.channel.name.replace("ticket-", "") == interaction.user.name.lower()[:87]

    if not (is_staff or is_manager or is_owner):
        await interaction.response.send_message("❌ Sem permissão para fechar este ticket.", ephemeral=True)
        return

    await interaction.response.send_message("🔒 Fechando ticket em 5 segundos...")

    async def deletar():
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except discord.HTTPException as e:
            print(f"Erro ao deletar: {e}")

    asyncio.create_task(deletar())


client.run(DISCORD_TOKEN)
