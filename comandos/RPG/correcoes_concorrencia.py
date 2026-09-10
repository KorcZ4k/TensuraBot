"""Proteções de concorrência e estado para o fluxo de combate."""

import asyncio

from . import luta_sync as base

_RESOLVER_ORIGINAL = base.Luta._resolver_ataque
_LOCKS = {}


def _lock_do_canal(channel_id):
    return _LOCKS.setdefault(channel_id, asyncio.Lock())


async def _resolver_ataque_seguro(self, ctx):
    channel_id = ctx.channel.id
    combate = self._obter_combate(channel_id)
    if not combate or not combate.get("ativo"):
        return

    tarefa_atual = asyncio.current_task()
    if combate.get("_resolver_task") is tarefa_atual:
        return await _resolver_ataque_interno(self, ctx, combate)

    lock = _lock_do_canal(channel_id)
    async with lock:
        combate = self._obter_combate(channel_id)
        if not combate or not combate.get("ativo"):
            return
        combate["_resolver_task"] = tarefa_atual
        try:
            return await _resolver_ataque_interno(self, ctx, combate)
        finally:
            if combate.get("_resolver_task") is tarefa_atual:
                combate.pop("_resolver_task", None)


async def _resolver_ataque_interno(self, ctx, combate):
    participantes = combate.get("participantes")
    if not isinstance(participantes, list) or not participantes:
        combate["ativo"] = False
        combate["ataque_pendente"] = None
        combate["fase"] = "ataque"
        return

    turno = combate.get("turno", 0)
    try:
        turno = int(turno)
    except (TypeError, ValueError):
        turno = 0
    if turno < 0 or turno >= len(participantes):
        combate["turno"] = 0
        combate["ataque_pendente"] = None
        combate["fase"] = "ataque"
        return

    ataque = combate.get("ataque_pendente")
    if not isinstance(ataque, dict):
        return
    if ataque.get("_resolvendo"):
        return

    ataque["_resolvendo"] = True
    try:
        await _RESOLVER_ORIGINAL(self, ctx)
    finally:
        ataque_atual = combate.get("ataque_pendente")
        if isinstance(ataque_atual, dict) and ataque_atual is ataque:
            ataque_atual["_resolvendo"] = False


async def setup(bot):
    base.Luta._resolver_ataque = _resolver_ataque_seguro
