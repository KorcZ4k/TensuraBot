"""Correções de regras para combates em party."""

from . import luta_sync as base

_FINALIZAR_ORIGINAL = base.Luta._finalizar
_PROXIMO_TURNO_ORIGINAL = base.Luta._proximo_turno
_DAR_RECOMPENSAS_ORIGINAL = base.Luta._dar_recompensas


def _jogadores_vivos(combate):
    return [
        p for p in combate.get("participantes", [])
        if p.get("tipo") == "jogador" and int(p.get("vida", 0) or 0) > 0
    ]


def _monstros_vivos(combate):
    return [
        p for p in combate.get("participantes", [])
        if p.get("tipo") == "monstro" and int(p.get("vida", 0) or 0) > 0
    ]


def _dar_recompensas(self, user_id, guild_id, xp, hunos):
    combate = next(
        (
            c for c in self.combates.values()
            if c.get("guild_id") == str(guild_id)
            and c.get("party")
            and any(str(p.get("id")) == str(user_id) for p in c.get("participantes", []))
        ),
        None,
    )
    if not combate:
        return _DAR_RECOMPENSAS_ORIGINAL(self, user_id, guild_id, xp, hunos)

    vivos = _jogadores_vivos(combate)
    if not vivos:
        return

    total = len(vivos)
    xp_total = int(xp or 0)
    hunos_total = int(hunos or 0)
    xp_base, xp_resto = divmod(max(0, xp_total), total)
    hunos_base, hunos_resto = divmod(max(0, hunos_total), total)
    for indice, jogador in enumerate(vivos):
        _DAR_RECOMPENSAS_ORIGINAL(
            self,
            jogador.get("id"),
            guild_id,
            xp_base + (1 if indice < xp_resto else 0),
            hunos_base + (1 if indice < hunos_resto else 0),
        )


async def _finalizar(self, ctx, motivo="vida", vencedor=None, perdedor=None):
    combate = self._obter_combate(ctx.channel.id)
    if not combate or not combate.get("party"):
        return await _FINALIZAR_ORIGINAL(self, ctx, motivo, vencedor, perdedor)

    jogadores_vivos = _jogadores_vivos(combate)
    monstros_vivos = _monstros_vivos(combate)

    if motivo in {"vida", "efeitos"} and perdedor is None and not jogadores_vivos:
        return await _FINALIZAR_ORIGINAL(self, ctx, motivo, vencedor, perdedor)

    if motivo in {"vida", "efeitos"} and vencedor is None and not monstros_vivos:
        return await _FINALIZAR_ORIGINAL(self, ctx, motivo, vencedor, perdedor)

    if motivo in {"vida", "efeitos"}:
        turno_atual = self._obter_atacante(combate)
        if int(turno_atual.get("vida", 0) or 0) <= 0:
            self._salvar_participantes(combate, situacao_padrao="ativo", morto_id=turno_atual.get("id"))
        else:
            defensor_atual = self._obter_defensor(combate)
            if int(defensor_atual.get("vida", 0) or 0) <= 0:
                self._salvar_participantes(combate, situacao_padrao="ativo", morto_id=defensor_atual.get("id"))

        combate["ativo"] = True
        combate["aguardando_finalizacao"] = False
        combate["fase"] = "ataque"
        combate["ataque_pendente"] = None
        await self._proximo_turno(ctx)
        return

    return await _FINALIZAR_ORIGINAL(self, ctx, motivo, vencedor, perdedor)


async def _proximo_turno(self, ctx):
    combate = self._obter_combate(ctx.channel.id)
    if not combate or not combate.get("party") or not combate.get("ativo"):
        return await _PROXIMO_TURNO_ORIGINAL(self, ctx)

    participantes = combate.get("participantes", [])
    if not participantes:
        combate["ativo"] = False
        return

    atual = combate.get("turno", 0) % len(participantes)
    vivos = [i for i, p in enumerate(participantes) if int(p.get("vida", 0) or 0) > 0]
    if not vivos:
        combate["ativo"] = False
        return await _FINALIZAR_ORIGINAL(self, ctx, "vida")

    proximo = next(
        (
            i for i in range(1, len(participantes) + 1)
            if (atual + i) % len(participantes) in vivos
        ),
        1,
    )
    # _PROXIMO_TURNO_ORIGINAL incrementa o índice exatamente uma vez.
    # Posicionamos o cursor imediatamente antes do participante escolhido,
    # evitando pular um membro vivo.
    combate["turno"] = (atual + proximo - 1) % len(participantes)
    return await _PROXIMO_TURNO_ORIGINAL(self, ctx)


async def setup(bot):
    base.Luta._dar_recompensas = _dar_recompensas
    base.Luta._finalizar = _finalizar
    base.Luta._proximo_turno = _proximo_turno
