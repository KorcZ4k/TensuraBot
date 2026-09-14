"""Motor de combate com apresentação desacoplada dos comandos."""

from __future__ import annotations

import asyncio

import discord

from database.python import luta as luta_db
from ..luta import Luta as _LutaLegada
from .Infos_Luta import obter_monstro
from .Mensagens_luta import imagem_golpe


class Luta(_LutaLegada):
    """Motor único. Os comandos criam os Embeds; o motor só executa e publica."""

    def __init__(self, bot):
        super().__init__(bot)
        self._embeds_acao = {}

    def _encontrar_monstro(self, nome):
        monstro_id, _ = obter_monstro(nome)
        return monstro_id

    def _vida(self, participante):
        vida = max(0, int(float((participante or {}).get("vida", 0) or 0)))
        maxima = max(1, int(float((participante or {}).get("vida_maxima", vida) or 1)))
        return f"{vida}/{maxima}"

    def _acao_embed(self, *, atacante, defensor, nome, emoji, turno, dano, mana, descricao, efeito="Nenhum"):
        embed = discord.Embed(title=f"{emoji} {nome}", description=descricao, color=discord.Color.blurple())
        embed.add_field(name="👤 Atacante", value=atacante.get("nome", "User"), inline=True)
        embed.add_field(name="🎯 Alvo", value=defensor.get("nome", "-"), inline=True)
        embed.add_field(name="⚔️ Dano base", value=str(dano), inline=True)
        embed.add_field(name="🔷 Mana", value=str(mana), inline=True)
        embed.add_field(name="✦ Efeito", value=str(efeito or "Nenhum"), inline=True)
        embed.add_field(name="🔄 Turno", value=str(turno), inline=True)
        embed.add_field(name="❤️ Vida", value=self._vida(atacante), inline=True)
        embed.add_field(name="👹 Vida do alvo", value=self._vida(defensor), inline=True)
        return embed

    async def mostrar_ataque(self, ctx, embed, arquivo=None):
        """Publica exatamente o Embed criado pelo comando, adicionando somente a imagem do golpe cadastrada."""
        if embed is None:
            return
        combate = self._obter_combate(ctx.channel.id)
        ataque = (combate or {}).get("ataque_pendente") or {}
        url = imagem_golpe(ataque.get("tipo") or ataque.get("nome"))
        if url:
            embed.set_image(url=url)
        kwargs = {"embed": embed}
        if arquivo is not None:
            kwargs["file"] = arquivo
        await ctx.send(**kwargs)
        if not combate or not combate.get("ativo"):
            return
        defensor = self._participante(combate, ataque.get("defensor_id"))
        if defensor and defensor.get("tipo") == "monstro":
            await asyncio.sleep(0.25)
            await self._defesa_monstro(ctx)

    async def executar_ataque_jogador(self, ctx, tipo_ataque, embed):
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
        self._criar_ataque(combate, tipo_ataque, atacante, defensor, nome=golpe.get("nome", tipo_ataque.title()), dano_base=float(golpe.get("dano_base", 0) or 0), com_arma=bool(golpe.get("com_arma")), efeito=golpe.get("efeito", {}))
        await self.mostrar_ataque(ctx, embed)

    async def executar_defesa_jogador(self, ctx, acao, embed):
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
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return
        ataque = combate.get("ataque_pendente")
        atacante = self._participante(combate, ataque.get("atacante_id")) if ataque else None
        defensor = self._participante(combate, ataque.get("defensor_id")) if ataque else None
        if not ataque or not atacante or not defensor:
            return
        embed = self._embeds_acao.pop(ctx.channel.id, None)
        if isinstance(embed, tuple):
            embed = embed[0]
        if embed is None:
            efeito = ataque.get("efeito") or {}
            if isinstance(efeito, dict):
                efeito = efeito.get("nome", "Nenhum") or "Nenhum"
            embed = self._acao_embed(atacante=atacante, defensor=defensor, nome=ataque.get("nome", "Ataque"), emoji="👹" if atacante.get("tipo") == "monstro" else "⚔️", turno=combate.get("numero_turno", 1), dano=ataque.get("dano_base", 0), mana=ataque.get("mana_base", 0), descricao="Oponente realizou uma ação de combate.", efeito=efeito)
        await self.mostrar_ataque(ctx, embed)

    async def _mostrar_inicio(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return
        preparado = self._embeds_acao.pop(ctx.channel.id, None)
        arquivo = None
        if isinstance(preparado, tuple):
            embed, arquivo = preparado
        else:
            embed = preparado
        if embed is None:
            atacante = self._obter_atacante(combate)
            defensor = self._obter_defensor(combate)
            embed = discord.Embed(title="⚔️ Combate PvP" if combate.get("pvp") else "⚔️ Combate PvE", description=f"🔔 Turno {combate.get('numero_turno', 1)}\n⚡ {atacante.get('nome')} começa contra {defensor.get('nome')}.", color=discord.Color.red())
        kwargs = {"embed": embed}
        if arquivo is not None:
            kwargs["file"] = arquivo
        await ctx.send(**kwargs)
        atacante = self._obter_atacante(combate)
        if atacante.get("tipo") == "monstro":
            await asyncio.sleep(0.25)
            await self._ataque_monstro(ctx)

    async def _finalizar_pvp(self, ctx, motivo):
        preparado = self._embeds_acao.pop(ctx.channel.id, None)
        embed = preparado[0] if isinstance(preparado, tuple) else preparado
        if embed is not None:
            await ctx.send(embed=embed)
        return await super()._finalizar_pvp(ctx, motivo)

    def preparar_embed(self, ctx, embed, arquivo=None):
        self._embeds_acao[ctx.channel.id] = (embed, arquivo) if arquivo is not None else embed

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
