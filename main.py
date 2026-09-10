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
MENSAGEM_MANUTENCAO = "O bot está em manutenção nesse momento, aguarde até ser reativado."

_context_send_original = commands.Context.send

def _partes_texto(texto, limite):
    texto = str(texto)
    if len(texto) <= limite:
        return [texto]
    partes = []
    restante = texto
    while restante:
        corte = restante.rfind("\n", 0, limite + 1)
        if corte < max(1, limite // 2):
            corte = restante.rfind(" ", 0, limite + 1)
        if corte < 1:
            corte = limite
        partes.append(restante[:corte])
        restante = restante[corte:].lstrip()
    return partes

def _normalizar_embed(embed):
    if embed is None:
        return []
    descricoes = []
    base = discord.Embed.from_dict(embed.to_dict())
    if base.description and len(base.description) > 4096:
        partes = _partes_texto(base.description, 4096)
        base.description = partes[0]
        descricoes.extend(partes[1:])
    novos_campos = []
    for campo in list(base.fields):
        for indice, valor in enumerate(_partes_texto(campo.value, 1024)):
            nome = campo.name if indice == 0 else f"{campo.name} (continuação)"
            novos_campos.append((nome[:256], valor, campo.inline))
    base.clear_fields()
    for nome, valor, inline in novos_campos[:25]:
        base.add_field(name=nome, value=valor, inline=inline)
    embeds = [base]
    for descricao in descricoes:
        extra = discord.Embed(description=descricao, color=base.color.value if base.color else discord.Color.blurple().value)
        if base.footer and base.footer.text:
            extra.set_footer(text=base.footer.text)
        embeds.append(extra)
    return embeds

async def _context_send_com_embed(self, content=None, *, embed=None, **kwargs):
    if content is not None and embed is None:
        ultimo = None
        for texto in _partes_texto(content, 2000):
            item = discord.Embed(description=texto, color=discord.Color.blurple(), timestamp=discord.utils.utcnow())
            item.set_footer(text="Tensura Moon - Korczak Technologies!")
            ultimo = await _context_send_original(self, content=None, embed=item, **kwargs)
        return ultimo
    if embed is not None:
        ultimo = None
        for item in _normalizar_embed(embed):
            ultimo = await _context_send_original(self, content=content if item is embed else None, embed=item, **kwargs)
        return ultimo
    return await _context_send_original(self, content=content, embed=embed, **kwargs)

commands.Context.send = _context_send_com_embed

@bot.check
async def verificar_canal_de_comandos(ctx):
    comando = getattr(ctx.command, "name", "").casefold()

    # Durante a manutenção, nenhum comando é executado. A única exceção é
    # !manutencao, que permanece disponível para que um administrador possa
    # encerrar a manutenção. Eventos não passam por este check.
    if getattr(bot, "em_manutencao", False) and comando != "manutencao":
        await ctx.send(MENSAGEM_MANUTENCAO)
        return False

    if ctx.guild is None:
        return True

    if ctx.channel.id == CANAL_REGISTRO_ID:
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
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument) and param_name == "membro" and getattr(command, "name", None) == "pvp" and getattr(parent, "name", None) == "luta":
        mencoes = [m for m in ctx.message.mentions if not m.bot]
        membro = next((m for m in mencoes if m.id != ctx.author.id), None)
        if membro is not None and hasattr(ctx, "cog"):
            await command.callback(ctx.cog, ctx, membro)
            return
        await ctx.send("❌ Mencione um membro válido. Exemplo: `!luta pvp @jogador`")
        return
    erro_original = getattr(error, "original", error)
    print(f"[COMANDO][ERRO] {type(erro_original).__name__}: {erro_original}")
    if ctx.guild is not None:
        try:
            luta = bot.get_cog("Luta")
            combate = luta._obter_combate(ctx.channel.id) if luta else None
            if combate and combate.get("ativo") and combate.get("fase") == "defesa":
                ataque = combate.get("ataque_pendente")
                if ataque and ataque.get("_resolvendo"):
                    ataque["_resolvendo"] = False
                    combate["ataque_pendente"] = None
                    combate["fase"] = "ataque"
                    await ctx.send("⚠️ A ação falhou e foi cancelada com segurança. O combate continua no turno atual.")
        except Exception as recuperacao_erro:
            print(f"[COMANDO][RECUPERACAO][ERRO] {type(recuperacao_erro).__name__}: {recuperacao_erro}")
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
        "comandos.RPG.treino", "comandos.RPG.magias", "comandos.RPG.habs",
        "comandos.RPG.status", "comandos.RPG.racas_chances", "comandos.RPG.desregistro_geral", "comandos.RPG.nivel", "comandos.RPG.nascimento",
        "comandos.RPG.habilidades_combate", "comandos.RPG.correcoes_luta",
        "comandos.RPG.progressao", "comandos.RPG.status_habilidades", "comandos.RPG.recuperacao", "comandos.RPG.loja",
        "comandos.RPG.inventario", "comandos.RPG.usarhab",
        "comandos.RPG.evento_monstros", "comandos.RPG.assentamentos",
        "comandos.ECONOMIA.Mora", "comandos.ECONOMIA.Hunos", "comandos.ADMINISTRACAO.luta_admin",
        "comandos.ADMINISTRACAO.autorole_commands", "comandos.ADMINISTRACAO.autorole", "comandos.ADMINISTRACAO.configurações",
        "comandos.ADMINISTRACAO.canais_comandos", "comandos.ADMINISTRACAO.moderacao", "comandos.ADMINISTRACAO.automod",
        "comandos.ADMINISTRACAO.boas_vindas", "comandos.ADMINISTRACAO.logs", "comandos.ADMINISTRACAO.ajuda",
        "comandos.ADMINISTRACAO.manutencao",
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
            await ensure_indexes()
            await bot.start(TOKEN)
    finally:
        await close_db()

asyncio.run(main())