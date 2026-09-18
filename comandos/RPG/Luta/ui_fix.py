"""Correcoes de integracao entre comandos de combate e a UI de Avancar."""

import asyncio
import traceback
import random

import discord

from database.python import luta as luta_db
from .sistemas_luta import Luta, _UIContext, _AvancarView, _vivo
from .Mensagens_luta import painel


async def _ataque_jogador_ui(self, ctx, tipo_ataque):
    return await self.executar_ataque_jogador(ctx, tipo_ataque, None)


async def _defesa_jogador_ui(self, ctx, acao):
    return await _executar_defesa_ui(self, ctx, acao, None)


async def _ui_editar_seguro(self, combate, embed, view=True):
    mensagem = combate.get("ui_message")
    if mensagem is None:
        return
    if not isinstance(embed, discord.Embed):
        embed = painel(extra=str(embed))
    kwargs = {"embed": embed}
    if view:
        view_obj = self._ui_views.get(mensagem.id)
        if view_obj is None:
            view_obj = _AvancarView(self)
            self._ui_views[mensagem.id] = view_obj
        kwargs["view"] = view_obj
    else:
        kwargs["view"] = None
    await mensagem.edit(**kwargs)


async def _ui_context_send_seguro(self, content=None, **kwargs):
    combate = self._combate
    atacante = self._get_participante(combate, combate.get("vencedor_id")) or self._atacante(combate) or {}
    defensor = self._get_participante(combate, combate.get("perdedor_id")) or self._defensor(combate) or {}
    embed = kwargs.get("embed")
    eh_erro = bool(kwargs.pop("_luta_error", False))
    extra = content or ""
    if embed is not None and embed.description:
        extra = embed.description if not extra else f"{extra}\n{embed.description}"
    padrao = painel(
        atacante=atacante.get("nome", "User"), ataque="resultado",
        vida=self._vida(atacante), mana=atacante.get("mana", 0),
        dano="-", efeito="Erro" if eh_erro else "Nenhum",
        alvo=defensor.get("nome", "-"), turno=combate.get("numero_turno", 1),
        oponente=defensor, vida_oponente=self._vida(defensor),
        extra=extra or "Atualizacao do combate.",
        cor=discord.Color.red() if eh_erro else discord.Color.blurple(),
    )
    etapa_anterior = combate.get("ui_stage", "attributes")
    aguardando_anterior = combate.get("ui_waiting_advance", False)
    if eh_erro:
        combate["ui_stage"] = etapa_anterior
        combate["ui_waiting_advance"] = aguardando_anterior
    else:
        combate["ui_stage"] = "result"
        combate["ui_waiting_advance"] = True
    view = self._owner._ui_views.get(self._message.id) if self._owner else None
    if view is None and self._owner:
        view = _AvancarView(self._owner)
        self._owner._ui_views[self._message.id] = view
    await self._message.edit(embed=padrao, view=view)
    return self._message


async def _resolver_defesa_ui(self, ctx, combate, ataque, defensor, atacante):
    """Resolve defesa sem depender do resolver legado."""
    if atacante is None or defensor is None:
        raise RuntimeError("atacante ou defensor ausente")

    if ataque.get("tipo") == "magia":
        dano, resultado = self._dano_magia(atacante, defensor, ataque)
    else:
        dano, resultado = self._dano_fisico(atacante, defensor, ataque)

    if resultado == "esquivou":
        mensagem = f"💨 **{defensor.get('nome')}** esquivou do ataque!"
    else:
        dano = max(0, int(dano))
        vida_antes = int(float(defensor.get("vida", 0) or 0))
        defensor["vida"] = max(0, vida_antes - dano)
        if ataque.get("tipo") == "magia":
            mensagem = f"✨ **{atacante.get('nome')}** causou **{dano} de dano mágico** em **{defensor.get('nome')}**."
        else:
            mensagem = f"⚔️ **{atacante.get('nome')}** causou **{dano} de dano** em **{defensor.get('nome')}**."
        efeito = self._aplicar_efeito(defensor, ataque.get("efeito"))
        if efeito:
            nome_efeito = efeito.get("nome", efeito.get("tipo", "Efeito")) if isinstance(efeito, dict) else str(efeito)
            mensagem += f"\n⚠️ Efeito: **{str(nome_efeito).title()}**."

    defensor["defesa_ativa"] = False
    defensor["esquiva_ativa"] = False
    combate.setdefault("historico", []).append(mensagem)
    combate["ataque_pendente"] = None
    combate["fase"] = "ataque"

    resultado_vitoria = self._condicao_vitoria(combate)
    if resultado_vitoria and not combate.get("pvp"):
        await self._salvar(combate)
        await self._finalizar(ctx, motivo="vida", vencedor=atacante, perdedor=defensor)
        return

    await self._salvar(combate)
    await asyncio.sleep(0.05)
    await self._ui_context(ctx, combate).send(mensagem)


async def _executar_defesa_ui(self, ctx, acao, embed=None):
    """Fluxo deterministico da defesa, sem depender do resolver legado."""
    combate = self._obter_combate(ctx.channel.id)
    if not combate or not combate.get("ativo"):
        if combate and combate.get("ui_message"):
            await self._ui_context(ctx, combate).send("❌ Não há combate ativo.", _luta_error=True)
        else:
            await ctx.send("❌ Não há combate ativo.")
        return

    ui = self._ui_context(ctx, combate)
    ataque = combate.get("ataque_pendente") or {}
    if combate.get("fase") != "defesa" or not ataque:
        await ui.send("❌ Não há ataque pendente para defender.", _luta_error=True)
        return
    if ataque.get("_resolvendo"):
        await ui.send("❌ Este ataque já está sendo resolvido. Aguarde o resultado.", _luta_error=True)
        return

    defensor = self._obter_defensor(combate)
    if not defensor:
        await ui.send("❌ Não foi possível identificar quem deve defender.", _luta_error=True)
        return
    if defensor.get("tipo") != "jogador" or str(defensor.get("id")) != str(ctx.author.id):
        await ui.send(f"❌ É **{defensor.get('nome', 'outro jogador')}** quem deve defender este ataque.", _luta_error=True)
        return

    atacante = self._participante(combate, ataque.get("atacante_id"))
    if not atacante or not _vivo(atacante):
        await ui.send("❌ O atacante não está mais disponível para resolver este ataque.", _luta_error=True)
        return

    defensor["defesa_ativa"] = acao == "defesa"
    defensor["esquiva_ativa"] = acao == "esquiva"
    ataque["_resolvendo"] = True
    combate["ui_stage"] = "resolving"
    combate["ui_waiting_advance"] = False
    try:
        await _resolver_defesa_ui(self, ui, combate, ataque, defensor, atacante)
    except Exception as erro:
        print(f"[LUTA][DEFESA][ERRO] {type(erro).__name__}: {erro}")
        traceback.print_exc()
        if combate.get("ativo") and combate.get("ataque_pendente") is ataque:
            ataque.pop("_resolvendo", None)
            combate["ui_stage"] = "defense_action"
            combate["ui_waiting_advance"] = False
            await ui.send(f"❌ Erro ao resolver a defesa: `{type(erro).__name__}: {erro}`.", _luta_error=True)
        return


async def _criar_ataque_monstro_ui_seguro(self, combate):
    """Garante um ataque pendente sem duplicar nem deixar o turno vazio."""
    if combate.get("ataque_pendente"):
        combate["fase"] = "defesa"
        combate["ui_stage"] = "attack"
        await self._mostrar_ataque_ui(combate)
        return

    atacante = self._obter_atacante(combate)
    defensor = self._obter_defensor(combate)
    if not atacante:
        raise RuntimeError("não foi possível identificar o atacante do turno")
    if atacante.get("tipo") != "monstro":
        raise RuntimeError("tentativa de criar ataque de monstro para atacante que não é monstro")
    if not defensor:
        raise RuntimeError("não foi possível identificar o defensor do turno")

    mensagem = combate.get("ui_message")
    if mensagem is None:
        raise RuntimeError("combate sem mensagem de interface")
    ui_ctx = _UIContext(self.bot, mensagem, combate, self)
    erro_original = None
    try:
        await self._ataque_monstro(ui_ctx)
    except Exception as erro:
        erro_original = erro
        print(f"[LUTA][UI][MONSTRO][ATAQUE][ERRO] {type(erro).__name__}: {erro}")
        traceback.print_exc()

    if combate.get("ataque_pendente"):
        combate["fase"] = "defesa"
        combate["ui_stage"] = "attack"
        return

    ids = atacante.get("golpes", [])
    disponiveis = [luta_db.GOLPES[i] for i in ids if i in luta_db.GOLPES]
    golpe = random.choice(disponiveis) if disponiveis else {
        "nome": "Ataque do Monstro",
        "dano_base": atacante.get("dano_base", 10),
        "efeito": {},
    }
    self._criar_ataque(
        combate,
        "ataque_monstro",
        atacante,
        defensor,
        nome=f"{golpe.get('emoji', '👹')} {golpe.get('nome', 'Ataque do Monstro')}",
        dano_base=float(golpe.get("dano_base", 0) or 0),
        efeito=golpe.get("efeito", {}),
        com_arma=bool(golpe.get("com_arma")),
    )
    if not combate.get("ataque_pendente"):
        if erro_original:
            raise RuntimeError("o reparo do turno do monstro não criou ataque pendente") from erro_original
        raise RuntimeError("o reparo do turno do monstro não criou ataque pendente")
    combate["fase"] = "defesa"
    combate["ui_stage"] = "attack"
    await self._mostrar_ataque_ui(combate)


_original_avancar = Luta.avancar


def _ui_stage_seguro(combate):
    """Escolhe uma etapa que ainda permite continuar depois de uma falha transitória."""
    ataque = combate.get("ataque_pendente") or {}
    if combate.get("fase") == "defesa" and ataque:
        defensor = next((p for p in combate.get("participantes", []) if str(p.get("id")) == str(ataque.get("defensor_id"))), None)
        return "defense_action" if defensor and defensor.get("tipo") == "jogador" else "attack"
    if combate.get("fase") == "ataque":
        return "turn"
    return combate.get("ui_stage", "turn")


async def _avancar_resiliente(self, interaction):
    """Serializa cliques e recupera a tela se uma etapa do motor falhar."""
    combate = self._obter_combate(interaction.channel.id)
    mensagem = combate.get("ui_message") if combate else None
    if mensagem is None:
        return await _original_avancar(self, interaction)

    locks = getattr(self, "_ui_avancar_locks", None)
    if locks is None:
        locks = self._ui_avancar_locks = {}
    lock = locks.setdefault(mensagem.id, asyncio.Lock())

    if lock.locked():
        if not interaction.response.is_done():
            await interaction.response.send_message("⏳ Estou processando o avanço anterior. Tente novamente em um instante.", ephemeral=True)
        else:
            await interaction.followup.send("⏳ Estou processando o avanço anterior. Tente novamente em um instante.", ephemeral=True)
        return

    async with lock:
        try:
            await _original_avancar(self, interaction)
            if not combate.get("ativo"):
                return
            stage = combate.get("ui_stage")
            fase = combate.get("fase")
            ataque = combate.get("ataque_pendente")
            if stage in {"velocity", "turn"} and fase == "ataque":
                atacante = self._obter_atacante(combate)
                if atacante and atacante.get("tipo") == "monstro" and not ataque:
                    await self._criar_ataque_monstro_ui(combate)
            stage = combate.get("ui_stage")
            fase = combate.get("fase")
            ataque = combate.get("ataque_pendente")
            if stage == "attack" and fase == "defesa" and not ataque:
                raise RuntimeError("a tela de ataque ficou sem ataque pendente")
        except Exception as erro:
            print(f"[LUTA][UI][AVANCAR][ERRO] {type(erro).__name__}: {erro}")
            traceback.print_exc()
            if combate.get("ativo") and combate.get("ui_message"):
                combate["ui_stage"] = _ui_stage_seguro(combate)
                combate["ui_waiting_advance"] = False
                atacante = self._obter_atacante(combate) or {}
                defensor = self._obter_defensor(combate) or {}
                try:
                    ui_ctx = self._ui_context(interaction, combate)
                    erro_embed = painel(
                        atacante=atacante.get("nome", "User"), ataque="erro recuperável",
                        vida=ui_ctx._vida(atacante), mana=atacante.get("mana", 0),
                        dano="-", efeito="Erro", alvo=defensor.get("nome", "-"),
                        turno=combate.get("numero_turno", 1), oponente=defensor,
                        vida_oponente=ui_ctx._vida(defensor),
                        extra=f"❌ Ocorreu um erro nesta etapa: `{type(erro).__name__}: {erro}`\n\nO estado do combate foi preservado. Clique em **Avançar** novamente.",
                        cor=discord.Color.red(),
                    )
                    await self._ui_editar(combate, erro_embed)
                except Exception as erro_tela:
                    print(f"[LUTA][UI][RECUPERACAO][ERRO] {type(erro_tela).__name__}: {erro_tela}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Houve uma falha nesta etapa, mas o combate foi preservado. Clique em Avançar novamente.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Houve uma falha nesta etapa, mas o combate foi preservado. Clique em Avançar novamente.", ephemeral=True)



__all__ = ["_ataque_jogador_ui", "_defesa_jogador_ui", "_ui_editar_seguro", "_executar_defesa_ui", "_criar_ataque_monstro_ui_seguro", "_avancar_resiliente"]
