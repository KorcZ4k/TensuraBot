"""Camada única de invariantes do combate.

A classe abaixo é a classe efetivamente registrada pelo Cog. Ela fica acima
das regras legadas/balanceamento e evita que patches de outras classes sejam
perdidos durante a criação do Cog.
"""
from __future__ import annotations

import asyncio
import discord

from .sistemas_luta import Luta as _BaseLuta, _UIContext, _AvancarView, _vivo
from database.python import luta as luta_db


class Luta(_BaseLuta):
    """Implementação final usada pelo Discord."""

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
        if combate.get("participantes"):
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
        ataque = {
            "tipo": tipo,
            "nome": dados.pop("nome", "⚔️ Ataque"),
            "atacante_id": atacante.get("id"),
            "defensor_id": defensor.get("id"),
            **dados,
        }
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
        embed = self._acao_embed(
            atacante=atacante, defensor=defensor,
            nome=ataque.get("nome", "Ataque"),
            emoji="👹" if atacante.get("tipo") == "monstro" else "⚔️",
            turno=combate.get("numero_turno", 1), dano=ataque.get("dano_base", 0),
            mana=ataque.get("mana_base", 0),
            descricao=f"**{atacante.get('nome')}** atacou **{defensor.get('nome')}**.",
            efeito=efeito,
        )
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
        atacante = self._por_id(combate, ataque.get("atacante_id"))
        defensor = self._por_id(combate, ataque.get("defensor_id"))
        if not atacante or not defensor:
            raise RuntimeError("ataque pendente sem alvo para anúncio")
        if combate.get("ui_message"):
            await self._mostrar_ataque_ui(combate)
            return
        embed = self._embeds_acao.pop(ctx.channel.id, None)
        if isinstance(embed, tuple):
            embed = embed[0]
        if embed is None:
            embed = discord.Embed(
                title=f"⚔️ Turno {combate.get('numero_turno', 1)}",
                description=f"**{atacante.get('nome')}** atacou **{defensor.get('nome')}**!",
                color=discord.Color.orange(),
            )
        await ctx.send(embed=embed)

    async def _criar_ataque_monstro_ui(self, combate):
        """Usa a IA/balanceamento do monstro; o helper antigo não ignora bosses."""
        mensagem = combate.get("ui_message")
        if mensagem is None:
            raise RuntimeError("combate sem mensagem para ataque de monstro")
        ctx = _UIContext(mensagem, mensagem, combate, self)
        await self._ataque_monstro(ctx)
        if combate.get("ativo") and not combate.get("ataque_pendente"):
            raise RuntimeError("turno do monstro terminou sem gerar ataque")
        if combate.get("ataque_pendente"):
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
            if combate.get("ataque_pendente") is ataque:
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
        for p in combate.get("participantes", []):
            p["defesa_ativa"] = False
            p["esquiva_ativa"] = False
        defensor["defesa_ativa"] = acao == "defesa"
        defensor["esquiva_ativa"] = acao == "esquiva"
        combate["ui_stage"] = "resolving"
        combate["ui_waiting_advance"] = False
        try:
            await self._resolver_ataque(self._ui_context(ctx, combate))
        except Exception as erro:
            for p in combate.get("participantes", []):
                p["defesa_ativa"] = False
                p["esquiva_ativa"] = False
            if combate.get("ataque_pendente") is ataque and combate.get("ativo"):
                combate["fase"] = "defesa"
                combate["ui_stage"] = "defense_action"
                await self._ui_context(ctx, combate).send(
                    f"❌ Erro ao resolver a defesa: `{type(erro).__name__}: {erro}`.", _luta_error=True)
            return
        finally:
            if combate.get("ataque_pendente") is ataque:
                ataque.pop("_resolvendo", None)

    async def avancar(self, interaction: discord.Interaction):
        combate = self._obter_combate(interaction.channel.id)
        if not combate or not combate.get("ativo"):
            return await super().avancar(interaction)
        if combate.get("ui_message") is None or interaction.message is None or interaction.message.id != combate["ui_message"].id:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Esta tela não pertence ao combate atual.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Esta tela não pertence ao combate atual.", ephemeral=True)
            return
        if combate.get("ui_owner_id") is not None and str(combate["ui_owner_id"]) != str(interaction.user.id):
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Apenas o jogador deste combate pode avançar a tela.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Apenas o jogador deste combate pode avançar a tela.", ephemeral=True)
            return
        locks = getattr(self, "_ui_avancar_locks", {})
        self._ui_avancar_locks = locks
        lock = locks.setdefault(interaction.message.id, asyncio.Lock())
        if lock.locked():
            if not interaction.response.is_done():
                await interaction.response.send_message("⏳ Aguarde o avanço anterior terminar.", ephemeral=True)
            else:
                await interaction.followup.send("⏳ Aguarde o avanço anterior terminar.", ephemeral=True)
            return
        if not interaction.response.is_done():
            await interaction.response.defer()
        async with lock:
            self._normalizar_estado(combate)
            try:
                stage = combate.get("ui_stage", "attributes")
                if combate.get("ataque_pendente"):
                    combate["fase"] = "defesa"
                    await self._mostrar_ataque_ui(combate)
                    return
                if stage == "attributes":
                    combate["ui_stage"] = "velocity"
                    await self._ui_editar(combate, self._embed_velocidade(combate))
                elif stage == "velocity":
                    await self._criar_ataque_monstro_ui(combate) if (self._obter_atacante(combate) or {}).get("tipo") == "monstro" else self._mostrar_aguarde_player(combate)
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
                if combate.get("ativo"):
                    combate["ui_waiting_advance"] = False
                    if combate.get("ataque_pendente"):
                        combate["fase"] = "defesa"
                        combate["ui_stage"] = "attack"
                    else:
                        combate["fase"] = "ataque"
                    try:
                        await self._ui_editar(combate, discord.Embed(
                            title="⚠️ Combate — recuperação",
                            description=f"A etapa falhou: `{type(erro).__name__}`. Clique em **Avançar** novamente.",
                            color=discord.Color.orange(),
                        ))
                    except Exception as ui_erro:
                        print(f"[LUTA][UI][RECUPERACAO][ERRO] {type(ui_erro).__name__}: {ui_erro}")
                if interaction.response.is_done():
                    await interaction.followup.send("❌ Não foi possível avançar. O estado foi preservado.", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ Não foi possível avançar. O estado foi preservado.", ephemeral=True)


async def _avancar_callback(interaction):
    cog = interaction.client.get_cog("Luta")
    if cog is None:
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Sistema de combate indisponível.", ephemeral=True)
        return
    try:
        await cog.avancar(interaction)
    except Exception as erro:
        print(f"[LUTA][UI][CALLBACK][ERRO] {type(erro).__name__}: {erro}")
        if interaction.response.is_done():
            await interaction.followup.send("❌ Erro interno do combate. O estado foi preservado.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Erro interno do combate. O estado foi preservado.", ephemeral=True)


_AvancarView._callback = _avancar_callback
