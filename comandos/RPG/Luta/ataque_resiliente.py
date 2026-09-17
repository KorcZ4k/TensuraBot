"""Garantias de integridade para o turno de ataque dos monstros."""

import random
import traceback

from database.python import luta as luta_db

from .sistemas_luta import Luta

_original_ataque_monstro = Luta._ataque_monstro


async def _ataque_monstro_resiliente(self, ctx):
    """Executa o ataque normal/especial e impede estado de turno sem ataque."""
    combate = self._obter_combate(ctx.channel.id)
    if not combate or not combate.get("ativo") or combate.get("fase") != "ataque":
        return

    # Um ataque pendente é a fonte de verdade, independentemente da fase/UI.
    # Nunca crie um segundo ataque para o mesmo turno.
    if combate.get("ataque_pendente"):
        if combate.get("fase") != "defesa":
            combate["fase"] = "defesa"
        return

    erro_original = None
    try:
        await _original_ataque_monstro(self, ctx)
    except Exception as erro:
        erro_original = erro
        print(f"[LUTA][MONSTRO][ATAQUE][ERRO] {type(erro).__name__}: {erro}")
        traceback.print_exc()

    # O ataque pode ter sido criado mesmo que a mensagem/UI tenha falhado.
    # Nesse caso NÃO criamos outro ataque, evitando dano/resolução duplicados.
    if not combate.get("ativo"):
        return
    if combate.get("ataque_pendente"):
        if combate.get("fase") != "defesa":
            combate["fase"] = "defesa"
        try:
            await self._anunciar_ataque(ctx)
        except Exception as erro_ui:
            print(f"[LUTA][MONSTRO][ANUNCIO][ERRO] {type(erro_ui).__name__}: {erro_ui}")
        return

    atacante = self._obter_atacante(combate)
    defensor = self._obter_defensor(combate)
    if not atacante or atacante.get("tipo") != "monstro":
        raise RuntimeError("turno de monstro sem atacante válido") from erro_original
    if not defensor:
        raise RuntimeError("turno de monstro sem defensor válido") from erro_original

    # Último recurso: cria um ataque válido com o mesmo formato do motor legado.
    # Mantém escolha aleatória para não alterar o comportamento normal dos monstros.
    ids = atacante.get("golpes", [])
    disponiveis = [luta_db.GOLPES[i] for i in ids if i in luta_db.GOLPES]
    golpe = random.choice(disponiveis) if disponiveis else {
        "nome": "Ataque do Monstro",
        "dano_base": atacante.get("dano_base", 10),
        "efeito": {},
    }

    ataque = self._criar_ataque(
        combate,
        "ataque_monstro",
        atacante,
        defensor,
        nome=f"{golpe.get('emoji', '👹')} {golpe.get('nome', 'Ataque do Monstro')}",
        dano_base=float(golpe.get("dano_base", 0) or 0),
        efeito=golpe.get("efeito", {}),
        com_arma=bool(golpe.get("com_arma")),
    )
    if not ataque or not combate.get("ataque_pendente"):
        raise RuntimeError("fallback do monstro não criou ataque pendente") from erro_original

    if combate.get("fase") != "defesa":
        combate["fase"] = "defesa"
    await self._anunciar_ataque(ctx)
    if combate.get("ativo") and not combate.get("ataque_pendente"):
        raise RuntimeError("o anúncio do ataque do monstro não deixou ataque pendente")


Luta._ataque_monstro = _ataque_monstro_resiliente
