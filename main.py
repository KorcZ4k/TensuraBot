import asyncio
import os
import datetime

import discord
from discord.ext import commands
from dotenv import load_dotenv

from database.python.users import cadastro_async
from database.python.mongodb import db, close_db
from database.python.mongo_indexes import ensure_indexes

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents, case_insensitive=True)
_cadastro_inicial_concluido = False


@bot.event
async def on_member_join(member):
    await cadastro_async([member])


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
    global _cadastro_inicial_concluido

    fuso_horario = datetime.timezone(datetime.timedelta(hours=-3))
    agora = datetime.datetime.now(fuso_horario)
    canal = bot.get_channel(1543040912912031775)

    print(f"Bot conectado como {bot.user}")

    if canal is not None:
        embed = discord.Embed(
            title="🟢 | Online",
            description="Moon Tensura está online e pronto para o RPG",
            colour=0x1CAA00,
            timestamp=agora,
        )
        embed.set_footer(text="Tensura Moon - Korczak Technologies!")
        await canal.send(embed=embed)

    if not _cadastro_inicial_concluido:
        asyncio.create_task(_cadastro_inicial_background())


async def carregar_extensoes():
    extensoes = [
        "comandos.RPG.luta",
        "comandos.RPG.party",
        "comandos.RPG.treino",
        "comandos.RPG.magias",
        "comandos.RPG.habs",
        "comandos.RPG.usarhab",
        "comandos.RPG.status",
        "comandos.RPG.nivel",
        "comandos.RPG.nascimento",
        "comandos.RPG.correcoes_luta",
        "comandos.RPG.status_habilidades",
        "comandos.ECONOMIA.Mora",
        "comandos.ADMINISTRACAO.autorole_commands",
        "comandos.ADMINISTRACAO.autorole",
        "comandos.ADMINISTRACAO.configurações",
        "comandos.ADMINISTRACAO.moderacao",
        "comandos.ADMINISTRACAO.automod",
        "comandos.ADMINISTRACAO.boas_vindas",
        "comandos.ADMINISTRACAO.logs",
        "comandos.ADMINISTRACAO.ajuda",
    ]

    for extensao in extensoes:
        try:
            await bot.load_extension(extensao)
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
