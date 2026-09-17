"""Invariantes do estado de combate e unificação da resolução da UI."""

from .sistemas_luta import Luta, _UIContext, _vivo
from . import ui_fix

_original_obter_defensor = Luta._obter_defensor
_original_obter_atacante = Luta._obter_atacante


def _participante_por_id(combate, participante_id):
    if participante_id is None:
        return None
    return next(
        (p for p in combate.get("participantes", []) if str(p.get("id")) == str(participante_id)),
        None,
    )


def _obter_defensor_integridade(self, combate):
    """Nunca troca o alvo de um ataque pendente por outro participante vivo."""
    ataque = combate.get("ataque_pendente") or {}
    if ataque.get("defensor_id") is not None:
        return _participante_por_id(combate, ataque.get("defensor_id"))
    return _original_obter_defensor(self, combate)


def _obter_atacante_integridade(self, combate):
    """Mantém o atacante do ataque pendente mesmo após mudanças no turno."""
    ataque = combate.get("ataque_pendente") or {}
    if ataque.get("atacante_id") is not None:
        return _participante_por_id(combate, ataque.get("atacante_id"))
    return _original_obter_atacante(self, combate)


async def _executar_defesa_unificado(self, ctx, acao, embed=None):
    """Usa o resolver canonico para UI e comandos, evitando regras divergentes."""
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
        await ui.send(
            f"❌ É **{defensor.get('nome', 'outro jogador')}** quem deve defender este ataque.",
            _luta_error=True,
        )
        return

    atacante = self._participante(combate, ataque.get("atacante_id"))
    if not atacante or not _vivo(atacante):
        await ui.send("❌ O atacante não está mais disponível para resolver este ataque.", _luta_error=True)
        return

    defensor["defesa_ativa"] = acao == "defesa"
    defensor["esquiva_ativa"] = acao == "esquiva"
    combate["ui_stage"] = "resolving"
    combate["ui_waiting_advance"] = False

    try:
        # Não marcamos _resolvendo aqui: o resolver canonico é o dono desse lock.
        # Assim cura, assentamento e finalização PvP seguem exatamente as mesmas regras.
        await self._resolver_ataque(ui)
    except Exception as erro:
        print(f"[LUTA][DEFESA][ERRO] {type(erro).__name__}: {erro}")
        if combate.get("ativo") and combate.get("ataque_pendente") is ataque:
            combate["ui_stage"] = "defense_action"
            combate["ui_waiting_advance"] = False
            await ui.send(
                f"❌ Erro ao resolver a defesa: `{type(erro).__name__}: {erro}`.",
                _luta_error=True,
            )
        elif combate.get("ativo"):
            # O motor já consumiu o ataque; não permita que o usuário aplique dano novamente.
            combate["ui_stage"] = "turn"
            combate["ui_waiting_advance"] = False
            await ui.send(
                f"⚠️ A resolução foi aplicada, mas a interface encontrou um erro: `{type(erro).__name__}`. Clique em **Avançar**.",
                _luta_error=True,
            )


Luta._obter_defensor = _obter_defensor_integridade
Luta._obter_atacante = _obter_atacante_integridade

# ui_fix usa esta função em runtime; substituímos o caminho divergente pelo
# mesmo resolver canonico usado pelo motor legado.
ui_fix._executar_defesa_ui = _executar_defesa_unificado
Luta.executar_defesa_jogador = _executar_defesa_unificado
