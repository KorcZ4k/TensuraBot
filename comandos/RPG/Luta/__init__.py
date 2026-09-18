"""Pacote modular do sistema de combate.

O motor efetivo é hardening_final.Luta. Os módulos antigos de monkey-patch
não são importados aqui para evitar múltiplos donos do mesmo método.
"""
from . import contrato_monstro
from . import hardening_final
from . import compat_ui

__all__ = ["Infos_Luta", "Mensagens_luta", "sistemas_luta", "comandos_luta"]
