# Ticket Bot — Python (discord.py)

Bot simples de tickets, configurável 100% pelo comando `/setup`.

## O que você precisa instalar

1. **Python 3.10 ou superior** → baixe em https://www.python.org/downloads/
   - No instalador do Windows, **marque a caixa "Add Python to PATH"** antes de clicar em Install

2. As bibliotecas do projeto (estão no `requirements.txt`, você instala com um único comando — veja abaixo)

## Passo a passo

### 1. Extraia o zip e abra o terminal/cmd dentro da pasta `ticket_bot_py`

### 2. (Recomendado) Crie um ambiente virtual
```bash
python -m venv venv
```
Ative o ambiente:
- Windows: `venv\Scripts\activate`
- Linux/Mac: `source venv/bin/activate`

### 3. Instale as dependências
```bash
pip install -r requirements.txt
```
Isso instala automaticamente:
- `discord.py` (a lib que conecta o bot ao Discord)
- `python-dotenv` (lê o arquivo `.env`)

### 4. Configure o bot
1. Copie `.env.example` e renomeie a cópia para `.env`
2. Abra o `.env` num editor de texto e preencha:
   - `DISCORD_TOKEN` → pegue em https://discord.com/developers/applications → sua aplicação → **Bot** → Reset Token
   - `GUILD_ID` → ative o Modo Desenvolvedor no Discord (Configurações > Avançado), clique direito no nome do servidor > Copiar ID
   - `TICKET_CATEGORY_ID` (opcional) → categoria onde os tickets serão criados
   - `STAFF_ROLE_ID` (opcional) → cargo que pode ver/fechar qualquer ticket

### 5. Convide o bot pro seu servidor
No Developer Portal → sua aplicação → **OAuth2 > URL Generator**:
- Scopes: `bot`, `applications.commands`
- Permissões: Manage Channels, Send Messages, Embed Links, Manage Roles, Read Message History

Copie o link gerado e abra no navegador pra convidar o bot.

### 6. Rode o bot
```bash
python bot.py
```

Pronto — os slash commands são sincronizados automaticamente toda vez que o bot inicia.

## Como usar

No Discord, rode (precisa de permissão **Gerenciar Servidor**):

```
/painel
```

Isso abre um painel interativo (só você vê) com botões para configurar:
- **Título** → abre uma janela pra digitar o título
- **Descrição** → abre uma janela pra digitar a descrição
- **Imagem** → abre uma janela pra colar a URL de uma imagem (opcional — Discord não permite upload de arquivo em botão/modal, só link)
- **Canal** → menu suspenso pra escolher o canal onde o painel será publicado
- **Publicar** → envia o embed configurado no canal escolhido, com o botão **Abrir Ticket**
- **Cancelar** → descarta a configuração

Quando alguém clicar em **Abrir Ticket**, um canal privado `ticket-usuario` é criado automaticamente,
visível só para o usuário (e staff, se configurado), com o botão **Fechar Ticket** dentro.

## Estrutura do projeto

```
ticket_bot_py/
├── data/
│   ├── config.json      → configuração do painel por servidor (gerado automaticamente)
│   └── tickets.json     → tickets abertos no momento (gerado automaticamente)
├── bot.py                → lógica principal do bot (eventos, embed, botões, /setup)
├── storage.py             → leitura/escrita simples em JSON
├── requirements.txt
├── .env.example
└── README.md
```

## Observações
- O armazenamento é em arquivos JSON simples — ótimo pra testar e servidores pequenos/médios
- Os botões usam `custom_id` fixo + `add_view()` na inicialização, então continuam
  funcionando mesmo depois de reiniciar o bot
- Nunca compartilhe seu `DISCORD_TOKEN` publicamente
