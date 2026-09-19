"""Compatibilidade para imports legados do sistema de combate.

O cog canonico agora vive em comandos.RPG.luta. Este modulo nao possui
estado nem monkeypatch e existe apenas para manter imports antigos validos.
"""

from .luta import Luta, _criar_participante

__all__ = ["Luta", "_criar_participante"]
