"""Compatibilidade mínima para a transição da tela de turno."""
from .hardening_final import Luta


async def _mostrar_aguarde_player(self, combate):
    combate["ui_stage"] = "player_action"
    await self._ui_editar(combate, self._embed_aguarde_jogador(combate))


Luta._mostrar_aguarde_player = _mostrar_aguarde_player
