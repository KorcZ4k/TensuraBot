"""Motor e estado do combate.

A implementação histórica do motor continua em ``comandos.RPG.luta`` para
manter compatibilidade com módulos legados. Este módulo é a nova fronteira
oficial do motor: novos módulos devem importar ``Luta`` daqui, e não acessar
implementações paralelas.
"""

from __future__ import annotations

from ..luta import Luta


SistemaLuta = Luta


__all__ = ["Luta", "SistemaLuta"]
