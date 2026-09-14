"""Motor, estado e apresentação do combate."""

from __future__ import annotations

import asyncio

from ..luta import Luta as _LutaLegada
from .Infos_Luta import obter_monstro
from .Mensagens_luta import imagens_combate, painel


class Luta(_LutaLegada):
    """Motor único de PvE/PvP/party exposto pelo pacote modular."""

    def _encontrar_monstro(self, nome):
        monstro_id, _ = obter_monstro(nome)
        return monstro_id

    def _imagens_da_luta(self, ataque, defensor):
        """Fluxo único: sistema -> Mensagens_luta -> URLs -> sistema."""
        nome_ataque = (ataque or {}).get("nome", "Ataque")
        monstro_id = (defensor or {}).get("id") if (defensor or {}).get("tipo") == "monstro" else None
        return imagens_combate(nome_ataque, monstro_id)

    async def _anunciar_ataque(self, ctx):
        """Monta e envia a mensagem usando as URLs resolvidas por Mensagens_luta."""
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return

        ataque = combate.get("ataque_pendente")
        atacante = self._participante(combate, ataque.get("atacante_id")) if ataque else self._obter_atacante(combate)
        defensor = self._participante(combate, ataque.get("defensor_id")) if ataque else self._obter_defensor(combate)
        if not ataque or not atacante or not defensor:
            return

        imagem_ataque, imagem_monstro = self._imagens_da_luta(ataque, defensor)
        vida_atacante = f"{max(0, int(float(atacante.get('vida', 0) or 0)))}/{max(1, int(float(atacante.get('vida_maxima', atacante.get('vida', 0)) or 1)))}"
        vida_defensor = f"{max(0, int(float(defensor.get('vida', 0) or 0)))}/{max(1, int(float(defensor.get('vida_maxima', defensor.get('vida', 0)) or 1)))}"

        mensagem = painel(
            atacante=atacante.get("nome", "User"),
            ataque=ataque.get("nome", "Ataque"),
            vida=vida_atacante,
            mana=int(float(atacante.get("mana", 0) or 0)),
            dano="-",
            efeito="Aguardando defesa",
            alvo=defensor.get("nome", "-"),
            turno=combate.get("numero_turno", 1),
            oponente=defensor,
            vida_oponente=vida_defensor,
            extra=f"Quem deve defender: {defensor.get('nome', 'Jogador')}",
            imagem_ataque=imagem_ataque,
            imagem_oponente=imagem_monstro,
        )
        await ctx.send(embed=mensagem)

        if defensor.get("tipo") == "monstro":
            await asyncio.sleep(0.25)
            await self._defesa_monstro(ctx)

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
