"""Compatibilidade de importação para versões antigas do módulo de UI.

O método efetivo agora vive diretamente em hardening_final.Luta; este arquivo
não faz monkey-patching em runtime.
"""
from .hardening_final import Luta

__all__ = ["Luta"]
