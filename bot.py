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
        self.add_view(BuyView())
        self.add_view(ConfirmarCompraView())
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
# Views persistentes
# ---------------------------------------------------------------------------

class BuyView(discord.ui.View):
    """Botão 'Comprar' no embed do produto."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Comprar",
        emoji="🛒",
        style=discord.ButtonStyle.success,
        custom_id="buy_button",
    )
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user

        # Buscar config do produto pelo message_id
        cfg = storage.get_config_by_message(guild.id, interaction.message.id)
        if not cfg:
            await interaction.response.send_message(
                "Produto não encontrado. Contate um administrador.", ephemeral=True
            )
            return

        confirm_channel_id = cfg.get("confirm_channel_id")
        if not confirm_channel_id:
            await interaction.response.send_message(
                "Canal de confirmação não configurado. Contate um administrador.", ephemeral=True
            )
            return

        confirm_channel = guild.get_channel(int(confirm_channel_id))
        if not confirm_channel:
            await interaction.response.send_message(
                "Canal de confirmação não encontrado. Contate um administrador.", ephemeral=True
            )
            return

        role_id = cfg.get("role_id")

        # Salvar solicitação pendente
        storage.add_pending(user.id, guild.id, {
            "user_id": user.id,
            "guild_id": guild.id,
            "role_id": role_id,
            "product_title": cfg.get("title", "Produto"),
        })

        # Enviar solicitação no canal de confirmação
        embed = discord.Embed(
            title="🛒 Nova solicitação de compra",
            description=(
                f"**Comprador:** {user.mention} (`{user}`)\n"
                f"**Produto:** {cfg.get('title', '—')}\n"
                f"**Cargo ao confirmar:** {'<@&' + str(role_id) + '>' if role_id else '*nenhum*'}\n\n"
                "Confirme ou recuse a compra abaixo."
            ),
            color=0xFEE75C,
        )

        view = ConfirmarCompraView()
        msg = await confirm_channel.send(embed=embed, view=view)

        # Salvar o message_id da solicitação pra poder editar depois
        storage.update_pending(user.id, guild.id, {"confirm_msg_id": msg.id, "confirm_channel_id": confirm_channel_id})

        await interaction.response.send_message(
            "✅ Sua solicitação foi enviada! Aguarde a confirmação da equipe.", ephemeral=True
        )


class ConfirmarCompraView(discord.ui.View):
    """Botões Confirmar/Recusar no canal de confirmação."""
    def __init__(self):
        super().__init__(timeout=None)

    async def _get_pending(self, interaction: discord.Interaction):
        """Acha a solicitação pendente pelo message_id da mensagem de confirmação."""
        return storage.get_pending_by_confirm_msg(interaction.guild.id, interaction.message.id)

    @discord.ui.button(
        label="✅ Confirmar",
        style=discord.ButtonStyle.success,
        custom_id="compra_confirmar",
    )
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        pending = await self._get_pending(interaction)
        if not pending:
            await interaction.response.send_message("Solicitação não encontrada.", ephemeral=True)
            return

        guild = interaction.guild
        user_id = pending["user_id"]
        role_id = pending.get("role_id")
        member = guild.get_member(user_id)

        # Dar cargo se configurado
        role = None
        if role_id:
            role = guild.get_role(int(role_id))
            if role and member:
                try:
                    await member.add_roles(role, reason=f"Compra confirmada por {interaction.user}")
                except discord.Forbidden:
                    await interaction.response.send_message(
                        "⚠️ Não consegui dar o cargo: o cargo do bot precisa estar **acima** do cargo configurado na hierarquia.",
                        ephemeral=True,
                    )
                    return

        # Criar canal de ticket para o comprador
        ticket_channel = await criar_ticket_channel(guild, member)

        # Embed no ticket
        embed_ticket = discord.Embed(
            title="✅ Compra confirmada!",
            description=(
                f"Olá {member.mention}! 🎉\n"
                f"Sua compra do produto **{pending.get('product_title', '')}** foi confirmada.\n"
                + (f"O cargo {role.mention} foi atribuído à sua conta.\n" if role else "")
                + "\nEste canal será deletado em breve."
            ),
            color=0x57F287,
        )
        close_view = CloseTicketView()
        await ticket_channel.send(content=member.mention, embed=embed_ticket, view=close_view)

        # Remover solicitação pendente
        storage.remove_pending(user_id, guild.id)

        # Atualizar embed de confirmação
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="✅ Compra confirmada",
                description=(
                    f"Confirmado por {interaction.user.mention}.\n"
                    f"Ticket criado: {ticket_channel.mention}"
                    + (f"\nCargo **{role.name}** atribuído." if role else "")
                ),
                color=0x57F287,
            ),
            view=self,
        )

    @discord.ui.button(
        label="❌ Recusar",
        style=discord.ButtonStyle.danger,
        custom_id="compra_recusar",
    )
    async def recusar(self, interaction: discord.Interaction, button: discord.ui.Button):
        pending = await self._get_pending(interaction)
        if not pending:
            await interaction.response.send_message("Solicitação não encontrada.", ephemeral=True)
            return

        guild = interaction.guild
        member = guild.get_member(pending["user_id"])

        storage.remove_pending(pending["user_id"], guild.id)

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="❌ Compra recusada",
                description=f"Recusado por {interaction.user.mention}.",
                color=0xED4245,
            ),
            view=self,
        )

        # Avisar comprador por DM
        if member:
            try:
                await member.send(
                    f"❌ Sua solicitação de compra do produto **{pending.get('product_title', '')}** foi recusada."
                )
            except discord.Forbidden:
                pass  # DM bloqueada, ignora


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
# Criar canal de ticket para o comprador
# ---------------------------------------------------------------------------
async def criar_ticket_channel(guild: discord.Guild, member: discord.Member) -> discord.TextChannel:
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True, read_message_history=True
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

    channel_name = f"compra-{member.name}".lower()[:90]
    return await guild.create_text_channel(name=channel_name, overwrites=overwrites, category=category)


# ---------------------------------------------------------------------------
# Fechar ticket
# ---------------------------------------------------------------------------
async def handle_close_ticket(interaction: discord.Interaction):
    is_staff = (
        STAFF_ROLE_ID is not None
        and any(role.id == int(STAFF_ROLE_ID) for role in interaction.user.roles)
    )
    is_manager = interaction.user.guild_permissions.manage_channels

    if not (is_staff or is_manager):
        await interaction.response.send_message(
            "Você não tem permissão para fechar este ticket.", ephemeral=True
        )
        return

    await interaction.response.send_message("Fechando o ticket em 5 segundos...")

    async def delete_later():
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except discord.HTTPException as e:
            print(f"Erro ao deletar canal: {e}")

    asyncio.create_task(delete_later())


# ---------------------------------------------------------------------------
# Painel de configuração do produto
# ---------------------------------------------------------------------------

class TituloModal(discord.ui.Modal, title="Título do produto"):
    def __init__(self, config_view: "ConfigPanelView"):
        super().__init__()
        self.config_view = config_view
        self.titulo = discord.ui.TextInput(
            label="Título",
            placeholder="Ex: VIP Gold",
            max_length=256,
            default=config_view.draft.get("title", ""),
        )
        self.add_item(self.titulo)

    async def on_submit(self, interaction: discord.Interaction):
        self.config_view.draft["title"] = self.titulo.value
        await self.config_view.refresh(interaction)


class DescricaoModal(discord.ui.Modal, title="Descrição do produto"):
    def __init__(self, config_view: "ConfigPanelView"):
        super().__init__()
        self.config_view = config_view
        self.descricao = discord.ui.TextInput(
            label="Descrição",
            style=discord.TextStyle.paragraph,
            placeholder="Ex: Acesso ao canal VIP, sem anúncios...",
            max_length=4096,
            default=config_view.draft.get("description", ""),
        )
        self.add_item(self.descricao)

    async def on_submit(self, interaction: discord.Interaction):
        self.config_view.draft["description"] = self.descricao.value
        await self.config_view.refresh(interaction)


class ImagemModal(discord.ui.Modal, title="Imagem do produto"):
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
        url = self.url.value.strip() if self.url.value else None
        if url and not (url.startswith("http://") or url.startswith("https://")):
            await interaction.response.send_message(
                "URL inválida. Use um link direto começando com `https://`.", ephemeral=True
            )
            return
        self.config_view.draft["image"] = url or None
        await self.config_view.refresh(interaction)


class CanalProdutoSelect(discord.ui.ChannelSelect):
    def __init__(self, config_view: "ConfigPanelView"):
        self.config_view = config_view
        super().__init__(
            placeholder="Canal onde o produto será publicado",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        self.config_view.draft["channel_id"] = self.values[0].id
        await self.config_view.refresh(interaction)


class CanalConfirmacaoSelect(discord.ui.ChannelSelect):
    def __init__(self, config_view: "ConfigPanelView"):
        self.config_view = config_view
        super().__init__(
            placeholder="Canal onde você receberá as solicitações",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        self.config_view.draft["confirm_channel_id"] = self.values[0].id
        await self.config_view.refresh(interaction)


class CargoSelect(discord.ui.RoleSelect):
    def __init__(self, config_view: "ConfigPanelView"):
        self.config_view = config_view
        super().__init__(
            placeholder="Cargo a dar após confirmar (opcional)",
            min_values=0,
            max_values=1,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction):
        self.config_view.draft["role_id"] = self.values[0].id if self.values else None
        await self.config_view.refresh(interaction)


class ConfigPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)
        self.draft = {
            "title": None,
            "description": None,
            "image": None,
            "channel_id": None,
            "confirm_channel_id": None,
            "role_id": None,
        }
        self.add_item(CanalProdutoSelect(self))
        self.add_item(CanalConfirmacaoSelect(self))
        self.add_item(CargoSelect(self))

    def build_embed(self) -> discord.Embed:
        titulo = self.draft.get("title") or "*(não definido)*"
        descricao = self.draft.get("description") or "*(não definida)*"
        canal_id = self.draft.get("channel_id")
        confirm_id = self.draft.get("confirm_channel_id")
        role_id = self.draft.get("role_id")

        embed = discord.Embed(
            title="⚙️ Configuração do produto",
            description=(
                f"**Título:** {titulo}\n"
                f"**Descrição:** {descricao}\n"
                f"**Canal do produto:** {'<#' + str(canal_id) + '>' if canal_id else '*(não selecionado)*'}\n"
                f"**Canal de confirmação:** {'<#' + str(confirm_id) + '>' if confirm_id else '*(não selecionado)*'}\n"
                f"**Cargo ao confirmar:** {'<@&' + str(role_id) + '>' if role_id else '*(nenhum)*'}\n"
                f"**Imagem:** {'definida ✅' if self.draft.get('image') else 'nenhuma'}"
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

    @discord.ui.button(label="Título", emoji="📝", style=discord.ButtonStyle.secondary, row=3)
    async def set_title(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TituloModal(self))

    @discord.ui.button(label="Descrição", emoji="🧾", style=discord.ButtonStyle.secondary, row=3)
    async def set_description(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DescricaoModal(self))

    @discord.ui.button(label="Imagem", emoji="🖼️", style=discord.ButtonStyle.secondary, row=3)
    async def set_image(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ImagemModal(self))

    @discord.ui.button(label="Publicar", emoji="✅", style=discord.ButtonStyle.success, row=4)
    async def publish(self, interaction: discord.Interaction, button: discord.ui.Button):
        faltando = []
        if not self.draft.get("title"):
            faltando.append("Título")
        if not self.draft.get("description"):
            faltando.append("Descrição")
        if not self.draft.get("channel_id"):
            faltando.append("Canal do produto")
        if not self.draft.get("confirm_channel_id"):
            faltando.append("Canal de confirmação")

        if faltando:
            await interaction.response.send_message(
                f"Faltando preencher: **{', '.join(faltando)}**.", ephemeral=True
            )
            return

        canal = interaction.guild.get_channel(self.draft["channel_id"])
        if canal is None:
            await interaction.response.send_message(
                "Canal do produto não encontrado. Tente selecionar novamente.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=self.draft["title"],
            description=self.draft["description"],
            color=0x5865F2,
        )
        embed.set_footer(text="Clique no botão abaixo para comprar")
        if self.draft.get("image"):
            embed.set_image(url=self.draft["image"])

        buy_view = BuyView()
        sent_message = await canal.send(embed=embed, view=buy_view)

        storage.set_guild_config(
            interaction.guild_id,
            sent_message.id,
            {
                "title": self.draft["title"],
                "description": self.draft["description"],
                "image": self.draft.get("image"),
                "channel_id": canal.id,
                "message_id": sent_message.id,
                "confirm_channel_id": self.draft["confirm_channel_id"],
                "role_id": self.draft.get("role_id"),
            },
        )

        for child in self.children:
            child.disabled = True

        role_id = self.draft.get("role_id")
        confirm_id = self.draft["confirm_channel_id"]
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="✅ Produto publicado",
                description=(
                    f"Produto publicado em <#{canal.id}>.\n"
                    f"Solicitações chegam em <#{confirm_id}>.\n"
                    + (f"Cargo ao confirmar: <@&{role_id}>" if role_id else "Sem cargo configurado.")
                ),
                color=0x57F287,
            ),
            view=self,
        )

    @discord.ui.button(label="Cancelar", emoji="✖️", style=discord.ButtonStyle.danger, row=4)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            embed=discord.Embed(title="Configuração cancelada", color=0xED4245),
            view=self,
        )
        self.stop()


@client.tree.command(name="painel", description="Cria e publica um produto com botão de compra")
async def painel(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "Você precisa da permissão **Gerenciar Servidor** para usar esse comando.",
            ephemeral=True,
        )
        return

    view = ConfigPanelView()
    await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)


client.run(DISCORD_TOKEN)
