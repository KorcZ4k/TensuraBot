import asyncio

import discord
from discord.ext import commands

from database.python.mongodb import db, run_db


ATRIBUTOS_VALIDOS = {
    "forca": "Força", "força": "Força", "defesa": "Defesa",
    "vitalidade": "Vitalidade", "velocidade": "Velocidade",
    "destreza": "Destreza", "magia": "Magia", "sorte": "Sorte",
    "inteligencia": "inteligencia", "inteligência": "inteligencia",
}


def _normalizar_atributo(valor):
    return ATRIBUTOS_VALIDOS.get(str(valor).strip().casefold())


def adicionar_tp(user_id, guild_id, quantidade, motivo=None):
    quantidade = int(quantidade)
    if quantidade <= 0:
        return 0
    resultado = db["Jogadores"].find_one_and_update(
        {"ID": str(user_id), "guild_id": str(guild_id)},
        {"$inc": {"TP": quantidade}},
        return_document=True,
    )
    return resultado.get("TP", 0) if resultado else 0


def aumentar_atributo_com_tp(user_id, guild_id, atributo, quantidade=1):
    atributo = _normalizar_atributo(atributo)
    quantidade = int(quantidade)
    if atributo is None:
        raise ValueError("Atributo inválido. Use Força, Defesa, Vitalidade, Velocidade, Destreza, Magia, Sorte ou Inteligência.")
    if quantidade <= 0:
        raise ValueError("A quantidade deve ser maior que zero.")

    jogador = db["Jogadores"].find_one({"ID": str(user_id), "guild_id": str(guild_id)})
    if not jogador:
        raise ValueError("Jogador não encontrado.")
    if jogador.get("Situação") == "morto":
        raise ValueError("Você está morto e não pode gastar TP.")

    tp = int(jogador.get("TP", 0) or 0)
    if tp < quantidade:
        raise ValueError(f"Você não possui TP suficiente. Você tem **{tp} TP** e precisa de **{quantidade} TP**.")

    valor_atual = float(jogador.get(atributo, 0) or 0)
    novo_valor = valor_atual + quantidade
    atualizacoes = {atributo: novo_valor, "TP": tp - quantidade}

    if atributo == "Vitalidade":
        vida_maxima_antiga = float(jogador.get("Vida_Maxima", valor_atual * 10) or 0)
        vida_atual = float(jogador.get("Vida", vida_maxima_antiga) or 0)
        vida_maxima_nova = novo_valor * 10
        aumento_vida = vida_maxima_nova - vida_maxima_antiga
        atualizacoes["Vida_Maxima"] = vida_maxima_nova
        atualizacoes["Vida"] = min(vida_maxima_nova, max(0, vida_atual + aumento_vida))

    resultado = db["Jogadores"].update_one(
        {"_id": jogador["_id"], "TP": {"$gte": quantidade}},
        {"$set": atualizacoes},
    )
    if resultado.modified_count == 0:
        raise ValueError("Não foi possível aplicar o aumento de atributo. Tente novamente.")

    return {"atributo": atributo, "novo_valor": novo_valor, "tp_restante": tp - quantidade,
            "vida_maxima": atualizacoes.get("Vida_Maxima"), "vida": atualizacoes.get("Vida")}


class Progressao(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._luta_patched = False

    def _patch_luta(self):
        if self._luta_patched:
            return
        luta = self.bot.get_cog("Luta")
        if luta is None:
            return
        classe = type(luta)
        original = getattr(classe, "_dar_recompensas", None)
        if original is None or getattr(original, "_tp_patch", False):
            return

        def wrapper(cog, user_id, guild_id, xp, hunos):
            resultado = original(cog, user_id, guild_id, xp, hunos)
            tp = max(1, int(xp or 0) // 50)
            asyncio.create_task(run_db(adicionar_tp, user_id, guild_id, tp, "monstro"))
            return resultado

        wrapper._tp_patch = True
        classe._dar_recompensas = wrapper
        self._luta_patched = True

    @commands.command(name="aumentar")
    async def aumentar(self, ctx, atributo: str, quantidade: int = 1):
        try:
            resultado = await run_db(aumentar_atributo_com_tp, str(ctx.author.id), str(ctx.guild.id), atributo, quantidade)
        except ValueError as erro:
            await ctx.send(f"❌ {erro}")
            return

        texto = f"✅ **{resultado['atributo']}** aumentou para **{resultado['novo_valor']:.0f}**.\n✨ TP restante: **{resultado['tp_restante']}**"
        if resultado["atributo"] == "Vitalidade":
            texto += f"\n❤️ Vida: **{resultado['vida']:.0f}/{resultado['vida_maxima']:.0f}**"
        await ctx.send(texto)

    @commands.command(name="tp", aliases=["pontos", "pontostreinamento"])
    async def tp(self, ctx):
        jogador = await run_db(db["Jogadores"].find_one, {"ID": str(ctx.author.id), "guild_id": str(ctx.guild.id)}, {"TP": 1, "_id": 0})
        if not jogador:
            await ctx.send("❌ Você não possui um personagem registrado.")
            return
        await ctx.send(f"✨ Você possui **{int(jogador.get('TP', 0) or 0)} TP** (Pontos de Treinamento).")

    @commands.Cog.listener()
    async def on_ready(self):
        self._patch_luta()


async def setup(bot):
    await bot.add_cog(Progressao(bot))
