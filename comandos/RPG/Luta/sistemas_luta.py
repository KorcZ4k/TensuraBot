"""Motor, estado e resolução dos resultados do combate.

A implementação histórica continua disponível em ``comandos.RPG.luta`` para
compatibilidade. A classe abaixo é a fronteira oficial usada pelo novo pacote
Luta e concentra pontos de entrada para a resolução de ações.
"""

from __future__ import annotations

from ..luta import Luta as _LutaLegada
from .Infos_Luta import obter_monstro


class Luta(_LutaLegada):
    """Motor único de PvE/PvP/party exposto pelo pacote modular."""

    def _encontrar_monstro(self, nome):
        monstro_id, _ = obter_monstro(nome)
        return monstro_id

    async def resultado_ataque(self, ctx):
        """Resolve o ataque atualmente pendente e avança o combate."""
        return await self._resolver_ataque(ctx)

    async def resultado_defesa(self, ctx, acao):
        """Registra defesa/esquiva e resolve o ataque pendente."""
        return await self._defesa_jogador(ctx, acao)

    async def resultado_magia(self, ctx, dados_magia):
        """Aplica o resultado de uma magia de combate."""
        return await self.usar_magia_no_combate(ctx, dados_magia)

    async def resultado_ataque_monstro(self, ctx):
        """Executa a escolha de ataque do monstro."""
        return await self._ataque_monstro(ctx)

    async def resultado_pvp(self, ctx, motivo):
        """Finaliza o PvP com morte ou desmaio."""
        return await self._finalizar_pvp(ctx, motivo)

    async def resultado_final(self, ctx, motivo="vida", vencedor=None, perdedor=None):
        """Centraliza o resultado final de qualquer combate."""
        return await self._finalizar(ctx, motivo=motivo, vencedor=vencedor, perdedor=perdedor)


SistemaLuta = Luta


__all__ = ["Luta", "SistemaLuta"]
