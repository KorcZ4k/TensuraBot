"""Cache de catálogos JSON estáticos carregados durante a vida do processo."""

import copy
import json
from functools import lru_cache


@lru_cache(maxsize=None)
def _load_json(path: str):
    with open(path, "r", encoding="utf-8") as arquivo:
        return json.load(arquivo)


def load_json(path: str):
    """Retorna uma cópia isolada do catálogo para evitar mutação do cache."""
    return copy.deepcopy(_load_json(path))


def clear_json_cache() -> None:
    """Limpa todos os catálogos JSON cacheados."""
    _load_json.cache_clear()
