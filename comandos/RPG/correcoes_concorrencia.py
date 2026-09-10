"""Proteções de concorrência e estado para o fluxo de combate."""

import asyncio


_LOCKS = {}


def _lock_do_canal(channel_id):
    return _LOCKS.setdefault(channel_id, asyncio.Lock())


async def _resolver_ataque_seguro(cog, ctx, original):
    channel_id = ctx.channel.id
    combate = cog._obter_combate(channel_id)
    if not combate or not combate.get("ativo"):
        return

    tarefa_atual = asyncio.current_task()
    if combate.get("_resolver_task") is tarefa_atual:
        return await _resolver_ataque_interno(cog, ctx, combate, original)

    lock = _lock_do_canal(channel_id)
    async with lock:
        combate = cog._obter_combate(channel_id)
        if not combate or not combate.get("ativo"):
            return
        combate["_resolver_task"] = tarefa_atual
        try:
            return await _resolver_ataque_interno(cog, ctx, combate, original)
        finally:
            if combate.get("_resolver_task") is tarefa_atual:
                combate.pop("_resolver_task", None)


async def _resolver_ataque_interno(cog, ctx, combate, original):
    participantes = combate.get("participantes")
    if not isinstance(participantes, list) or not participantes:
        combate["ativo"] = False
        combate["ataque_pendente"] = None
        combate["fase"] = "ataque"
        return

    try:
        turno = int(combate.get("turno", 0))
    except (TypeError, ValueError):
        turno = 0
    if turno < 0 or turno >= len(participantes):
        combate["turno"] = 0
        combate["ataque_pendente"] = None
        combate["fase"] = "ataque"
        return

    ataque = combate.get("ataque_pendente")
    if not isinstance(ataque, dict) or ataque.get("_resolvendo"):
        return

    ataque["_resolvendo"] = True
    try:
        await original(ctx)
    finally:
        ataque_atual = combate.get("ataque_pendente")
        if isinstance(ataque_atual, dict) and ataque_atual is ataque:
            ataque_atual["_resolvendo"] = False


async def setup(bot):
    """Envolve o método efetivamente instalado na instância do Cog.

    Isso é necessário porque outras correções também substituem métodos na
    instância de ``Luta``; alterar apenas a classe deixaria essa proteção fora
    do caminho real de execução.
    """
    luta = bot.get_cog("Luta")
    if luta is None:
        raise RuntimeError("O Cog Luta não está carregado para aplicar a proteção de concorrência.")
    if getattr(luta, "_concorrencia_corrigida", False):
        return

    original = luta._resolver_ataque

    async def resolver_seguro(ctx):
        return await _resolver_ataque_seguro(luta, ctx, original)

    luta._resolver_ataque = resolver_seguro
    luta._concorrencia_corrigida = True
    print("✅ Proteção de concorrência aplicada ao resolver ativo de combate.")
