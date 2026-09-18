"""Compatibilidade do antigo módulo de ataque resiliente.

O motor efetivo é hardening_final.Luta. Este módulo não altera classes em
tempo de importação; a função abaixo pode ser usada por integrações antigas.
"""

import random
from database.python import luta as luta_db

_original_ataque_monstro = None


async def _ataque_monstro_resiliente(self, ctx):
    combate = self._obter_combate(ctx.channel.id)
    if not combate or not combate.get("ativo"):
        return None
    if combate.get("ataque_pendente"):
        combate["fase"] = "defesa"
        combate["ui_stage"] = "attack"
        return combate["ataque_pendente"]
    try:
        callback = _original_ataque_monstro or self._ataque_monstro
        ataque = await callback(self, ctx) if _original_ataque_monstro else await callback(ctx)
        if ataque is not None:
            return ataque
    except Exception as erro_original:
        print(f"[LUTA][MONSTRO][COMPAT][ERRO] {type(erro_original).__name__}: {erro_original}")
    if combate.get("ataque_pendente"):
        combate["fase"] = "defesa"
        combate["ui_stage"] = "attack"
        return combate["ataque_pendente"]
    atacante = self._obter_atacante(combate)
    defensor = self._obter_defensor(combate)
    if not atacante or atacante.get("tipo") != "monstro" or not defensor:
        raise RuntimeError("turno de monstro sem participantes válidos")
    golpes = [luta_db.GOLPES[i] for i in atacante.get("golpes", []) if i in luta_db.GOLPES]
    golpe = random.choice(golpes) if golpes else {"nome": "Ataque do Monstro", "dano_base": atacante.get("dano_base", 10), "efeito": {}}
    ataque = self._criar_ataque(combate, "ataque_monstro", atacante, defensor,
                                nome=golpe.get("nome", "Ataque do Monstro"),
                                dano_base=float(golpe.get("dano_base", 0) or 0),
                                efeito=golpe.get("efeito", {}) or {},
                                com_arma=bool(golpe.get("com_arma")))
    if not ataque or not combate.get("ataque_pendente"):
        raise RuntimeError("fallback não criou ataque pendente")
    combate["fase"] = "defesa"
    combate["ui_stage"] = "attack"
    await self._anunciar_ataque(ctx)
    return ataque
