"""Pacote modular do sistema de combate.

Responsabilidades:
- Infos_Luta: regras, dados e consultas de combate.
- Mensagens_luta: interface visual e textos/embeds.
- sistemas_luta: motor, estado e resolução dos combates.
- comandos_luta: comandos públicos !luta, !soco, !defesa etc.
"""

# Carrega a ponte de compatibilidade antes dos comandos públicos.
from . import ui_fix  # noqa: F401,E402
# Contrato único de recompensas/atributos dos monstros.
from . import contrato_monstro  # noqa: F401,E402
# Regras especiais e recuperação de erros.
from . import robustez  # noqa: F401,E402
# Último nível: garante que o turno de monstro sempre gere um ataque.
from . import ataque_resiliente  # noqa: F401,E402
# Invariantes: um ataque pendente nunca troca de atacante/alvo silenciosamente.
from . import integridade_estado  # noqa: F401,E402
# Camada final: estado, UI, turnos, defesa e anúncio ficam com invariantes únicas.
from . import hardening_final  # noqa: F401,E402

__all__ = ["Infos_Luta", "Mensagens_luta", "sistemas_luta", "comandos_luta"]
