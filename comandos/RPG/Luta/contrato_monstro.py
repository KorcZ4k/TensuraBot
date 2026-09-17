"""Normaliza o contrato dos monstros sem alterar o balanceamento existente."""

from database.python import luta as luta_db


def _normalizar_recompensa(monstro):
    """Garante que todo monstro tenha XP, TP e Hunos coerentes."""
    if not monstro:
        return monstro
    xp = int(float(monstro.get("xp_recompensa", 0) or 0))
    monstro.setdefault("tp_recompensa", xp)
    monstro.setdefault("hunos_recompensa", 0)
    return monstro


_original_criar_monstro = luta_db.criar_monstro


def criar_monstro_contrato(tipo, nivel=1):
    return _normalizar_recompensa(_original_criar_monstro(tipo, nivel))


luta_db.criar_monstro = criar_monstro_contrato

try:
    from .. import monstros_balanceamento
except ImportError:
    monstros_balanceamento = None

if monstros_balanceamento is not None:
    _original_balanceado = monstros_balanceamento.criar_monstro_balanceado

    def criar_monstro_balanceado_contrato(tipo, nivel=1):
        return _normalizar_recompensa(_original_balanceado(tipo, nivel))

    monstros_balanceamento.criar_monstro_balanceado = criar_monstro_balanceado_contrato
