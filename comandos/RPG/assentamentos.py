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

# Guardamos as funções originais para instalar uma camada não letal sem substituir o combate.
_LUTA_MODULE = None
_ORIG_DANO_FISICO = None
_ORIG_DANO_MAGIA = None
_ORIG_PROCESSAR_EFEITOS = None
_HABS_MODULE = None
_ORIG_DANO_HABILIDADE = None


def _agendar(coro):
    return asyncio.create_task(coro)


async def _get_assentamento(channel_id):
    return await run_db(db[COLLECTION].find_one, {"tipo": "assentamento", "guild_id": str(GUILD_ID), "canal_id": str(channel_id)})


async def _garantir_assentamento(channel_id):
    doc = await _get_assentamento(channel_id)
    if doc:
        return doc
    agora = datetime.now(timezone.utc)
    doc = {
        "tipo": "assentamento",
        "guild_id": str(GUILD_ID),
        "canal_id": str(channel_id),
        "DONO": None,
        "data_posse": None,
        "hora_posse": None,
        "derrotados": 0,
        "pessoas_derrotadas": 0,
        "criado_em": agora,
    }
    await run_db(db[COLLECTION].update_one,
                 {"tipo": "assentamento", "guild_id": str(GUILD_ID), "canal_id": str(channel_id)},
                 {"$setOnInsert": doc}, upsert=True)
    return await _get_assentamento(channel_id)


async def _definir_dono(channel_id, user_id):
    agora = datetime.now(timezone.utc)
    await run_db(db[COLLECTION].update_one,
                 {"tipo": "assentamento", "guild_id": str(GUILD_ID), "canal_id": str(channel_id)},
                 {"$set": {
                     "DONO": str(user_id),
                     "data_posse": agora.strftime("%d/%m/%Y"),
                     "hora_posse": agora.strftime("%H:%M:%S"),
                 }, "$inc": {"derrotados": 1, "pessoas_derrotadas": 1}}, upsert=True)


def _eh_duelo(combate):
    return bool(combate and combate.get("assentamento_duelo"))


def _instalar_protecao_nao_letal():
    global _LUTA_MODULE, _ORIG_DANO_FISICO, _ORIG_DANO_MAGIA, _ORIG_PROCESSAR_EFEITOS
    global _HABS_MODULE, _ORIG_DANO_HABILIDADE
    try:
        from . import luta as luta_mod
        _LUTA_MODULE = luta_mod
        if _ORIG_DANO_FISICO is None:
            _ORIG_DANO_FISICO = luta_mod._calcular_dano_fisico
            def dano_fisico_duelo(atacante, defensor):
                dano, motivo = _ORIG_DANO_FISICO(atacante, defensor)
                if defensor.get("_duelo_assentamento"):
                    dano = min(int(dano), max(0, int(defensor.get("vida", 1)) - 1))
                return dano, motivo
            luta_mod._calcular_dano_fisico = dano_fisico_duelo

        if _ORIG_DANO_MAGIA is None and hasattr(luta_mod, "_calcular_dano_magia"):
            _ORIG_DANO_MAGIA = luta_mod._calcular_dano_magia
            def dano_magia_duelo(self, atacante, defensor, ataque):
                dano, motivo = _ORIG_DANO_MAGIA(self, atacante, defensor, ataque)
                if defensor.get("_duelo_assentamento"):
                    dano = min(int(dano), max(0, int(defensor.get("vida", 1)) - 1))
                return dano, motivo
            luta_mod._calcular_dano_magia = dano_magia_duelo

        # Efeitos periódicos também não podem matar em um duelo.
        if _ORIG_PROCESSAR_EFEITOS is None and hasattr(luta_mod.Luta, "_processar_efeitos"):
            _ORIG_PROCESSAR_EFEITOS = luta_mod.Luta._processar_efeitos
            async def processar_efeitos_duelo(self, *args, **kwargs):
                resultado = await _ORIG_PROCESSAR_EFEITOS(self, *args, **kwargs)
                for combate in getattr(self, "combates", {}).values():
                    if _eh_duelo(combate):
                        for participante in combate.get("participantes", []):
                            if participante.get("tipo") == "jogador":
                                participante["vida"] = max(1, int(participante.get("vida", 1)))
                return resultado
            luta_mod.Luta._processar_efeitos = processar_efeitos_duelo

        try:
            from . import habilidades_combate as habs_mod
            _HABS_MODULE = habs_mod
            if _ORIG_DANO_HABILIDADE is None and hasattr(habs_mod, "_dano_habilidade_fisica"):
                _ORIG_DANO_HABILIDADE = habs_mod._dano_habilidade_fisica
                def dano_habilidade_duelo(atacante, defensor, habilidade):
                    resultado = _ORIG_DANO_HABILIDADE(atacante, defensor, habilidade)
                    if defensor.get("_duelo_assentamento"):
                        if isinstance(resultado, tuple):
                            return (min(int(resultado[0]), max(0, int(defensor.get("vida", 1)) - 1)), *resultado[1:])
                        return min(int(resultado), max(0, int(defensor.get("vida", 1)) - 1))
                    return resultado
                habs_mod._dano_habilidade_fisica = dano_habilidade_duelo
        except Exception:
            pass
    except Exception as erro:
        print(f"[ASSENTAMENTOS][ERRO][PATCH] {type(erro).__name__}: {erro}")


class Duelo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._instalado = False

    async def cog_load(self):
        if not self._instalado:
            _instalar_protecao_nao_letal()
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
        if dono and str(ctx.author.id) == str(dono):
            adversario = membro
        elif dono and str(membro.id) == str(dono):
            adversario = membro
        else:
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
        combate = {
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
        luta.combates[ctx.channel.id] = combate
        for jogador in participantes:
            luta._atualizar_situacao(jogador["id"], str(ctx.guild.id), "ativo_combate")

        await ctx.send(embed=discord.Embed(
            title="🏰 | Duelo pelo Assentamento",
            description=f"⚔️ **{ctx.author.display_name}** desafiou **{adversario.display_name}**!\n\nO vencedor ficará com a posse do assentamento.\n❤️ O duelo é **não letal**: nenhum jogador pode ficar abaixo de 1 HP.",
            color=discord.Color.dark_gold(),
        ))
        await luta._mostrar_inicio(ctx)

    @commands.command(name="assentamento", aliases=["assentamento-info", "posse"])
    async def assentamento(self, ctx):
        if not ctx.guild or ctx.guild.id != GUILD_ID or ctx.channel.id not in CANAIS_ASSENTAMENTOS:
            await ctx.send("❌ Este comando só pode ser usado nos canais de assentamento.")
            return
        doc = await _garantir_assentamento(ctx.channel.id)
        dono = doc.get("DONO")
        embed = discord.Embed(title="🏰 | Assentamento", color=discord.Color.dark_gold())
        embed.add_field(name="👑 DONO", value=f"<@{dono}>" if dono else "**Sem dono**", inline=False)
        embed.add_field(name="📅 Posse", value=(f"{doc.get('data_posse')} às {doc.get('hora_posse')}" if dono else "—"), inline=True)
        embed.add_field(name="⚔️ Pessoas derrotadas", value=str(doc.get("derrotados", doc.get("pessoas_derrotadas", 0))), inline=True)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Duelo(bot))
