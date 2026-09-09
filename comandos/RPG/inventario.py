"""Inventário persistente, equipamentos e ataques com armas."""

import asyncio
import json
from pathlib import Path

import discord
from discord.ext import commands

from database.python.mongodb import db, run_db

BASE_DIR = Path(__file__).resolve().parents[2]
LOJA_FILE = BASE_DIR / "database" / "json" / "loja.json"


def _carregar_itens():
    try:
        dados = json.loads(LOJA_FILE.read_text(encoding="utf-8"))
        return {str(item["id"]): item for itens in dados.get("categorias", {}).values() for item in itens}
    except Exception as erro:
        print(f"[INVENTARIO] Erro ao carregar loja: {erro}")
        return {}


class Inventario(commands.Cog):
    LIMITE_EQUIPADOS = 2

    def __init__(self, bot):
        self.bot = bot
        self.itens_catalogo = _carregar_itens()
        self._patch_combate()

    def _patch_combate(self):
        luta = self.bot.get_cog("Luta")
        if not luta or getattr(luta.__class__, "_inventario_patched", False):
            return
        original = luta.__class__._criar_participante
        # O método atual de Luta é assíncrono e já carrega os atributos do jogador.
        async def criar_participante_com_equipamento(self, user_id, guild_id):
            participante = await original(self, user_id, guild_id)
            if participante:
                await _carregar_equipamento_participante(participante, user_id, guild_id)
            return participante
        luta.__class__._criar_participante = criar_participante_com_equipamento
        luta.__class__._inventario_patched = True

    async def cog_load(self):
        self._patch_combate()

    def _catalogo(self, item_id):
        return self.itens_catalogo.get(str(item_id))

    async def _obter(self, uid, gid):
        doc = await run_db(db["Inventários"].find_one, {"ID": str(uid), "guild_id": str(gid)})
        if not doc:
            doc = {"ID": str(uid), "guild_id": str(gid), "Situação": "ativo", "itens": [], "equipados": []}
            await run_db(db["Inventários"].insert_one, doc)
        doc.setdefault("itens", [])
        doc.setdefault("equipados", [])
        return doc

    async def _salvar_equipados(self, uid, gid, equipados):
        await run_db(db["Inventários"].update_one,
                     {"ID": str(uid), "guild_id": str(gid)},
                     {"$set": {"equipados": equipados, "Situação": "ativo"}}, upsert=True)

    def _possui(self, itens, item_id):
        alvo = str(item_id).casefold()
        for valor in itens:
            if str(valor).casefold() == alvo:
                return True
        return False

    def _descricao_equipado(self, item):
        partes = []
        for chave, nome in (("dano", "⚔️"), ("defesa", "🛡️"), ("forca", "💪"), ("vitalidade", "❤️"), ("velocidade", "💨"), ("destreza", "🎯"), ("magia", "✨"), ("sorte", "🍀")):
            if item.get(chave) is not None:
                partes.append(f"{nome} {item[chave]}")
        return " • ".join(partes) or "Equipamento"

    @commands.command(name="inventario", aliases=["inv", "mochila"])
    async def inventario(self, ctx):
        if not ctx.guild:
            return
        doc = await self._obter(ctx.author.id, ctx.guild.id)
        itens = doc.get("itens", [])
        equipados = [str(x) for x in doc.get("equipados", [])]
        linhas = []
        for index, item_id in enumerate(itens, 1):
            item = self._catalogo(item_id)
            nome = item.get("nome", item_id) if item else item_id
            marca = " ⚔️ EQUIPADO" if str(item_id) in equipados else ""
            linhas.append(f"`{index}` **{nome}** (`{item_id}`){marca}")
        if not linhas:
            linhas.append("Seu inventário está vazio.")
        eq_linhas = []
        for item_id in equipados:
            item = self._catalogo(item_id)
            if item:
                eq_linhas.append(f"• **{item['nome']}** — {self._descricao_equipado(item)}")
        embed = discord.Embed(title=f"🎒 Inventário — {ctx.author.display_name}", description="\n".join(linhas), color=discord.Color.blurple())
        embed.add_field(name=f"⚔️ Equipados ({len(equipados)}/{self.LIMITE_EQUIPADOS})", value="\n".join(eq_linhas) or "Nenhum item equipado.", inline=False)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="Use !inventario equipar <id> • !inventario desequipar <id> • !inventario usar <id>")
        await ctx.send(embed=embed)

    @commands.command(name="equipar")
    async def equipar(self, ctx, *, item_id: str):
        await self._equipar(ctx, item_id)

    @commands.command(name="desequipar", aliases=["dequipar"])
    async def desequipar(self, ctx, *, item_id: str):
        if not ctx.guild:
            return
        doc = await self._obter(ctx.author.id, ctx.guild.id)
        alvo = self._resolver_item(doc.get("itens", []), item_id)
        if alvo is None:
            await ctx.send("❌ Você não possui esse item.")
            return
        equipados = [str(x) for x in doc.get("equipados", [])]
        if str(alvo) not in equipados:
            await ctx.send("❌ Esse item não está equipado.")
            return
        equipados.remove(str(alvo))
        await self._salvar_equipados(ctx.author.id, ctx.guild.id, equipados)
        item = self._catalogo(alvo)
        await ctx.send(f"✅ **{item.get('nome', alvo) if item else alvo}** foi desequipado.")

    @commands.command(name="usaritem", aliases=["item"])
    async def usaritem(self, ctx, *, item_id: str):
        if not ctx.guild:
            return
        doc = await self._obter(ctx.author.id, ctx.guild.id)
        alvo = self._resolver_item(doc.get("itens", []), item_id)
        if alvo is None:
            await ctx.send("❌ Você não possui esse item.")
            return
        item = self._catalogo(alvo)
        if not item:
            await ctx.send("❌ Item sem definição funcional.")
            return
        if self._eh_equipavel(item):
            await self._equipar(ctx, alvo)
            return
        cura = int(item.get("cura", 0) or 0)
        mana = int(item.get("mana", 0) or 0)
        if not cura and not mana:
            await ctx.send("❌ Esse item não pode ser usado diretamente.")
            return
        jogador = await run_db(db["Jogadores"].find_one, {"ID": str(ctx.author.id), "guild_id": str(ctx.guild.id)})
        if not jogador:
            await ctx.send("❌ Personagem não encontrado.")
            return
        vida = int(jogador.get("Vida", 0) or 0)
        vida_max = int(jogador.get("Vida_Maxima", vida) or vida)
        mana_atual = int(float(jogador.get("Mana", 0) or 0))
        mana_max = int(float(jogador.get("Mana Total", mana_atual) or mana_atual))
        nova_vida = min(vida_max, vida + cura)
        nova_mana = min(mana_max, mana_atual + mana)
        await run_db(db["Jogadores"].update_one, {"_id": jogador["_id"]}, {"$set": {"Vida": nova_vida, "Mana": nova_mana}})
        itens = list(doc.get("itens", []))
        itens.remove(alvo)
        await run_db(db["Inventários"].update_one, {"_id": doc["_id"]}, {"$set": {"itens": itens}})
        item_nome = item.get("nome", alvo)
        await ctx.send(embed=discord.Embed(title="🧪 Item utilizado", description=f"**{item_nome}** foi consumido.\n❤️ Vida: **{vida} → {nova_vida}**\n💧 Mana: **{mana_atual} → {nova_mana}**", color=discord.Color.green()))

    async def _equipar(self, ctx, item_id):
        if not ctx.guild:
            return
        doc = await self._obter(ctx.author.id, ctx.guild.id)
        alvo = self._resolver_item(doc.get("itens", []), item_id)
        if alvo is None:
            await ctx.send("❌ Você não possui esse item.")
            return
        item = self._catalogo(alvo)
        if not item or not self._eh_equipavel(item):
            await ctx.send("❌ Esse item não é equipável.")
            return
        equipados = [str(x) for x in doc.get("equipados", [])]
        if str(alvo) in equipados:
            await ctx.send("❌ Esse item já está equipado.")
            return
        if len(equipados) >= self.LIMITE_EQUIPADOS:
            await ctx.send("❌ Você já possui **2 itens equipados**. Desequipe um item primeiro.")
            return
        equipados.append(str(alvo))
        await self._salvar_equipados(ctx.author.id, ctx.guild.id, equipados)
        await ctx.send(embed=discord.Embed(title="⚔️ Equipamento alterado", description=f"**{item['nome']}** foi equipado.\n\nEquipados: **{len(equipados)}/{self.LIMITE_EQUIPADOS}**", color=discord.Color.green()))

    def _resolver_item(self, itens, valor):
        valor = str(valor).strip()
        if valor.isdigit() and 1 <= int(valor) <= len(itens):
            return str(itens[int(valor) - 1])
        alvo = valor.casefold()
        for item_id in itens:
            item = self._catalogo(item_id)
            if str(item_id).casefold() == alvo or (item and str(item.get("nome", "")).casefold() == alvo):
                return str(item_id)
        return None

    @staticmethod
    def _eh_equipavel(item):
        return any(chave in item for chave in ("dano", "defesa", "forca", "vitalidade", "velocidade", "destreza", "magia", "sorte"))


def _carregar_inventario_sync(uid, gid):
    return db["Inventários"].find_one({"ID": str(uid), "guild_id": str(gid)}) or {}


async def _carregar_equipamento_participante(participante, user_id, guild_id):
    if db is None or participante.get("tipo") != "jogador":
        return participante
    doc = await run_db(_carregar_inventario_sync, user_id, guild_id)
    catalogo = _carregar_itens()
    equipados = doc.get("equipados", []) if doc else []
    dano_arma = 0
    nome_arma = ""
    for item_id in equipados[:2]:
        item = catalogo.get(str(item_id))
        if not item:
            continue
        for chave in ("forca", "defesa", "vitalidade", "velocidade", "destreza", "magia", "sorte"):
            if chave in item:
                chave_destino = {"forca": "Força", "defesa": "Defesa", "vitalidade": "Vitalidade", "velocidade": "Velocidade", "destreza": "Destreza", "magia": "Magia", "sorte": "Sorte"}[chave]
                participante[chave_destino] = int(float(participante.get(chave_destino, 0) or 0) + float(item[chave] or 0))
        if "dano" in item:
            dano_arma += int(item.get("dano", 0) or 0)
            nome_arma = item.get("nome", str(item_id))
    participante["dano_arma"] = dano_arma
    participante["arma_nome"] = nome_arma
    participante["defesa"] = int(float(participante.get("Força", 0) or 0) + float(participante.get("Defesa", 0) or 0))
    participante["vida_maxima"] = int(float(participante.get("Vitalidade", 0) or 0) * 10) if participante.get("Vitalidade") is not None else participante.get("vida_maxima", 0)
    return participante


async def setup(bot):
    await bot.add_cog(Inventario(bot))
