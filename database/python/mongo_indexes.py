"""Índices MongoDB necessários para os hot paths do bot."""

from database.python.mongodb import db, run_db


_INDEXES = {
    "Jogadores": [
        ([('ID', 1), ('guild_id', 1)], {"name": "idx_id_guild"}),
    ],
    "configuracoes_servidor": [
        ([('guild_id', 1)], {"name": "idx_guild_id"}),
    ],
    "Hunos": [
        ([('ID', 1), ('guild_id', 1)], {"name": "idx_id_guild"}),
    ],
    "Mora": [
        ([('ID', 1), ('guild_id', 1)], {"name": "idx_id_guild"}),
    ],
    "Magias": [
        ([('ID', 1), ('guild_id', 1)], {"name": "idx_id_guild"}),
    ],
    "Habilidades": [
        ([('ID', 1), ('guild_id', 1)], {"name": "idx_id_guild"}),
    ],
    "Inventários": [
        ([('ID', 1), ('guild_id', 1)], {"name": "idx_id_guild"}),
    ],
    "Recursos": [
        ([('governo_id', 1)], {"name": "idx_governo_id"}),
    ],
}


async def ensure_indexes():
    """Cria somente os índices aprovados; operação idempotente."""
    for collection_name, indexes in _INDEXES.items():
        collection = db[collection_name]
        for keys, options in indexes:
            await run_db(collection.create_index, keys, **options)
