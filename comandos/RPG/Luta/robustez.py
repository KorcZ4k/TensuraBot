"""Camada de robustez para falhas transitórias do fluxo de combate."""

import random
import traceback

from . import ui_fix
from .sistemas_luta import Luta
from database.python import luta as luta_db


# Compatibilidade de carregamento: o balanceamento de monstros envolve
# ``_ataque_monstro`` antes de instalar o próprio wrapper. O motor atual usa
# ``_criar_ataque_monstro_ui`` na interface, mas o contrato legado também é
# usado pelos patches e pelos eventos automáticos. Mantemos um único fallback
# pequeno aqui em vez de duplicar o motor de resolução.
if not callable(getattr(Luta, "_ataque_monstro", None)):
    async def _ataque_monstro_base(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo") or combate.get("fase") != "ataque":
            return
        if combate.get("ataque_pendente"):
            combate["fase"] = "defesa"
            return
        atacante = self._obter_atacante(combate)
        defensor = self._obter_defensor(combate)
        if not atacante or atacante.get("tipo") != "monstro":
            raise RuntimeError("turno de monstro sem atacante válido")
        if not defensor:
            raise RuntimeError("turno de monstro sem defensor válido")
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
            raise RuntimeError("ataque de monstro não criou ataque pendente")
        await self._anunciar_ataque(ctx)

    Luta._ataque_monstro = _ataque_monstro_base


# O balanceamento instala as regras especiais dos monstros diretamente na
# classe Luta. Ele precisa ser carregado antes dos wrappers abaixo.
from .. import monstros_balanceamento  # noqa: F401,E402

# Auditoria de compatibilidade: todos estes métodos são usados pelo fluxo de
# ataque/defesa dos monstros. Se um patch futuro remover algum deles, o erro
# fica explícito no carregamento em vez de aparecer no meio de uma luta.
_METODOS_MONSTRO_OBRIGATORIOS = (
    "_regras_monstro",
    "_criar_ataque",
    "_ataque_monstro",
    "_resolver_ataque",
    "_aplicar_efeitos_inicio",
    "_dano_fisico",
    "_dano_magia",
    "_aplicar_efeito",
    "_proximo_turno",
    "_recompensar",
    "_aplicar_corrosao",
    "_matar_invocados_por_boss",
    "_obter_combate_por_participantes",
)

# Fenix já possui comportamento especial no balanceamento (cura e queimadura),
# então precisa ser reconhecida como boss pelo criador balanceado também.
monstros_balanceamento.BOSS_IDS.add("fenix")

# ``_aplicar_corrosao`` é uma rotina definida dentro de ``_patch_luta`` no
# módulo de balanceamento. Mantemos a implementação diretamente na classe para
# que o método exista mesmo se a ordem de imports mudar no futuro.
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
    try:
        stacks = min(3, max(1, int(corrosao.get("acumulo", 1))))
    except (TypeError, ValueError):
        stacks = 1
    return int(dano * (1 - 0.10 * stacks))


_original_resolver_defesa_ui = ui_fix._resolver_defesa_ui


async def _resolver_defesa_ui_robusto(self, ctx, combate, ataque, defensor, atacante):
    """Evita deixar a UI em ``resolving`` quando o estado já foi aplicado."""
    historico_antes = len(combate.get("historico", []))
    fase_antes = combate.get("fase")
    try:
        return await _original_resolver_defesa_ui(self, ctx, combate, ataque, defensor, atacante)
    except Exception:
        traceback.print_exc()
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


__all__ = ["_aplicar_corrosao_robusto", "_resolver_defesa_ui_robusto", "_executar_ataque_jogador_robusto"]
