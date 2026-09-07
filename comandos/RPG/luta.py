"""Camada não bloqueante do sistema de combate."""

import asyncio
import random
import unicodedata

import discord

from database.python.mongodb import db, run_db
from database.python import luta as luta_db
from . import luta_sync as _base

Luta = _base.Luta
_RESOLVER_ATAQUE_ORIGINAL = _base.Luta._resolver_ataque


def _normalizar_nome(nome):
    texto = str(nome or "").strip()
    texto = unicodedata.normalize("NFKC", texto)
    return texto.casefold()


async def _pode_lutar(user_id, guild_id):
    return await run_db(luta_db.pode_lutar, user_id, guild_id)


async def _criar_participante(user_id, guild_id):
    return await run_db(luta_db.criar_participante_jogador, user_id, guild_id)


def _agendar_db(self, operation, *args, **kwargs):
    tasks = getattr(self, "_mongo_tasks", None)
    if tasks is None:
        tasks = self._mongo_tasks = set()
    task = asyncio.create_task(run_db(operation, *args, **kwargs))
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return task


def _encontrar_monstro(self, nome):
    nome_normalizado = _normalizar_nome(nome)
    for monstro_id, dados in luta_db.MONSTROS.items():
        if _normalizar_nome(monstro_id) == nome_normalizado:
            return monstro_id
        if _normalizar_nome(dados.get("nome", "")) == nome_normalizado:
            return monstro_id
    return None


async def _aguardar_escritas(self):
    tasks = getattr(self, "_mongo_tasks", None)
    if tasks:
        await asyncio.gather(*tuple(tasks))


def _atualizar_situacao(self, user_id, guild_id, situacao):
    if db is None:
        return
    return _agendar_db(
        self,
        db["Jogadores"].update_one,
        {"ID": str(user_id), "guild_id": str(guild_id)},
        {"$set": {"Situação": situacao}},
    )


def _dar_recompensas(self, user_id, guild_id, xp, hunos):
    if db is None:
        return
    xp = int(xp or 0)
    hunos = int(hunos or 0)
    if xp > 0:
        _agendar_db(
            self,
            db["Jogadores"].update_one,
            {"ID": str(user_id), "guild_id": str(guild_id)},
            {"$inc": {"XP": xp}},
        )
    if hunos > 0:
        _agendar_db(
            self,
            db["Hunos"].update_one,
            {"ID": str(user_id), "guild_id": str(guild_id)},
            {"$inc": {"carteira": hunos}},
            upsert=True,
        )


def _salvar_participantes(self, combate, situacao_padrao="ativo", morto_id=None):
    if db is None:
        return
    guild_id = combate["guild_id"]
    for participante in combate["participantes"]:
        if participante["tipo"] != "jogador":
            continue
        situacao = situacao_padrao
        if morto_id is not None and str(participante["id"]) == str(morto_id):
            situacao = "morto"
        _agendar_db(
            self,
            db["Jogadores"].update_one,
            {"ID": str(participante["id"]), "guild_id": str(guild_id)},
            {
                "$set": {
                    "Vida": int(participante.get("vida", 0)),
                    "Mana": int(participante.get("mana", 0)),
                    "Situação": situacao,
                }
            },
        )


def _obter_golpe_monstro(monstro):
    # A lista de golpes vem da configuração do tipo do monstro, não do
    # participante de combate. Assim, um golpe só pode ser usado se estiver
    # explicitamente permitido para aquele monstro.
    configuracao = luta_db.MONSTROS.get(str(monstro.get("id", "")), {})
    golpes_ids = configuracao.get("golpes", [])
    disponiveis = [
        luta_db.GOLPES[g]
        for g in golpes_ids
        if g in luta_db.GOLPES
    ]
    return random.choice(disponiveis) if disponiveis else {
        "nome": "Ataque do Monstro",
        "emoji": "👹",
        "efeito": {},
    }


async def _ataque_monstro(self, ctx):
    combate = self._obter_combate(ctx.channel.id)
    if not combate or not combate.get("ativo") or combate["fase"] != "ataque":
        return
    atacante = self._obter_atacante(combate)
    defensor = self._obter_defensor(combate)
    if atacante["tipo"] != "monstro":
        return

    golpe = _obter_golpe_monstro(atacante)
    efeito = dict(golpe.get("efeito", {})) if isinstance(golpe.get("efeito"), dict) else {}
    if _normalizar_nome(efeito.get("nome", "")) == "sangramento":
        efeito["turnos"] = random.randint(
            int(efeito.get("turnos_min", 1) or 1),
            int(efeito.get("turnos_max", 3) or 3),
        )

    combate["ataque_pendente"] = {
        "tipo": "ataque_monstro",
        "nome": f"{golpe.get('emoji', '👹')} {golpe.get('nome', 'Ataque do Monstro')}",
        "atacante_id": atacante.get("id"),
        "defensor_id": defensor.get("id"),
        "magia": False,
        "efeito": efeito,
    }
    combate["fase"] = "defesa"
    await self._anunciar_ataque(ctx)


async def _resolver_ataque(self, ctx):
    combate = self._obter_combate(ctx.channel.id)
    ataque = combate.get("ataque_pendente") if combate else None

    if combate and ataque and ataque.get("tipo") == "ataque_monstro":
        atacante = self._obter_atacante(combate)
        defensor = self._obter_defensor(combate)
        efeito = ataque.get("efeito") or {}

        if _normalizar_nome(efeito.get("nome", "")) == "sangramento":
            # No motor atual, defesa_total = (Força + Defesa) * 2.
            # Recuperamos a Defesa pura para a comparação solicitada.
            forca_jogador = float(defensor.get("Força", 0) or 0)
            defesa_total = float(defensor.get("defesa", 0) or 0)
            defesa_base = max(0.0, defesa_total / 2 - forca_jogador)

            if (
                defensor.get("tipo") == "jogador"
                and not defensor.get("defesa_ativa", False)
                and float(atacante.get("Força", 0) or 0) > defesa_base
            ):
                defensor.setdefault("efeitos", []).append({
                    "nome": "sangramento",
                    "turnos": int(efeito.get("turnos", random.randint(1, 3)) or 1),
                    "valor": int(efeito.get("valor", 10) or 10),
                })

    await _RESOLVER_ATAQUE_ORIGINAL(self, ctx)


async def luta_pve(self, ctx, monstro_tipo: str):
    if not ctx.guild:
        return
    if self._combate_ativo(ctx.channel.id):
        await ctx.send("❌ Já existe um combate ativo neste canal.")
        return
    monstro_tipo = _normalizar_nome(monstro_tipo)
    monstro_id = self._encontrar_monstro(monstro_tipo)
    if not monstro_id:
        await ctx.send(f"❌ Monstro `{monstro_tipo}` não encontrado.")
        return
    guild_id = str(ctx.guild.id)
    user_id = str(ctx.author.id)
    verificacao = await _pode_lutar(user_id, guild_id)
    if not verificacao.get("pode", False):
        await ctx.send(verificacao.get("mensagem", "❌ Você não pode lutar."))
        return
    jogador = await _criar_participante(user_id, guild_id)
    if not jogador:
        await ctx.send("❌ Você não possui um personagem registrado.")
        return
    jogador["nome"] = jogador.get("nome") or ctx.author.display_name
    monstro = luta_db.criar_monstro(monstro_id, 1)
    if not monstro:
        await ctx.send("❌ Não foi possível criar esse monstro.")
        return
    participantes = [jogador, monstro]
    participantes.sort(key=lambda p: p.get("velocidade", 0), reverse=True)
    self.combates[ctx.channel.id] = {
        "participantes": participantes,
        "turno": 0,
        "numero_turno": 1,
        "fase": "ataque",
        "ativo": True,
        "pvp": False,
        "guild_id": guild_id,
        "ataque_pendente": None,
        "historico": [],
        "aguardando_finalizacao": False,
        "vencedor_id": None,
        "perdedor_id": None,
    }
    _atualizar_situacao(self, jogador["id"], guild_id, "ativo_combate")
    await self._mostrar_inicio(ctx)


async def luta_pvp(self, ctx, membro: discord.Member):
    if not ctx.guild:
        return
    if not isinstance(membro, discord.Member):
        await ctx.send("❌ Mencione um membro válido. Exemplo: `!luta pvp @jogador`")
        return
    if membro.bot:
        await ctx.send("❌ Você não pode lutar contra bots.")
        return
    if membro.id == ctx.author.id:
        await ctx.send("❌ Você não pode lutar contra si mesmo.")
        return
    if self._combate_ativo(ctx.channel.id):
        await ctx.send("❌ Já existe um combate ativo neste canal.")
        return
    guild_id = str(ctx.guild.id)
    for usuario in [ctx.author, membro]:
        verificacao = await _pode_lutar(str(usuario.id), guild_id)
        if not verificacao.get("pode", False):
            await ctx.send(
                f"❌ {usuario.display_name}: "
                f"{verificacao.get('mensagem', 'não pode lutar.')}"
            )
            return
    jogador_1 = await _criar_participante(str(ctx.author.id), guild_id)
    jogador_2 = await _criar_participante(str(membro.id), guild_id)
    if not jogador_1 or not jogador_2:
        await ctx.send("❌ Um dos jogadores não possui personagem registrado.")
        return
    jogador_1["nome"] = jogador_1.get("nome") or ctx.author.display_name
    jogador_2["nome"] = jogador_2.get("nome") or membro.display_name
    participantes = [jogador_1, jogador_2]
    participantes.sort(key=lambda p: p.get("velocidade", 0), reverse=True)
    self.combates[ctx.channel.id] = {
        "participantes": participantes,
        "turno": 0,
        "numero_turno": 1,
        "fase": "ataque",
        "ativo": True,
        "pvp": True,
        "guild_id": guild_id,
        "ataque_pendente": None,
        "historico": [],
        "aguardando_finalizacao": False,
        "vencedor_id": None,
        "perdedor_id": None,
    }
    for jogador in participantes:
        _atualizar_situacao(self, jogador["id"], guild_id, "ativo_combate")
    await self._mostrar_inicio(ctx)


async def _cog_after_invoke(self, ctx):
    await _aguardar_escritas(self)


async def _cog_unload(self):
    await _aguardar_escritas(self)


_base.Luta.luta_pve.callback = luta_pve
_base.Luta.luta_pvp.callback = luta_pvp
_base.Luta._ataque_monstro = _ataque_monstro
_base.Luta._resolver_ataque = _resolver_ataque
_base.Luta._encontrar_monstro = _encontrar_monstro
_base.Luta._atualizar_situacao = _atualizar_situacao
_base.Luta._dar_recompensas = _dar_recompensas
_base.Luta._salvar_participantes = _salvar_participantes
_base.Luta.cog_after_invoke = _cog_after_invoke
_base.Luta.cog_unload = _cog_unload


async def setup(bot):
    await bot.add_cog(Luta(bot))
