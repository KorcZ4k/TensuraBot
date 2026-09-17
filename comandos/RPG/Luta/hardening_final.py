"""Camada final de invariantes do combate.

Este módulo é carregado por último e concentra as garantias que não podem ser
quebradas por wrappers anteriores: um único ataque pendente, alvo fixo,
transição de turno consistente, recuperação da UI e limpeza de locks/flags.
"""

from __future__ import annotations

import asyncio
import random
import traceback

import discord

from database.python import luta as luta_db
from .sistemas_luta import Luta, _UIContext, _AvancarView, _vivo


# Guardamos as implementações já montadas pelos módulos de regras/balanceamento.
_ORIGINAL_ATAQUE_MONSTRO = Luta._ataque_monstro
_ORIGINAL_RESOLVER = Luta._resolver_ataque
_ORIGINAL_AVANCAR = Luta.avancar


def _por_id(combate, participante_id):
    if participante_id is None:
        return None
    return next(
        (p for p in combate.get("participantes", [])
         if str(p.get("id")) == str(participante_id)),
        None,
    )


def _normalizar_estado(self, combate):
    """Corrige somente invariantes seguras, sem trocar alvo ou atacante."""
    combate.setdefault("participantes", [])
    combate.setdefault("historico", [])
    combate.setdefault("ativo", True)
    combate.setdefault("fase", "ataque")
    combate.setdefault("turno", 0)
    combate.setdefault("numero_turno", 1)
    combate.setdefault("ataque_pendente", None)
    combate.setdefault("ui_waiting_advance", False)

    participantes = combate["participantes"]
    if participantes:
        combate["turno"] = int(combate.get("turno", 0)) % len(participantes)
    combate["numero_turno"] = max(1, int(combate.get("numero_turno", 1)))

    ataque = combate.get("ataque_pendente")
    if ataque:
        # O ataque pendente sempre é a fonte de verdade da defesa.
        atacante = _por_id(combate, ataque.get("atacante_id"))
        defensor = _por_id(combate, ataque.get("defensor_id"))
        if not atacante or not defensor:
            raise RuntimeError("ataque pendente aponta para participante inexistente")
        combate["fase"] = "defesa"
        if combate.get("ui_stage") == "resolving" and not ataque.get("_resolvendo"):
            combate["ui_stage"] = "defense_action"
    elif combate.get("fase") == "defesa":
        combate["fase"] = "ataque"
        combate.pop("_resolvendo", None)


def _obter_atacante_final(self, combate):
    _normalizar_estado(self, combate)
    ataque = combate.get("ataque_pendente")
    if ataque:
        return _por_id(combate, ataque.get("atacante_id"))
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


def _obter_defensor_final(self, combate):
    _normalizar_estado(self, combate)
    ataque = combate.get("ataque_pendente")
    if ataque:
        return _por_id(combate, ataque.get("defensor_id"))
    atacante = _obter_atacante_final(self, combate)
    if not atacante:
        return None
    equipe = atacante.get("equipe")
    return next(
        (p for p in combate.get("participantes", [])
         if p is not atacante and _vivo(p) and p.get("equipe") != equipe),
        None,
    )


def _criar_ataque_final(self, combate, tipo, atacante, defensor, **dados):
    """Cria exatamente um ataque por vez e nunca substitui um pendente."""
    _normalizar_estado(self, combate)
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


async def _mostrar_ataque_ui_final(self, combate):
    ataque = combate.get("ataque_pendente")
    if not ataque:
        raise RuntimeError("tentativa de mostrar ataque sem ataque pendente")
    atacante = _por_id(combate, ataque.get("atacante_id"))
    defensor = _por_id(combate, ataque.get("defensor_id"))
    if not atacante or not defensor:
        raise RuntimeError("ataque pendente sem atacante/defensor válido")
    # Usa o renderizador existente, mas não permite que ele silencie estado inválido.
    from .sistemas_luta import Luta as _LutaAtual
    original = getattr(_LutaAtual, "_mostrar_ataque_ui", None)
    if original is None:
        raise RuntimeError("renderizador de ataque da UI ausente")
    await original(self, combate)
    combate["ui_stage"] = "attack"
    combate["ui_waiting_advance"] = False


async def _anunciar_ataque_final(self, ctx):
    combate = self._obter_combate(ctx.channel.id)
    if not combate or not combate.get("ativo"):
        return
    ataque = combate.get("ataque_pendente")
    if not ataque:
        raise RuntimeError("tentativa de anunciar ataque inexistente")
    atacante = _por_id(combate, ataque.get("atacante_id"))
    defensor = _por_id(combate, ataque.get("defensor_id"))
    if not atacante or not defensor:
        raise RuntimeError("ataque pendente sem alvo para anúncio")

    chave = (str(ataque.get("atacante_id")), str(ataque.get("defensor_id")), id(ataque))
    if combate.get("_ultimo_ataque_anunciado") == chave:
        return
    combate["_ultimo_ataque_anunciado"] = chave

    if combate.get("ui_message"):
        await _mostrar_ataque_ui_final(self, combate)
        # Monstros defensores continuam usando a IA legada; jogadores recebem
        # os comandos de defesa pela própria UI.
        if defensor.get("tipo") == "monstro":
            await asyncio.sleep(0.05)
            await self._defesa_monstro(_UIContext(ctx, combate["ui_message"], combate, self))
        return

    # Fora da UI, preserva o anúncio canônico já existente.
    embed = discord.Embed(
        title=f"⚔️ Turno {combate.get('numero_turno', 1)}",
        description=f"{ataque.get('nome', 'Ataque')}\n\n⚔️ **{atacante.get('nome')}** atacou **{defensor.get('nome')}**!",
        color=discord.Color.orange(),
    )
    embed.add_field(name="🛡️ Quem deve defender", value=f"**{defensor.get('nome')}**", inline=False)
    await ctx.send(embed=embed)
    if defensor.get("tipo") == "monstro":
        await asyncio.sleep(0.05)
        await self._defesa_monstro(ctx)


async def _ataque_monstro_final(self, ctx):
    combate = self._obter_combate(ctx.channel.id)
    if not combate or not combate.get("ativo"):
        return
    _normalizar_estado(self, combate)
    if combate.get("ataque_pendente"):
        return
    if combate.get("fase") != "ataque":
        raise RuntimeError("turno de monstro fora da fase de ataque")

    atacante = _obter_atacante_final(self, combate)
    defensor = _obter_defensor_final(self, combate)
    if not atacante or atacante.get("tipo") != "monstro":
        raise RuntimeError("turno de monstro sem atacante válido")
    if not defensor or not _vivo(defensor):
        raise RuntimeError("turno de monstro sem defensor válido")

    erro_original = None
    try:
        await _ORIGINAL_ATAQUE_MONSTRO(self, ctx)
    except Exception as erro:
        erro_original = erro
        print(f"[LUTA][MONSTRO][ATAQUE][ORIGINAL] {type(erro).__name__}: {erro}")
        traceback.print_exc()

    if combate.get("ataque_pendente"):
        combate["fase"] = "defesa"
        return

    # Só existe fallback quando o caminho especial realmente não produziu ataque.
    ids = atacante.get("golpes", []) or []
    disponiveis = [luta_db.GOLPES[i] for i in ids if i in luta_db.GOLPES]
    golpe = random.choice(disponiveis) if disponiveis else {
        "nome": "Ataque do Monstro", "dano_base": atacante.get("dano_base", 10), "efeito": {},
    }
    ataque = _criar_ataque_final(
        self, combate, "ataque_monstro", atacante, defensor,
        nome=f"{golpe.get('emoji', '👹')} {golpe.get('nome', 'Ataque do Monstro')}",
        dano_base=float(golpe.get("dano_base", 0) or 0),
        efeito=golpe.get("efeito", {}),
        com_arma=bool(golpe.get("com_arma")),
    )
    if not ataque or combate.get("ataque_pendente") is not ataque:
        raise RuntimeError("fallback do monstro não criou ataque pendente") from erro_original
    await _anunciar_ataque_final(self, ctx)


async def _resolver_ataque_final(self, ctx):
    combate = self._obter_combate(ctx.channel.id)
    if not combate or not combate.get("ativo"):
        return
    ataque = combate.get("ataque_pendente")
    if not ataque:
        return
    if ataque.get("_resolvendo"):
        return
    ataque["_resolvendo"] = True
    try:
        await _ORIGINAL_RESOLVER(self, ctx)
        if combate.get("ativo") and combate.get("ataque_pendente") is None:
            combate["ui_stage"] = "result"
            combate["ui_waiting_advance"] = True
    except Exception:
        ataque.pop("_resolvendo", None)
        for p in combate.get("participantes", []):
            p["defesa_ativa"] = False
            p["esquiva_ativa"] = False
        if combate.get("ataque_pendente") is ataque and combate.get("ativo"):
            combate["fase"] = "defesa"
            combate["ui_stage"] = "defense_action"
            combate["ui_waiting_advance"] = False
        raise
    finally:
        if combate.get("ataque_pendente") is ataque:
            ataque.pop("_resolvendo", None)


async def _executar_defesa_final(self, ctx, acao, embed=None):
    combate = self._obter_combate(ctx.channel.id)
    if not combate or not combate.get("ativo"):
        await ctx.send("❌ Não há combate ativo.")
        return
    ataque = combate.get("ataque_pendente")
    if combate.get("fase") != "defesa" or not ataque:
        ui = self._ui_context(ctx, combate)
        await ui.send("❌ Não há ataque pendente para defender.", _luta_error=True)
        return
    if ataque.get("_resolvendo"):
        await self._ui_context(ctx, combate).send("❌ Este ataque já está sendo resolvido.", _luta_error=True)
        return

    defensor = _obter_defensor_final(self, combate)
    atacante = _obter_atacante_final(self, combate)
    if not defensor or str(defensor.get("id")) != str(ctx.author.id):
        nome = defensor.get("nome", "outro jogador") if defensor else "outro jogador"
        await self._ui_context(ctx, combate).send(f"❌ É **{nome}** quem deve defender este ataque.", _luta_error=True)
        return
    if not atacante:
        raise RuntimeError("ataque pendente sem atacante")

    for p in combate.get("participantes", []):
        p["defesa_ativa"] = False
        p["esquiva_ativa"] = False
    defensor["defesa_ativa"] = acao == "defesa"
    defensor["esquiva_ativa"] = acao == "esquiva"
    ataque["_resolvendo"] = True
    combate["ui_stage"] = "resolving"
    combate["ui_waiting_advance"] = False
    try:
        await _resolver_ataque_final(self, self._ui_context(ctx, combate))
    except Exception as erro:
        ataque.pop("_resolvendo", None)
        if combate.get("ataque_pendente") is ataque and combate.get("ativo"):
            combate["fase"] = "defesa"
            combate["ui_stage"] = "defense_action"
            combate["ui_waiting_advance"] = False
            await self._ui_context(ctx, combate).send(
                f"❌ Erro ao resolver a defesa: `{type(erro).__name__}: {erro}`.",
                _luta_error=True,
            )
        else:
            combate["ui_waiting_advance"] = False
        return
    finally:
        if combate.get("ataque_pendente") is ataque:
            ataque.pop("_resolvendo", None)
            for p in combate.get("participantes", []):
                p["defesa_ativa"] = False
                p["esquiva_ativa"] = False


async def _avancar_final(self, interaction):
    combate = self._obter_combate(interaction.channel.id)
    if not combate or not combate.get("ativo"):
        return await _ORIGINAL_AVANCAR(self, interaction)
    locks = getattr(self, "_ui_avancar_locks", None)
    if locks is None:
        locks = self._ui_avancar_locks = {}
    mensagem = combate.get("ui_message")
    lock = locks.setdefault(getattr(mensagem, "id", interaction.channel.id), asyncio.Lock())
    if lock.locked():
        if interaction.response.is_done():
            await interaction.followup.send("⏳ O avanço anterior ainda está sendo processado.", ephemeral=True)
        else:
            await interaction.response.send_message("⏳ O avanço anterior ainda está sendo processado.", ephemeral=True)
        return
    async with lock:
        _normalizar_estado(self, combate)
        try:
            # Um pending nunca é recriado e uma tela de defesa não avança o turno.
            if combate.get("ataque_pendente"):
                if combate.get("fase") != "defesa":
                    combate["fase"] = "defesa"
                if combate.get("ui_message"):
                    await _mostrar_ataque_ui_final(self, combate)
                return
            await _ORIGINAL_AVANCAR(self, interaction)
            if not combate.get("ativo"):
                return
            _normalizar_estado(self, combate)
            atacante = _obter_atacante_final(self, combate)
            if atacante and atacante.get("tipo") == "monstro" and combate.get("fase") == "ataque" and not combate.get("ataque_pendente"):
                await _ataque_monstro_final(self, _UIContext(interaction, combate["ui_message"], combate, self) if combate.get("ui_message") else interaction)
            _normalizar_estado(self, combate)
            if combate.get("fase") == "defesa" and not combate.get("ataque_pendente"):
                raise RuntimeError("fase de defesa sem ataque pendente")
        except Exception as erro:
            print(f"[LUTA][AVANCAR][ERRO] {type(erro).__name__}: {erro}")
            traceback.print_exc()
            if combate.get("ativo"):
                _normalizar_estado(self, combate)
                if combate.get("ui_message"):
                    atacante = _obter_atacante_final(self, combate) or {}
                    defensor = _obter_defensor_final(self, combate) or {}
                    embed = discord.Embed(
                        title="⚠️ Combate — recuperação",
                        description=f"A etapa encontrou `{type(erro).__name__}`. O estado foi preservado; clique em **Avançar** novamente.",
                        color=discord.Color.orange(),
                    )
                    embed.add_field(name="Atacante", value=str(atacante.get("nome", "-")))
                    embed.add_field(name="Alvo", value=str(defensor.get("nome", "-")))
                    try:
                        await self._ui_editar(combate, embed)
                    except Exception as tela_erro:
                        print(f"[LUTA][AVANCAR][UI][ERRO] {type(tela_erro).__name__}: {tela_erro}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Não foi possível avançar esta etapa. O estado foi preservado.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Não foi possível avançar esta etapa. O estado foi preservado.", ephemeral=True)


async def _avancar_callback_final(self, interaction):
    try:
        await _avancar_final(self, interaction)
    except Exception as erro:
        print(f"[LUTA][UI][CALLBACK][ERRO] {type(erro).__name__}: {erro}")
        try:
            if interaction.response.is_done():
                await interaction.followup.send("❌ Erro interno do combate. O estado foi preservado.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Erro interno do combate. O estado foi preservado.", ephemeral=True)
        except Exception as resposta_erro:
            print(f"[LUTA][UI][CALLBACK][RESPOSTA][ERRO] {type(resposta_erro).__name__}: {resposta_erro}")


# Atribuições finais: esta classe é a implementação efetivamente usada pelo Cog.
Luta._obter_atacante = _obter_atacante_final
Luta._obter_defensor = _obter_defensor_final
Luta._criar_ataque = _criar_ataque_final
Luta._ataque_monstro = _ataque_monstro_final
Luta._resolver_ataque = _resolver_ataque_final
Luta.executar_defesa_jogador = _executar_defesa_final
Luta._anunciar_ataque = _anunciar_ataque_final
Luta.avancar = _avancar_final
_AvancarView._callback = _avancar_callback_final
