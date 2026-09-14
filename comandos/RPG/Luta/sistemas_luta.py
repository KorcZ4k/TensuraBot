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

    def _id_monstro(self, defensor):
        """Obtém o ID/nome do monstro usado por Mensagens_luta para buscar a imagem."""
        defensor = defensor or {}
        return (
            defensor.get("id")
            or defensor.get("monstro_id")
            or defensor.get("nome")
            if defensor.get("tipo") == "monstro"
            else None
        )

    def _imagens_da_luta(self, ataque, defensor):
        """Fluxo único: sistema -> Mensagens_luta -> URLs do Imagens.json."""
        ataque = ataque or {}
        nome_ataque = ataque.get("nome", "Ataque")
        monstro_id = self._id_monstro(defensor)
        return imagens_combate(nome_ataque, monstro_id)

    async def _mostrar_inicio(self, ctx):
        """Mostra o início do combate já com a imagem do monstro resolvida."""
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return

        atacante = self._obter_atacante(combate)
        defensor = self._obter_defensor(combate)

        # No primeiro turno do PvE não existe ataque_pendente. Portanto a
        # imagem precisa ser resolvida diretamente do participante monstro.
        if not defensor:
            defensor = next(
                (
                    participante
                    for participante in combate.get("participantes", [])
                    if participante.get("tipo") == "monstro"
                ),
                None,
            )

        if not atacante or not defensor:
            return

        imagem_ataque, imagem_monstro = imagens_combate("início do combate", self._id_monstro(defensor))
        mensagem = painel(
            atacante=atacante.get("nome", "User"),
            ataque="início do combate",
            vida=f"{max(0, int(float(atacante.get('vida', 0) or 0)))}/{max(1, int(float(atacante.get('vida_maxima', atacante.get('vida', 0)) or 1)))}",
            mana=int(float(atacante.get("mana", 0) or 0)),
            dano="-",
            efeito="Nenhum",
            alvo=defensor.get("nome", "-"),
            turno=combate.get("numero_turno", 1),
            oponente=defensor,
            vida_oponente=f"{max(0, int(float(defensor.get('vida', 0) or 0)))}/{max(1, int(float(defensor.get('vida_maxima', defensor.get('vida', 0)) or 1)))}",
            extra="Combate PvE iniciado.",
            imagem_ataque=imagem_ataque,
            imagem_oponente=imagem_monstro,
        )
        await ctx.send(embed=mensagem)

    async def _anunciar_ataque(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return

        ataque = combate.get("ataque_pendente")
        atacante = self._participante(combate, ataque.get("atacante_id")) if ataque else self._obter_atacante(combate)
        defensor = self._participante(combate, ataque.get("defensor_id")) if ataque else self._obter_defensor(combate)
        if not ataque or not atacante or not defensor:
            return

        imagem_ataque, imagem_monstro = self._imagens_da_luta(ataque, defensor)
        mensagem = painel(
            atacante=atacante.get("nome", "User"),
            ataque=ataque.get("nome", "Ataque"),
            vida=f"{max(0, int(float(atacante.get('vida', 0) or 0)))}/{max(1, int(float(atacante.get('vida_maxima', atacante.get('vida', 0)) or 1)))}",
            mana=int(float(atacante.get("mana", 0) or 0)),
            dano="-",
            efeito="Aguardando defesa",
            alvo=defensor.get("nome", "-"),
            turno=combate.get("numero_turno", 1),
            oponente=defensor,
            vida_oponente=f"{max(0, int(float(defensor.get('vida', 0) or 0)))}/{max(1, int(float(defensor.get('vida_maxima', defensor.get('vida', 0)) or 1)))}",
            extra=f"Quem deve defender: {defensor.get('nome', 'Jogador')}",
            imagem_ataque=imagem_ataque,
            imagem_oponente=imagem_monstro,
        )
        await ctx.send(embed=mensagem)

        if defensor.get("tipo") == "monstro":
            await asyncio.sleep(0.25)
            await self._defesa_monstro(ctx)

    async def resultado_ataque(self, ctx):
        return await self._resolver_ataque(ctx)

    async def resultado_defesa(self, ctx, acao):
        return await self._defesa_jogador(ctx, acao)

    async def resultado_magia(self, ctx, dados_magia):
        return await self.usar_magia_no_combate(ctx, dados_magia)

    async def resultado_ataque_monstro(self, ctx):
        return await self._ataque_monstro(ctx)

    async def resultado_pvp(self, ctx, motivo):
        return await self._finalizar_pvp(ctx, motivo)

    async def resultado_final(self, ctx, motivo="vida", vencedor=None, perdedor=None):
        return await self._finalizar(ctx, motivo=motivo, vencedor=vencedor, perdedor=perdedor)


SistemaLuta = Luta

__all__ = ["Luta", "SistemaLuta"]
