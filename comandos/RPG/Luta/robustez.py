"""Camada de robustez para falhas transitórias do fluxo de combate."""

import traceback

from . import ui_fix
from .sistemas_luta import Luta

# Garante que as regras especiais dos monstros estejam aplicadas antes dos wrappers.
from .. import monstros_balanceamento  # noqa: F401,E402


# ``_aplicar_corrosao`` é definido dentro de ``_patch_luta`` no módulo de
# balanceamento. Ele precisa ser instalado na classe junto das demais regras;
# sem esta ponte, qualquer ataque físico/mágico de jogador contra um alvo que
# use o balanceamento quebra com AttributeError antes de concluir a defesa.
def _aplicar_corrosao_robusto(self, dano, defensor):
    corrosao = next(
        (
            efeito
            for efeito in defensor.get("efeitos", [])
            if str(efeito.get("nome", "")).casefold() == "corrosao"
        ),
        None,
    )
    if not corrosao:
        return dano
    stacks = min(3, max(1, int(corrosao.get("acumulo", 1))))
    return int(dano * (1 - 0.10 * stacks))


Luta._aplicar_corrosao = _aplicar_corrosao_robusto


_original_resolver_defesa_ui = ui_fix._resolver_defesa_ui


async def _resolver_defesa_ui_robusto(self, ctx, combate, ataque, defensor, atacante):
    """Evita deixar a UI em ``resolving`` quando o estado já foi aplicado."""
    historico_antes = len(combate.get("historico", []))
    fase_antes = combate.get("fase")
    try:
        return await _original_resolver_defesa_ui(self, ctx, combate, ataque, defensor, atacante)
    except Exception:
        traceback.print_exc()
        # A resolução já pode ter sido aplicada antes de falhar ao salvar/editar
        # a mensagem. Nesse caso, repetir a defesa causaria dano/efeito duplicado.
        aplicado = (
            combate.get("fase") == "ataque"
            and combate.get("ataque_pendente") is None
            and len(combate.get("historico", [])) > historico_antes
        )
        if aplicado:
            combate["ui_stage"] = "result"
            combate["ui_waiting_advance"] = True
            try:
                await self._salvar(combate)
            except Exception as erro_salvar:
                print(f"[LUTA][ROBUSTEZ][SALVAR][ERRO] {type(erro_salvar).__name__}: {erro_salvar}")
            return
        if fase_antes == "defesa" and combate.get("ataque_pendente") is ataque:
            ataque.pop("_resolvendo", None)
            combate["ui_stage"] = "defense_action"
            combate["ui_waiting_advance"] = False
        raise


ui_fix._resolver_defesa_ui = _resolver_defesa_ui_robusto


_original_ataque_jogador = Luta.executar_ataque_jogador


async def _executar_ataque_jogador_robusto(self, ctx, tipo_ataque, embed=None):
    """Mantém um ataque pendente utilizável se a edição da mensagem falhar."""
    try:
        return await _original_ataque_jogador(self, ctx, tipo_ataque, embed)
    except Exception as erro:
        combate = self._obter_combate(ctx.channel.id)
        print(f"[LUTA][ATAQUE][ERRO] {type(erro).__name__}: {erro}")
        traceback.print_exc()
        if not combate or not combate.get("ativo"):
            raise
        ataque = combate.get("ataque_pendente")
        if ataque and combate.get("fase") == "defesa":
            combate["ui_stage"] = "attack"
            combate["ui_waiting_advance"] = False
            try:
                await self._mostrar_ataque_ui(combate)
            except Exception as erro_tela:
                print(f"[LUTA][ATAQUE][RECUPERACAO][ERRO] {type(erro_tela).__name__}: {erro_tela}")
            return
        raise


Luta.executar_ataque_jogador = _executar_ataque_jogador_robusto
