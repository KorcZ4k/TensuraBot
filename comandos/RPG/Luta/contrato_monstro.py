"""Contrato único de atributos e recompensas dos monstros."""

from database.python import luta as luta_db


def _normalizar_recompensa(monstro):
    if not monstro:
        return monstro
    xp = int(float(monstro.get("xp_recompensa", 0) or 0))
    monstro.setdefault("tp_recompensa", xp)
    monstro.setdefault("hunos_recompensa", 0)
    monstro.setdefault("vida", monstro.get("vida_base", 1))
    monstro.setdefault("vida_maxima", monstro.get("vida", 1))
    monstro.setdefault("dano_base", 0)
    monstro.setdefault("golpes", [])
    return monstro


# A própria tabela também precisa respeitar o contrato; eventos que consultam
# MONSTROS diretamente não podem encontrar um dicionário sem tp_recompensa.
for _dados in luta_db.MONSTROS.values():
    _normalizar_recompensa(_dados)

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
