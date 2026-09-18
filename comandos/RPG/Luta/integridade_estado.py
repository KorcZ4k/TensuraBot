"""Compatibilidade de invariantes sem monkey patch.

O estado efetivo pertence a hardening_final.Luta. Estas funções ficam
disponíveis para integrações antigas, mas nenhum método é substituído no
processo de importação.
"""

def _participante_por_id(combate, participante_id):
    if participante_id is None:
        return None
    return next((p for p in combate.get("participantes", []) if str(p.get("id")) == str(participante_id)), None)


def _obter_defensor_integridade(self, combate):
    ataque = combate.get("ataque_pendente") or {}
    if ataque.get("defensor_id") is not None:
        return _participante_por_id(combate, ataque.get("defensor_id"))
    return self._obter_defensor(combate)


def _obter_atacante_integridade(self, combate):
    ataque = combate.get("ataque_pendente") or {}
    if ataque.get("atacante_id") is not None:
        return _participante_por_id(combate, ataque.get("atacante_id"))
    return self._obter_atacante(combate)


async def _executar_defesa_unificado(self, ctx, acao, embed=None):
    combate = self._obter_combate(ctx.channel.id)
    if not combate or not combate.get("ativo"):
        return
    ui = self._ui_context(ctx, combate)
    ataque = combate.get("ataque_pendente") or {}
    defensor = self._obter_defensor(combate)
    if not defensor or str(defensor.get("id")) != str(ctx.author.id):
        return
    defensor["defesa_ativa"] = acao == "defesa"
    defensor["esquiva_ativa"] = acao == "esquiva"
    combate["ui_stage"] = "resolving"
    try:
        await self._resolver_ataque(ui)
    except Exception:
        ataque.pop("_resolvendo", None)
        if combate.get("ativo") and combate.get("ataque_pendente") is ataque:
            combate["ui_stage"] = "defense_action"
            combate["ui_waiting_advance"] = False
            await ui.send("❌ Erro ao resolver a defesa.", _luta_error=True)

