"""Camada visual segura para o combate.

Restaura os metodos originais do Cog Luta antes de aplicar a estetica.
Diferentemente da primeira implementacao, nunca silencia ctx.send nem
reimplementa o motor de combate: apenas intercepta a mensagem de resultado.
"""

import discord

from comandos.RPG.luta import Luta
from comandos.RPG.correcoes_monstros import (
    _embed,
    _imagem,
    _imagem_ataque,
    _linhas,
    _slug,
)


def _instalar(cog):
    # Os metodos originais continuam definidos na classe Luta. A correcao
    # anterior gravou wrappers diretamente na instancia; restauramos aqui
    # somente o comportamento do motor antes de aplicar a camada visual.
    cog._anunciar_ataque = Luta._anunciar_ataque.__get__(cog, Luta)
    cog._resolver_ataque = Luta._resolver_ataque.__get__(cog, Luta)
    cog._defesa_jogador = Luta._defesa_jogador.__get__(cog, Luta)
    cog._defesa_monstro = Luta._defesa_monstro.__get__(cog, Luta)
    cog._mostrar_inicio = Luta._mostrar_inicio.__get__(cog, Luta)

    original_anunciar = cog._anunciar_ataque
    original_resolver = cog._resolver_ataque
    original_inicio = cog._mostrar_inicio

    async def anunciar(ctx):
        combate = cog._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return await original_anunciar(ctx)

        ataque = combate.get("ataque_pendente")
        atacante = cog._participante(combate, ataque.get("atacante_id")) if ataque else None
        defensor = cog._participante(combate, ataque.get("defensor_id")) if ataque else None
        if not ataque or not atacante or not defensor:
            return await original_anunciar(ctx)

        linhas = _linhas(combate, atacante, defensor, ataque, 0, "Aguardando defesa", "ataque")
        await ctx.send(embed=_embed(linhas, _imagem_ataque(ataque, atacante), discord.Color.orange()))

        # O metodo original so adiciona a defesa automatica do monstro apos
        # anunciar o golpe; mantemos exatamente esse comportamento.
        if defensor.get("tipo") == "monstro":
            import asyncio
            await asyncio.sleep(0.25)
            await cog._defesa_monstro(ctx)

    async def resolver(ctx):
        combate = cog._obter_combate(ctx.channel.id)
        ataque = (combate or {}).get("ataque_pendente") or {}
        atacante = cog._participante(combate, ataque.get("atacante_id")) if combate else None
        defensor = cog._participante(combate, ataque.get("defensor_id")) if combate else None
        vida_antes = int(defensor.get("vida", 0)) if defensor else 0
        historico_antes = len(combate.get("historico", [])) if combate else 0

        original_send = ctx.send
        resultado_enviado = False

        async def send_visual(*args, **kwargs):
            nonlocal resultado_enviado

            # O motor continua livre para enviar mensagens. Apenas a primeira
            # mensagem produzida durante a resolucao recebe a nova estetica.
            if not resultado_enviado and combate and ataque and atacante and defensor:
                dano = max(0, vida_antes - int(defensor.get("vida", 0)))
                efeito = "Nenhum"
                if defensor.get("efeitos"):
                    ultimo = defensor["efeitos"][-1]
                    if isinstance(ultimo, dict):
                        efeito = str(ultimo.get("nome", "Nenhum")).title()
                elif len(combate.get("historico", [])) > historico_antes:
                    ultimo_historico = str(combate["historico"][-1]).lower()
                    if "esquivou" in ultimo_historico:
                        efeito = "Esquiva"

                acao = str(ataque.get("_acao", "ataque"))
                if acao == "defesa":
                    imagem = _imagem(
                        f"{ataque.get('_defesa_tipo', 'defesa')}-luta-url",
                        "defesa-luta-url",
                    )
                    linhas = _linhas(combate, defensor, atacante, ataque, dano, efeito, acao)
                    cor = discord.Color.blurple()
                else:
                    imagem = _imagem_ataque(ataque, atacante)
                    linhas = _linhas(combate, atacante, defensor, ataque, dano, efeito, acao)
                    cor = discord.Color.red()

                resultado_enviado = True
                return await original_send(embed=_embed(linhas, imagem, cor))

            return await original_send(*args, **kwargs)

        ctx.send = send_visual
        try:
            # O motor original permanece responsavel por dano, efeitos,
            # finalizacao, recompensas e passagem de turno.
            await original_resolver(ctx)
        finally:
            ctx.send = original_send

    async def mostrar_inicio(ctx):
        combate = cog._obter_combate(ctx.channel.id)
        defensor = cog._obter_defensor(combate) if combate else None
        if not combate or not defensor or defensor.get("tipo") != "monstro":
            return await original_inicio(ctx)

        atacante = cog._obter_atacante(combate)
        if not atacante:
            return await original_inicio(ctx)

        imagem = _imagem(
            f"{_slug(defensor.get('nome', 'monstro'))}-luta-url",
            "monstro-luta-url",
        )
        embed = discord.Embed(
            title=f"🌙 MOON TENSURA • {defensor.get('emoji', '👹')} {defensor.get('nome', 'Monstro')}",
            description=(
                f"❤️ **Vida:** {int(defensor.get('vida', 0))}\n"
                f"⚔️ **Dano:** {int(defensor.get('dano_base', 0))}\n"
                f"🎯 **Alvo:** {atacante.get('nome', 'Jogador')}\n"
                f"⏱️ **Cooldown:** 6h"
            ),
            color=discord.Color.dark_red(),
        )
        if imagem:
            embed.set_image(url=imagem)
        await ctx.send(embed=embed)
        await anunciar(ctx)

    cog._anunciar_ataque = anunciar
    cog._resolver_ataque = resolver
    cog._mostrar_inicio = mostrar_inicio


async def setup(bot):
    luta = bot.get_cog("Luta")
    if luta is not None:
        _instalar(luta)
