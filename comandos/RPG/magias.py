"""Comando de magias com Mongo e catálogos pré-carregados fora do event loop."""

import asyncio
import os
from contextvars import ContextVar

from database.python.mongodb import db, run_db
from database.python.magias import DatabaseMagias
from database.python.magias_async import get_magia_doc
from database.python.magias_catalog_cache import (
    get_elementos_catalogo,
    get_formas_catalogo,
)
from comandos.RPG.magias_sync import Magias as _MagiasSync

_MISSING = object()
_magia_doc = ContextVar("magia_doc", default=_MISSING)
_formas_catalogo = ContextVar("formas_catalogo", default=_MISSING)
_elementos_catalogo = ContextVar("elementos_catalogo", default=_MISSING)

_original_get_magia_doc = DatabaseMagias.get_magia_doc
_original_carregar_json = DatabaseMagias._carregar_json


def _get_magia_doc_nonblocking(self, user_id, guild_id):
    cached = _magia_doc.get()
    if cached is not _MISSING:
        return cached
    return _original_get_magia_doc(self, user_id, guild_id)


def _carregar_json_nonblocking(self, caminho):
    nome = os.path.basename(caminho).lower()
    if nome == "formas.json":
        cached = _formas_catalogo.get()
        if cached is not _MISSING:
            return {"formas": cached}
    elif nome == "elementos.json":
        cached = _elementos_catalogo.get()
        if cached is not _MISSING:
            return {"elementos": cached}
    return _original_carregar_json(self, caminho)


DatabaseMagias.get_magia_doc = _get_magia_doc_nonblocking
DatabaseMagias._carregar_json = _carregar_json_nonblocking


class Magias(_MagiasSync):
    async def cog_before_invoke(self, ctx):
        command = getattr(ctx, "command", None)
        qualified_name = getattr(command, "qualified_name", "")
        if qualified_name not in {"magias list", "magias count", "usarmagia"}:
            return
        if ctx.guild is None:
            return

        doc, formas, elementos = await asyncio.gather(
            get_magia_doc(db, str(ctx.author.id), str(ctx.guild.id)),
            run_db(get_formas_catalogo),
            run_db(get_elementos_catalogo),
        )
        _magia_doc.set(doc)
        _formas_catalogo.set(formas)
        _elementos_catalogo.set(elementos)

    async def cog_after_invoke(self, ctx):
        _magia_doc.set(_MISSING)
        _formas_catalogo.set(_MISSING)
        _elementos_catalogo.set(_MISSING)


async def setup(bot):
    await bot.add_cog(Magias(bot))
