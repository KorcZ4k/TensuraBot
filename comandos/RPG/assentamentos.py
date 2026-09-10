"""Assentamentos e duelos não letais para conquista territorial."""

import asyncio
from datetime import datetime, timezone

import discord
from discord.ext import commands

from database.python.mongodb import db, run_db
from database.python import luta as luta_db

GUILD_ID = 1543039757146136586
CANAIS_ASSENTAMENTOS = (
    1546990003467587625,
    1546989793391546450,
    1546989722885423155,
    1546989674290085979,
    1546989565892501515,
)
COLLECTION = "Evento"


async def _get_assentamento(channel_id):
    return await run_db(db[COLLECTION].find_one, {"tipo": "assentamento", "guild_id": str(GUILD_ID), "canal_id": str(channel_id)})


async def _garantir_assentamento(channel_id):
    doc = await _get_assentamento(channel_id)
    if doc:
        return doc
    doc = {
        "tipo": "assentamento",
        "guild_id": str(GUILD_ID),
        "canal_id": str(channel_id),
        "DONO": None,
        "data_posse": None,
        "hora_posse": None,
        "derrotados": 0,
        "pessoas_derrotadas": 0,
        "criado_em": datetime.now(timezone.utc),
    }
    await run_db(db[COLLECTION].update_one,
                 {"tipo": "assentamento", "guild_id": str(GUILD_ID), "canal_id": str(channel_id)},
                 {"$setOnInsert": doc}, upsert=True)
    return await _get_assentamento(channel_id)


async def _registrar_vitoria(channel_id, vencedor_id):
    agora = datetime.now(timezone.utc)
    await run_db(db[COLLECTION].update_one,
                 {"tipo": "assentamento", "guild_id": str(GUILD_ID), "canal_id": str(channel_id)},
                 {"$set": {
                     "DONO": str(vencedor_id),
                     "data_posse": agora.strftime("%d/%m/%Y"),
                     "hora_posse": agora.strftime("%H:%M:%S"),
                 }, "$inc": {"derrotados": 1, "pessoas_derrotadas": 1}}, upsert=True)


class Duelo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._instalado = False

    async def cog_load(self):
        if self._instalado:
            return
        self._instalado = True
        for canal_id in CANAIS_ASSENTAMENTOS:
            try:
                await _garantir_assentamento(canal_id)
            except Exception as erro:
                print(f"[ASSENTAMENTOS][ERRO][INIT] {canal_id}: {type(erro).__name__}: {erro}")
        print("[ASSENTAMENTOS] Sistema de assentamentos carregado.")

    @commands.command(name="duelo")
    async def duelo(self, ctx, membro: discord.Member):
        if not ctx.guild or ctx.guild.id != GUILD_ID or ctx.channel.id not in CANAIS_ASSENTAMENTOS:
            await ctx.send("❌ O comando `!duelo` só pode ser usado nos canais de assentamento.")
            return
        if membro.bot or membro.id == ctx.author.id:
            await ctx.send("❌ Escolha outro jogador válido para o duelo.")
            return
        luta = self.bot.get_cog("Luta")
        if luta is None:
            await ctx.send("❌ O sistema de luta não está disponível.")
            return
        if luta._combate_ativo(ctx.channel.id):
            await ctx.send("❌ Já existe um combate ativo neste assentamento.")
            return

        assentamento = await _garantir_assentamento(ctx.channel.id)
        dono = assentamento.get("DONO")
        if dono and str(ctx.author.id) != str(dono) and str(membro.id) != str(dono):
            await ctx.send(f"❌ Este assentamento pertence a <@{dono}>. Para conquistá-lo, o duelo deve ser contra o dono.")
            return
        adversario = membro

        for usuario in (ctx.author, adversario):
            verificacao = await run_db(luta_db.pode_lutar, str(usuario.id), str(ctx.guild.id))
            if not verificacao.get("pode", False):
                await ctx.send(f"❌ {usuario.display_name}: {verificacao.get('mensagem', 'não pode lutar.')}")
                return

        jogador_1 = await luta._criar_participante(str(ctx.author.id), str(ctx.guild.id))
        jogador_2 = await luta._criar_participante(str(adversario.id), str(ctx.guild.id))
        if not jogador_1 or not jogador_2:
            await ctx.send("❌ Um dos jogadores não possui personagem registrado.")
            return
        jogador_1["nome"] = jogador_1.get("nome") or ctx.author.display_name
        jogador_2["nome"] = jogador_2.get("nome") or adversario.display_name
        for jogador in (jogador_1, jogador_2):
            jogador["_duelo_assentamento"] = True
            jogador["vida"] = max(1, int(jogador.get("vida", 1)))

        participantes = [jogador_1, jogador_2]
        participantes.sort(key=lambda p: p.get("Velocidade", p.get("velocidade", 0)), reverse=True)
        luta.combates[ctx.channel.id] = {
            "participantes": participantes,
            "turno": 0,
            "numero_turno": 1,
            "fase": "ataque",
            "ativo": True,
            "pvp": True,
            "guild_id": str(ctx.guild.id),
            "ataque_pendente": None,
            "historico": [],
            "aguardando_finalizacao": False,
            "vencedor_id": None,
            "perdedor_id": None,
            "assentamento_duelo": True,
            "assentamento_canal_id": ctx.channel.id,
        }
        for jogador in participantes:
            await luta._marcar_combate(participantes, str(ctx.guild.id), "ativo_combate")

        await ctx.send(embed=discord.Embed(
            title="🏰 | Duelo pelo Assentamento",
            description=f"⚔️ **{ctx.author.display_name}** desafiou **{adversario.display_name}**!\n\n👑 O vencedor ficará com a posse do assentamento.\n❤️ Duelo não letal: nenhum jogador pode ser reduzido abaixo de **1 HP**.",
            color=discord.Color.dark_gold(),
        ))
        await luta._mostrar_inicio(ctx)

    @commands.command(name="assentamento", aliases=["posse"])
    async def assentamento(self, ctx):
        if not ctx.guild or ctx.guild.id != GUILD_ID or ctx.channel.id not in CANAIS_ASSENTAMENTOS:
            await ctx.send("❌ Este comando só pode ser usado nos canais de assentamento.")
            return
        doc = await _garantir_assentamento(ctx.channel.id)
        dono = doc.get("DONO")
        derrotados = int(doc.get("derrotados", doc.get("pessoas_derrotadas", 0)) or 0)
        embed = discord.Embed(title="🏰 | Assentamento", color=discord.Color.dark_gold())
        embed.add_field(name="👑 DONO", value=f"<@{dono}>" if dono else "**Sem dono**", inline=False)
        embed.add_field(name="📅 Posse", value=(f"{doc.get('data_posse')} às {doc.get('hora_posse')}" if dono else "—"), inline=True)
        embed.add_field(name="⚔️ Pessoas derrotadas", value=str(derrotados), inline=True)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Duelo(bot))
