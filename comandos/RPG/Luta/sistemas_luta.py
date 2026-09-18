"""Compatibilidade do motor de combate.

A implementação canônica vive em comandos.RPG.luta; este módulo não contém
regras de combate nem cálculos de dano. Os símbolos são mantidos para imports
legados.
"""
from .luta import Luta, _vivo


class _UIContext:
    """Adaptador mínimo para chamadas legadas que precisam de channel/author."""
    def __init__(self, original, message, combate=None, owner=None):
        self._original = original
        self._message = message
        self._combate = combate or {}
        self._owner = owner

    @property
    def channel(self):
        return self._message.channel

    @property
    def author(self):
        return getattr(self._original, "user", getattr(self._original, "author", None))

    def __getattr__(self, name):
        return getattr(self._original, name)


__all__ = ["Luta", "_vivo", "_UIContext"]
