"""Fallback deterministico para ataques de monstros que retornem sem criar ataque."""

import traceback

from database.python import luta as luta_db

from .sistemas_luta import Luta

_original_ataque_monstro = Luta._ataque_monstro


async def _ataque_monstro_resiliente(self, ctx):
    """Garante que um turno de monstro nunca termine sem ataque pendente."""
    combate = self._obter_combate(ctx.channel.id)
    if not combate or not combate.get("ativo") or combate.get("fase") != "ataque":
        return

    try:
        await _original_ataque_monstro(self, ctx)
    except Exception:
        # O fluxo especial de boss continua sendo a primeira tentativa.
        traceback.print_exc()

    if not combate.get("ativo") or combate.get("fase") == "defesa" and combate.get("ataque_pendente"):
        return

    atacante = self._obter_atacante(combate)
    defensor = self._obter_defensor(combate)
    if not atacante or atacante.get("tipo") != "monstro" or not defensor:
        return

    # Último recurso: usa exatamente o mesmo formato do ataque normal do motor.
    # Isso evita deixar o combate preso, sem substituir uma habilidade especial
    # que tenha conseguido criar seu ataque.
    ids = atacante.get("golpes", [])
    disponiveis = [luta_db.GOLPES[i] for i in ids if i in luta_db.GOLPES]
    golpe = disponiveis[0] if disponiveis else {
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
    await self._anunciar_ataque(ctx)


Luta._ataque_monstro = _ataque_monstro_resiliente
