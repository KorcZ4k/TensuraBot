"""Contrato de dados dos monstros.

O contrato é implementado pelos criadores de dados; este módulo apenas valida
e normaliza registros já existentes, sem substituir funções em runtime.
"""
from database.python import luta as luta_db
from ..monstros_balanceamento import criar_monstro_balanceado

def normalizar_recompensa(monstro):
    if not monstro:
        return monstro
    monstro["xp_recompensa"] = int(float(monstro.get("xp_recompensa", 0) or 0))
    monstro["tp_recompensa"] = int(float(monstro.get("tp_recompensa", monstro["xp_recompensa"]) or 0))
    monstro["hunos_recompensa"] = int(float(monstro.get("hunos_recompensa", 0) or 0))
    monstro["vida"] = monstro.get("vida", monstro.get("vida_base", 1))
    monstro["vida_maxima"] = monstro.get("vida_maxima", monstro["vida"])
    monstro["dano_base"] = int(float(monstro.get("dano_base", 0) or 0))
    monstro["golpes"] = list(monstro.get("golpes") or [])
    monstro.setdefault("efeitos", [])
    return monstro

for _dados in luta_db.MONSTROS.values():
    normalizar_recompensa(_dados)

__all__ = ["normalizar_recompensa", "criar_monstro_balanceado"]
