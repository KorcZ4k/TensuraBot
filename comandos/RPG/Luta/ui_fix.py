"""Correcoes de integracao entre comandos de combate e a UI de Avancar."""

from .sistemas_luta import Luta


async def _ataque_jogador_ui(self, ctx, tipo_ataque):
    """Usa o fluxo UI em vez do metodo legado que cria mensagens separadas."""
    return await self.executar_ataque_jogador(ctx, tipo_ataque, None)


async def _defesa_jogador_ui(self, ctx, acao):
    """Resolve defesa/esquiva na mesma mensagem e libera o proximo Avancar."""
    return await self.executar_defesa_jogador(ctx, acao, None)


Luta._ataque_jogador = _ataque_jogador_ui
Luta._defesa_jogador = _defesa_jogador_ui
