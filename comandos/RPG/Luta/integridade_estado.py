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
    """Encaminha a defesa para o resolver canônico do motor efetivo."""
    return await self.executar_defesa_jogador(ctx, acao, embed=embed)
