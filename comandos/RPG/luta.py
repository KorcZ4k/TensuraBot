"""Camada não bloqueante do sistema de combate.

O código legado do combate fica em ``luta_sync.py``. Este módulo mantém a
mesma classe e comandos, mas tira as operações MongoDB do event loop.
"""

import asyncio

from database.python.mongodb import db, run_db
from database.python import luta as luta_db
from database.python import luta as _luta_sync

# O arquivo legado é preservado sem alterações para minimizar risco.
from . import luta_sync as _base

Luta = _base.Luta


async def _pode_lutar(user_id, guild_id):
    return await run_db(luta_db.pode_lutar, user_id, guild_id)


async def _criar_participante(user_id, guild_id):
    return await run_db(luta_db.criar_participante_jogador, user_id, guild_id)


def _agendar_db(self, operation, *args, **kwargs):
    """Agenda uma escrita Mongo sem bloquear o event loop."""
    tasks = getattr(self, "_mongo_tasks", None)
    if tasks is None:
        tasks = self._mongo_tasks = set()

    task = asyncio.create_task(run_db(operation, *args, **kwargs))
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return task


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


async def luta_pve(self, ctx, monstro_tipo: str):
    if not ctx.guild:
        return

    if self._combate_ativo(ctx.channel.id):
        await ctx.send("❌ Já existe um combate ativo neste canal.")
        return

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

    monstro = self._encontrar_monstro(monstro_tipo)
    monstro = _luta_sync.criar_monstro(monstro_id, 1)
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


async def luta_pvp(self, ctx, membro):
    if not ctx.guild:
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


# Substitui apenas os dois callbacks que consultam Mongo durante a criação
# do combate. Todo o restante do motor permanece exatamente no código legado.
_base.Luta.luta_pve.callback = luta_pve
_base.Luta.luta_pvp.callback = luta_pvp
_base.Luta._atualizar_situacao = _atualizar_situacao
_base.Luta._dar_recompensas = _dar_recompensas
_base.Luta._salvar_participantes = _salvar_participantes


async def setup(bot):
    await bot.add_cog(Luta(bot))
