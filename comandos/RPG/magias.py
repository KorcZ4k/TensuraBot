"""Comando de magias com leitura Mongo pré-carregada fora do event loop."""

from contextvars import ContextVar

from database.python.mongodb import db, run_db
from database.python.magias import DatabaseMagias
from comandos.RPG.magias_sync import Magias as _MagiasSync

_magia_doc = ContextVar("magia_doc", default=None)
_original_get_magia_doc = DatabaseMagias.get_magia_doc


def _get_magia_doc_nonblocking(self, user_id, guild_id):
    cached = _magia_doc.get()
    if cached is not None:
        return cached
    return _original_get_magia_doc(self, user_id, guild_id)


DatabaseMagias.get_magia_doc = _get_magia_doc_nonblocking


class Magias(_MagiasSync):
    async def cog_before_invoke(self, ctx):
        command = getattr(ctx, "command", None)
        qualified_name = getattr(command, "qualified_name", "")
        if qualified_name not in {"magias list", "magias count", "usarmagia"}:
            return
        if ctx.guild is None:
            return
        database = DatabaseMagias(db)
        doc = await run_db(
            _original_get_magia_doc,
            database,
            str(ctx.author.id),
            str(ctx.guild.id),
        )
        _magia_doc.set(doc)
