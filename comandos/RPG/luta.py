"""Sistema de lutas completo do TensuraBot — arquivo único.

Tudo que pertence ao sistema de combate fica neste arquivo: motor, regras,
interface, comandos e regras especiais de monstros. O prefixo público continua
sendo ! (por exemplo: !luta pve slime).
"""

import asyncio
import copy
import io
import json
import random
import unicodedata
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import aiohttp
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


class _AvancarView(discord.ui.View):
    def __init__(self, cog, timeout=7200):
        super().__init__(timeout=timeout)
        self.cog = cog
        botao = discord.ui.Button(label="Avançar", emoji="▶️", style=discord.ButtonStyle.primary, custom_id="luta:avancar")
        botao.callback = self._callback
        self.add_item(botao)

    async def _callback(self, interaction: discord.Interaction):
        # O callback sempre responde ao Discord, mesmo se alguma etapa do motor falhar.
        try:
            await self.cog.avancar(interaction)
        except Exception as erro:
            print(f"[LUTA][UI][AVANCAR][ERRO] {type(erro).__name__}: {erro}")
            try:
                if interaction.response.is_done():
                    await interaction.followup.send("❌ Erro ao avançar o combate. O estado foi preservado.", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ Erro ao avançar o combate. O estado foi preservado.", ephemeral=True)
            except Exception as resposta_erro:
                print(f"[LUTA][UI][AVANCAR][RESPOSTA][ERRO] {type(resposta_erro).__name__}: {resposta_erro}")



class Luta(commands.Cog):
    def _acao_embed(self, *, atacante, defensor, nome, emoji, turno, dano, mana, descricao, efeito="Nenhum"):
        return painel(
            atacante=atacante.get("nome", "User"), ataque=f"{emoji} {nome}", vida=self._vida(atacante), mana=mana,
            dano=dano, efeito=efeito or "Nenhum", alvo=defensor.get("nome", "-"), turno=turno,
            oponente=defensor, vida_oponente=self._vida(defensor), extra=descricao, cor=discord.Color.blurple(),
        )
    
    async def _ui_editar(self, combate, embed, view=True):
        mensagem = combate.get("ui_message")
        if mensagem is None:
            return
        if not isinstance(embed, discord.Embed):
            embed = painel(extra=str(embed))
        kwargs = {"embed": embed, "attachments": []}
        if view:
            view_obj = self._ui_views.get(mensagem.id)
            if view_obj is None:
                view_obj = _AvancarView(self)
                self._ui_views[mensagem.id] = view_obj
            kwargs["view"] = view_obj
        else:
            kwargs["view"] = None
        await mensagem.edit(**kwargs)
    
    def _ui_context(self, ctx, combate):
        mensagem = combate.get("ui_message")
        return _UIContext(ctx, mensagem, combate, self) if mensagem is not None else ctx
    
    def _embed_velocidade(self, combate):
        ordem = "\n".join(f"{i + 1}. {p.get('nome', 'Desconhecido')} — {int(float(p.get('Velocidade', p.get('velocidade', 0)) or 0))} Vel." for i, p in enumerate(combate.get("participantes", []))) or "Nenhum participante."
        atacante = self._obter_atacante(combate) or {}
        return painel(atacante=atacante.get("nome", "User"), ataque="ordem de velocidade", vida=self._vida(atacante), mana=atacante.get("mana", 0), dano="-", efeito="-", alvo="Todos", turno=combate.get("numero_turno", 1), oponente="Todos", vida_oponente="-", extra=ordem, cor=discord.Color.blurple())
    
    def _embed_aguarde_jogador(self, combate):
        atacante = self._obter_atacante(combate) or {}
        defensor = self._obter_defensor(combate) or {}
        return self._acao_embed(atacante=atacante, defensor=defensor, nome="Sua vez", emoji="👤", turno=combate.get("numero_turno", 1), dano=0, mana=atacante.get("mana", 0), descricao=f"Use `!soco` ou `!chute` para atacar **{defensor.get('nome', '-')}**.")
    
    def _embed_turno_monstro(self, combate):
        atacante = self._obter_atacante(combate) or {}
        defensor = self._obter_defensor(combate) or {}
        return self._acao_embed(atacante=atacante, defensor=defensor, nome="Vez do monstro", emoji="👹", turno=combate.get("numero_turno", 1), dano=0, mana=0, descricao=f"**{atacante.get('nome', 'Monstro')}** está pronto para atacar.")
    
    def _embed_defesa(self, combate):
        ataque = combate.get("ataque_pendente") or {}
        defensor = self._obter_defensor(combate) or {}
        atacante = self._participante(combate, ataque.get("atacante_id")) or {}
        return self._acao_embed(atacante=atacante, defensor=defensor, nome="Defenda-se", emoji="🛡️", turno=combate.get("numero_turno", 1), dano=ataque.get("dano_base", 0), mana=0, descricao=f"**{defensor.get('nome', 'Jogador')}**, use `!defesa` ou `!esquiva`.")
    
    async def mostrar_ataque(self, ctx, embed, arquivo=None):
        combate = self._obter_combate(ctx.channel.id)
        if combate and combate.get("ui_message"):
            await self._mostrar_ataque_ui(combate)
            combate["ui_stage"] = "attack"
            return
        if embed is not None:
            kwargs = {"embed": embed}
            if arquivo is not None:
                kwargs["file"] = arquivo
            await ctx.send(**kwargs)
    
    async def executar_ataque_jogador(self, ctx, tipo_ataque, embed):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            if combate and combate.get("ui_message"):
                await self._ui_context(ctx, combate).send("❌ Não há combate ativo.")
            else:
                await ctx.send("❌ Não há combate ativo.")
            return
        ui = self._ui_context(ctx, combate)
        if combate.get("aguardando_finalizacao"):
            await ui.send("❌ O combate aguarda a finalização PvP.")
            return
        if combate.get("fase") != "ataque":
            await ui.send("❌ O ataque anterior ainda não foi defendido.")
            return
        atacante = self._obter_atacante(combate)
        defensor = self._obter_defensor(combate)
        if not atacante or not defensor:
            return
        if atacante.get("tipo") != "jogador" or str(atacante.get("id")) != str(ctx.author.id):
            await ui.send(f"❌ É a vez de **{atacante.get('nome', 'outro jogador')}**.")
            return
        golpe = luta_db.GOLPES.get(tipo_ataque)
        if not isinstance(golpe, dict):
            await ui.send("Golpe não está configurado.")
            return
        tipo = str(golpe.get("tipo", "fisico") or "fisico")
        if tipo not in {"fisico", "magia"}:
            tipo = "fisico"
        self._criar_ataque(combate, tipo, atacante, defensor, nome=golpe.get("nome", tipo_ataque.title()), dano_base=float(golpe.get("dano_base", 0) or 0), com_arma=bool(golpe.get("com_arma")), efeito=golpe.get("efeito", {}))
        if combate.get("ui_message"):
            await self._mostrar_ataque_ui(combate)
            combate["ui_stage"] = "attack"
        else:
            await self.mostrar_ataque(ctx, embed)
    
    async def executar_defesa_jogador(self, ctx, acao, embed):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo") or combate.get("fase") != "defesa":
            if combate and combate.get("ui_message"):
                await self._ui_context(ctx, combate).send("❌ Não há ataque pendente para defender.")
            else:
                await ctx.send("❌ Não há ataque pendente para defender.")
            return
        defensor = self._obter_defensor(combate)
        if not defensor or defensor.get("tipo") != "jogador" or str(defensor.get("id")) != str(ctx.author.id):
            nome = defensor.get("nome", "outro jogador") if defensor else "outro jogador"
            await self._ui_context(ctx, combate).send(f"❌ É **{nome}** quem deve defender este ataque.")
            return
        defensor["defesa_ativa"] = acao == "defesa"
        defensor["esquiva_ativa"] = acao == "esquiva"
        if combate.get("ui_message"):
            combate["ui_waiting_advance"] = False
            await self._resolver_ataque(self._ui_context(ctx, combate))
        else:
            await self._resolver_ataque(ctx)
    
    async def _anunciar_ataque(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return
        ataque = combate.get("ataque_pendente")
        atacante = self._participante(combate, ataque.get("atacante_id")) if ataque else None
        defensor = self._participante(combate, ataque.get("defensor_id")) if ataque else None
        if not ataque or not atacante or not defensor:
            return
        if combate.get("ui_message"):
            await self._mostrar_ataque_ui(combate)
            combate["ui_stage"] = "attack"
            return
        embed = self._embeds_acao.pop(ctx.channel.id, None)
        embed = embed[0] if isinstance(embed, tuple) else embed
        await self.mostrar_ataque(ctx, embed)
    
    async def _mostrar_inicio(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return
        preparado = self._embeds_acao.pop(ctx.channel.id, None)
        arquivo = preparado[1] if isinstance(preparado, tuple) else None
        embed = preparado[0] if isinstance(preparado, tuple) else preparado
        if embed is None:
            atacante = self._obter_atacante(combate) or {}
            defensor = self._obter_defensor(combate) or {}
            embed = painel(atacante=atacante.get("nome", "User"), ataque="início do combate", vida=self._vida(atacante), mana=atacante.get("mana", 0), alvo=defensor.get("nome", "-"), turno=1, oponente=defensor, vida_oponente=self._vida(defensor), extra="Combate iniciado.", cor=discord.Color.red())
        if combate.get("ui_message"):
            await self._ui_editar(combate, embed)
            return
        kwargs = {"embed": embed}
        if arquivo is not None:
            kwargs["file"] = arquivo
        mensagem = await ctx.send(**kwargs)
        combate["ui_message"] = mensagem
        combate["ui_owner_id"] = getattr(ctx.author, "id", None)
        combate["ui_stage"] = "attributes"
        combate["ui_waiting_advance"] = True
        self._ui_views[mensagem.id] = _AvancarView(self)
        await self._ui_editar(combate, embed, view=True)
    
    def preparar_embed(self, ctx, embed, arquivo=None):
        self._embeds_acao[ctx.channel.id] = (embed, arquivo) if arquivo is not None else embed
    
    async def resultado_ataque(self, ctx):
        return await self._resolver_ataque(ctx)
    
    async def resultado_defesa(self, ctx, acao):
        return await self._defesa_jogador(ctx, acao)
    
    async def resultado_magia(self, ctx, dados_magia):
        return await self.usar_magia_no_combate(ctx, dados_magia)
    
    async def resultado_ataque_monstro(self, ctx):
        return await self._ataque_monstro(ctx)
    
    async def resultado_pvp(self, ctx, motivo):
        return await self._finalizar_pvp(ctx, motivo)
    
    async def resultado_final(self, ctx, motivo="vida", vencedor=None, perdedor=None):
        return await self._finalizar(ctx, motivo=motivo, vencedor=vencedor, perdedor=perdedor)
    
    
    """Maquina de estados unica para PvP, PvE e party."""

    def __init__(self, bot):
        self.bot = bot
        self.combates = {}
        self._locks = {}
        self._ui_views = {}
        self._embeds_acao = {}
        self._ui_avancar_locks = {}

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

    def _obter_combate_por_participantes(self, participante):
        """Retorna o combate que contém a mesma instância do participante."""
        if participante is None:
            return {}
        for combate in self.combates.values():
            if any(p is participante for p in combate.get("participantes", [])):
                return combate
        return {}


    def _dano_magia(self, atacante, defensor, ataque):
        if defensor.get("esquiva_ativa"):
            defensor["esquiva_ativa"] = False
            if random.random() < min(0.75, 0.10 + _velocidade(defensor) / 500):
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
        dano = max(0, int(dano))
        combate = self._obter_combate_por_participantes(defensor)
        dano = boss_rules.corrosao(dano, defensor)
        return boss_rules.regras_dano(dano, "atingiu", atacante, defensor, ataque, combate)

    def _aplicar_efeito(self, defensor, efeito):
        if not isinstance(efeito, dict):
            return None
        especial = boss_rules.efeito_especial(defensor, efeito)
        if especial is not None:
            return especial
        nome = str(efeito.get("nome", efeito.get("tipo", ""))).strip().lower()
        if not nome:
            return None
        turnos = max(1, int(_num(efeito.get("turnos", efeito.get("duracao", 1)), 1)))
        valor = int(_num(efeito.get("valor"), 5))
        defensor.setdefault("efeitos", []).append({"nome": nome, "turnos": turnos, "valor": valor})
        return nome

    async def _aplicar_efeitos_inicio(self, ctx, participante):
        combate = self._obter_combate(ctx.channel.id)
        boss_rules.inicio_especial(combate or {}, participante)
        dano_total = 0
        bloqueado = False
        novos = []
        for efeito in list(participante.get("efeitos", []) or []):
            if not isinstance(efeito, dict):
                continue
            nome = _normalizar(efeito.get("nome", efeito.get("tipo", "")))
            valor = max(0, int(_num(efeito.get("valor"), 5)))
            if nome in {"veneno", "queimadura", "sangramento"}:
                dano_total += valor
            elif nome == "sangramento_profundo":
                defesa = _attr(participante, "Defesa", "defesa") + _attr(participante, "Força", "forca")
                dano_total += max(1, int(valor - defesa * 0.5))
            if nome in {"paralisia", "stun", "prisao", "prisão"}:
                bloqueado = True
            turnos = int(_num(efeito.get("turnos"), 1)) - 1
            if turnos > 0:
                copia = dict(efeito)
                copia["turnos"] = turnos
                novos.append(copia)
        participante["efeitos"] = novos
        if dano_total:
            participante["vida"] = max(0, int(_num(participante.get("vida")) - dano_total))
            await ctx.send(f"⚠️ **{participante.get('nome')}** sofreu **{dano_total}** de efeitos.")
        return bloqueado


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
        if acao not in {"defesa", "esquiva", "normal"}:
            raise ValueError(f"ação de defesa inválida: {acao}")
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


# Camada de interface visual incorporada ao arquivo único.
"""Interface visual única das mensagens de combate e dos painéis RPG."""




FOOTER = "Tensura Moon - Korczak Technologies!"


def _carregar_imagens():
    caminho = Path(__file__).resolve().parents[2] / "database" / "json" / "Imagens.json"
    try:
        with caminho.open("r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        imagens = dados.get("Imagens", {})
        return imagens if isinstance(imagens, dict) else {}
    except (OSError, ValueError, TypeError) as erro:
        print(f"[LUTA][IMAGENS] Erro ao carregar Imagens.json: {erro}")
        return {}


IMAGENS = _carregar_imagens()


def _normalizar_nome(valor):
    texto = unicodedata.normalize("NFKD", str(valor or "")).casefold().strip()
    return "".join(c for c in texto if not unicodedata.combining(c))


def imagem_ataque(nome):
    # imagem_ataque é propositalmente ignorada; ataques não exibem imagem.
    return None


def imagem_monstro(monstro):
    """Retorna a imagem do monstro somente para a apresentação inicial do PvE."""
    if isinstance(monstro, dict):
        valor = monstro.get("id") or monstro.get("monstro_id") or monstro.get("nome")
    else:
        valor = monstro
    mapa = {
        "slime": "slime-luta-url", "goblin": "goblin-luta-url", "lobo": "lobo-luta-url",
        "orc": "orc-luta-url", "esqueleto": "esqueleto-luta-url", "dragao": "dragao-luta-url",
        "titan": "titan-luta-url", "fenix": "fenix-luta-url", "demonio": "demonio-luta-url",
    }
    url = IMAGENS.get(mapa.get(_normalizar_nome(valor)))
    return url if isinstance(url, str) and "discord" in url.lower() else None


def imagem_golpe(nome):
    return None


def imagens_combate(nome_ataque, monstro=None):
    return None, imagem_monstro(monstro)


def _imagem_monstro(oponente):
    return None


def _vida(p):
    if not p:
        return "-"
    vida = int(float(p.get("vida", 0) or 0))
    maxima = int(float(p.get("vida_maxima", vida) or vida or 1))
    return f"{max(0, vida)}/{max(1, maxima)}"


def _mana(p):
    if not p:
        return "-"
    return str(int(float(p.get("mana", 0) or 0)))


def _nome(p, padrao="-"):
    if isinstance(p, dict):
        return str(p.get("nome") or padrao)
    if p is None:
        return str(padrao)
    return str(p)


def _linha(texto):
    return f"**{texto}**"


def _rotulo_acao(ataque):
    texto = str(ataque or "").strip()
    genericos = {
        "resultado": "📋 | Resultado", "ordem de velocidade": "📋 | Ordem de velocidade",
        "aguardando ação": "⏳ | Aguardando ação", "início do combate": "⚔️ | Início do combate",
        "finalização": "🏁 | Finalização", "resultado da defesa": "🛡️ | Resultado da defesa",
        "stun": "⛓️ | Stun", "⛓️ stun": "⛓️ | Stun",
        "apresentação do monstro": "👹 | Apresentação do monstro", "lista de monstros": "👹 | Lista de monstros",
        "comandos": "📖 | Comandos", "status": "📊 | Status", "🛌 descanso": "🛌 | Descanso",
        "🧘 meditação": "🧘 | Meditação", "⏰ recuperação": "⏰ | Recuperação",
        "⚔️ pvp": "⚔️ | PvP", "defenda-se": "🛡️ | Defesa",
    }
    return genericos.get(texto.casefold())


def _limpar_marcacao(texto):
    return str(texto).replace("**", "").strip()


def _extrair_valor(linhas, prefixos, padrao="-"):
    if isinstance(prefixos, str):
        prefixos = (prefixos,)
    for linha in linhas:
        linha = _limpar_marcacao(linha)
        for prefixo in prefixos:
            if linha.startswith(prefixo):
                return linha.split(":", 1)[1].strip() if ":" in linha else linha
    return padrao


def _painel_status(*, atacante, vida, mana, extra, cor, imagem_oponente=None):
    """Ficha pública: moldura obrigatória, negrito e leitura rápida no Discord."""
    linhas = [_limpar_marcacao(l) for l in str(extra or "").splitlines() if str(l).strip()]

    nome = _extrair_valor(linhas, "👤 Nome:", atacante)
    personagem = _extrair_valor(linhas, "🧬 Personagem:", "Não definido")
    raca = _extrair_valor(linhas, "🧬 Raça:", "Não definida")
    nivel = _extrair_valor(linhas, "📈 Nível:", "0")
    situacao = _extrair_valor(linhas, "📌 Situação:", "ativo")
    experiencia = _extrair_valor(linhas, ("⭐ XP:", "⭐ Experiência:"), "-")
    vida_txt = _extrair_valor(linhas, "❤️ Vida:", str(vida))
    mana_txt = _extrair_valor(linhas, "💧 Mana:", str(mana))
    magiculas = _extrair_valor(linhas, "✨ Magículas:", "0")
    tp = _extrair_valor(linhas, "✨ TP:", "0")

    # Cada atributo fica obrigatoriamente em sua própria linha.
    mapa_atributos = (
        ("💪", "Força"), ("🛡️", "Defesa"), ("❤️", "Vitalidade"), ("⚡", "Velocidade"),
        ("🎯", "Destreza"), ("✨", "Magia"), ("🍀", "Sorte"), ("🧠", "Inteligência"),
    )
    atributos = []
    for emoji, nome_atributo in mapa_atributos:
        valor = None
        for linha in linhas:
            partes = [parte.strip() for parte in linha.split("|")]
            for parte in partes:
                limpo = _limpar_marcacao(parte)
                if limpo.startswith(f"{nome_atributo}:"):
                    valor = limpo.split(":", 1)[1].strip()
                    break
            if valor is not None:
                break
        atributos.append((emoji, nome_atributo, valor if valor is not None else "0"))

    recuperacao = []
    for emoji, nome_rec in (("🛌", "Descanso"), ("🧘", "Meditação")):
        valor = _extrair_valor(linhas, f"{nome_rec}:", None)
        if valor is not None:
            recuperacao.append((emoji, nome_rec, valor))

    if not recuperacao:
        recuperacao = [("🔄", "Status", "Disponível para consulta")]

    linhas_saida = [
        "╭────────────────────────────────────────────╮",
        "│              🌙 MOON TENSURA               │",
        "├────────────────────────────────────────────┤",
        f"│ ⋮ → 👤 | Jogador: {nome}",
        f"│ ⋮ → 🧬 | Personagem: {personagem}",
        f"│ ⋮ → 🧬 | Raça: {raca}",
        f"│ ⋮ → 🎚️ | Nível: {nivel}",
        f"│ ⋮ → 📌 | Situação: {situacao}",
        f"│ ⋮ → ⭐ | Experiência: {experiencia}",
        f"│ ⋮ → ❤️ | Vida: {vida_txt}",
        f"│ ⋮ → 💧 | Mana: {mana_txt}",
        f"│ ⋮ → ✨ | Magículas: {magiculas}",
        f"│ ⋮ → 🔷 | TP: {tp}",
        "├────────────────────────────────────────────┤",
        "│ │ → 📊 | ATRIBUTOS DO PERSONAGEM",
    ]
    linhas_saida.extend(f"│ │ → {emoji} | {nome_atributo}: {valor}" for emoji, nome_atributo, valor in atributos)
    linhas_saida.extend([
        "├────────────────────────────────────────────┤",
        "│ │ → 🔄 | RECUPERAÇÃO",
    ])
    linhas_saida.extend(f"│ │ → {emoji} | {nome_rec}: {valor}" for emoji, nome_rec, valor in recuperacao)
    linhas_saida.append("╰────────────────────────────────────────────╯")

    descricao = "\n".join(_linha(linha) for linha in linhas_saida)
    embed = discord.Embed(
        title="🌙 MOON TENSURA",
        description=descricao,
        color=cor or discord.Color.blurple(),
        timestamp=discord.utils.utcnow(),
    )
    embed.set_footer(text=FOOTER)
    return embed


def painel(*, atacante="User", ataque="Ataque", vida="-", mana="-", dano="-", efeito="Nenhum", alvo="-", turno="-", oponente="-", vida_oponente="-", extra="", cor=None, imagem_ataque=None, imagem_oponente=None):
    if str(ataque or "").strip().casefold() == "status":
        return _painel_status(atacante=atacante, vida=vida, mana=mana, extra=extra, cor=cor, imagem_oponente=imagem_oponente)

    nome_oponente = _nome(oponente, str(oponente) if not isinstance(oponente, dict) else "-")
    texto_ataque = str(ataque or "").strip()
    rotulo = _rotulo_acao(ataque)
    if "sua vez" in texto_ataque.casefold() or "vez do monstro" in texto_ataque.casefold():
        linha_acao = f"│ ⋮ → 👤 | Vez de {atacante}"
    elif rotulo:
        linha_acao = f"│ ⋮ → {rotulo}"
    elif texto_ataque.casefold().startswith("vez de"):
        linha_acao = f"│ ⋮ → 👤 | {ataque}"
    else:
        linha_acao = f"│ ⋮ → 👤 | {atacante} atacou usando {ataque}"
    linhas = [
        "╭────────────────────────────────────────────╮",
        "│              🌙  MOON TENSURA              │",
        "├────────────────────────────────────────────┤",
        linha_acao,
        f"│ ⋮ → ❤️ | Vida de {atacante}: {vida}",
        f"│ ⋮ → 🔷 | Mana de: {mana}",
        "├────────────────────────────────────────────┤",
        f"│ │ → ⚔️ | Dano: {dano}",
        f"│ │ → ✦ | Efeito: {efeito}",
        f"│ │ → 🎯 | Alvo: {alvo}",
        f"│ │ → 🔄 | Turno: {turno}",
        "├ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┤",
        f"│ │ → 👹 | Oponente: {nome_oponente}",
        f"│ │ → ❤️ | Vida: {vida_oponente}",
    ]
    if extra:
        linhas.extend(f"│ │ → ℹ️ | {linha}" for linha in str(extra).splitlines())
    linhas.append("╰────────────────────────────────────────────╯")
    texto = "\n".join(_linha(linha) for linha in linhas)
    mensagem = discord.Embed(title="🌙 MOON TENSURA", description=texto, color=cor or discord.Color.blurple(), timestamp=discord.utils.utcnow())
    mensagem.set_footer(text=FOOTER)
    return mensagem


def embed(titulo, descricao="", *, cor=None, imagem=None):
    return painel(extra=f"{titulo}: {descricao}" if descricao else titulo, cor=cor)


def resultado(texto, *, status=None):
    return painel(ataque="resultado", extra=f"Resultado: {texto}" + (f" | Status: {status}" if status else ""), cor=discord.Color.red())


def turno(numero, atacante, defensor):
    return painel(atacante=atacante, ataque="aguardando ação", alvo=defensor, turno=numero, oponente=defensor, extra="Escolha sua ação de combate.", cor=discord.Color.green())


def ataque(numero, nome_ataque, atacante, defensor, status):
    return painel(atacante=atacante, ataque=nome_ataque, alvo=defensor, turno=numero, oponente=defensor, vida_oponente=status, cor=discord.Color.orange())


def finalizacao(descricao, status, xp=0, hunos=0, *, venceu=False):
    return painel(ataque="finalização", efeito=f"XP +{xp} | Hunos +{hunos}", turno="fim", extra=descricao, oponente="Combate encerrado", vida_oponente=status, cor=discord.Color.green() if venceu else discord.Color.red())


def inicio(*, pvp, turno, atacante, defensor):
    return painel(atacante=atacante, ataque="início do combate", alvo=defensor, turno=turno, oponente=defensor, extra="Combate PvP iniciado." if pvp else "Combate PvE iniciado.", cor=discord.Color.red())


def ordem_velocidade(participantes):
    ordem = " | ".join(f"{i + 1}. {p.get('nome')} ({int(float(p.get('Velocidade', p.get('velocidade', 0)) or 0))})" for i, p in enumerate(participantes)) or "Nenhum participante."
    return painel(ataque="ordem de velocidade", turno=1, oponente="Todos", extra=ordem, cor=discord.Color.blurple())


def acao(*, atacante, defensor, nome_ataque, dano=0, efeito="Nenhum", turno="-", extra="", cor=None):
    return painel(atacante=_nome(atacante, "User"), ataque=nome_ataque, vida=_vida(atacante), mana=_mana(atacante), dano=dano, efeito=efeito or "Nenhum", alvo=_nome(defensor), turno=turno, oponente=defensor or "-", vida_oponente=_vida(defensor), extra=extra, cor=cor)


# Regras especiais dos monstros incorporadas ao arquivo único.
"""Regras especiais de monstros, sem monkey-patching.

Este módulo só fornece funções puras/serviços chamados explicitamente pelo
motor efetivo de combate. A classe Luta não é modificada durante import.
"""

ATRIBUTOS = ("Força","Defesa","Vitalidade","Velocidade","Destreza","Magia","Sorte","Inteligencia")
BOSS_IDS = {"slime-rei","goblin-rei","lobo-alpha","orc-rei","cavaleiro-esqueletico","dragao-adulto","arquidemonio","fenix"}

def estado(monstro):
    return monstro.setdefault("boss_estado", {})

def eh(monstro, *ids):
    return str(monstro.get("boss_id", monstro.get("id",""))) in ids

def vivo(p):
    try: return float(p.get("vida",0) or 0) > 0
    except (TypeError,ValueError): return False

def alvos(combate, atacante):
    equipe=atacante.get("equipe")
    return [p for p in combate.get("participantes",[]) if vivo(p) and p is not atacante and p.get("equipe") != equipe]

def matar_invocados(combate,boss_id):
    if boss_id != "cavaleiro-esqueletico": return
    for p in combate.get("participantes",[]):
        if p.get("invocado") and p.get("equipe")=="inimigos": p["vida"]=0

def ataque_especial(combate, atacante, defensor):
    mid=str(atacante.get("boss_id",atacante.get("id","")))
    st=estado(atacante); turno=int(combate.get("numero_turno",1))
    if mid=="dragao-adulto" and turno%4==0:
        mult=4 if st.get("furia_draconica") else 3
        normal=float(atacante.get("Força",0) or 0)+float(atacante.get("Velocidade",0) or 0)+float(atacante.get("dano_base",0) or 0)
        base=max(0,int(normal*mult-(normal-float(atacante.get("dano_base",0) or 0))))
        st["sopro_elemental"]=True
        return {"nome":"🔥 Sopro Elemental","dano_base":base,"efeito":{"nome":"queimadura","valor":10,"turnos":3},"com_arma":False,"area":True,"area_targets":alvos(combate,atacante),"multiplicador_area":mult}
    return None

def ajustar_ataque(atacante, dados):
    mid=str(atacante.get("boss_id",atacante.get("id","")))
    out=dict(dados)
    if mid=="slime-rei": out.update(nome="🧪 Lodo Corrosivo",efeito={"nome":"corrosao","valor":10,"turnos":3})
    elif mid=="lobo-alpha": out["nome"]="🦷 Mordida Predatória"
    elif mid=="orc-rei": out["nome"]="🩸 Investida Predatória"
    elif mid=="fenix":
        e=dict(out.get("efeito") or {})
        if str(e.get("nome","")).casefold()!="queimadura": out["efeito"]={"nome":"queimadura","valor":10,"turnos":3}
    return out

def regras_dano(dano,resultado,atacante,defensor,ataque,combate):
    st=estado(atacante); mid=str(atacante.get("boss_id",atacante.get("id","")))
    if atacante.get("tipo")!="monstro" or resultado!="atingiu": return dano,resultado
    alvo=str(defensor.get("id"))
    if mid=="goblin-rei":
        if st.get("alvo_id")!=alvo: st.update(alvo_id=alvo,acertos_consecutivos=0)
        st["acertos_consecutivos"]=int(st.get("acertos_consecutivos",0))+1
        if st.pop("critico_pendente",False): dano=int(dano*2)
        if st["acertos_consecutivos"]%3==0: st["acumulos"]=min(3,int(st.get("acumulos",0))+1); st["critico_pendente"]=int(st.get("acumulos",0))>=3
        dano=int(dano*(1+0.15*int(st.get("acumulos",0))))
    elif mid in {"lobo-alpha","orc-rei"}:
        if st.get("alvo_id")!=alvo: st.update(alvo_id=alvo,acertos_consecutivos=0)
        st["acertos_consecutivos"]=int(st.get("acertos_consecutivos",0))+1
        if st.pop("furia_alvo_pendente",False) and st.get("furia_alvo_id")==alvo: dano=int(dano*1.5); st["furia_alvo_id"]=None
        if float(defensor.get("vida",0) or 0)-dano <= float(defensor.get("vida_maxima",1) or 1)*.30: st["furia_alvo_pendente"]=True; st["furia_alvo_id"]=alvo
        if st["acertos_consecutivos"]%3==0: adicionar_efeito(defensor,{"nome":"sangramento_profundo","valor":10,"turnos":3,"ignora_defesa":.5})
    elif mid=="cavaleiro-esqueletico":
        if st.get("alvo_id")!=alvo: st.update(alvo_id=alvo,acertos_consecutivos=0)
        st["acertos_consecutivos"]=int(st.get("acertos_consecutivos",0))+1
        if st["acertos_consecutivos"]%3==0:
            fr=st.setdefault("fraturas",{}); fr[alvo]=int(fr.get(alvo,0))+1
            adicionar_efeito(defensor,{"nome":"fratura","valor":0,"turnos":3})
            if fr[alvo]>=3: adicionar_efeito(defensor,{"nome":"stun","valor":0,"turnos":1}); fr[alvo]=0
    return dano,resultado

def corrosao(dano,defensor):
    e=next((x for x in defensor.get("efeitos",[]) if str(x.get("nome","")).casefold()=="corrosao"),None)
    if not e:return dano
    stacks=min(3,max(1,int(e.get("acumulo",1) or 1)))
    return int(dano*(1-.10*stacks))

def adicionar_efeito(defensor,efeito):
    nome=str(efeito.get("nome",efeito.get("tipo",""))).casefold()
    efeitos=defensor.setdefault("efeitos",[])
    atual=next((e for e in efeitos if str(e.get("nome","")).casefold()==nome),None)
    novo=dict(efeito)
    if atual:
        atual["turnos"]=max(int(atual.get("turnos",1)),int(novo.get("turnos",1)))
        atual["valor"]=max(int(atual.get("valor",0)),int(novo.get("valor",0)))
        if nome=="corrosao": atual["acumulo"]=min(3,int(atual.get("acumulo",1))+int(novo.get("acumulo",1)))
        return atual
    efeitos.append(novo); return novo

def efeito_especial(defensor,efeito):
    if not isinstance(efeito,dict): return None
    nome=str(efeito.get("nome",efeito.get("tipo",""))).casefold()
    if eh(defensor,"dragao-adulto") and nome in {"stun","paralisia","sono","sleep","prisao","prisão"} and random.random()<.75: return False
    if nome in {"corrosao","sangramento_profundo"}: return adicionar_efeito(defensor,efeito)
    return None

def inicio_especial(combate, participante):
    """Aplica apenas efeitos exclusivos de boss; o dano periódico é do motor base."""
    if not vivo(participante):
        if eh(participante, "cavaleiro-esqueletico"):
            matar_invocados(combate, "cavaleiro-esqueletico")
        return False
    if eh(participante, "fenix"):
        cura=max(1,int(float(participante.get("vida_maxima",0))*0.04))
        participante["vida"]=min(float(participante.get("vida_maxima",participante.get("vida",0))),
                                 float(participante.get("vida",0))+cura)
    if not vivo(participante) and eh(participante, "cavaleiro-esqueletico"):
        matar_invocados(combate, "cavaleiro-esqueletico")
    return False

def preparar_proximo_turno(combate):
    """Calcula regras especiais sem alterar a lista de participantes."""
    turno = int(combate.get("numero_turno", 1))
    participantes = combate.get("participantes", [])
    expirados = {
        str(p.get("id")) for p in participantes
        if p.get("invocado") and turno >= int(p.get("expira_turno", 10**9))
    }
    combate["_participantes_expirados"] = expirados
    for p in participantes:
        if eh(p,"dragao-adulto") and not estado(p).get("furia_draconica") and vivo(p) and float(p.get("vida",0)) <= float(p.get("vida_maxima",1)) * .25:
            estado(p)["furia_draconica"] = True
            p["Velocidade"] = float(p.get("Velocidade",0)) * 1.2
            p["velocidade"] = p["Velocidade"]


boss_rules = SimpleNamespace(
    estado=estado, eh=eh, vivo=vivo, alvos=alvos,
    matar_invocados=matar_invocados, ataque_especial=ataque_especial,
    ajustar_ataque=ajustar_ataque, regras_dano=regras_dano,
    corrosao=corrosao, adicionar_efeito=adicionar_efeito,
    efeito_especial=efeito_especial, inicio_especial=inicio_especial,
    preparar_proximo_turno=preparar_proximo_turno,
)
    async def _mostrar_aguarde_player(self, combate):
        combate["ui_stage"] = "player_action"
        await self._ui_editar(combate, self._embed_aguarde_jogador(combate))
    
    def _por_id(self, combate, participante_id):
        if participante_id is None:
            return None
        return next((p for p in combate.get("participantes", [])
                     if str(p.get("id")) == str(participante_id)), None)
    
    def _normalizar_estado(self, combate):
        """Normaliza invariantes sem trocar identidade de turno silenciosamente."""
        participantes = combate.setdefault("participantes", [])
        combate.setdefault("historico", [])
        combate.setdefault("ataque_pendente", None)
        combate.setdefault("turno", 0)
        combate.setdefault("numero_turno", 1)
        combate.setdefault("fase", "ataque")
        combate.setdefault("ativo", True)
        combate.setdefault("ui_stage", "attributes")
        combate.setdefault("ui_waiting_advance", False)
        combate.setdefault("_turno_participante_id", None)
        if participantes:
            ids = {str(p.get("id")) for p in participantes}
            turno_id = combate.get("_turno_participante_id")
            if turno_id is not None and str(turno_id) in ids:
                combate["turno"] = next(i for i,p in enumerate(participantes) if str(p.get("id")) == str(turno_id))
            else:
                combate["turno"] = max(0, min(int(combate.get("turno", 0)), len(participantes)-1))
                combate["_turno_participante_id"] = participantes[combate["turno"]].get("id")
        combate["numero_turno"] = max(1, int(combate.get("numero_turno", 1)))
        ataque = combate.get("ataque_pendente")
        if ataque:
            atacante = self._por_id(combate, ataque.get("atacante_id"))
            defensor = self._por_id(combate, ataque.get("defensor_id"))
            if not atacante or not defensor:
                combate["ataque_pendente"] = None
                combate["fase"] = "ataque"
                combate["ui_stage"] = "turn"
                combate["ui_waiting_advance"] = False
            else:
                combate["fase"] = "defesa"
    
    def _obter_atacante(self, combate):
        self._normalizar_estado(combate)
        ataque = combate.get("ataque_pendente")
        if ataque:
            return self._por_id(combate, ataque.get("atacante_id"))
        participantes = combate.get("participantes", [])
        if not participantes:
            return None
        atual = int(combate.get("turno", 0)) % len(participantes)
        if _vivo(participantes[atual]):
            combate["_turno_participante_id"] = participantes[atual].get("id")
            return participantes[atual]
        for passo in range(1, len(participantes) + 1):
            indice = (atual + passo) % len(participantes)
            if _vivo(participantes[indice]):
                combate["turno"] = indice
                combate["_turno_participante_id"] = participantes[indice].get("id")
                return participantes[indice]
        return None
    
    def _obter_defensor(self, combate):
        self._normalizar_estado(combate)
        ataque = combate.get("ataque_pendente")
        if ataque:
            return self._por_id(combate, ataque.get("defensor_id"))
        atacante = self._obter_atacante(combate)
        if not atacante:
            return None
        equipe = atacante.get("equipe")
        return next((p for p in combate.get("participantes", [])
                     if p is not atacante and _vivo(p) and p.get("equipe") != equipe), None)
    
    def _criar_ataque(self, combate, tipo, atacante, defensor, **dados):
        """Cria exatamente um ataque e congela atacante/alvo até a resolução."""
        self._normalizar_estado(combate)
        existente = combate.get("ataque_pendente")
        if existente:
            if (str(existente.get("atacante_id")) != str((atacante or {}).get("id")) or
                    str(existente.get("defensor_id")) != str((defensor or {}).get("id"))):
                raise RuntimeError("tentativa de substituir ataque pendente por outro alvo")
            combate["fase"] = "defesa"
            return existente
        if not atacante or not defensor:
            raise RuntimeError("ataque criado sem atacante ou defensor")
        if not _vivo(atacante):
            raise RuntimeError("ataque criado por participante derrotado")
        if not _vivo(defensor):
            raise RuntimeError("ataque criado contra participante derrotado")
        if tipo not in {"fisico", "magia", "soco", "chute", "ataque_monstro"}:
            raise ValueError(f"tipo de ataque inválido: {tipo}")
        dados.setdefault("efeito", {})
        dados.setdefault("mana_base", 0)
        dados.setdefault("com_arma", False)
        try:
            dados["dano_base"] = float(dados.get("dano_base", 0) or 0)
            dados["mana_base"] = float(dados.get("mana_base", 0) or 0)
        except (TypeError, ValueError) as erro:
            raise ValueError("dano_base/mana_base inválidos") from erro
        efeito = dados.get("efeito")
        if isinstance(efeito, str):
            efeito = {"nome": efeito}
            dados["efeito"] = efeito
        if efeito is not None and not isinstance(efeito, dict):
            raise ValueError("efeito de ataque inválido")
        ataque = {"tipo": tipo, "nome": dados.pop("nome", "⚔️ Ataque"),
                  "atacante_id": atacante.get("id"), "defensor_id": defensor.get("id"), **dados}
        combate["ataque_pendente"] = ataque
        combate["fase"] = "defesa"
        combate["ui_waiting_advance"] = False
        combate["ui_stage"] = "attack"
        return ataque
    
    async def _mostrar_ataque_ui(self, combate):
        ataque = combate.get("ataque_pendente")
        if not ataque:
            raise RuntimeError("UI solicitada sem ataque pendente")
        atacante = self._por_id(combate, ataque.get("atacante_id"))
        defensor = self._por_id(combate, ataque.get("defensor_id"))
        if not atacante or not defensor:
            raise RuntimeError("ataque pendente sem atacante ou defensor")
        efeito = ataque.get("efeito") or "Nenhum"
        if isinstance(efeito, dict):
            efeito = efeito.get("nome", efeito.get("tipo", "Nenhum"))
        embed = self._acao_embed(atacante=atacante, defensor=defensor,
            nome=ataque.get("nome", "Ataque"),
            emoji="👹" if atacante.get("tipo") == "monstro" else "⚔️",
            turno=combate.get("numero_turno", 1), dano=ataque.get("dano_base", 0),
            mana=ataque.get("mana_base", 0),
            descricao=f"**{atacante.get('nome')}** atacou **{defensor.get('nome')}**.", efeito=efeito)
        await self._ui_editar(combate, embed)
        combate["ui_stage"] = "attack"
        combate["ui_waiting_advance"] = False
    
    async def _anunciar_ataque(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return
        ataque = combate.get("ataque_pendente")
        if not ataque:
            raise RuntimeError("tentativa de anunciar ataque inexistente")
        if not self._por_id(combate, ataque.get("atacante_id")) or not self._por_id(combate, ataque.get("defensor_id")):
            raise RuntimeError("ataque pendente sem participantes para anúncio")
        if combate.get("ui_message"):
            await self._mostrar_ataque_ui(combate)
            return
        embed = self._embeds_acao.pop(ctx.channel.id, None)
        if isinstance(embed, tuple):
            embed = embed[0]
        if embed is None:
            atacante = self._por_id(combate, ataque["atacante_id"])
            defensor = self._por_id(combate, ataque["defensor_id"])
            embed = discord.Embed(description=f"**{atacante.get('nome')}** atacou **{defensor.get('nome')}**!", color=discord.Color.orange())
        await ctx.send(embed=embed)
    
    async def _ataque_monstro(self, ctx):
        """Único caminho de criação do ataque de monstro; nunca duplica pending."""
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return None
        if combate.get("ataque_pendente"):
            combate["fase"] = "defesa"
            combate["ui_stage"] = "attack"
            return combate["ataque_pendente"]
        atacante = self._obter_atacante(combate)
        defensor = self._obter_defensor(combate)
        if not atacante or not defensor or atacante.get("tipo") != "monstro":
            raise RuntimeError("turno do monstro sem atacante/defensor válido")
        import random
        especial = boss_rules.ataque_especial(combate, atacante, defensor)
        if especial is not None:
            dados, tipo = especial, "fisico"
        else:
            golpes = [luta_db.GOLPES[i] for i in (atacante.get("golpes") or []) if i in luta_db.GOLPES]
            if not golpes:
                raise RuntimeError("monstro sem golpe válido: configure pelo menos um golpe válido")
            golpe = boss_rules.ajustar_ataque(atacante, random.choice(golpes))
            dados = {"nome": golpe.get("nome", "Ataque"), "dano_base": float(golpe.get("dano_base", atacante.get("dano_base", 0)) or 0),
                     "mana_base": float(golpe.get("custo_mana", 0) or 0), "com_arma": bool(golpe.get("com_arma", False)),
                     "efeito": golpe.get("efeito", {}) or {}}
            tipo_original = str(golpe.get("tipo", "monstro")).casefold()
            tipo = "magia" if tipo_original in {"magia", "magico", "mágico"} else "ataque_monstro"
        ataque = self._criar_ataque(combate, tipo, atacante, defensor, **dados)
        if combate.get("ui_message"):
            await self._mostrar_ataque_ui(combate)
        else:
            await self._anunciar_ataque(ctx)
        return ataque
    
    async def _criar_ataque_monstro_ui(self, combate):
        mensagem = combate.get("ui_message")
        if mensagem is None:
            raise RuntimeError("combate sem mensagem para ataque de monstro")
        ctx = _UIContext(mensagem, mensagem, combate, self)
        await self._ataque_monstro(ctx)
        if combate.get("ativo") and not combate.get("ataque_pendente"):
            raise RuntimeError("turno do monstro terminou sem gerar ataque")
        if combate.get("ataque_pendente") and combate.get("ui_stage") != "attack":
            combate["fase"] = "defesa"
            await self._mostrar_ataque_ui(combate)
    
    async def _resolver_ataque(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return
        ataque = combate.get("ataque_pendente")
        if not ataque or ataque.get("_resolvendo"):
            return
        participante_snapshots = [(p, copy.deepcopy(p)) for p in combate.get("participantes", [])]
        estado_anterior = {
            "ataque_pendente": copy.deepcopy(ataque),
            "fase": combate.get("fase", "defesa"),
            "ui_stage": combate.get("ui_stage", "attack"),
            "ui_waiting_advance": combate.get("ui_waiting_advance", False),
            "aguardando_finalizacao": combate.get("aguardando_finalizacao", False),
            "vencedor_id": combate.get("vencedor_id"),
            "perdedor_id": combate.get("perdedor_id"),
            "historico": list(combate.get("historico", [])),
        }
        atacante = self._por_id(combate, ataque.get("atacante_id"))
        defensor = self._por_id(combate, ataque.get("defensor_id"))
        ataque["_resolvendo"] = True
        try:
            if not atacante or not defensor:
                combate["historico"].append("Ataque pendente descartado: participante ausente.")
                combate["ataque_pendente"] = None
                combate["fase"] = "ataque"
                combate["ui_stage"] = "turn"
                self._limpar_defesas(combate)
                await self._salvar(combate)
                await self._proximo_turno(ctx)
                return
            if not _vivo(atacante) or not _vivo(defensor):
                combate["historico"].append("Ataque pendente descartado: participante derrotado.")
                combate["ataque_pendente"] = None
                combate["fase"] = "ataque"
                combate["ui_stage"] = "turn"
                self._limpar_defesas(combate)
                await self._salvar(combate)
                await self._proximo_turno(ctx)
                return
            duelo_pendente = False
            if ataque.get("tipo") == "magia" and float(ataque.get("cura_base", 0) or 0) > 0:
                cura = int(float(atacante.get("Magia", atacante.get("magia", 0)) or 0) + float(atacante.get("Inteligencia", atacante.get("Inteligência", 0)) or 0) + float(ataque.get("cura_base", 0) or 0))
                atacante["vida"] = min(int(float(atacante.get("vida_maxima", atacante.get("vida", 0)) or 0)), int(float(atacante.get("vida", 0) or 0)) + cura)
                mensagem = f"✨ **{atacante.get('nome')}** recuperou **{cura} de vida**."
            else:
                if ataque.get("tipo") == "magia":
                    dano, resultado = self._dano_magia(atacante, defensor, ataque)
                    tipo_texto = "mágico"
                else:
                    dano, resultado = self._dano_fisico(atacante, defensor, ataque)
                    tipo_texto = ""
                if resultado == "esquivou":
                    mensagem = f"💨 **{defensor.get('nome')}** esquivou do ataque!"
                else:
                    vida_antes = int(float(defensor.get("vida", 0) or 0))
                    if combate.get("assentamento_duelo") and dano >= vida_antes:
                        dano = max(0, vida_antes - 1)
                        duelo_pendente = True
                    defensor["vida"] = max(0, vida_antes - dano)
                    mensagem = (f"✨ **{atacante.get('nome')}** causou **{dano} de dano mágico** em **{defensor.get('nome')}**."
                                if tipo_texto else f"⚔️ **{atacante.get('nome')}** causou **{dano} de dano** em **{defensor.get('nome')}**.")
                    efeito = self._aplicar_efeito(defensor, ataque.get("efeito"))
                    if efeito:
                        mensagem += f"\n⚠️ Efeito: **{efeito.title()}**."
                    if combate.get("assentamento_duelo") and defensor.get("vida", 0) <= 0:
                        defensor["vida"] = 1
                        duelo_pendente = True
            if ataque.get("area"):
                alvos_area = []
                vistos = {str(defensor.get("id"))}
                for alvo in ataque.get("area_targets", []) or []:
                    alvo_id = str((alvo or {}).get("id"))
                    if alvo_id in vistos:
                        continue
                    alvo_real = self._por_id(combate, alvo_id)
                    if alvo_real and _vivo(alvo_real):
                        vistos.add(alvo_id)
                        alvos_area.append(alvo_real)
                for alvo in alvos_area:
                    dano_area, resultado_area = (
                        self._dano_magia(atacante, alvo, ataque)
                        if ataque.get("tipo") == "magia"
                        else self._dano_fisico(atacante, alvo, ataque)
                    )
                    if resultado_area == "esquivou":
                        mensagem += f"\n💨 **{alvo.get('nome')}** esquivou da área do ataque."
                        continue
                    vida_area = int(float(alvo.get("vida", 0) or 0))
                    alvo["vida"] = max(0, vida_area - max(0, int(dano_area)))
                    efeito_area = self._aplicar_efeito(alvo, ataque.get("efeito"))
                    mensagem += f"\n🔥 **{alvo.get('nome')}** sofreu **{max(0, int(dano_area))} de dano**."
                    if efeito_area:
                        mensagem += f" Efeito: **{str(efeito_area).title()}**."
            combate["historico"].append(mensagem)
            self._limpar_defesas(combate)
            combate["ataque_pendente"] = None
            combate["fase"] = "ataque"
            combate["ui_stage"] = "result"
            combate["ui_waiting_advance"] = True
            embed = discord.Embed(title="💥 Resultado", description=mensagem, color=discord.Color.red())
            embed.add_field(name="📋 Status", value=self._texto_status(combate["participantes"]), inline=False)
            await self._ui_editar(combate, embed)
            if combate.get("assentamento_duelo") and duelo_pendente:
                await self._finalizar_duelo_assentamento(ctx, atacante, defensor)
                return
            if combate.get("pvp") and not _vivo(defensor):
                combate["aguardando_finalizacao"] = True
                combate["vencedor_id"] = str(atacante.get("id"))
                combate["perdedor_id"] = str(defensor.get("id"))
                combate["fase"] = "finalizacao"
                await self._salvar(combate)
                return
            resultado = self._condicao_vitoria(combate)
            if resultado:
                combate["ui_waiting_advance"] = False
                await self._finalizar(self._ui_context(ctx, combate), motivo="vida", vencedor=atacante, perdedor=defensor)
                return
            await self._salvar(combate)
        except Exception:
            for participante, snapshot in participante_snapshots:
                participante.clear()
                participante.update(snapshot)
            combate["ataque_pendente"] = estado_anterior["ataque_pendente"]
            combate["fase"] = estado_anterior["fase"]
            combate["ui_stage"] = estado_anterior["ui_stage"]
            combate["ui_waiting_advance"] = estado_anterior["ui_waiting_advance"]
            combate["aguardando_finalizacao"] = estado_anterior["aguardando_finalizacao"]
            if estado_anterior["vencedor_id"] is None:
                combate.pop("vencedor_id", None)
            else:
                combate["vencedor_id"] = estado_anterior["vencedor_id"]
            if estado_anterior["perdedor_id"] is None:
                combate.pop("perdedor_id", None)
            else:
                combate["perdedor_id"] = estado_anterior["perdedor_id"]
            combate["historico"] = estado_anterior["historico"]
            if combate.get("ataque_pendente"):
                combate["ataque_pendente"].pop("_resolvendo", None)
            raise
        finally:
            if combate.get("ataque_pendente") is ataque:
                ataque.pop("_resolvendo", None)
    
    async def executar_defesa_jogador(self, ctx, acao, embed=None):
        """Entrada compatível; a resolução de defesa vive no motor canônico."""
        return await self._defesa_jogador(ctx, acao)
    
    async def _limpar_recursos_combate(self, channel_id, combate):
        """Libera recursos locais e invalida a View no Discord sem mascarar falhas."""
        self._embeds_acao.pop(channel_id, None)
        mensagem = combate.get("ui_message")
        if mensagem is None:
            return
        view = self._ui_views.pop(mensagem.id, None)
        if view is not None:
            view.stop()
        getattr(self, "_ui_avancar_locks", {}).pop(mensagem.id, None)
        try:
            await mensagem.edit(view=None)
        except Exception as erro:
            print(f"[LUTA][UI][LIMPEZA][ERRO] {type(erro).__name__}: {erro}")
    
    def _dano_fisico(self, atacante, defensor, ataque):
        if defensor.get("esquiva_ativa"):
            defensor["esquiva_ativa"] = False
            velocidade = float(defensor.get("Velocidade", defensor.get("velocidade", 0)) or 0)
            destreza = float(defensor.get("Destreza", defensor.get("destreza", 0)) or 0)
            if __import__("random").random() < min(0.75, 0.10 + (velocidade + destreza) / 500):
                return 0, "esquivou"
        dano = float(atacante.get("Força", atacante.get("forca", 0)) or 0) + float(atacante.get("Velocidade", atacante.get("velocidade", 0)) or 0)
        dano += float(ataque.get("dano_base", 0) or 0)
        if ataque.get("com_arma"):
            dano += float(atacante.get("dano_arma", 0) or 0)
        if defensor.get("defesa_magica_ativa"):
            dano -= float(defensor.get("defesa_magica_valor", 0) or 0)
            defensor["defesa_magica_ativa"] = False
            defensor["defesa_magica_valor"] = 0
        elif defensor.get("defesa_ativa"):
            defesa_total = float(defensor.get("Força", defensor.get("forca", 0)) or 0) + float(defensor.get("Defesa", defensor.get("defesa", 0)) or 0)
            dano *= 1.0 - min(1.0, max(0.0, defesa_total) / 300.0)
        defensor["defesa_ativa"] = False
        dano = max(0, int(dano))
        combate = self._obter_combate_por_participantes(defensor)
        dano = boss_rules.corrosao(dano, defensor)
        return boss_rules.regras_dano(dano, "atingiu", atacante, defensor, ataque, combate)
    
    def _dano_magia(self, atacante, defensor, ataque):
        if defensor.get("esquiva_ativa"):
            defensor["esquiva_ativa"] = False
            velocidade = float(defensor.get("Velocidade", defensor.get("velocidade", 0)) or 0)
            if __import__("random").random() < min(0.75, 0.10 + velocidade / 500):
                return 0, "esquivou"
        dano = float(atacante.get("Magia", atacante.get("magia", 0)) or 0) + float(atacante.get("Inteligencia", atacante.get("Inteligência", 0)) or 0)
        dano += float(ataque.get("dano_base", 0) or 0)
        if defensor.get("defesa_magica_ativa"):
            dano -= float(defensor.get("defesa_magica_valor", 0) or 0)
            defensor["defesa_magica_ativa"] = False
            defensor["defesa_magica_valor"] = 0
        elif defensor.get("defesa_ativa"):
            dano -= float(defensor.get("Defesa", defensor.get("defesa", 0)) or 0) * 0.5
        defensor["defesa_ativa"] = False
        dano = max(0, int(dano))
        combate = self._obter_combate_por_participantes(defensor)
        dano = boss_rules.corrosao(dano, defensor)
        return boss_rules.regras_dano(dano, "atingiu", atacante, defensor, ataque, combate)
    
    def _aplicar_efeito(self, defensor, efeito):
        if not isinstance(efeito, dict):
            return None
        especial = boss_rules.efeito_especial(defensor, efeito)
        if especial is not None:
            return especial
        nome = str(efeito.get("nome", efeito.get("tipo", ""))).strip().lower()
        if not nome:
            return None
        turnos = max(1, int(float(efeito.get("turnos", efeito.get("duracao", 1)) or 1)))
        valor = int(float(efeito.get("valor", 5) or 5))
        entrada = {"nome": nome, "turnos": turnos, "valor": valor}
        defensor.setdefault("efeitos", []).append(entrada)
        return nome
    
    async def _aplicar_efeitos_inicio(self, ctx, participante):
        combate = self._obter_combate(ctx.channel.id)
        boss_rules.inicio_especial(combate or {}, participante)
        dano_total = 0
        bloqueado = False
        novos = []
        for efeito in list(participante.get("efeitos", []) or []):
            if not isinstance(efeito, dict):
                continue
            nome = str(efeito.get("nome", efeito.get("tipo", ""))).strip().lower()
            valor = max(0, int(float(efeito.get("valor", 5) or 5)))
            if nome in {"veneno", "queimadura", "sangramento"}:
                dano_total += valor
            elif nome == "sangramento_profundo":
                defesa = float(participante.get("Defesa", participante.get("defesa", 0)) or 0) + float(participante.get("Força", participante.get("forca", 0)) or 0)
                dano_total += max(1, int(valor - defesa * 0.5))
            if nome in {"paralisia", "stun", "prisao", "prisão"}:
                bloqueado = True
            turnos = int(float(efeito.get("turnos", 1) or 1)) - 1
            if turnos > 0:
                copia = dict(efeito); copia["turnos"] = turnos; novos.append(copia)
        participante["efeitos"] = novos
        if dano_total:
            participante["vida"] = max(0, int(float(participante.get("vida", 0) or 0)) - dano_total)
            await ctx.send(f"⚠️ **{participante.get('nome')}** sofreu **{dano_total}** de efeitos.")
        return bloqueado
    
    def _obter_combate_por_participantes(self, participante):
        """Busca por identidade do objeto, evitando colisões de IDs entre combates."""
        if participante is None:
            return {}
        for combate in self.combates.values():
            if any(p is participante for p in combate.get("participantes", [])):
                return combate
        return {}
    
    def _limpar_defesas(self, combate):
        for participante in combate.get("participantes", []):
            participante["defesa_ativa"] = False
            participante["esquiva_ativa"] = False
            participante["defesa_magica_ativa"] = False
            participante["defesa_magica_valor"] = 0
    
    async def _recompensar(self, combate):
        """Único cálculo de recompensa; protegido contra aplicação duplicada."""
        if combate.get("recompensa_aplicada"):
            return (int(combate.get("recompensa_xp", 0)), int(combate.get("recompensa_hunos", 0)), int(combate.get("recompensa_tp", 0)))
        if self._condicao_vitoria(combate) != "jogadores" or luta_db.db is None:
            return 0, 0, 0
        monstros = [p for p in combate.get("participantes", [])
                    if p.get("tipo") == "monstro" and not p.get("invocado") and _vivo(p) is False]
        xp_total = sum(int(float(p.get("xp_recompensa", 0) or 0)) for p in monstros)
        tp_total = sum(int(float(p.get("tp_recompensa", p.get("xp_recompensa", 0)) or 0)) for p in monstros)
        hunos_total = sum(int(float(p.get("hunos_recompensa", 0) or 0)) for p in monstros)
        vivos = [p for p in combate.get("participantes", [])
                 if p.get("tipo") == "jogador" and _vivo(p)]
        if not vivos:
            return xp_total, hunos_total, tp_total
        guild_id = str(combate.get("guild_id"))
        for i, jogador in enumerate(vivos):
            xp = xp_total // len(vivos) + (i < xp_total % len(vivos))
            tp = tp_total // len(vivos) + (i < tp_total % len(vivos))
            hunos = hunos_total // len(vivos) + (i < hunos_total % len(vivos))
            filtro = {"ID": str(jogador.get("id")), "guild_id": guild_id}
            await luta_db.run_db(luta_db.db["Jogadores"].update_one, filtro, {"$inc": {"XP": int(xp), "TP": int(tp)}})
            await luta_db.run_db(luta_db.db["Hunos"].update_one, filtro, {"$inc": {"carteira": int(hunos)}}, upsert=True)
        combate["recompensa_aplicada"] = True
        combate["recompensa_xp"] = xp_total
        combate["recompensa_hunos"] = hunos_total
        combate["recompensa_tp"] = tp_total
        return xp_total, hunos_total, tp_total
    
    async def _finalizar(self, ctx, motivo="vida", vencedor=None, perdedor=None):
        combate = self._obter_combate(ctx.channel.id)
        if not combate:
            return
        estado_anterior = {
            "ativo": combate.get("ativo", True), "fase": combate.get("fase", "ataque"),
            "ui_stage": combate.get("ui_stage", "turn"), "ui_waiting_advance": combate.get("ui_waiting_advance", False),
            "ataque_pendente": combate.get("ataque_pendente"),
        }
        resultado = self._condicao_vitoria(combate)
        if resultado is None and motivo in {"vida", "efeitos"}:
            combate["ativo"] = True
            combate["fase"] = "ataque"
            combate["ataque_pendente"] = None
            combate["ui_waiting_advance"] = False
            await self._proximo_turno(ctx)
            return
        combate["ativo"] = False
        combate["fase"] = "finalizado"
        try:
            await self._salvar(combate)
            xp = hunos = tp = 0
            if not combate.get("pvp") and resultado == "jogadores":
                xp, hunos, tp = await self._recompensar(combate)
            descricao = (
                f"💀 **{vencedor.get('nome')}** finalizou **{perdedor.get('nome')}** ({motivo})."
                if combate.get("pvp") and vencedor and perdedor else
                "🏆 Os jogadores venceram o combate!" if resultado == "jogadores" else
                "💀 Os jogadores foram derrotados." if resultado == "inimigos" else
                "⚖️ O combate terminou em empate."
            )
            embed = discord.Embed(title="⚔️ Combate Finalizado", description=descricao, color=discord.Color.green() if resultado == "jogadores" else discord.Color.red())
            embed.add_field(name="🎁 Recompensas", value=f"✨ XP: **{xp}**\n🔷 TP: **{tp}**\n💰 Hunos: **{hunos}**", inline=False)
            embed.add_field(name="📋 Status", value=self._texto_status(combate["participantes"]), inline=False)
            await ctx.send(embed=embed)
            await self._limpar_recursos_combate(ctx.channel.id, combate)
            self.combates.pop(ctx.channel.id, None)
        except Exception:
            combate.update(estado_anterior)
            if combate.get("ativo"):
                combate["fase"] = "defesa" if combate.get("ataque_pendente") else estado_anterior["fase"]
                combate["ui_stage"] = "attack" if combate.get("ataque_pendente") else estado_anterior["ui_stage"]
            try:
                await self._salvar(combate)
            except Exception as save_erro:
                print(f"[LUTA][ROLLBACK][ERRO] {type(save_erro).__name__}: {save_erro}")
            raise
    
    async def _abandonar_combate(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return False
        snapshot = {"ativo": combate.get("ativo", True), "fase": combate.get("fase", "ataque"),
                    "ataque_pendente": copy.deepcopy(combate.get("ataque_pendente")),
                    "ui_stage": combate.get("ui_stage", "turn")}
        try:
            combate["ativo"] = False
            combate["fase"] = "finalizado"
            combate["ataque_pendente"] = None
            self._limpar_defesas(combate)
            await self._salvar(combate)
            jogadores = [p for p in combate.get("participantes", []) if p.get("tipo") == "jogador"]
            await self._marcar_combate(jogadores, str(combate.get("guild_id")), "ativo")
            await self._limpar_recursos_combate(ctx.channel.id, combate)
            self.combates.pop(ctx.channel.id, None)
            return True
        except Exception:
            combate.update(snapshot)
            raise
    
    async def _finalizar_pvp(self, ctx, motivo):
        """Finaliza PvP somente quando existe uma vitória pendente válida."""
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            await ctx.send("❌ Não há combate PvP ativo.")
            return
        if not combate.get("pvp") or not combate.get("aguardando_finalizacao"):
            await ctx.send("❌ Este combate não está aguardando finalização PvP.")
            return
        vencedor = self._por_id(combate, combate.get("vencedor_id"))
        perdedor = self._por_id(combate, combate.get("perdedor_id"))
        if not vencedor or not perdedor:
            raise RuntimeError("finalização PvP sem vencedor ou perdedor válido")
        if str(vencedor.get("id")) != str(getattr(ctx.author, "id", "")):
            await ctx.send("❌ Apenas o vencedor do turno decisivo pode finalizar este PvP.")
            return
        if motivo not in {"morte", "desmaio"}:
            raise ValueError("motivo de finalização PvP inválido")
        if motivo == "morte":
            perdedor["vida"] = 0
        else:
            perdedor["vida"] = max(1, int(float(perdedor.get("vida", 0) or 0)))
        combate["aguardando_finalizacao"] = False
        combate["fase"] = "finalizacao"
        await self._finalizar(ctx, motivo=motivo, vencedor=vencedor, perdedor=perdedor)
    
    async def avancar(self, interaction: discord.Interaction):
        channel_id = interaction.channel.id
        lock = self._lock(channel_id)
        if lock.locked():
            msg = "⏳ Aguarde a ação de combate anterior terminar."
            if not interaction.response.is_done(): await interaction.response.send_message(msg, ephemeral=True)
            else: await interaction.followup.send(msg, ephemeral=True)
            return
        async with lock:
            return await self._avancar_locked(interaction)
    
    async def _avancar_locked(self, interaction: discord.Interaction):
        combate = self._obter_combate(interaction.channel.id)
        if not combate or not combate.get("ativo"):
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Não há combate ativo neste canal.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Não há combate ativo neste canal.", ephemeral=True)
            return
        mensagem = combate.get("ui_message")
        if mensagem is None or interaction.message is None or interaction.message.id != mensagem.id:
            msg = "❌ Esta tela não pertence ao combate atual."
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
            return
        if combate.get("ui_owner_id") is not None and str(combate["ui_owner_id"]) != str(interaction.user.id):
            msg = "❌ Apenas o jogador deste combate pode avançar a tela."
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
            return
        if not interaction.response.is_done():
            await interaction.response.defer()
        self._normalizar_estado(combate)
        try:
            stage = combate.get("ui_stage", "attributes")
            if combate.get("ataque_pendente"):
                await self._mostrar_ataque_ui(combate)
                return
            if stage == "attributes":
                combate["ui_stage"] = "velocity"
                await self._ui_editar(combate, self._embed_velocidade(combate))
            elif stage == "velocity":
                if (self._obter_atacante(combate) or {}).get("tipo") == "monstro":
                    await self._criar_ataque_monstro_ui(combate)
                else:
                    combate["ui_stage"] = "player_action"
                    await self._ui_editar(combate, self._embed_aguarde_jogador(combate))
            elif stage == "attack":
                defensor = self._obter_defensor(combate)
                if defensor and defensor.get("tipo") == "monstro":
                    self._limpar_defesas(combate)
                    await self._resolver_ataque(self._ui_context(interaction, combate))
                else:
                    combate["ui_stage"] = "defense_action"
                    await self._ui_editar(combate, self._embed_defesa(combate))
            elif stage == "result":
                combate["ui_waiting_advance"] = False
                await self._proximo_turno(interaction)
            elif stage == "turn":
                atacante = self._obter_atacante(combate)
                if atacante and atacante.get("tipo") == "monstro":
                    await self._criar_ataque_monstro_ui(combate)
                else:
                    combate["ui_stage"] = "player_action"
                    await self._ui_editar(combate, self._embed_aguarde_jogador(combate))
            elif stage == "player_action":
                await self._ui_editar(combate, self._embed_aguarde_jogador(combate))
            elif stage == "defense_action":
                await self._ui_editar(combate, self._embed_defesa(combate))
            elif stage == "resolving":
                await interaction.followup.send("❌ A defesa está sendo processada. Aguarde o resultado.", ephemeral=True)
        except Exception as erro:
            combate["ui_waiting_advance"] = False
            if combate.get("ataque_pendente"):
                combate["fase"] = "defesa"
                combate["ui_stage"] = "attack"
            else:
                combate["fase"] = "ataque"
                combate["ui_stage"] = "turn"
            print(f"[LUTA][AVANCAR][ERRO] {type(erro).__name__}: {erro}")
            msg = f"❌ Não foi possível avançar: `{type(erro).__name__}`. O estado foi preservado."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
    async def _proximo_turno(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return
        if combate.get("ataque_pendente"):
            combate["fase"] = "defesa"
            combate["ui_stage"] = "attack"
            return
        self._normalizar_estado(combate)
        if combate.get("ui_message"):
            if combate.get("ui_waiting_advance"):
                return
            resultado = self._condicao_vitoria(combate)
            if resultado:
                await self._finalizar(self._ui_context(ctx, combate), motivo="vida")
                return
            boss_rules.preparar_proximo_turno(combate)
            atual_id = combate.get("_turno_participante_id")
            expirados = {str(x) for x in combate.pop("_participantes_expirados", set())}
            if expirados:
                combate["participantes"] = [p for p in combate.get("participantes", []) if str(p.get("id")) not in expirados]
            if not combate.get("participantes"):
                await self._finalizar(self._ui_context(ctx, combate), motivo="vida")
                return
            if atual_id is not None:
                atual_index = next((i for i,p in enumerate(combate["participantes"]) if str(p.get("id")) == str(atual_id)), -1)
            else:
                atual_index = int(combate.get("turno", 0)) % len(combate["participantes"])
            proximo = self._proximo_indice(combate, atual_index if atual_index >= 0 else -1)
            if proximo is None:
                await self._finalizar(self._ui_context(ctx, combate), motivo="vida")
                return
            combate["turno"] = proximo
            combate["_turno_participante_id"] = combate["participantes"][proximo].get("id")
            combate["numero_turno"] = int(combate.get("numero_turno", 1)) + 1
            combate["fase"] = "ataque"
            combate["ataque_pendente"] = None
            combate["ui_stage"] = "turn"
            combate["ui_waiting_advance"] = False
            self._limpar_defesas(combate)
            atacante = self._obter_atacante(combate)
            if not atacante:
                await self._finalizar(self._ui_context(ctx, combate), motivo="vida")
                return
            ui_ctx = self._ui_context(ctx, combate)
            bloqueado = await self._aplicar_efeitos_inicio(ui_ctx, atacante)
            if not _vivo(atacante):
                await self._salvar(combate)
                await self._finalizar(ui_ctx, motivo="efeitos")
                return
            if bloqueado:
                combate["ui_stage"] = "result"
                combate["ui_waiting_advance"] = True
                await self._ui_editar(combate, self._acao_embed(atacante=atacante, defensor=atacante,
                    nome="Stun", emoji="💫", turno=combate.get("numero_turno",1), dano=0,
                    mana=atacante.get("mana",0), descricao=f"**{atacante.get('nome')}** perdeu este turno."))
                return
            await self._ui_editar(combate, self._embed_turno_monstro(combate) if atacante.get("tipo")=="monstro" else self._embed_aguarde_jogador(combate))
            return
        return await super()._proximo_turno(ctx)

# Comandos públicos registrados pelo próprio arquivo.
"""Comandos públicos do sistema de luta com interface Moon Tensura padronizada."""





FOOTER = "Tensura Moon - Korczak Technologies!"


def _vida(p):
    p = p or {}
    try:
        vida = int(float(p.get("vida", 0) or 0))
        maxima = int(float(p.get("vida_maxima", vida) or vida or 1))
    except (TypeError, ValueError):
        vida, maxima = 0, 1
    return f"{max(0, vida)}/{max(1, maxima)}"


def _mana(p):
    try:
        return str(int(float((p or {}).get("mana", 0) or 0)))
    except (TypeError, ValueError):
        return "0"


def _valor_int(v, padrao=0):
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return int(padrao)


def _efeito_texto(efeito):
    if isinstance(efeito, dict):
        return str(efeito.get("nome", efeito.get("tipo", "Nenhum")) or "Nenhum")
    return str(efeito or "Nenhum")


def _embed_erro(titulo: str, descricao: str) -> discord.Embed:
    return painel(ataque="resultado", efeito="Erro", alvo="-", turno="-", oponente="-", extra=f"**❌ {titulo}:** {descricao}", cor=discord.Color.red())


def _embed_acao(titulo, atacante, defensor, turno, *, dano=0, mana=0, efeito="Nenhum", extra="", cor=None):
    return painel(
        atacante=atacante.get("nome", "User"), ataque=titulo, vida=_vida(atacante), mana=mana,
        dano=dano, efeito=efeito, alvo=defensor.get("nome", "-"), turno=turno,
        oponente=defensor, vida_oponente=_vida(defensor), extra=extra, cor=cor or discord.Color.blurple(),
    )


async def _baixar_imagem_monstro(url):
    if not url:
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as sessao:
            async with sessao.get(url) as resposta:
                if resposta.status != 200:
                    return None
                dados = await resposta.read()
                if not dados:
                    return None
        return discord.File(io.BytesIO(dados), filename="monstro.webp")
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError):
        return None


def _kwargs_embed(embed, arquivo=None):
    kwargs = {"embed": embed}
    if arquivo is not None:
        kwargs["file"] = arquivo
    return kwargs


async def _cog(ctx) -> Optional[Luta]:
    cog = ctx.bot.get_cog("Luta")
    if cog is None:
        await ctx.send(embed=_embed_erro("Combate", "O sistema de combate não foi carregado."))
    return cog


async def luta(ctx):
    embed = painel(
        atacante=ctx.author.display_name, ataque="Comandos", vida="-", mana="-", dano="-", efeito="Ajuda",
        alvo="-", turno="-", oponente="-", vida_oponente="-",
        extra=("**`!luta monstros`** — lista os monstros\n"
               "**`!luta pve <monstro>`** — inicia PvE\n"
               "**`!luta pvp @jogador`** — inicia PvP\n"
               "**`!soco` · `!chute` · `!defesa` · `!esquiva` · `!fugir`**"),
        cor=discord.Color.blurple(),
    )
    await ctx.send(embed=embed)


async def monstros(ctx):
    if not luta_db.MONSTROS:
        await ctx.send(embed=_embed_erro("Monstros", "Nenhum monstro foi carregado."))
        return
    itens = list(luta_db.MONSTROS.items())
    for inicio in range(0, len(itens), 10):
        linhas = []
        for monstro_id, dados in itens[inicio:inicio + 10]:
            linhas.append(
                f"**{dados.get('emoji', '👹')} {dados.get('nome', monstro_id)}** — "
                f"**ID:** `{monstro_id}` | **❤️ Vida:** {dados.get('vida_base', 0)} | "
                f"**⚔️ Dano:** {dados.get('dano_base', 0)} | **✨ XP:** {dados.get('xp_recompensa', 0)} | "
                f"**💰 Hunos:** {dados.get('hunos_recompensa', 0)} | **🔷 TP:** {dados.get('tp_recompensa', 0)}"
            )
        embed = painel(
            atacante=ctx.author.display_name, ataque="Lista de monstros", vida="-", mana="-", dano="-",
            efeito="Consulta", alvo="Todos", turno="-", oponente="Monstros", vida_oponente="-",
            extra="\n".join(linhas), cor=discord.Color.dark_red(),
        )
        await ctx.send(embed=embed)


async def pve(ctx, *, monstro_tipo: str = ""):
    if ctx.guild is None:
        await ctx.send(embed=_embed_erro("PvE", "Este comando só funciona em servidor."))
        return
    monstro_tipo = str(monstro_tipo or "").strip()
    if not monstro_tipo:
        await ctx.send(embed=_embed_erro("PvE", "Informe o monstro. Exemplo: `!luta pve slime`"))
        return
    cog = await _cog(ctx)
    if cog is None:
        return
    async with cog._lock(ctx.channel.id):
        if cog._combate_ativo(ctx.channel.id):
            await ctx.send(embed=_embed_erro("PvE", "Já existe um combate ativo neste canal."))
            return
        monstro_id = cog._encontrar_monstro(monstro_tipo)
        if not monstro_id:
            await ctx.send(embed=_embed_erro("PvE", f"Monstro `{monstro_tipo}` não encontrado. Use `!luta monstros`."))
            return
        guild_id, user_id = str(ctx.guild.id), str(ctx.author.id)
        verificacao = await run_db(luta_db.pode_lutar, user_id, guild_id)
        if not verificacao.get("pode"):
            await ctx.send(embed=_embed_erro("PvE", verificacao.get("mensagem", "Você não pode lutar.")))
            return
        jogador = await _criar_participante(user_id, guild_id)
        if not jogador:
            await ctx.send(embed=_embed_erro("PvE", "Você precisa ter um personagem registrado para lutar."))
            return
        jogador["nome"] = ctx.author.display_name
        reserva = await run_db(luta_db.iniciar_cooldown_monstro, user_id, guild_id, str(monstro_id))
        if not reserva.get("sucesso"):
            segundos = max(0, _valor_int(reserva.get("segundos_restantes")))
            horas, resto = divmod(segundos, 3600)
            minutos = resto // 60
            restante = f"{horas}h {minutos}min" if horas else f"{max(1, minutos)}min"
            nome = luta_db.MONSTROS.get(str(monstro_id), {}).get("nome", str(monstro_id))
            await ctx.send(embed=_embed_erro("PvE", f"Você já lutou contra **{nome}**. Tente novamente em **{restante}**."))
            return
        fim_cooldown = reserva.get("fim")
        try:
            monstro = await run_db(luta_db.criar_monstro, str(monstro_id), 1)
            if not monstro:
                raise RuntimeError("criar_monstro retornou vazio")
            combate = cog._novo_combate([jogador, monstro], guild_id)
            cog.combates[ctx.channel.id] = combate
            await cog._marcar_combate([jogador], guild_id, "ativo_combate")
            atacante = cog._obter_atacante(combate)
            defensor = cog._obter_defensor(combate)
            if not atacante or not defensor:
                raise RuntimeError("combate criado sem atacante ou defensor")
            dados = luta_db.MONSTROS.get(str(monstro_id), {})
            atributos = dados.get("atributos_base", {}) or {}
            linhas = [
                f"**👤 Jogador:** {ctx.author.display_name}", f"**👹 Monstro:** {defensor.get('nome', monstro_id)}",
                f"**❤️ Vida:** {_vida(defensor)}", f"**⚔️ Dano base:** {dados.get('dano_base', 0)}",
                f"**🎚️ Nível:** {defensor.get('nivel', 1)}", "", "**📊 ATRIBUTOS DO MONSTRO**",
                f"**💪 Força:** {atributos.get('Força', 0)}", f"**🛡️ Defesa:** {atributos.get('Defesa', 0)}",
                f"**❤️ Vitalidade:** {atributos.get('Vitalidade', 0)}", f"**⚡ Velocidade:** {atributos.get('Velocidade', 0)}",
                f"**🎯 Destreza:** {atributos.get('Destreza', 0)}", f"**✨ Magia:** {atributos.get('Magia', 0)}",
                f"**🍀 Sorte:** {atributos.get('Sorte', 0)}", f"**🧠 Inteligência:** {atributos.get('Inteligencia', atributos.get('Inteligência', 0))}", "",
                f"**👊 Golpes:** {', '.join(str(g) for g in dados.get('golpes', [])) or 'Nenhum'}",
                f"**✨ XP:** {dados.get('xp_recompensa', 0)} | **💰 Hunos:** {dados.get('hunos_recompensa', 0)} | **🔷 TP:** {dados.get('tp_recompensa', 0)}",
            ]
            panel = painel(
                atacante=ctx.author.display_name, ataque="Apresentação do monstro", vida=_vida(atacante), mana=_mana(atacante),
                dano=dados.get("dano_base", 0), efeito="Apresentação", alvo=defensor.get("nome", monstro_id),
                turno=combate.get("numero_turno", 1), oponente=defensor, vida_oponente=_vida(defensor),
                extra="\n".join(linhas), cor=discord.Color.red(),
            )
            url = imagem_monstro(monstro)
            arquivo = await _baixar_imagem_monstro(url)
            if arquivo is not None:
                filename = arquivo.filename
                panel.set_image(url=f"attachment://{filename}")
            elif url:
                panel.set_image(url=url)
            cog.preparar_embed(ctx, panel, arquivo=arquivo)
            await cog._mostrar_inicio(ctx)
        except Exception:
            try:
                if "combate" in locals():
                    await cog._marcar_combate([jogador], guild_id, "ativo")
            except Exception as erro_estado:
                print("[LUTA][PVE][ROLLBACK][ERRO]", type(erro_estado).__name__, erro_estado)
            if fim_cooldown is not None:
                try:
                    await run_db(luta_db.cancelar_cooldown_monstro, user_id, guild_id, str(monstro_id), fim_cooldown)
                except Exception as erro:
                    print(f"[LUTA][PVE][COOLDOWN][ERRO] {type(erro).__name__}: {erro}")
            await cog._limpar_recursos_combate(ctx.channel.id, combate if "combate" in locals() else {})
            cog.combates.pop(ctx.channel.id, None)
            await ctx.send(embed=_embed_erro("PvE", "Não foi possível iniciar o combate. A reserva foi desfeita."))
            return


async def pvp(ctx, membro: Optional[discord.Member] = None):
    if ctx.guild is None:
        await ctx.send(embed=_embed_erro("PvP", "Este comando só funciona em servidor."))
        return
    if membro is None:
        membro = next((m for m in ctx.message.mentions if not m.bot and m.id != ctx.author.id), None)
    if membro is None or membro.bot or membro.id == ctx.author.id:
        await ctx.send(embed=_embed_erro("PvP", "Mencione um membro válido. Exemplo: `!luta pvp @jogador`"))
        return
    cog = await _cog(ctx)
    if cog is None:
        return
    async with cog._lock(ctx.channel.id):
        if cog._combate_ativo(ctx.channel.id):
            await ctx.send(embed=_embed_erro("PvP", "Já existe um combate ativo neste canal."))
            return
        guild_id = str(ctx.guild.id)
        jogadores = []
        for usuario in (ctx.author, membro):
            verificacao = await run_db(luta_db.pode_lutar, str(usuario.id), guild_id)
            if not verificacao.get("pode"):
                await ctx.send(embed=_embed_erro("PvP", f"{usuario.display_name}: {verificacao.get('mensagem', 'não pode lutar.') }"))
                return
            jogador = await _criar_participante(usuario.id, guild_id)
            if not jogador:
                await ctx.send(embed=_embed_erro("PvP", f"{usuario.display_name} não possui personagem registrado."))
                return
            jogador["nome"] = usuario.display_name
            jogadores.append(jogador)
        combate = cog._novo_combate(jogadores, guild_id, pvp=True)
        cog.combates[ctx.channel.id] = combate
        try:
            await cog._marcar_combate(jogadores, guild_id, "ativo_combate")
        except Exception:
            cog.combates.pop(ctx.channel.id, None)
            await cog._marcar_combate(jogadores, guild_id, "ativo")
            raise
        atacante = cog._obter_atacante(combate)
        defensor = cog._obter_defensor(combate)
        if not atacante or not defensor:
            cog.combates.pop(ctx.channel.id, None)
            await cog._marcar_combate(jogadores, guild_id, "ativo")
            await ctx.send(embed=_embed_erro("PvP", "Não foi possível montar os participantes do combate."))
            return
        embed = _embed_acao("⚔️ PvP", atacante, defensor, combate.get("numero_turno", 1), extra="**Duelo PvP iniciado.**", cor=discord.Color.red())
        try:
            cog.preparar_embed(ctx, embed)
            await cog._mostrar_inicio(ctx)
        except Exception as erro:
            await cog._marcar_combate(jogadores, guild_id, "ativo")
            await cog._limpar_recursos_combate(ctx.channel.id, combate)
            cog.combates.pop(ctx.channel.id, None)
            print(f"[LUTA][PVP][ROLLBACK] {type(erro).__name__}: {erro}")
            await ctx.send(embed=_embed_erro("PvP", "Não foi possível abrir a tela do combate. O duelo foi desfeito."))
            return


async def _ataque(ctx, chave, titulo):
    cog = await _cog(ctx)
    if cog is None:
        return
    async with cog._lock(ctx.channel.id):
        combate = cog._obter_combate(ctx.channel.id)
        atacante = cog._obter_atacante(combate) if combate else {"nome": ctx.author.display_name}
        defensor = cog._obter_defensor(combate) if combate else {"nome": "-"}
        golpe = luta_db.GOLPES.get(chave, {})
        embed = _embed_acao(
            titulo, atacante, defensor, combate.get("numero_turno", 1) if combate else 1,
            dano=_valor_int(golpe.get("dano_base")), mana=_valor_int(golpe.get("custo_mana")),
            efeito=_efeito_texto(golpe.get("efeito")), extra=golpe.get("descricao", "Ação de combate."),
        )
        await cog.executar_ataque_jogador(ctx, chave, embed=embed)


async def soco(ctx):
    await _ataque(ctx, "soco", "👊 Soco")


async def chute(ctx):
    await _ataque(ctx, "chute", "🦶 Chute")


async def defesa(ctx):
    cog = await _cog(ctx)
    if cog is None:
        return
    async with cog._lock(ctx.channel.id):
        combate = cog._obter_combate(ctx.channel.id)
        atacante = cog._obter_atacante(combate) if combate else {"nome": ctx.author.display_name}
        defensor = cog._obter_defensor(combate) if combate else atacante
        golpe = luta_db.GOLPES.get("defesa", {})
        embed = _embed_acao("🛡️ Defesa", defensor, atacante, combate.get("numero_turno", 1) if combate else 1, mana=_valor_int(golpe.get("custo_mana")), efeito="Redução de dano", extra=golpe.get("descricao", "Reduz o dano do próximo ataque."))
        await cog.executar_defesa_jogador(ctx, "defesa", embed=embed)



async def esquiva(ctx):
    cog = await _cog(ctx)
    if cog is None:
        return
    async with cog._lock(ctx.channel.id):
        combate = cog._obter_combate(ctx.channel.id)
        atacante = cog._obter_atacante(combate) if combate else {"nome": ctx.author.display_name}
        defensor = cog._obter_defensor(combate) if combate else atacante
        golpe = luta_db.GOLPES.get("esquiva", {})
        embed = _embed_acao("💨 Esquiva", defensor, atacante, combate.get("numero_turno", 1) if combate else 1, mana=_valor_int(golpe.get("custo_mana")), efeito="Tentativa de esquiva", extra=golpe.get("descricao", "Tenta desviar do próximo ataque."))
        await cog.executar_defesa_jogador(ctx, "esquiva", embed=embed)



async def fugir(ctx):
    cog = await _cog(ctx)
    if cog is None:
        return
    async with cog._lock(ctx.channel.id):
        combate = cog._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            await ctx.send(embed=_embed_erro("Fuga", "Você não está em combate."))
            return
        jogador = cog._participante(combate, str(ctx.author.id))
        if not jogador or jogador.get("tipo") != "jogador":
            await ctx.send(embed=_embed_erro("Fuga", "Você não participa deste combate."))
            return
        sucesso = random.random() < (0.15 if not combate.get("pvp") else 0.10)
        embed = painel(
            atacante=ctx.author.display_name, ataque="resultado", vida=_vida(jogador), mana=_mana(jogador), dano="-",
            efeito="Fuga", alvo="Combate", turno=combate.get("numero_turno", 1), oponente="-", vida_oponente="-",
            extra=f"**{'🏃 Fuga realizada com sucesso!' if sucesso else '❌ Não conseguiu fugir do combate.'}**",
            cor=discord.Color.green() if sucesso else discord.Color.orange(),
        )
        if not sucesso:
            await ctx.send(embed=embed)
            return
        try:
            await cog._abandonar_combate(ctx)
        except Exception as erro:
            print(f"[LUTA][FUGA][ERRO] {type(erro).__name__}: {erro}")
            await ctx.send(embed=_embed_erro("Fuga", "Não foi possível concluir a fuga; o combate foi preservado."))
            return
        await ctx.send(embed=embed)


async def matar(ctx):
    cog = await _cog(ctx)
    if cog is None:
        return
    async with cog._lock(ctx.channel.id):
        await cog._finalizar_pvp(ctx, "morte")



async def desmaiar(ctx):
    cog = await _cog(ctx)
    if cog is None:
        return
    async with cog._lock(ctx.channel.id):
        await cog._finalizar_pvp(ctx, "desmaio")



def _comando(callback, nome, **kwargs):
    return commands.Command(callback, name=nome, **kwargs)


async def setup(bot):
    cog = bot.get_cog("Luta")
    if cog is None:
        cog = Luta(bot)
        await bot.add_cog(cog)
    for nome in (
        "luta", "fight", "combate", "soco", "chute", "defesa", "defender", "def", "shield", "block", "bloquear", "bloqueio",
        "esquiva", "esquivar", "desviar", "dodge", "desvio", "fugir", "fuga", "escape", "escapar", "run", "matar", "desmaiar",
    ):
        bot.remove_command(nome)
    grupo = commands.Group(luta, name="luta", aliases=["fight", "combate"], invoke_without_command=True, help="Sistema de combate.")
    grupo.add_command(_comando(monstros, "monstros", help="Lista os monstros disponíveis."))
    grupo.add_command(_comando(pve, "pve", help="Inicia um combate PvE."))
    grupo.add_command(_comando(pvp, "pvp", help="Inicia um combate PvP."))
    bot.add_command(grupo)
    comandos = (
        (soco, "soco", {}), (chute, "chute", {}),
        (defesa, "defesa", {"aliases": ["defender", "def", "shield", "block", "bloquear", "bloqueio"]}),
        (esquiva, "esquiva", {"aliases": ["esquivar", "desviar", "dodge", "desvio"]}),
        (fugir, "fugir", {"aliases": ["fuga", "escape", "escapar", "run"]}),
        (matar, "matar", {}), (desmaiar, "desmaiar", {}),
    )
    for callback, nome, opcoes in comandos:
        bot.add_command(_comando(callback, nome, **opcoes))
    comando_luta = bot.get_command("luta")
    print("[LUTA][REGISTRO]", f"luta={bool(comando_luta)}", f"monstros={bool(comando_luta and comando_luta.get_command('monstros'))}", f"pve={bool(comando_luta and comando_luta.get_command('pve'))}", "arquitetura=embed-no-comando")


__all__ = ["Luta", "setup", "_criar_participante"]
