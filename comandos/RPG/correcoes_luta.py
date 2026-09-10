import asyncio
import random
import types

import discord
from discord.ext import commands

from . import luta_sync as _base


def _calcular_dano_fisico_defesa_acao(atacante, defensor):
    """Ataque físico = Força + Velocidade; uma única camada de defesa é aplicada."""
    if defensor.get("esquiva_ativa"):
        defensor["esquiva_ativa"] = False
        if random.random() < 0.40:
            return 0, "esquivou"
    dano = float(atacante.get("Força", 0) or 0) + float(atacante.get("Velocidade", atacante.get("velocidade", 0)) or 0)
    if defensor.get("defesa_magica_ativa"):
        dano -= float(defensor.get("defesa_magica_valor", 0) or 0)
        defensor["defesa_magica_ativa"] = False
        defensor["defesa_magica_valor"] = 0
        return max(0, int(dano)), "barreira"
    if defensor.get("defesa_ativa"):
        dano -= float(defensor.get("Força", 0) or 0) + float(defensor.get("Defesa", 0) or 0)
        defensor["defesa_ativa"] = False
        return max(0, int(dano)), "defendeu"
    return max(0, int(dano)), "normal"


def _defesa_magica(defensor, defesa_base):
    magia = float(defensor.get("Magia", 0) or 0)
    defesa = float(defensor.get("Defesa", 0) or 0)
    return max(0, int(magia + defesa + float(defesa_base or 0)))


def _calcular_dano_magico(atacante, defensor, ataque):
    if defensor.get("esquiva_ativa"):
        defensor["esquiva_ativa"] = False
        if random.random() < min(0.75, 0.10 + float(defensor.get("Velocidade", 0) or 0) / 500):
            return 0, "esquivou"
    dano = float(atacante.get("Magia", 0) or 0) + float(atacante.get("Inteligencia", 0) or 0) + float(ataque.get("dano_base", 0) or 0)
    if ataque.get("com_arma"):
        dano += float(atacante.get("dano_arma", 0) or 0)
    if defensor.get("defesa_magica_ativa"):
        dano -= float(defensor.get("defesa_magica_valor", 0) or 0)
        defensor["defesa_magica_ativa"] = False
        defensor["defesa_magica_valor"] = 0
    return max(0, int(dano)), "normal"


class CorrecoesLuta(commands.Cog):
    """Integra as regras de defesa física e defesa mágica ao combate."""

    def __init__(self, bot):
        self.bot = bot
        self._aplicar_correcoes()

    def _eh_magia_defensiva(self, dados_magia):
        tipos = dados_magia.get("tipos", [])
        if isinstance(tipos, str):
            tipos = [tipos]
        tipos = {str(tipo).strip().lower() for tipo in tipos}
        efeito = dados_magia.get("efeito", {})
        nome_efeito = str(efeito.get("nome", "")).strip().lower() if isinstance(efeito, dict) else ""
        defesa_base = float(dados_magia.get("defesa_base", 0) or 0)
        return "defesa" in tipos or "protecao" in tipos or "proteção" in tipos or defesa_base > 0 or nome_efeito in {"barreira", "escudo", "proteção", "protecao"}

    def _aplicar_correcoes(self):
        luta = self.bot.get_cog("Luta")
        if luta is None:
            return False
        _base.calcular_dano = _calcular_dano_fisico_defesa_acao
        if getattr(luta, "_magia_defensiva_corrigida", False):
            return True
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
            if combate.get("fase") == "defesa":
                defensor = cog._obter_defensor(combate)
                if defensor.get("tipo") != "jogador" or str(defensor.get("id")) != str(ctx.author.id):
                    await ctx.send(f"❌ É **{defensor.get('nome', 'Defensor')}** quem deve defender.")
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
                valor = _defesa_magica(defensor, defesa_base)
                if valor <= 0:
                    await ctx.send("❌ Essa magia não possui força suficiente para criar uma barreira.")
                    return True
                defensor["mana"] = mana_atual - mana_base
                defensor["defesa_magica_ativa"] = True
                defensor["defesa_magica_valor"] = valor
                defensor["defesa_ativa"] = False
                defensor["esquiva_ativa"] = False
                nome = dados_magia.get("nome", "Magia Defensiva")
                descricao = f"✨ **{defensor.get('nome', 'Defensor')}** conjurou **{nome}** como reação defensiva.\n🛡️ Defesa mágica: **{valor}**\n📐 Magia: **{int(float(defensor.get('Magia', 0) or 0))}** + Defesa: **{int(float(defensor.get('Defesa', 0) or 0))}** + Base: **{int(defesa_base)}**\n💙 Mana gasta: **{mana_base}**"
                if efeito.get("nome"):
                    descricao += f"\n🔮 Efeito: **{str(efeito['nome']).title()}**"
                await ctx.send(embed=discord.Embed(title="🛡️ Barreira Mágica", description=descricao, color=discord.Color.blue(), timestamp=discord.utils.utcnow()))
                await asyncio.sleep(0.5)
                return await original_resolver(ctx)
            usuario = cog._obter_atacante(combate)
            if usuario.get("tipo") != "jogador" or str(usuario.get("id")) != str(ctx.author.id):
                await ctx.send("❌ Não é sua vez de agir.")
                return True
            mana_base = int(float(dados_magia.get("mana_base", 0) or 0))
            if int(float(usuario.get("mana", 0) or 0)) < mana_base:
                await ctx.send(f"❌ Mana insuficiente. Necessário: {mana_base}.")
                return True
            defesa_base = float(dados_magia.get("defesa_base", 0) or 0)
            valor = _defesa_magica(usuario, defesa_base)
            if valor <= 0:
                await ctx.send("❌ Essa magia não possui força suficiente para criar uma barreira.")
                return True
            usuario["mana"] = int(float(usuario.get("mana", 0) or 0)) - mana_base
            usuario["defesa_magica_ativa"] = True
            usuario["defesa_magica_valor"] = valor
            usuario["defesa_ativa"] = False
            usuario["esquiva_ativa"] = False
            await ctx.send(f"🛡️ **{usuario.get('nome', 'Jogador')}** criou uma defesa mágica de **{valor}**!")
            await asyncio.sleep(0.5)
            await cog._proximo_turno(ctx)
            return True

        async def resolver_corrigido(cog, ctx):
            combate = cog._obter_combate(ctx.channel.id)
            if combate and combate.get("ativo"):
                defensor = cog._obter_defensor(combate)
                barreira = float(defensor.get("defesa_magica_valor", 0) or 0) if defensor.get("defesa_magica_ativa") else 0
                if barreira > 0 and combate.get("ataque_pendente"):
                    defensor["defesa_magica_ativa"] = True
                    defensor["defesa_magica_valor"] = barreira
            return await original_resolver(ctx)

        luta.usar_magia_no_combate = types.MethodType(usar_magia_corrigida, luta)
        luta._resolver_ataque = types.MethodType(resolver_corrigido, luta)
        luta._calcular_dano_magia = _calcular_dano_magico
        luta._magia_defensiva_corrigida = True
        print("✅ Defesa física e defesa mágica integradas ao sistema de combate.")
        return True

    @commands.Cog.listener()
    async def on_ready(self):
        self._aplicar_correcoes()


async def setup(bot):
    await bot.add_cog(CorrecoesLuta(bot))
