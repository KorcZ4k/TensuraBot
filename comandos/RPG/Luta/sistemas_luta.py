"""Motor de combate com apresentação desacoplada dos comandos."""

from __future__ import annotations

import asyncio
import random

import discord

from database.python import luta as luta_db
from ..luta import Luta as _LutaLegada
from .Infos_Luta import obter_monstro
from .Mensagens_luta import painel


class Luta(_LutaLegada):
    """Motor único de combate.

    O comando cria o Embed da própria ação e entrega ao motor. O motor não
    cria mensagens para soco/chute/defesa/esquiva; ele apenas executa a regra
    e chama ``mostrar_ataque(ctx, embed)`` para publicar a ação recebida.
    """

    def __init__(self, bot):
        super().__init__(bot)
        self._embeds_acao = {}

    def _encontrar_monstro(self, nome):
        monstro_id, _ = obter_monstro(nome)
        return monstro_id

    def _id_monstro(self, defensor):
        defensor = defensor or {}
        if defensor.get("tipo") == "monstro":
            return defensor.get("id") or defensor.get("monstro_id") or defensor.get("nome")
        return defensor.get("monstro_id")

    def _vida(self, participante):
        vida = max(0, int(float((participante or {}).get("vida", 0) or 0)))
        maxima = max(1, int(float((participante or {}).get("vida_maxima", vida) or 1)))
        return f"{vida}/{maxima}"

    def _acao_embed(self, *, atacante, defensor, nome, emoji, turno, dano, mana, descricao, efeito="Nenhum"):
        """Fallback usado somente quando uma ação não veio de um comando."""
        embed = discord.Embed(
            title=f"{emoji} {nome}",
            description=descricao,
            color=discord.Color.blurple(),
        )
        embed.add_field(name="👤 Atacante", value=atacante.get("nome", "User"), inline=True)
        embed.add_field(name="🎯 Alvo", value=defensor.get("nome", "-"), inline=True)
        embed.add_field(name="⚔️ Dano base", value=str(dano), inline=True)
        embed.add_field(name="🔷 Mana", value=str(mana), inline=True)
        embed.add_field(name="✦ Efeito", value=str(efeito or "Nenhum"), inline=True)
        embed.add_field(name="🔄 Turno", value=str(turno), inline=True)
        embed.add_field(name="❤️ Vida", value=self._vida(atacante), inline=True)
        embed.add_field(name="👹 Vida do alvo", value=self._vida(defensor), inline=True)
        return embed

    async def mostrar_ataque(self, ctx, embed):
        """Publica exatamente o Embed criado pelo comando que foi usado."""
        if embed is None:
            return
        await ctx.send(embed=embed)

        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return
        ataque = combate.get("ataque_pendente") or {}
        defensor = self._participante(combate, ataque.get("defensor_id"))
        if defensor and defensor.get("tipo") == "monstro":
            await asyncio.sleep(0.25)
            await self._defesa_monstro(ctx)

    async def executar_ataque_jogador(self, ctx, tipo_ataque, embed):
        """Cria o ataque e entrega o Embed do comando ao mostrar_ataque."""
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            await ctx.send("❌ Não há combate ativo.")
            return
        if combate.get("aguardando_finalizacao"):
            await ctx.send("❌ O combate aguarda a finalização PvP.")
            return
        if combate.get("fase") != "ataque":
            await ctx.send("❌ O ataque anterior ainda não foi defendido.")
            return

        atacante = self._obter_atacante(combate)
        defensor = self._obter_defensor(combate)
        if not atacante or not defensor:
            return
        if atacante.get("tipo") != "jogador" or str(atacante.get("id")) != str(ctx.author.id):
            await ctx.send(f"❌ É a vez de **{atacante.get('nome', 'outro jogador')}**.")
            return

        golpe = luta_db.GOLPES.get(tipo_ataque, {})
        self._criar_ataque(
            combate,
            tipo_ataque,
            atacante,
            defensor,
            nome=golpe.get("nome", tipo_ataque.title()),
            dano_base=float(golpe.get("dano_base", 0) or 0),
            com_arma=bool(golpe.get("com_arma")),
            efeito=golpe.get("efeito", {}),
        )
        await self.mostrar_ataque(ctx, embed)

    async def executar_defesa_jogador(self, ctx, acao, embed):
        """Aplica defesa/esquiva e publica o Embed criado pelo comando."""
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo") or combate.get("fase") != "defesa":
            await ctx.send("❌ Não há ataque pendente para defender.")
            return
        defensor = self._obter_defensor(combate)
        if not defensor or defensor.get("tipo") != "jogador" or str(defensor.get("id")) != str(ctx.author.id):
            nome = defensor.get("nome", "outro jogador") if defensor else "outro jogador"
            await ctx.send(f"❌ É **{nome}** quem deve defender este ataque.")
            return

        defensor["defesa_ativa"] = acao == "defesa"
        defensor["esquiva_ativa"] = acao == "esquiva"
        await ctx.send(embed=embed)
        await self._resolver_ataque(ctx)

    async def _anunciar_ataque(self, ctx):
        """Usa o Embed entregue pelo comando; monstros recebem fallback gerado."""
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return
        ataque = combate.get("ataque_pendente")
        atacante = self._participante(combate, ataque.get("atacante_id")) if ataque else None
        defensor = self._participante(combate, ataque.get("defensor_id")) if ataque else None
        if not ataque or not atacante or not defensor:
            return

        embed = self._embeds_acao.pop(ctx.channel.id, None)
        if embed is None:
            efeito = ataque.get("efeito") or {}
            if isinstance(efeito, dict):
                efeito = efeito.get("nome", "Nenhum") or "Nenhum"
            embed = self._acao_embed(
                atacante=atacante,
                defensor=defensor,
                nome=ataque.get("nome", "Ataque"),
                emoji="👹" if atacante.get("tipo") == "monstro" else "⚔️",
                turno=combate.get("numero_turno", 1),
                dano=ataque.get("dano_base", 0),
                mana=ataque.get("mana_base", 0),
                descricao="Oponente realizou uma ação de combate.",
                efeito=efeito,
            )
        await self.mostrar_ataque(ctx, embed)

    async def _mostrar_inicio(self, ctx):
        """Mostra o início usando o Embed preparado pelo comando PvE/PvP."""
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return
        embed = self._embeds_acao.pop(ctx.channel.id, None)
        if embed is None:
            atacante = self._obter_atacante(combate)
            defensor = self._obter_defensor(combate)
            embed = discord.Embed(
                title="⚔️ Combate PvP" if combate.get("pvp") else "⚔️ Combate PvE",
                description=f"🔔 Turno {combate.get('numero_turno', 1)}\n⚡ {atacante.get('nome')} começa contra {defensor.get('nome')}.",
                color=discord.Color.red(),
            )
        await ctx.send(embed=embed)
        atacante = self._obter_atacante(combate)
        if atacante and atacante.get("tipo") == "monstro":
            await asyncio.sleep(0.25)
            await self._ataque_monstro(ctx)

    def preparar_embed(self, ctx, embed):
        """Entrega um Embed pronto para o próximo ponto de publicação."""
        self._embeds_acao[ctx.channel.id] = embed

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
