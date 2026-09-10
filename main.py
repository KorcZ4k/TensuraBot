import asyncio
import os
import datetime

import discord
from discord.ext import commands
from dotenv import load_dotenv

from database.python.users import cadastro_async
from database.python.mongodb import db, close_db
from database.python.mongo_indexes import ensure_indexes
from database.python.canais_comandos import canal_bloqueado

load_dotenv()
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents, case_insensitive=True)
_cadastro_inicial_concluido = False
_online_notificado = False
CANAL_REGISTRO_ID = 1543040925788413982
COMANDOS_REGISTRO_PERMITIDOS = {"registrar", "desregistrar"}

_context_send_original = commands.Context.send
async def _context_send_com_embed(self, content=None, *, embed=None, **kwargs):
    if content is not None and embed is None:
        embed = discord.Embed(description=str(content), color=discord.Color.blurple(), timestamp=discord.utils.utcnow())
        embed.set_footer(text="Tensura Moon - Korczak Technologies!")
        content = None
    return await _context_send_original(self, content=content, embed=embed, **kwargs)
commands.Context.send = _context_send_com_embed

@bot.check
async def verificar_canal_de_comandos(ctx):
    if ctx.guild is None:
        return True
    if ctx.channel.id == CANAL_REGISTRO_ID:
        comando = getattr(ctx.command, "name", "").casefold()
        if comando not in COMANDOS_REGISTRO_PERMITIDOS:
            await ctx.send("🚫 Neste canal, apenas os comandos `!registrar` e `!desregistrar` estão disponíveis.")
            return False
        return True
    if ctx.author.guild_permissions.administrator:
        return True
    if await canal_bloqueado(ctx.guild.id, ctx.channel.id):
        await ctx.send("🚫 Este canal não permite o uso de comandos.")
        return False
    return True

@bot.event
async def on_member_join(member):
    await cadastro_async([member])

@bot.event
async def on_command_error(ctx, error):
    command = getattr(ctx, "command", None)
    parent = getattr(command, "parent", None)
    param_name = getattr(getattr(error, "param", None), "name", None)
    if isinstance(error, commands.CheckFailure):
        if ctx.guild is not None:
            if ctx.channel.id == CANAL_REGISTRO_ID:
                return
            if not ctx.author.guild_permissions.administrator:
                try:
                    if await canal_bloqueado(ctx.guild.id, ctx.channel.id):
                        return
                except Exception:
                    pass
    if (isinstance(error, commands.MissingRequiredArgument) and param_name == "membro" and getattr(command, "name", None) == "pvp" and getattr(parent, "name", None) == "luta"):
        mencoes = [m for m in ctx.message.mentions if not m.bot]
        membro = next((m for m in mencoes if m.id != ctx.author.id), None)
        if membro is not None and hasattr(ctx, "cog"):
            await command.callback(ctx.cog, ctx, membro)
            return
        await ctx.send("❌ Mencione um membro válido. Exemplo: `!luta pvp @jogador`")
        return
    if isinstance(error, commands.CommandNotFound):
        return
    raise error

async def _cadastrar_guild(guild):
    membros = [member for member in guild.members if not member.bot]
    quantidade = await cadastro_async(membros)
    print(f"{guild.name}: {quantidade} usuários processados.")
    return quantidade

async def _cadastro_inicial_background():
    global _cadastro_inicial_concluido
    try:
        await asyncio.gather(*(_cadastrar_guild(guild) for guild in bot.guilds))
    except Exception as erro:
        print(f"[CADASTRO][ERRO] {type(erro).__name__}: {erro}")
        return
    _cadastro_inicial_concluido = True

@bot.event
async def on_ready():
    global _cadastro_inicial_concluido, _online_notificado
    fuso_horario = datetime.timezone(datetime.timedelta(hours=-3))
    agora = datetime.datetime.now(fuso_horario)
    canal = bot.get_channel(1543040912912031775)
    print(f"Bot conectado como {bot.user}")
    # on_ready pode ser disparado novamente após uma reconexão. Não envie
    # várias mensagens "Online" para o mesmo processo.
    if canal is not None and not _online_notificado:
        embed = discord.Embed(title="🟢 | Online", description="Moon Tensura está online e pronto para o RPG", colour=0x1CAA00, timestamp=agora)
        embed.set_footer(text="Tensura Moon - Korczak Technologies!")
        await canal.send(embed=embed)
        _online_notificado = True
    if not _cadastro_inicial_concluido:
        asyncio.create_task(_cadastro_inicial_background())

async def _carregar_extensao_com_recuperacao_de_conflito(extensao):
    try:
        await bot.load_extension(extensao)
        return
    except commands.ExtensionFailed as erro:
        original = getattr(erro, "original", None) or getattr(erro, "__cause__", None)
        if not isinstance(original, commands.CommandRegistrationError):
            raise
        nome = getattr(original, "name", None)
        if not nome:
            raise
        removido = bot.remove_command(nome)
        if removido is None:
            raise
        print(f"[EXTENSÃO][CONFLITO] {extensao}: comando '{nome}' já existia; registro anterior removido, tentando novamente.")
        await bot.load_extension(extensao)

async def carregar_extensoes():
    extensoes = [
        "comandos.RPG.luta", "comandos.RPG.monstros_balanceamento", "comandos.RPG.party",
        "comandos.RPG.treino", "comandos.RPG.magias", "comandos.RPG.habs", "comandos.RPG.usarhab",
        "comandos.RPG.status", "comandos.RPG.racas_chances", "comandos.RPG.desregistro_geral", "comandos.RPG.nivel", "comandos.RPG.nascimento", "comandos.RPG.correcoes_luta",
        "comandos.RPG.progressao", "comandos.RPG.status_habilidades", "comandos.RPG.recuperacao", "comandos.RPG.loja", "comandos.RPG.inventario",
        "comandos.RPG.habilidades_combate", "comandos.RPG.evento_monstros", "comandos.RPG.assentamentos",
        "comandos.ECONOMIA.Mora", "comandos.ECONOMIA.Hunos", "comandos.ADMINISTRACAO.luta_admin",
        "comandos.ADMINISTRACAO.autorole_commands", "comandos.ADMINISTRACAO.autorole", "comandos.ADMINISTRACAO.configurações",
        "comandos.ADMINISTRACAO.canais_comandos", "comandos.ADMINISTRACAO.moderacao", "comandos.ADMINISTRACAO.automod",
        "comandos.ADMINISTRACAO.boas_vindas", "comandos.ADMINISTRACAO.logs", "comandos.ADMINISTRACAO.ajuda",
    ]
    for extensao in extensoes:
        try:
            await _carregar_extensao_com_recuperacao_de_conflito(extensao)
            print(f"[EXTENSÃO][OK] {extensao}")
        except Exception as erro:
            print(f"[EXTENSÃO][ERRO] {extensao}: {type(erro).__name__}: {erro}")
            raise

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN não foi configurado.")

async def main():
    try:
        async with bot:
            await carregar_extensoes()
            asyncio.create_task(ensure_indexes())
            await bot.start(TOKEN)
    finally:
        await close_db()

asyncio.run(main())