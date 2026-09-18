"""Compatibilidade de robustez sem alterar o motor em tempo de importação."""

import traceback


def _aplicar_corrosao_robusto(self, dano, defensor):
    corrosao = next(
        (efeito for efeito in defensor.get("efeitos", [])
         if str(efeito.get("nome", "")).casefold() == "corrosao"),
        None,
    )
    if not corrosao:
        return dano
    try:
        stacks = min(3, max(1, int(corrosao.get("acumulo", 1))))
    except (TypeError, ValueError):
        stacks = 1
    return int(dano * (1 - 0.10 * stacks))


async def _resolver_defesa_ui_robusto(self, ctx, combate, ataque, defensor, atacante):
    """Delegação de compatibilidade; o resolver efetivo pertence a Luta."""
    try:
        return await self._resolver_ataque(ctx)
    except Exception:
        traceback.print_exc()
        if combate.get("ativo") and combate.get("ataque_pendente") is ataque:
            ataque.pop("_resolvendo", None)
            combate["ui_stage"] = "defense_action"
            combate["ui_waiting_advance"] = False
        raise


async def _executar_ataque_jogador_robusto(self, ctx, tipo_ataque, embed=None):
    """Delegação de compatibilidade para o método efetivo do Cog."""
    return await self.executar_ataque_jogador(ctx, tipo_ataque, embed)


__all__ = ["_aplicar_corrosao_robusto", "_resolver_defesa_ui_robusto", "_executar_ataque_jogador_robusto"]
