"""Sistema de combate canonico do TensuraBot.

Este modulo e a unica fonte de verdade do sistema de luta: motor, estado,
regras e registro dos comandos publicos ficam aqui. Os callbacks publicos sao
registrados como funcoes de modulo para que discord.py entregue ``ctx``
diretamente, sem binding de ``self`` em callbacks de Cog.
"""

import asyncio
import random
import unicodedata
from typing import Optional

import discord
from discord.ext import commands

from database.python.mongodb import db, run_db
from database.python import luta as luta_db


def _num(valor, padrao=0.0):
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return float(padrao)


def _attr(p, *nomes, padrao=0.0):
    for nome in nomes:
        if nome in p:
            return _num(p.get(nome), padrao)
    return float(padrao)


def _vivo(p):
    return _num(p.get("vida")) > 0


def _velocidade(p):
    return _attr(p, "Velocidade", "velocidade", padrao=0)


def _normalizar(texto):
    return unicodedata.normalize("NFKC", str(texto or "").strip()).casefold()


async def _criar_participante(user_id, guild_id):
    participante = await run_db(luta_db.criar_participante_jogador, str(user_id), str(guild_id))
    if not participante:
        return None
    jogador = await run_db(luta_db.obter_jogador, str(user_id), str(guild_id))
    if jogador:
        participante.update({
            "Força": _num(jogador.get("Força"), 10),
            "Defesa": _num(jogador.get("Defesa"), 10),
            "Destreza": _num(jogador.get("Destreza"), 10),
            "Velocidade": _num(jogador.get("Velocidade"), 50),
            "velocidade": _num(jogador.get("Velocidade"), 50),
            "Magia": _num(jogador.get("Magia"), 0),
            "Inteligencia": _num(jogador.get("Inteligencia", jogador.get("Inteligência")), 0),
            "dano_arma": _num(jogador.get("dano_arma", jogador.get("Dano_Arma", jogador.get("arma_dano"))), 0),
            "arma_nome": jogador.get("arma_nome", jogador.get("Arma", "")) or "",
        })
    participante["defesa"] = _attr(participante, "Força") + _attr(participante, "Defesa")
    participante.setdefault("efeitos", [])
    participante.setdefault("buffs_ativos", {})
    participante.setdefault("defesa_ativa", False)
    participante.setdefault("esquiva_ativa", False)
    participante.setdefault("defesa_magica_ativa", False)
    participante.setdefault("defesa_magica_valor", 0)
    return participante


class Luta(commands.Cog):
    """Maquina de estados unica para PvP, PvE e party."""

    def __init__(self, bot):
        self.bot = bot
        self.combates = {}
        self._locks = {}

    def _lock(self, channel_id):
        return self._locks.setdefault(channel_id, asyncio.Lock())

    def _combate_ativo(self, channel_id):
        combate = self.combates.get(channel_id)
        return bool(combate and combate.get("ativo"))

    def _obter_combate(self, channel_id):
        return self.combates.get(channel_id)

    def _encontrar_monstro(self, nome):
        alvo = _normalizar(nome)
        for monstro_id, dados in luta_db.MONSTROS.items():
            if _normalizar(monstro_id) == alvo or _normalizar(dados.get("nome")) == alvo:
                return monstro_id
        return None

    def _ordenar(self, participantes):
        return sorted(participantes, key=_velocidade, reverse=True)

    def _novo_combate(self, participantes, guild_id, pvp=False, party=False, party_id=None):
        participantes = self._ordenar(list(participantes))
        for p in participantes:
            if pvp and p.get("tipo") == "jogador":
                p["equipe"] = f"jogador:{p.get('id')}"
            else:
                p.setdefault("equipe", "jogadores" if p.get("tipo") == "jogador" else "inimigos")
            p.setdefault("efeitos", [])
            p.setdefault("defesa_ativa", False)
            p.setdefault("esquiva_ativa", False)
        return {
            "participantes": participantes,
            "turno": 0,
            "numero_turno": 1,
            "fase": "ataque",
            "ativo": True,
            "pvp": bool(pvp),
            "party": bool(party),
            "party_id": party_id,
            "guild_id": str(guild_id),
            "ataque_pendente": None,
            "historico": [],
            "aguardando_finalizacao": False,
            "vencedor_id": None,
            "perdedor_id": None,
        }

    def _participante(self, combate, participante_id):
        if participante_id is None:
            return None
        for p in combate.get("participantes", []):
            if str(p.get("id")) == str(participante_id):
                return p
        return None

    def _obter_atacante(self, combate):
        participantes = combate.get("participantes", [])
        if not participantes:
            return None
        indice = int(combate.get("turno", 0)) % len(participantes)
        atacante = participantes[indice]
        if _vivo(atacante):
            return atacante
        proximo = self._proximo_indice(combate, indice)
        if proximo is None:
            return None
        # Se o índice atual aponta para um derrotado, sincroniza o estado.
        # Sem isso, cada consulta poderia devolver o mesmo vivo sem avançar o turno.
        combate["turno"] = proximo
        return participantes[proximo]

    def _inimigos_vivos(self, combate, atacante):
        equipe = atacante.get("equipe")
        return [p for p in combate.get("participantes", []) if _vivo(p) and p is not atacante and p.get("equipe") != equipe]

    def _obter_defensor(self, combate):
        ataque = combate.get("ataque_pendente") or {}
        if ataque.get("defensor_id") is not None:
            # Ataque pendente tem alvo fixo. Se ele morreu, devolvemos o próprio
            # participante para o resolver tratar o ataque como inválido, em vez
            # de redirecioná-lo silenciosamente para outro inimigo.
            return self._participante(combate, ataque.get("defensor_id"))
        atacante = self._obter_atacante(combate)
        if not atacante:
            return None
        inimigos = self._inimigos_vivos(combate, atacante)
        return inimigos[0] if inimigos else None

    def _proximo_indice(self, combate, atual=None):
        participantes = combate.get("participantes", [])
        if not participantes:
            return None
        atual = int(combate.get("turno", 0) if atual is None else atual) % len(participantes)
        for passo in range(1, len(participantes) + 1):
            indice = (atual + passo) % len(participantes)
            if _vivo(participantes[indice]):
                return indice
        return None

    def _condicao_vitoria(self, combate):
        if combate.get("pvp"):
            vivos = [p for p in combate.get("participantes", []) if _vivo(p)]
            if len(vivos) == 1:
                return "pvp"
            if not vivos:
                return "empate"
            return None
        jogadores = [p for p in combate["participantes"] if p.get("equipe") == "jogadores" and _vivo(p)]
        inimigos = [p for p in combate["participantes"] if p.get("equipe") == "inimigos" and _vivo(p)]
        if jogadores and not inimigos:
            return "jogadores"
        if inimigos and not jogadores:
            return "inimigos"
        if not jogadores and not inimigos:
            return "empate"
        return None

    def _texto_status(self, participantes):
        linhas = []
        for p in participantes:
            vida = max(0, int(_num(p.get("vida"))))
            maximo = max(1, int(_num(p.get("vida_maxima"), vida)))
            icone = "👤" if p.get("tipo") == "jogador" else p.get("emoji", "👹")
            mana = f"\n💙 {int(_num(p.get('mana')))}" if p.get("tipo") == "jogador" else ""
            estado = "☠️ DERROTADO" if vida <= 0 else "🟢 Vivo"
            linhas.append(f"{icone} **{p.get('nome', 'Desconhecido')}**\n❤️ {vida}/{maximo}{mana}\n{estado}")
        return "\n\n".join(linhas) or "Sem participantes."

    async def _salvar(self, combate, situacao="ativo"):
        if db is None:
            return
        tarefas = []
        for p in combate.get("participantes", []):
            if p.get("tipo") != "jogador":
                continue
            vida = max(0, int(_num(p.get("vida"))))
            status = "morto" if vida <= 0 else situacao
            tarefas.append(run_db(db["Jogadores"].update_one,
                {"ID": str(p.get("id")), "guild_id": str(combate.get("guild_id"))},
                {"$set": {"Vida": vida, "Mana": int(_num(p.get("mana"))), "Situação": status}}))
        if tarefas:
            await asyncio.gather(*tarefas)

    async def _marcar_combate(self, participantes, guild_id, situacao):
        if db is None:
            return
        await asyncio.gather(*(
            run_db(db["Jogadores"].update_one,
                {"ID": str(p.get("id")), "guild_id": str(guild_id)},
                {"$set": {"Situação": situacao}})
            for p in participantes if p.get("tipo") == "jogador"
        ))

    async def _recompensar(self, combate):
        """Compatibilidade legada: mantém o mesmo contrato XP/TP/Hunos do motor final."""
        resultado = self._condicao_vitoria(combate)
        if resultado != "jogadores" or db is None:
            return 0, 0, 0
        xp = sum(int(_num(p.get("xp_recompensa"))) for p in combate["participantes"] if p.get("tipo") == "monstro" and not p.get("invocado"))
        tp = sum(int(_num(p.get("tp_recompensa", p.get("xp_recompensa", 0)))) for p in combate["participantes"] if p.get("tipo") == "monstro" and not p.get("invocado"))
        hunos = sum(int(_num(p.get("hunos_recompensa"))) for p in combate["participantes"] if p.get("tipo") == "monstro" and not p.get("invocado"))
        vivos = [p for p in combate["participantes"] if p.get("tipo") == "jogador" and _vivo(p)]
        if not vivos:
            return xp, hunos, tp
        for i, p in enumerate(vivos):
            ganho_xp = xp // len(vivos) + (1 if i < xp % len(vivos) else 0)
            ganho_tp = tp // len(vivos) + (1 if i < tp % len(vivos) else 0)
            ganho_hunos = hunos // len(vivos) + (1 if i < hunos % len(vivos) else 0)
            filtro = {"ID": str(p.get("id")), "guild_id": str(combate.get("guild_id"))}
            await run_db(db["Jogadores"].update_one, filtro, {"$inc": {"XP": ganho_xp, "TP": ganho_tp}})
            await run_db(db["Hunos"].update_one, filtro, {"$inc": {"carteira": ganho_hunos}}, upsert=True)
        return xp, hunos, tp

    async def _finalizar_duelo_assentamento(self, ctx, vencedor, perdedor):
        combate = self._obter_combate(ctx.channel.id)
        if not combate:
            return
        combate["ativo"] = False
        combate["fase"] = "finalizado"
        combate["aguardando_finalizacao"] = False
        combate["vencedor_id"] = str(vencedor.get("id"))
        combate["perdedor_id"] = str(perdedor.get("id"))
        for participante in combate.get("participantes", []):
            participante.pop("_duelo_vitoria_pendente", None)
            participante.pop("_duelo_assentamento", None)
        await self._salvar(combate)
        try:
            if db is not None:
                await run_db(
                    db["Evento"].update_one,
                    {"tipo": "assentamento", "guild_id": str(combate.get("guild_id")), "canal_id": str(combate.get("assentamento_canal_id"))},
                    {"$set": {"DONO": str(vencedor.get("id")), "data_posse": discord.utils.utcnow().strftime("%d/%m/%Y"), "hora_posse": discord.utils.utcnow().strftime("%H:%M:%S")}, "$inc": {"derrotados": 1, "pessoas_derrotadas": 1}},
                    upsert=True,
                )
        except Exception as erro:
            print(f"[LUTA][ASSENTAMENTO][ERRO] {type(erro).__name__}: {erro}")
        await ctx.send(embed=discord.Embed(
            title="🏰 | Assentamento conquistado!",
            description=f"👑 **{vencedor.get('nome', 'Jogador')}** venceu o duelo contra **{perdedor.get('nome', 'o adversário')}** e agora é o dono do assentamento.\n\n❤️ O duelo foi não letal; o derrotado ficou com **1 HP**.",
            color=discord.Color.gold(),
        ))
        self.combates.pop(ctx.channel.id, None)

    async def _finalizar(self, ctx, motivo="vida", vencedor=None, perdedor=None):
        combate = self._obter_combate(ctx.channel.id)
        if not combate:
            return
        resultado = self._condicao_vitoria(combate)
        if resultado is None and motivo in {"vida", "efeitos"}:
            combate["ativo"] = True
            combate["fase"] = "ataque"
            combate["ataque_pendente"] = None
            await self._proximo_turno(ctx)
            return
        combate["ativo"] = False
        combate["fase"] = "finalizado"
        await self._salvar(combate)
        xp = hunos = tp = 0
        if combate.get("pvp"):
            descricao = f"💀 **{vencedor.get('nome')}** finalizou **{perdedor.get('nome')}** ({motivo})." if vencedor and perdedor else "⚖️ O combate PvP terminou em empate."
        elif resultado == "jogadores":
            recompensas = await self._recompensar(combate)
            xp, hunos = recompensas[0], recompensas[1]
            tp = recompensas[2] if len(recompensas) > 2 else 0
            descricao = "🏆 Os jogadores venceram o combate!"
        elif resultado == "inimigos":
            descricao = "💀 Os jogadores foram derrotados."
        else:
            descricao = "⚖️ O combate terminou em empate."
        if combate.get("pvp") and vencedor and perdedor:
            descricao = f"💀 **{vencedor.get('nome')}** finalizou **{perdedor.get('nome')}** ({motivo})."
        embed = discord.Embed(title="⚔️ Combate Finalizado", description=descricao, color=discord.Color.green() if resultado == "jogadores" else discord.Color.red())
        embed.add_field(name="🎁 Recompensas", value=f"✨ XP: **{xp}**\n🔷 TP: **{tp}**\n💰 Hunos: **{hunos}**", inline=False)
        embed.add_field(name="📋 Status", value=self._texto_status(combate["participantes"]), inline=False)
        await ctx.send(embed=embed)
        self.combates.pop(ctx.channel.id, None)

    async def _aplicar_efeitos_inicio(self, ctx, participante):
        dano_total = 0
        bloqueado = False
        novos = []
        for efeito in participante.get("efeitos", []):
            nome = _normalizar(efeito.get("nome"))
            valor = max(0, int(_num(efeito.get("valor"), 5)))
            if nome in {"veneno", "queimadura", "sangramento"}:
                dano_total += valor
            elif nome == "sangramento_profundo":
                dano_total += max(1, int(valor - _attr(participante, "defesa", padrao=_attr(participante, "Força") + _attr(participante, "Defesa")) * 0.50))
            if nome in {"paralisia", "stun", "prisao", "prisão"}:
                bloqueado = True
            turnos = int(_num(efeito.get("turnos"), 1)) - 1
            if turnos > 0:
                efeito["turnos"] = turnos
                novos.append(efeito)
        participante["efeitos"] = novos
        if dano_total:
            participante["vida"] = max(0, int(_num(participante.get("vida")) - dano_total))
            await ctx.send(f"⚠️ **{participante.get('nome')}** sofreu **{dano_total}** de efeitos.")
        return bloqueado

    def _dano_fisico(self, atacante, defensor, ataque):
        if defensor.get("esquiva_ativa"):
            defensor["esquiva_ativa"] = False
            velocidade = _velocidade(defensor)
            destreza = _attr(defensor, "Destreza", "destreza")
            chance = min(0.75, 0.10 + (velocidade + destreza) / 500)
            if random.random() < chance:
                return 0, "esquivou"
        dano = _attr(atacante, "Força", "forca") + _velocidade(atacante)
        dano += _num(ataque.get("dano_base"))
        if ataque.get("com_arma"):
            dano += _num(atacante.get("dano_arma"))
        if defensor.get("defesa_magica_ativa"):
            dano -= _num(defensor.get("defesa_magica_valor"))
            defensor["defesa_magica_ativa"] = False
            defensor["defesa_magica_valor"] = 0
        elif defensor.get("defesa_ativa"):
            dano -= _attr(defensor, "defesa", padrao=_attr(defensor, "Força") + _attr(defensor, "Defesa"))
        defensor["defesa_ativa"] = False
        return max(0, int(dano)), "atingiu"

    def _dano_magia(self, atacante, defensor, ataque):
        if defensor.get("esquiva_ativa"):
            defensor["esquiva_ativa"] = False
            chance = min(0.75, 0.10 + _velocidade(defensor) / 500)
            if random.random() < chance:
                return 0, "esquivou"
        dano = _attr(atacante, "Magia", "magia") + _attr(atacante, "Inteligencia", "Inteligência")
        dano += _num(ataque.get("dano_base"))
        if defensor.get("defesa_magica_ativa"):
            dano -= _num(defensor.get("defesa_magica_valor"))
            defensor["defesa_magica_ativa"] = False
            defensor["defesa_magica_valor"] = 0
        elif defensor.get("defesa_ativa"):
            dano -= _attr(defensor, "Defesa", "defesa") * 0.5
        defensor["defesa_ativa"] = False
        return max(1, int(dano)), "atingiu"

    def _aplicar_efeito(self, defensor, efeito):
        if not isinstance(efeito, dict):
            return None
        nome = str(efeito.get("nome", efeito.get("tipo", ""))).strip().lower()
        if not nome:
            return None
        turnos = max(1, int(_num(efeito.get("turnos", efeito.get("duracao", 1)), 1)))
        valor = int(_num(efeito.get("valor"), 5))
        defensor.setdefault("efeitos", []).append({"nome": nome, "turnos": turnos, "valor": valor})
        return nome

    async def _resolver_ataque(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo") or combate.get("fase") != "defesa":
            return
        ataque = combate.get("ataque_pendente")
        if not ataque or ataque.get("_resolvendo"):
            return
        ataque["_resolvendo"] = True
        try:
            atacante = self._participante(combate, ataque.get("atacante_id"))
            defensor = self._participante(combate, ataque.get("defensor_id"))
            if not atacante or not defensor or not _vivo(atacante) or not _vivo(defensor):
                combate["ataque_pendente"] = None
                combate["fase"] = "ataque"
                await self._proximo_turno(ctx)
                return
            duelo_pendente = False
            if ataque.get("tipo") == "magia" and ataque.get("cura_base", 0) > 0:
                cura = int(_attr(atacante, "Magia") + _attr(atacante, "Inteligencia") + _num(ataque.get("cura_base")))
                atacante["vida"] = min(int(_num(atacante.get("vida_maxima"), _num(atacante.get("vida")))), int(_num(atacante.get("vida"))) + cura)
                mensagem = f"✨ **{atacante.get('nome')}** recuperou **{cura} de vida**."
            elif ataque.get("tipo") == "magia":
                dano, resultado = self._dano_magia(atacante, defensor, ataque)
                if resultado == "esquivou":
                    mensagem = f"💨 **{defensor.get('nome')}** esquivou da magia!"
                else:
                    vida_antes = int(_num(defensor.get("vida")))
                    if combate.get("assentamento_duelo") and dano >= vida_antes:
                        dano = max(0, vida_antes - 1)
                        duelo_pendente = True
                    defensor["vida"] = max(0, vida_antes - dano)
                    mensagem = f"✨ **{atacante.get('nome')}** causou **{dano} de dano mágico** em **{defensor.get('nome')}**."
                    efeito = self._aplicar_efeito(defensor, ataque.get("efeito"))
                    if efeito:
                        mensagem += f"\n⚠️ Efeito: **{efeito.title()}**."
            else:
                dano, resultado = self._dano_fisico(atacante, defensor, ataque)
                if resultado == "esquivou":
                    mensagem = f"💨 **{defensor.get('nome')}** esquivou do ataque!"
                else:
                    vida_antes = int(_num(defensor.get("vida")))
                    if combate.get("assentamento_duelo") and dano >= vida_antes:
                        dano = max(0, vida_antes - 1)
                        duelo_pendente = True
                    defensor["vida"] = max(0, vida_antes - dano)
                    mensagem = f"⚔️ **{atacante.get('nome')}** causou **{dano} de dano** em **{defensor.get('nome')}**."
                    efeito = self._aplicar_efeito(defensor, ataque.get("efeito"))
                    if efeito:
                        mensagem += f"\n⚠️ Efeito: **{efeito.title()}**."
            if combate.get("assentamento_duelo") and defensor.get("vida", 0) <= 0:
                defensor["vida"] = 1
                duelo_pendente = True
            combate["historico"].append(mensagem)
            defensor["defesa_ativa"] = False
            defensor["esquiva_ativa"] = False
            combate["ataque_pendente"] = None
            combate["fase"] = "ataque"
            embed = discord.Embed(title="💥 Resultado", description=mensagem, color=discord.Color.red())
            embed.add_field(name="📋 Status", value=self._texto_status(combate["participantes"]), inline=False)
            await ctx.send(embed=embed)
            if combate.get("assentamento_duelo") and duelo_pendente:
                await self._finalizar_duelo_assentamento(ctx, atacante, defensor)
                return
            if combate.get("pvp") and not _vivo(defensor):
                combate["aguardando_finalizacao"] = True
                combate["vencedor_id"] = str(atacante.get("id"))
                combate["perdedor_id"] = str(defensor.get("id"))
                combate["fase"] = "finalizacao"
                await ctx.send(f"⚔️ **{atacante.get('nome')}** venceu o turno decisivo. Use `!matar` ou `!desmaiar` para finalizar o PvP.")
                return
            resultado = self._condicao_vitoria(combate)
            if resultado and not combate.get("pvp"):
                await self._finalizar(ctx, motivo="vida", vencedor=atacante, perdedor=defensor)
                return
            await self._salvar(combate)
            await asyncio.sleep(0.25)
            await self._proximo_turno(ctx)
        finally:
            ataque.pop("_resolvendo", None)

    def _criar_ataque(self, combate, tipo, atacante, defensor, **dados):
        ataque = {"tipo": tipo, "nome": dados.pop("nome", "⚔️ Ataque"), "atacante_id": atacante.get("id"), "defensor_id": defensor.get("id"), **dados}
        combate["ataque_pendente"] = ataque
        combate["fase"] = "defesa"
        return ataque

    async def _anunciar_ataque(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return
        ataque = combate.get("ataque_pendente")
        atacante = self._participante(combate, ataque.get("atacante_id")) if ataque else self._obter_atacante(combate)
        defensor = self._participante(combate, ataque.get("defensor_id")) if ataque else self._obter_defensor(combate)
        if not ataque or not atacante or not defensor:
            return
        embed = discord.Embed(title=f"⚔️ Turno {combate['numero_turno']}", description=f"{ataque.get('nome', 'Ataque')}\n\n⚔️ **{atacante.get('nome')}** atacou **{defensor.get('nome')}**!", color=discord.Color.orange())
        embed.add_field(name="🛡️ Quem deve defender", value=f"**{defensor.get('nome')}**", inline=False)
        embed.add_field(name="📋 Status", value=self._texto_status(combate["participantes"]), inline=False)
        await ctx.send(embed=embed)
        if defensor.get("tipo") == "monstro":
            await asyncio.sleep(0.25)
            await self._defesa_monstro(ctx)

    async def _defesa_jogador(self, ctx, acao):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo") or combate.get("fase") != "defesa":
            await ctx.send("❌ Não há ataque pendente para defender.")
            return
        defensor = self._obter_defensor(combate)
        if not defensor or defensor.get("tipo") != "jogador" or str(defensor.get("id")) != str(ctx.author.id):
            nome = defensor.get("nome", "outro jogador") if defensor else "outro jogador"
            await ctx.send(f"❌ É **{nome}** quem deve defender este ataque.")
            return
        defensor["defesa_ativa"] = acao == "defesa"
        defensor["esquiva_ativa"] = acao == "esquiva"
        await ctx.send(f"🛡️ **{defensor.get('nome')}** escolheu **{acao}**.")
        await self._resolver_ataque(ctx)

    async def _defesa_monstro(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo") or combate.get("fase") != "defesa":
            return
        defensor = self._obter_defensor(combate)
        if not defensor or defensor.get("tipo") != "monstro":
            return
        escolha = random.choice(("defesa", "esquiva", "normal"))
        defensor["defesa_ativa"] = escolha == "defesa"
        defensor["esquiva_ativa"] = escolha == "esquiva"
        await ctx.send(f"🤖 **{defensor.get('nome')}** escolheu **{escolha}**.")
        await self._resolver_ataque(ctx)

    async def _ataque_jogador(self, ctx, tipo_ataque):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            await ctx.send("❌ Não há combate ativo.")
            return
        if combate.get("aguardando_finalizacao"):
            await ctx.send("❌ O combate aguarda a finalização PvP.")
            return
        if combate.get("fase") != "ataque":
            await ctx.send("❌ O ataque anterior ainda não foi defendido.")
            return
        atacante = self._obter_atacante(combate)
        defensor = self._obter_defensor(combate)
        if not atacante or not defensor:
            return
        if atacante.get("tipo") != "jogador" or str(atacante.get("id")) != str(ctx.author.id):
            await ctx.send(f"❌ É a vez de **{atacante.get('nome', 'outro jogador')}**.")
            return
        golpe = luta_db.GOLPES.get(tipo_ataque, {})
        self._criar_ataque(combate, tipo_ataque, atacante, defensor, nome={"soco": "👊 Soco", "chute": "🦵 Chute"}.get(tipo_ataque, "⚔️ Ataque"), dano_base=_num(golpe.get("dano_base")), com_arma=bool(golpe.get("com_arma")), efeito=golpe.get("efeito", {}))
        await self._anunciar_ataque(ctx)

    async def usar_magia_no_combate(self, ctx, dados_magia):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return False
        if combate.get("fase") != "ataque":
            await ctx.send("❌ O ataque anterior ainda precisa ser resolvido.")
            return True
