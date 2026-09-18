"""Implementação final das invariantes do combate.

Esta classe é a que os comandos registram no Cog. Ela herda o motor já
balanceado e centraliza alvo, ataque pendente, defesa, UI e avanço.
"""
from __future__ import annotations

import asyncio
import discord
from database.python import luta as luta_db

from .sistemas_luta import Luta as _BaseLuta, _UIContext, _AvancarView, _vivo


class Luta(_BaseLuta):
    def _por_id(self, combate, participante_id):
        if participante_id is None:
            return None
        return next((p for p in combate.get("participantes", [])
                     if str(p.get("id")) == str(participante_id)), None)

    def _normalizar_estado(self, combate):
        combate.setdefault("participantes", [])
        combate.setdefault("historico", [])
        combate.setdefault("ataque_pendente", None)
        combate.setdefault("turno", 0)
        combate.setdefault("numero_turno", 1)
        combate.setdefault("fase", "ataque")
        combate.setdefault("ativo", True)
        combate.setdefault("ui_waiting_advance", False)
        if combate["participantes"]:
            combate["turno"] = int(combate.get("turno", 0)) % len(combate["participantes"])
        combate["numero_turno"] = max(1, int(combate.get("numero_turno", 1)))
        ataque = combate.get("ataque_pendente")
        if ataque:
            if not self._por_id(combate, ataque.get("atacante_id")) or not self._por_id(combate, ataque.get("defensor_id")):
                raise RuntimeError("ataque pendente aponta para participante inexistente")
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
            return participantes[atual]
        for passo in range(1, len(participantes) + 1):
            indice = (atual + passo) % len(participantes)
            if _vivo(participantes[indice]):
                combate["turno"] = indice
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
        self._normalizar_estado(combate)
        existente = combate.get("ataque_pendente")
        if existente:
            if (str(existente.get("atacante_id")) != str(atacante.get("id")) or
                    str(existente.get("defensor_id")) != str(defensor.get("id"))):
                raise RuntimeError("tentativa de substituir ataque pendente por outro alvo")
            combate["fase"] = "defesa"
            return existente
        if not atacante or not defensor or not _vivo(atacante) or not _vivo(defensor):
            raise RuntimeError("ataque criado com participante inválido ou derrotado")
        ataque = {"tipo": tipo, "nome": dados.pop("nome", "⚔️ Ataque"),
                  "atacante_id": atacante.get("id"), "defensor_id": defensor.get("id"), **dados}
        combate["ataque_pendente"] = ataque
        combate["fase"] = "defesa"
        combate["ui_waiting_advance"] = False
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
        golpes = [luta_db.GOLPES[i] for i in (atacante.get("golpes") or []) if i in luta_db.GOLPES]
        if not golpes:
            raise RuntimeError("monstro sem golpe válido")
        golpe = random.choice(golpes)
        ataque = self._criar_ataque(combate, golpe.get("tipo", "fisico"), atacante, defensor,
            nome=golpe.get("nome", "Ataque"), dano_base=float(golpe.get("dano_base", atacante.get("dano_base", 0)) or 0),
            mana_base=float(golpe.get("custo_mana", 0) or 0), com_arma=bool(golpe.get("com_arma", False)),
            efeito=golpe.get("efeito", {}) or {})
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
        ataque["_resolvendo"] = True
        try:
            await super()._resolver_ataque(ctx)
        except Exception:
            if combate.get("ataque_pendente") is ataque and combate.get("ativo"):
                combate["fase"] = "defesa"
                combate["ui_stage"] = "defense_action"
                combate["ui_waiting_advance"] = False
            raise
        finally:
            if combate.get("ataque_pendente") is ataque:
                ataque.pop("_resolvendo", None)

    async def executar_defesa_jogador(self, ctx, acao, embed=None):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            await ctx.send("❌ Não há combate ativo.")
            return
        ataque = combate.get("ataque_pendente")
        if combate.get("fase") != "defesa" or not ataque:
            await self._ui_context(ctx, combate).send("❌ Não há ataque pendente para defender.", _luta_error=True)
            return
        defensor = self._obter_defensor(combate)
        if not defensor or str(defensor.get("id")) != str(ctx.author.id):
            nome = defensor.get("nome", "outro jogador") if defensor else "outro jogador"
            await self._ui_context(ctx, combate).send(f"❌ É **{nome}** quem deve defender este ataque.", _luta_error=True)
            return
        for participante in combate.get("participantes", []):
            participante["defesa_ativa"] = False
            participante["esquiva_ativa"] = False
        defensor["defesa_ativa"] = acao == "defesa"
        defensor["esquiva_ativa"] = acao == "esquiva"
        combate["ui_stage"] = "resolving"
        combate["ui_waiting_advance"] = False
        try:
            await self._resolver_ataque(self._ui_context(ctx, combate))
        except Exception as erro:
            for participante in combate.get("participantes", []):
                participante["defesa_ativa"] = False
                participante["esquiva_ativa"] = False
            if combate.get("ataque_pendente") is ataque and combate.get("ativo"):
                combate["fase"] = "defesa"
                combate["ui_stage"] = "defense_action"
                await self._ui_context(ctx, combate).send(f"❌ Erro ao resolver a defesa: `{type(erro).__name__}: {erro}`.", _luta_error=True)
            return

    async def _limpar_recursos_combate(self, channel_id, combate):
        self._embeds_acao.pop(channel_id, None)
        mensagem = combate.get("ui_message")
        if mensagem is not None:
            self._ui_views.pop(mensagem.id, None)
            getattr(self, "_ui_avancar_locks", {}).pop(mensagem.id, None)

    async def _recompensar(self, combate):
        """Único cálculo de recompensa: XP, TP e Hunos dos monstros derrotados."""
        if self._condicao_vitoria(combate) != "jogadores" or luta_db.db is None:
            return 0, 0
        monstros = [p for p in combate.get("participantes", [])
                    if p.get("tipo") == "monstro" and not p.get("invocado") and _vivo(p) is False]
        xp_total = sum(int(float(p.get("xp_recompensa", 0) or 0)) for p in monstros)
        tp_total = sum(int(float(p.get("tp_recompensa", p.get("xp_recompensa", 0)) or 0)) for p in monstros)
        hunos_total = sum(int(float(p.get("hunos_recompensa", 0) or 0)) for p in monstros)
        vivos = [p for p in combate.get("participantes", [])
                 if p.get("tipo") == "jogador" and _vivo(p)]
        if not vivos:
            return xp_total, hunos_total
        guild_id = str(combate.get("guild_id"))
        for i, jogador in enumerate(vivos):
            xp = xp_total // len(vivos) + (i < xp_total % len(vivos))
            tp = tp_total // len(vivos) + (i < tp_total % len(vivos))
            hunos = hunos_total // len(vivos) + (i < hunos_total % len(vivos))
            filtro = {"ID": str(jogador.get("id")), "guild_id": guild_id}
            await luta_db.run_db(luta_db.db["Jogadores"].update_one, filtro, {"$inc": {"XP": int(xp), "TP": int(tp)}})
            await luta_db.run_db(luta_db.db["Hunos"].update_one, filtro, {"$inc": {"carteira": int(hunos)}}, upsert=True)
        return xp_total, hunos_total

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
            return await super().avancar(interaction)
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
                    defensor["defesa_ativa"] = False
                    defensor["esquiva_ativa"] = False
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


async def _callback_avancar_seguro(self, interaction: discord.Interaction):
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


_AvancarView._callback = _callback_avancar_seguro
