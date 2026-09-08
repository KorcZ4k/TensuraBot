import asyncio
import random
import types

import discord
from discord.ext import commands

from . import luta_sync as _base


def _calcular_dano_fisico_defesa_acao(atacante, defensor):
    """Dano físico: defesa só reduz dano quando a ação DEFENDER foi usada.

    Ataque = Força + Velocidade.
    Sem defesa ativa: dano cheio.
    Com defesa ativa: dano = ataque - (Força + Defesa).
    Esquiva bem-sucedida: 0 dano.
    Esquiva falha: dano cheio, sem usar Defesa.
    A regra é idêntica para jogadores e monstros.
    """
    if defensor.get("esquiva_ativa"):
        if random.random() < 0.40:
            defensor["esquiva_ativa"] = False
            return 0, "esquivou"
        defensor["esquiva_ativa"] = False

    forca_atacante = float(atacante.get("Força", 0) or 0)
    velocidade_atacante = float(atacante.get("Velocidade", atacante.get("velocidade", 0)) or 0)
    dano = forca_atacante + velocidade_atacante

    if defensor.get("defesa_ativa"):
        defesa = float(defensor.get("defesa", 0) or 0)
        if not defesa:
            defesa = float(defensor.get("Força", 0) or 0) + float(defensor.get("Defesa", 0) or 0)
        dano -= defesa
        defensor["defesa_ativa"] = False

    return max(0, int(dano)), "normal"


class CorrecoesLuta(commands.Cog):
    """Correções de integração entre o sistema de magias e o combate."""

    def __init__(self, bot):
        self.bot = bot
        self._aplicar_correcoes()

    def _eh_magia_defensiva(self, dados_magia):
        tipos = dados_magia.get("tipos", [])
        if isinstance(tipos, str):
            tipos = [tipos]
        tipos = {str(tipo).strip().lower() for tipo in tipos}
        efeito = dados_magia.get("efeito", {})
        nome_efeito = ""
        if isinstance(efeito, dict):
            nome_efeito = str(efeito.get("nome", "")).strip().lower()
        defesa_base = float(dados_magia.get("defesa_base", 0) or 0)
        return (
            "defesa" in tipos
            or "protecao" in tipos
            or "proteção" in tipos
            or defesa_base > 0
            or nome_efeito in {"barreira", "escudo", "proteção", "protecao"}
        )

    def _aplicar_correcoes(self):
        luta = self.bot.get_cog("Luta")
        if luta is None:
            return False
        if getattr(luta, "_magia_defensiva_corrigida", False):
            return True

        _base.calcular_dano = _calcular_dano_fisico_defesa_acao

        original_usar_magia = luta.usar_magia_no_combate
        original_resolver = luta._resolver_ataque

        async def usar_magia_corrigida(cog, ctx, dados_magia):
            if not self._eh_magia_defensiva(dados_magia):
                return await original_usar_magia(ctx, dados_magia)

            combate = cog._obter_combate(ctx.channel.id)
            if not combate or not combate.get("ativo"):
                return False
            if combate.get("aguardando_finalizacao"):
                await ctx.send("❌ O combate está aguardando a finalização.")
                return True

            # Quando já existe um ataque pendente, a barreira é a própria
            # ação de DEFESA. Ela não deve ser tratada como uma nova ação de
            # ataque, portanto não pode ser bloqueada pela fase "defesa".
            if combate.get("fase") == "defesa":
                defensor = cog._obter_defensor(combate)
                if defensor.get("tipo") != "jogador" or str(defensor.get("id")) != str(ctx.author.id):
                    await ctx.send(f"❌ É **{defensor['nome']}** quem deve defender.")
                    return True

                mana_base = int(float(dados_magia.get("mana_base", 0) or 0))
                mana_atual = int(float(defensor.get("mana", 0) or 0))
                if mana_atual < mana_base:
                    await ctx.send(f"❌ Mana insuficiente. Necessário: {mana_base}.")
                    return True

                efeito = dados_magia.get("efeito", {})
                if not isinstance(efeito, dict):
                    efeito = {}
                defesa_base = float(dados_magia.get("defesa_base", 0) or 0)
                valor = int(float(defensor.get("Magia", 0) or 0) + float(defensor.get("Inteligencia", 0) or 0) + defesa_base)
                if valor <= 0:
                    await ctx.send("❌ Essa magia não possui força suficiente para criar uma barreira.")
                    return True

                defensor["mana"] = mana_atual - mana_base
                defensor["defesa_magica_ativa"] = True
                defensor["defesa_magica_valor"] = valor
                defensor["defesa_ativa"] = False
                defensor["esquiva_ativa"] = False

                nome = dados_magia.get("nome", "Magia Defensiva")
                descricao = (
                    f"✨ **{defensor['nome']}** conjurou **{nome}** como reação defensiva.\n"
                    f"🛡️ Barreira mágica: **{valor}**\n"
                    f"💙 Mana gasta: **{mana_base}**"
                )
                if efeito.get("nome"):
                    descricao += f"\n🔮 Efeito: **{str(efeito['nome']).title()}**"
                embed = discord.Embed(
                    title="🛡️ Barreira Mágica",
                    description=descricao,
                    color=discord.Color.blue(),
                    timestamp=discord.utils.utcnow(),
                )
                await ctx.send(embed=embed)
                await asyncio.sleep(0.5)

                # Resolve o ATAQUE QUE JÁ ESTAVA PENDENTE contra a barreira.
                # Não cria uma nova ação e não troca a vez do defensor.
                return await original_resolver(ctx)

            # Se ainda estamos na fase de ataque, a barreira é uma ação
            # defensiva antecipada e segue o comportamento normal.
            usuario = cog._obter_atacante(combate)
            if usuario.get("tipo") != "jogador":
                await ctx.send("❌ Não é a vez de um jogador usar magia.")
                return True
            if str(usuario.get("id")) != str(ctx.author.id):
                await ctx.send("❌ Não é sua vez de agir.")
                return True
            mana_base = int(float(dados_magia.get("mana_base", 0) or 0))
            mana_atual = int(float(usuario.get("mana", 0) or 0))
            if mana_atual < mana_base:
                await ctx.send(f"❌ Mana insuficiente. Necessário: {mana_base}.")
                return True
            efeito = dados_magia.get("efeito", {})
            if not isinstance(efeito, dict):
                efeito = {}
            defesa_base = int(float(dados_magia.get("defesa_base", 0) or 0))
            usuario["mana"] = mana_atual - mana_base
            usuario["defesa_magica_ativa"] = True
            usuario["defesa_magica_valor"] = max(0, int(float(usuario.get("Magia", 0) or 0) + float(usuario.get("Inteligencia", 0) or 0) + defesa_base))
            usuario["defesa_ativa"] = False
            usuario["esquiva_ativa"] = False
            nome = dados_magia.get("nome", "Magia Defensiva")
            descricao = (
                f"✨ **{usuario['nome']}** conjurou **{nome}** como defesa.\n"
                f"🛡️ Barreira mágica: **{usuario['defesa_magica_valor']}**\n"
                f"💙 Mana gasta: **{mana_base}**"
            )
            if efeito.get("nome"):
                descricao += f"\n🔮 Efeito: **{str(efeito['nome']).title()}**"
            embed = discord.Embed(title="🛡️ Barreira Mágica", description=descricao, color=discord.Color.blue(), timestamp=discord.utils.utcnow())
            await ctx.send(embed=embed)
            await asyncio.sleep(0.5)
            await cog._proximo_turno(ctx)
            return True

        async def resolver_corrigido(cog, ctx):
            # Mantém compatibilidade com a correção antiga de defesa física.
            combate = cog._obter_combate(ctx.channel.id)
            defensor = cog._obter_defensor(combate) if combate else None
            bonus = 0.0
            if defensor and defensor.get("magia_defensiva_ativa") and defensor.get("defesa_bonus_magica"):
                bonus = float(defensor.get("defesa_bonus_magica", 0) or 0)
                defesa_atual = float(defensor.get("defesa", 0) or 0)
                defensor["defesa"] = defesa_atual + bonus
            try:
                return await original_resolver(ctx)
            finally:
                if defensor and defensor.get("magia_defensiva_ativa") and bonus:
                    defesa_atual = float(defensor.get("defesa", 0) or 0)
                    defensor["defesa"] = max(0, defesa_atual - bonus)
                    defensor.pop("defesa_bonus_magica", None)

        luta.usar_magia_no_combate = types.MethodType(usar_magia_corrigida, luta)
        luta._resolver_ataque = types.MethodType(resolver_corrigido, luta)
        luta._magia_defensiva_corrigida = True
        print("✅ Defesa/esquiva e magias defensivas integradas ao sistema de combate.")
        return True

    @commands.Cog.listener()
    async def on_ready(self):
        self._aplicar_correcoes()


async def setup(bot):
    await bot.add_cog(CorrecoesLuta(bot))
