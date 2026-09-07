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
_CALCULAR_MAGIA_ORIGINAL = _base.Luta._calcular_dano_magia
_USAR_MAGIA_ORIGINAL = _base.Luta.usar_magia_no_combate
_ATAQUE_JOGADOR_ORIGINAL = _base.Luta._ataque_jogador


def _normalizar_nome(nome):
    texto = str(nome or "").strip()
    texto = unicodedata.normalize("NFKC", texto)
    return texto.casefold()


async def _pode_lutar(user_id, guild_id):
    return await run_db(luta_db.pode_lutar, user_id, guild_id)


async def _criar_participante(user_id, guild_id):
    participante = await run_db(luta_db.criar_participante_jogador, user_id, guild_id)
    if not participante:
        return None
    jogador = await run_db(luta_db.obter_jogador, user_id, guild_id)
    if jogador:
        participante["Força"] = float(jogador.get("Força", 10) or 0)
        participante["Defesa"] = float(jogador.get("Defesa", 10) or 0)
        participante["Destreza"] = float(jogador.get("Destreza", 10) or 0)
        participante["Velocidade"] = float(jogador.get("Velocidade", 50) or 0)
        participante["Magia"] = float(jogador.get("Magia", 0) or 0)
        participante["Inteligencia"] = float(jogador.get("Inteligencia", jogador.get("Inteligência", 0)) or 0)
        participante["dano_arma"] = float(jogador.get("dano_arma", jogador.get("Dano_Arma", jogador.get("arma_dano", 0))) or 0)
        participante["arma_nome"] = jogador.get("arma_nome", jogador.get("Arma", "")) or ""
    else:
        participante["Defesa"] = 10
        participante["Magia"] = 0
        participante["Inteligencia"] = 0
        participante["dano_arma"] = 0
        participante["arma_nome"] = ""
    return participante


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


def _cog_after_invoke(self, ctx):
    return _aguardar_escritas(self)


def _cog_unload(self):
    return _aguardar_escritas(self)


def _atualizar_situacao(self, user_id, guild_id, situacao):
    if db is None:
        return
    return _agendar_db(self, db["Jogadores"].update_one,
                       {"ID": str(user_id), "guild_id": str(guild_id)},
                       {"$set": {"Situação": situacao}})


def _dar_recompensas(self, user_id, guild_id, xp, hunos):
    if db is None:
        return
    xp = int(xp or 0)
    hunos = int(hunos or 0)
    if xp > 0:
        _agendar_db(self, db["Jogadores"].update_one,
                    {"ID": str(user_id), "guild_id": str(guild_id)},
                    {"$inc": {"XP": xp}})
    if hunos > 0:
        _agendar_db(self, db["Hunos"].update_one,
                    {"ID": str(user_id), "guild_id": str(guild_id)},
                    {"$inc": {"carteira": hunos}}, upsert=True)


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
        _agendar_db(self, db["Jogadores"].update_one,
                    {"ID": str(participante["id"]), "guild_id": str(guild_id)},
                    {"$set": {"Vida": int(participante.get("vida", 0)),
                               "Mana": int(participante.get("mana", 0)),
                               "Situação": situacao}})


def _obter_golpe_monstro(monstro):
    configuracao = luta_db.MONSTROS.get(str(monstro.get("id", "")), {})
    golpes_ids = configuracao.get("golpes", [])
    disponiveis = [luta_db.GOLPES[g] for g in golpes_ids if g in luta_db.GOLPES]
    return random.choice(disponiveis) if disponiveis else {"nome": "Ataque do Monstro", "emoji": "👹", "efeito": {}}


def _resistencia_defensor(defensor):
    if defensor.get("defesa_magica_ativa"):
        return float(defensor.get("Magia", 0) or 0) + float(defensor.get("Defesa", 0) or 0)
    return float(defensor.get("Defesa", 0) or 0) + float(defensor.get("defesa", 0) or 0)


def _preparar_efeito(efeito, atacante, defensor, tipo_ataque):
    if not isinstance(efeito, dict):
        return {}
    efeito = dict(efeito)
    nome = _normalizar_nome(efeito.get("nome", ""))
    if not nome:
        return {}
    if "turnos_min" in efeito or "turnos_max" in efeito:
        minimo = int(efeito.get("turnos_min", 1) or 1)
        maximo = int(efeito.get("turnos_max", minimo) or minimo)
        efeito["turnos"] = random.randint(minimo, maximo)
    if nome == "sangramento" and tipo_ataque == "ataque_monstro":
        if (defensor.get("tipo") == "jogador" and not defensor.get("defesa_ativa", False)
                and float(atacante.get("Força", 0) or 0) > float(defensor.get("Defesa", 0) or 0)):
            efeito["valor"] = 10
            return efeito
        return {}
    if tipo_ataque == "magia":
        poder = float(atacante.get("Magia", 0) or 0) + float(atacante.get("Inteligencia", 0) or 0)
    else:
        poder = float(atacante.get("Força", 0) or 0) + float(atacante.get("Velocidade", atacante.get("velocidade", 0)) or 0)
    resistencia = _resistencia_defensor(defensor)
    valor = int(poder - resistencia)
    if valor <= 0:
        return {}
    efeito["valor"] = valor
    return efeito


async def _ataque_monstro(self, ctx):
    combate = self._obter_combate(ctx.channel.id)
    if not combate or not combate.get("ativo") or combate["fase"] != "ataque":
        return
    atacante = self._obter_atacante(combate)
    defensor = self._obter_defensor(combate)
    if atacante["tipo"] != "monstro":
        return
    golpe = _obter_golpe_monstro(atacante)
    efeito = _preparar_efeito(golpe.get("efeito", {}), atacante, defensor, "ataque_monstro")
    combate["ataque_pendente"] = {
        "tipo": "ataque_monstro",
        "nome": f"{golpe.get('emoji', '👹')} {golpe.get('nome', 'Ataque do Monstro')}",
        "atacante_id": atacante.get("id"),
        "defensor_id": defensor.get("id"),
        "magia": False,
        "dano_base": float(golpe.get("dano_base", 0) or 0),
        "efeito": efeito,
        "com_arma": False,
    }
    combate["fase"] = "defesa"
    await self._anunciar_ataque(ctx)


def _calcular_dano_fisico(atacante, defensor, ataque):
    if defensor.get("esquiva_ativa"):
        if random.random() < 0.40:
            defensor["esquiva_ativa"] = False
            return 0, "esquivou"
        defensor["esquiva_ativa"] = False
    forca = float(atacante.get("Força", 0) or 0)
    destreza = float(atacante.get("Destreza", 0) or 0)
    base = float(ataque.get("dano_base", 0) or 0)
    arma = float(atacante.get("dano_arma", 0) or 0) if ataque.get("com_arma") else 0
    dano = forca + destreza + base + arma
    dano -= float(defensor.get("Defesa", 0) or 0)
    if defensor.get("defesa_ativa"):
        dano *= 0.50
        defensor["defesa_ativa"] = False
    if defensor.get("defesa_magica_ativa"):
        dano -= float(defensor.get("defesa_magica_valor", 0) or 0)
        defensor["defesa_magica_ativa"] = False
    return max(1, int(dano)), "normal"


def _calcular_dano_magia(self, atacante, defensor, ataque):
    if defensor.get("esquiva_ativa"):
        velocidade = float(defensor.get("Velocidade", defensor.get("velocidade", 0)) or 0)
        chance = min(0.75, 0.10 + velocidade / 500)
        if random.random() < chance:
            defensor["esquiva_ativa"] = False
            return 0, "esquivou"
        defensor["esquiva_ativa"] = False
    magia = float(atacante.get("Magia", atacante.get("magia", 0)) or 0)
    inteligencia = float(atacante.get("Inteligencia", atacante.get("inteligencia", 0)) or 0)
    base = float(ataque.get("dano_base", 0) or 0)
    arma = float(atacante.get("dano_arma", 0) or 0) if ataque.get("com_arma") else 0
    dano = magia + inteligencia + base + arma
    if defensor.get("defesa_magica_ativa"):
        dano -= float(defensor.get("Magia", 0) or 0)
        dano -= float(defensor.get("Defesa", 0) or 0)
        dano -= float(defensor.get("defesa_magica_valor", 0) or 0)
        defensor["defesa_magica_ativa"] = False
    else:
        dano -= float(defensor.get("Defesa", 0) or 0)
    return max(1, int(dano)), "atingiu"


async def _ataque_jogador(self, ctx, tipo_ataque):
    await _ATAQUE_JOGADOR_ORIGINAL(self, ctx, tipo_ataque)
    combate = self._obter_combate(ctx.channel.id)
    if not combate or not combate.get("ataque_pendente"):
        return
    ataque = combate["ataque_pendente"]
    if ataque.get("tipo") != tipo_ataque:
        return
    golpe = luta_db.GOLPES.get(tipo_ataque, {})
    ataque["dano_base"] = float(golpe.get("dano_base", 0) or 0)
    ataque["com_arma"] = bool(golpe.get("com_arma", False))
    ataque["efeito"] = golpe.get("efeito", {}) if isinstance(golpe.get("efeito"), dict) else {}


async def _usar_magia_no_combate(self, ctx, dados_magia):
    resultado = await _USAR_MAGIA_ORIGINAL(self, ctx, dados_magia)
    if not resultado:
        return resultado
    combate = self._obter_combate(ctx.channel.id)
    if not combate or not combate.get("ataque_pendente"):
        return resultado
    ataque = combate["ataque_pendente"]
    ataque["cura_base"] = float(dados_magia.get("cura_base", 0) or 0)
    ataque["defesa_base"] = float(dados_magia.get("defesa_base", 0) or 0)
    ataque["com_arma"] = bool(dados_magia.get("imbuida_em_arma", dados_magia.get("com_arma", False)))
    ataque["efeito"] = dados_magia.get("efeito", {}) if isinstance(dados_magia.get("efeito"), dict) else {}
    return resultado


async def _resolver_ataque(self, ctx):
    combate = self._obter_combate(ctx.channel.id)
    ataque = combate.get("ataque_pendente") if combate else None
    if combate and ataque:
        atacante = self._obter_atacante(combate)
        defensor = self._obter_defensor(combate)
        if ataque.get("tipo") == "magia":
            magia = float(atacante.get("Magia", 0) or 0)
            inteligencia = float(atacante.get("Inteligencia", 0) or 0)
            if ataque.get("cura_base", 0) > 0:
                ataque["dano_base"] = -(magia + inteligencia + float(ataque["cura_base"]))
            elif ataque.get("defesa_base", 0) > 0:
                valor = int(magia + inteligencia + float(ataque["defesa_base"]))
                atacante["defesa_magica_ativa"] = True
                atacante["defesa_magica_valor"] = valor
                await ctx.send(f"🛡️ **{atacante['nome']}** criou uma defesa mágica de **{valor}**!")
                combate["ataque_pendente"] = None
                combate["fase"] = "ataque"
                await asyncio.sleep(1)
                await self._proximo_turno(ctx)
                return
            ataque["efeito"] = _preparar_efeito(ataque.get("efeito", {}), atacante, defensor, "magia")
        else:
            ataque["efeito"] = _preparar_efeito(ataque.get("efeito", {}), atacante, defensor, ataque.get("tipo", ""))
    await _RESOLVER_ATAQUE_ORIGINAL(self, ctx)


_base.Luta.luta_pve.callback = None
_base.Luta.luta_pvp.callback = None
_base.Luta._ataque_monstro = _ataque_monstro
_base.Luta._ataque_jogador = _ataque_jogador
_base.Luta._resolver_ataque = _resolver_ataque
_base.Luta._calcular_dano_magia = _calcular_dano_magia
_base.Luta.usar_magia_no_combate = _usar_magia_no_combate
_base.Luta._encontrar_monstro = _encontrar_monstro
_base.Luta._atualizar_situacao = _atualizar_situacao
_base.Luta._dar_recompensas = _dar_recompensas
_base.Luta._salvar_participantes = _salvar_participantes
_base.Luta.cog_after_invoke = _cog_after_invoke
_base.Luta.cog_unload = _cog_unload


async def luta_pve(self, ctx, monstro_tipo: str):
    if not ctx.guild:
        return
    if self._combate_ativo(ctx.channel.id):
        await ctx.send("❌ Já existe um combate ativo neste canal.")
        return
    monstro_id = self._encontrar_monstro(_normalizar_nome(monstro_tipo))
    if not monstro_id:
        await ctx.send(f"❌ Monstro `{monstro_tipo}` não encontrado.")
        return
    guild_id = str(ctx.guild.id)
    verificacao = await _pode_lutar(str(ctx.author.id), guild_id)
    if not verificacao.get("pode", False):
        await ctx.send(verificacao.get("mensagem", "❌ Você não pode lutar."))
        return
    jogador = await _criar_participante(str(ctx.author.id), guild_id)
    if not jogador:
        await ctx.send("❌ Você não possui um personagem registrado.")
        return
    jogador["nome"] = jogador.get("nome") or ctx.author.display_name
    monstro = luta_db.criar_monstro(monstro_id, 1)
    if not monstro:
        await ctx.send("❌ Não foi possível criar esse monstro.")
        return
    participantes = sorted([jogador, monstro], key=lambda p: p.get("velocidade", 0), reverse=True)
    self.combates[ctx.channel.id] = {"participantes": participantes, "turno": 0, "numero_turno": 1,
        "fase": "ataque", "ativo": True, "pvp": False, "guild_id": guild_id,
        "ataque_pendente": None, "historico": [], "aguardando_finalizacao": False,
        "vencedor_id": None, "perdedor_id": None}
    _atualizar_situacao(self, jogador["id"], guild_id, "ativo_combate")
    await self._mostrar_inicio(ctx)


async def luta_pvp(self, ctx, membro: discord.Member):
    if not ctx.guild:
        return
    if not isinstance(membro, discord.Member):
        await ctx.send("❌ Mencione um membro válido. Exemplo: `!luta pvp @jogador`")
        return
    if membro.bot or membro.id == ctx.author.id:
        await ctx.send("❌ Alvo de PvP inválido.")
        return
    if self._combate_ativo(ctx.channel.id):
        await ctx.send("❌ Já existe um combate ativo neste canal.")
        return
    guild_id = str(ctx.guild.id)
    for usuario in (ctx.author, membro):
        verificacao = await _pode_lutar(str(usuario.id), guild_id)
        if not verificacao.get("pode", False):
            await ctx.send(f"❌ {usuario.display_name}: {verificacao.get('mensagem', 'não pode lutar.')}")
            return
    jogador_1 = await _criar_participante(str(ctx.author.id), guild_id)
    jogador_2 = await _criar_participante(str(membro.id), guild_id)
    if not jogador_1 or not jogador_2:
        await ctx.send("❌ Um dos jogadores não possui personagem registrado.")
        return
    jogador_1["nome"] = jogador_1.get("nome") or ctx.author.display_name
    jogador_2["nome"] = jogador_2.get("nome") or membro.display_name
    participantes = sorted([jogador_1, jogador_2], key=lambda p: p.get("velocidade", 0), reverse=True)
    self.combates[ctx.channel.id] = {"participantes": participantes, "turno": 0, "numero_turno": 1,
        "fase": "ataque", "ativo": True, "pvp": True, "guild_id": guild_id,
        "ataque_pendente": None, "historico": [], "aguardando_finalizacao": False,
        "vencedor_id": None, "perdedor_id": None}
    for jogador in participantes:
        _atualizar_situacao(self, jogador["id"], guild_id, "ativo_combate")
    await self._mostrar_inicio(ctx)


_base.Luta.luta_pve.callback = luta_pve
_base.Luta.luta_pvp.callback = luta_pvp


async def setup(bot):
    await bot.add_cog(Luta(bot))
