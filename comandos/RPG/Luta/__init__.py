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

__all__ = ["Infos_Luta", "Mensagens_luta", "sistemas_luta", "comandos_luta"]
