import json
from pathlib import Path
import discord
from discord.ext import commands
from database.python.mongodb import db

ARQUIVO = Path(__file__).resolve().parents[2] / "database/json/loja.json"

class Loja(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.itens = self._carregar()

    def _carregar(self):
        try:
            return json.loads(ARQUIVO.read_text(encoding="utf-8"))
        except Exception as erro:
            print(f"[LOJA] Erro: {erro}")
            return {"categorias": {}}

    def _todos(self):
        return [item for lista in self.itens.get("categorias", {}).values() for item in lista]

    def _buscar(self, identificador):
        alvo = str(identificador).casefold().strip()
        return next((x for x in self._todos() if str(x.get("id", "")).casefold() == alvo or str(x.get("nome", "")).casefold() == alvo), None)

    @commands.group(name="loja", aliases=["shop"], invoke_without_command=True)
    async def loja(self, ctx):
        e = discord.Embed(title="🛒 Loja de Aventureiros", description="Salário mínimo: **1.000 Hunos**\nOs preços foram balanceados para tornar equipamentos relevantes uma conquista de longo prazo.", color=discord.Color.gold())
        for categoria, itens in self.itens.get("categorias", {}).items():
            nomes = "\n".join(f"`{x['id']}` — **{x['nome']}** • {x['preco']:,} Hunos" for x in itens[:12])
            if nomes:
                e.add_field(name=f"📦 {categoria.title()}", value=nomes, inline=False)
        e.set_footer(text="Use !loja comprar <id> • !loja ver <id> • !loja inventario")
        await ctx.send(embed=e)

    @loja.command(name="ver")
    async def ver(self, ctx, *, identificador: str):
        item = self._buscar(identificador)
        if not item:
            await ctx.send("❌ Item não encontrado.")
            return
        detalhes = [f"💰 **Preço:** {item['preco']:,} Hunos"]
        for chave, label in (("dano","⚔️ Dano"),("defesa","🛡️ Defesa"),("cura","❤️ Cura"),("mana","💧 Mana"),("forca","💪 Força"),("vitalidade","❤️ Vitalidade"),("velocidade","💨 Velocidade"),("destreza","🎯 Destreza"),("magia","✨ Magia"),("sorte","🍀 Sorte")):
            if chave in item: detalhes.append(f"{label}: **{item[chave]}**")
        await ctx.send(embed=discord.Embed(title=f"🛒 {item['nome']}", description="\n".join(detalhes), color=discord.Color.gold()))

    @loja.command(name="comprar")
    async def comprar(self, ctx, *, identificador: str):
        item = self._buscar(identificador)
        if not item:
            await ctx.send("❌ Item não encontrado.")
            return
        uid, gid = str(ctx.author.id), str(ctx.guild.id)
        hunos = db["Hunos"].find_one({"ID": uid, "guild_id": gid})
        saldo = int((hunos or {}).get("carteira", 0) or 0)
        preco = int(item["preco"])
        if saldo < preco:
            await ctx.send(embed=discord.Embed(title="💰 Saldo insuficiente", description=f"Você possui **{saldo:,} Hunos**.\nPreço: **{preco:,} Hunos**.\nFaltam **{preco-saldo:,} Hunos**.", color=discord.Color.red()))
            return
        resultado = db["Hunos"].update_one({"ID": uid, "guild_id": gid, "carteira": {"$gte": preco}}, {"$inc": {"carteira": -preco}})
        if resultado.modified_count == 0:
            await ctx.send("❌ A compra não pôde ser concluída. Seu saldo pode ter mudado.")
            return
        db["Inventários"].update_one({"ID": uid, "guild_id": gid}, {"$setOnInsert": {"ID":uid,"guild_id":gid,"Situação":"ativo","itens":[]}, "$push": {"itens": item["id"]}}, upsert=True)
        await ctx.send(embed=discord.Embed(title="✅ Compra realizada", description=f"Você comprou **{item['nome']}** por **{preco:,} Hunos**.", color=discord.Color.green()))

    @loja.command(name="inventario", aliases=["inv"])
    async def inventario(self, ctx):
        doc = db["Inventários"].find_one({"ID":str(ctx.author.id),"guild_id":str(ctx.guild.id)}) or {}
        itens = doc.get("itens", [])
        nomes = []
        for valor in itens:
            item = self._buscar(valor)
            nomes.append(f"• {item['nome']} (`{valor}`)" if item else f"• `{valor}`")
        await ctx.send(embed=discord.Embed(title=f"🎒 Inventário de {ctx.author.display_name}", description="\n".join(nomes) or "Inventário vazio.", color=discord.Color.blurple()))

async def setup(bot):
    await bot.add_cog(Loja(bot))
