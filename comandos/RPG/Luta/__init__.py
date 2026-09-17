"""Pacote modular do sistema de combate.

Responsabilidades:
- Infos_Luta: regras, dados e consultas de combate.
- Mensagens_luta: interface visual e textos/embeds.
- sistemas_luta: motor, estado e resolução dos combates.
- comandos_luta: comandos públicos !luta, !soco, !defesa etc.
"""

# Carrega a ponte de compatibilidade antes dos comandos públicos.
# Ela redireciona ataque/defesa para o fluxo de mensagem única.
from . import ui_fix  # noqa: F401,E402
# A camada de robustez deve entrar depois da ponte e das regras especiais.
from . import robustez  # noqa: F401,E402
# Último nível: garante que o turno de monstro sempre gere um ataque.
from . import ataque_resiliente  # noqa: F401,E402

__all__ = ["Infos_Luta", "Mensagens_luta", "sistemas_luta", "comandos_luta"]
