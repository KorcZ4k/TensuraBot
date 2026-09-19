"""Compatibilidade de importação para versões antigas do módulo de UI.

O método efetivo agora vive diretamente em luta.Luta; este arquivo
não faz monkey-patching em runtime.
"""
from ..luta import Luta

__all__ = ["Luta"]
