"""Cache de catálogos estáticos de magia carregados uma vez por processo."""

import copy
from functools import lru_cache

from database.python.magias import DatabaseMagias


@lru_cache(maxsize=1)
def _catalogos():
    catalogo = DatabaseMagias(None)
    return (
        copy.deepcopy(catalogo.get_formas_catalogo()),
        copy.deepcopy(catalogo.get_elementos_catalogo()),
    )


def get_formas_catalogo():
    return copy.deepcopy(_catalogos()[0])


def get_elementos_catalogo():
    return copy.deepcopy(_catalogos()[1])


def clear_catalogos_cache():
    _catalogos.cache_clear()
