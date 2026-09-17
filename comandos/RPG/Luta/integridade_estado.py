"""Invariantes do estado de combate para impedir alvos/telas inconsistentes."""

from .sistemas_luta import Luta

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


Luta._obter_defensor = _obter_defensor_integridade
Luta._obter_atacante = _obter_atacante_integridade
