import asyncio
import types

import discord
from discord.ext import commands


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
            if combate.get("fase") != "ataque":
                await ctx.send("❌ Você não pode conjurar uma defesa durante outra ação pendente.")
                return True
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
            if defesa_base <= 0:
                defesa_base = int(float(efeito.get("valor", 0) or 0))
            usuario["mana"] = mana_atual - mana_base
            usuario["defesa_bonus_magica"] = max(0, defesa_base)
            usuario["defesa_ativa"] = True
            usuario["esquiva_ativa"] = False
            usuario["magia_defensiva_ativa"] = True
            nome = dados_magia.get("nome", "Magia Defensiva")
            nome_efeito = str(efeito.get("nome", "")).strip()
            descricao = (
                f"✨ **{usuario['nome']}** conjurou **{nome}** como defesa.\n"
                f"🛡️ Bônus de defesa: **+{max(0, defesa_base)}**\n"
                f"💙 Mana gasta: **{mana_base}**"
            )
            if nome_efeito:
                descricao += f"\n🔮 Efeito: **{nome_efeito}**"
            embed = discord.Embed(title="🛡️ Defesa Mágica", description=descricao, color=discord.Color.blue(), timestamp=discord.utils.utcnow())
            await ctx.send(embed=embed)
            await asyncio.sleep(0.5)
            await cog._proximo_turno(ctx)
            return True

        async def resolver_corrigido(cog, ctx):
            combate = cog._obter_combate(ctx.channel.id)
            defensor = cog._obter_defensor(combate) if combate else None
            bonus = 0.0
            if defensor and defensor.get("magia_defensiva_ativa"):
                bonus = float(defensor.get("defesa_bonus_magica", 0) or 0)
                if bonus:
                    defesa_atual = float(defensor.get("defesa", 0) or 0)
                    defensor["defesa"] = defesa_atual + bonus
            try:
                return await original_resolver(ctx)
            finally:
                if defensor and defensor.get("magia_defensiva_ativa"):
                    if bonus:
                        defesa_atual = float(defensor.get("defesa", 0) or 0)
                        defensor["defesa"] = max(0, defesa_atual - bonus)
                    defensor.pop("defesa_bonus_magica", None)
                    defensor.pop("magia_defensiva_ativa", None)

        luta.usar_magia_no_combate = types.MethodType(usar_magia_corrigida, luta)
        luta._resolver_ataque = types.MethodType(resolver_corrigido, luta)
        luta._magia_defensiva_corrigida = True
        print("✅ Magias defensivas integradas ao sistema de combate.")
        return True

    @commands.Cog.listener()
    async def on_ready(self):
        self._aplicar_correcoes()


async def setup(bot):
    await bot.add_cog(CorrecoesLuta(bot))
