"""Índices MongoDB necessários para os hot paths do bot."""

from database.python.mongodb import db, run_db


_INDEXES = {
    "Jogadores": [
        ([('ID', 1), ('guild_id', 1)], {"name": "idx_id_guild"}),
    ],
    "configuracoes_servidor": [
        ([('guild_id', 1)], {"name": "idx_guild_id"}),
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
    """Garante os índices sem falhar por diferenças de nome pré-existentes."""
    for collection_name, indexes in _INDEXES.items():
        collection = db[collection_name]
        existing = await run_db(lambda: list(collection.list_indexes()))
        existing_keys = {
            tuple(item["key"].items())
            for item in existing
        }

        for keys, options in indexes:
            if tuple(keys) in existing_keys:
                continue
            await run_db(collection.create_index, keys, **options)
