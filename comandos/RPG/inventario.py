"""Inventário persistente, equipamentos e ataques com armas."""

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


def _carregar_inventario_sync(uid, gid):
    return db["Inventários"].find_one({"ID": str(uid), "guild_id": str(gid)}) or {}


async def _carregar_equipamento_participante(participante, user_id, guild_id):
    if db is None or participante.get("tipo") != "jogador":
        return participante
    doc = await run_db(_carregar_inventario_sync, user_id, guild_id)
    catalogo = _carregar_itens()
    equipados = list(doc.get("equipados", []))[:2] if doc else []
    dano_arma = 0
    nomes_armas = []
    for item_id in equipados:
        item = catalogo.get(str(item_id))
        if not item:
            continue
        for chave, destino in (("forca", "Força"), ("defesa", "Defesa"), ("vitalidade", "Vitalidade"), ("velocidade", "Velocidade"), ("destreza", "Destreza"), ("magia", "Magia"), ("sorte", "Sorte")):
            if chave in item:
                participante[destino] = int(float(participante.get(destino, 0) or 0) + float(item[chave] or 0))
        if "dano" in item:
            dano_arma += int(item.get("dano", 0) or 0)
            nomes_armas.append(item.get("nome", str(item_id)))
    participante["dano_arma"] = dano_arma
    participante["arma_nome"] = ", ".join(nomes_armas)
    participante["defesa"] = int(float(participante.get("Força", 0) or 0) + float(participante.get("Defesa", 0) or 0))
    if participante.get("Vitalidade") is not None:
        participante["vida_maxima"] = int(float(participante.get("Vitalidade", 0) or 0) * 10)
        participante["vida"] = min(int(participante.get("vida", 0) or 0), participante["vida_maxima"])
    return participante


class Inventario(commands.Cog):
    LIMITE_EQUIPADOS = 2

    def __init__(self, bot):
        self.bot = bot
        self.itens_catalogo = _carregar_itens()

    async def cog_load(self):
        self._patch_combate()
        self._patch_status()

    def _patch_combate(self):
        import comandos.RPG.luta as luta_mod
        if getattr(luta_mod, "_INVENTARIO_PATCHED", False):
            return
        original_criar = luta_mod._criar_participante
        async def criar_participante_com_equipamento(user_id, guild_id):
            participante = await original_criar(user_id, guild_id)
            if participante:
                await _carregar_equipamento_participante(participante, user_id, guild_id)
            return participante
        luta_mod._criar_participante = criar_participante_com_equipamento
        luta_mod._INVENTARIO_PATCHED = True

    def _patch_status(self):
        if getattr(commands.Context, "_INVENTARIO_STATUS_PATCHED", False):
            return
        original_send = commands.Context.send
        async def send_com_equipamentos(ctx, content=None, *, embed=None, **kwargs):
            if embed is not None and getattr(embed, "title", "") == "📊 Status do Personagem" and getattr(ctx, "guild", None):
                doc = await run_db(_carregar_inventario_sync, ctx.author.id, ctx.guild.id)
                equipados = list(doc.get("equipados", []))[:2] if doc else []
                linhas = []
                for item_id in equipados:
                    item = self.itens_catalogo.get(str(item_id))
                    if not item:
                        continue
                    efeitos = []
                    for chave, emoji in (("dano", "⚔️"), ("defesa", "🛡️"), ("forca", "💪"), ("vitalidade", "❤️"), ("velocidade", "💨"), ("destreza", "🎯"), ("magia", "✨"), ("sorte", "🍀")):
                        if chave in item:
                            efeitos.append(f"{emoji} {item[chave]}")
                    linhas.append(f"**{item.get('nome', item_id)}**\n{' • '.join(efeitos) if efeitos else 'Equipado'}")
                valor = "\n\n".join(linhas) if linhas else "Nenhum item equipado."
                indice = next((i for i, campo in enumerate(embed.fields) if campo.name == "⚔️ Atributos"), len(embed.fields))
                embed.insert_field_at(indice, name=f"⚔️ Equipamentos ({len(equipados)}/2)", value=valor, inline=True)
            return await original_send(ctx, content=content, embed=embed, **kwargs)
        commands.Context.send = send_com_equipamentos
        commands.Context._INVENTARIO_STATUS_PATCHED = True

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
        await run_db(db["Inventários"].update_one, {"ID": str(uid), "guild_id": str(gid)}, {"$set": {"equipados": equipados, "Situação": "ativo"}}, upsert=True)

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

    def _descricao_equipado(self, item):
        partes = []
        for chave, emoji in (("dano", "⚔️"), ("defesa", "🛡️"), ("forca", "💪"), ("vitalidade", "❤️"), ("velocidade", "💨"), ("destreza", "🎯"), ("magia", "✨"), ("sorte", "🍀")):
            if chave in item:
                partes.append(f"{emoji} {item[chave]}")
        return " • ".join(partes) or "Equipamento"

    @staticmethod
    def _eh_equipavel(item):
        return any(chave in item for chave in ("dano", "defesa", "forca", "vitalidade", "velocidade", "destreza", "magia", "sorte"))

    @commands.command(name="inventario", aliases=["inv", "mochila"])
    async def inventario(self, ctx):
        if not ctx.guild:
            return
        doc = await self._obter(ctx.author.id, ctx.guild.id)
        itens = doc.get("itens", [])
        equipados = [str(x) for x in doc.get("equipados", [])][:2]
        linhas = []
        for index, item_id in enumerate(itens, 1):
            item = self._catalogo(item_id)
            nome = item.get("nome", item_id) if item else item_id
            marca = " ⚔️ EQUIPADO" if str(item_id) in equipados else ""
            linhas.append(f"`{index}` **{nome}** (`{item_id}`){marca}")
        embed = discord.Embed(title=f"🎒 Inventário — {ctx.author.display_name}", description="\n".join(linhas) or "Seu inventário está vazio.", color=discord.Color.blurple())
        eq = "\n\n".join(f"• **{self._catalogo(x).get('nome', x)}** — {self._descricao_equipado(self._catalogo(x))}" for x in equipados if self._catalogo(x)) or "Nenhum item equipado."
        embed.add_field(name=f"⚔️ Equipados ({len(equipados)}/2)", value=eq, inline=False)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="!equipar <id> • !desequipar <id> • !usaritem <id>")
        await ctx.send(embed=embed)

    @commands.command(name="equipar")
    async def equipar(self, ctx, *, item_id: str):
        if not ctx.guild:
            return
        doc = await self._obter(ctx.author.id, ctx.guild.id)
        alvo = self._resolver_item(doc["itens"], item_id)
        item = self._catalogo(alvo) if alvo else None
        if not item or not self._eh_equipavel(item):
            await ctx.send("❌ Esse item não é equipável ou você não o possui.")
            return
        equipados = [str(x) for x in doc.get("equipados", [])]
        if str(alvo) in equipados:
            await ctx.send("❌ Esse item já está equipado.")
            return
        if len(equipados) >= self.LIMITE_EQUIPADOS:
            await ctx.send("❌ Você já possui **2 itens equipados**. Desequipe um primeiro.")
            return
        equipados.append(str(alvo))
        await self._salvar_equipados(ctx.author.id, ctx.guild.id, equipados)
        await ctx.send(f"✅ **{item['nome']}** equipado. ({len(equipados)}/2)")

    @commands.command(name="desequipar", aliases=["dequipar"])
    async def desequipar(self, ctx, *, item_id: str):
        if not ctx.guild:
            return
        doc = await self._obter(ctx.author.id, ctx.guild.id)
        alvo = self._resolver_item(doc["itens"], item_id)
        equipados = [str(x) for x in doc.get("equipados", [])]
        if alvo is None or str(alvo) not in equipados:
            await ctx.send("❌ Esse item não está equipado.")
            return
        equipados.remove(str(alvo))
        await self._salvar_equipados(ctx.author.id, ctx.guild.id, equipados)
        item = self._catalogo(alvo)
        await ctx.send(f"✅ **{item.get('nome', alvo)}** foi desequipado.")

    @commands.command(name="usaritem", aliases=["item"])
    async def usaritem(self, ctx, *, item_id: str):
        if not ctx.guild:
            return
        doc = await self._obter(ctx.author.id, ctx.guild.id)
        alvo = self._resolver_item(doc["itens"], item_id)
        item = self._catalogo(alvo) if alvo else None
        if not item:
            await ctx.send("❌ Você não possui esse item.")
            return
        if self._eh_equipavel(item):
            await self._equipar(ctx, alvo)
            return
        cura = int(item.get("cura", 0) or 0)
        mana = int(item.get("mana", 0) or 0)
        if not cura and not mana:
            await ctx.send("❌ Esse item não possui uso direto implementado.")
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
        itens = list(doc["itens"])
        itens.remove(alvo)
        equipados = [x for x in doc.get("equipados", []) if str(x) != str(alvo)]
        await run_db(db["Inventários"].update_one, {"_id": doc["_id"]}, {"$set": {"itens": itens, "equipados": equipados}})
        await ctx.send(embed=discord.Embed(title="🧪 Item utilizado", description=f"**{item['nome']}** consumido.\n❤️ {vida} → {nova_vida}\n💧 {mana_atual} → {nova_mana}", color=discord.Color.green()))

    async def _equipar(self, ctx, item_id):
        doc = await self._obter(ctx.author.id, ctx.guild.id)
        alvo = self._resolver_item(doc["itens"], item_id)
        item = self._catalogo(alvo) if alvo else None
        if not item or not self._eh_equipavel(item):
            await ctx.send("❌ Esse item não é equipável.")
            return
        equipados = [str(x) for x in doc.get("equipados", [])]
        if str(alvo) in equipados:
            await ctx.send("❌ Esse item já está equipado.")
            return
        if len(equipados) >= self.LIMITE_EQUIPADOS:
            await ctx.send("❌ Você já possui **2 itens equipados**.")
            return
        equipados.append(str(alvo))
        await self._salvar_equipados(ctx.author.id, ctx.guild.id, equipados)
        await ctx.send(f"✅ **{item['nome']}** equipado. ({len(equipados)}/2)")

    async def _ataque_com_arma(self, ctx, estilo="atacar"):
        if not ctx.guild:
            return
        luta = self.bot.get_cog("Luta")
        if not luta:
            await ctx.send("❌ Sistema de luta não está carregado.")
            return
        combate = luta._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            await ctx.send("❌ Não há combate ativo.")
            return
        if combate.get("fase") != "ataque":
            await ctx.send("❌ O ataque anterior ainda precisa ser resolvido.")
            return
        atacante = luta._obter_atacante(combate)
        defensor = luta._obter_defensor(combate)
        if atacante.get("tipo") != "jogador" or str(atacante.get("id")) != str(ctx.author.id):
            await ctx.send("❌ Não é sua vez de atacar.")
            return
        doc = await self._obter(ctx.author.id, ctx.guild.id)
        equipados = [str(x) for x in doc.get("equipados", [])][:2]
        armas = [self._catalogo(x) for x in equipados if self._catalogo(x) and "dano" in self._catalogo(x)]
        if not armas:
            await ctx.send("❌ Você precisa equipar uma arma primeiro. Use `!equipar <id>`.")
            return
        arma = armas[0]
        nome = str(arma.get("nome", "Arma"))
        texto = str(estilo).casefold()
        cortante = any(x in nome.casefold() for x in ("espada", "katana", "adaga", "machado", "foice", "sabre", "rapieira", "rapiera", "lança", "lanca"))
        if texto == "corte" and not cortante:
            await ctx.send("❌ Essa arma não possui um ataque de **corte**.")
            return
        if texto == "disparo" and not any(x in nome.casefold() for x in ("arco", "besta")):
            await ctx.send("❌ Essa arma não é adequada para **disparo**.")
            return
        ataque_nome = {"corte": "⚔️ Corte", "estocada": "🗡️ Estocada", "golpe": "🔨 Golpe", "disparo": "🏹 Disparo"}.get(texto, f"⚔️ Ataque com {nome}")
        combate["ataque_pendente"] = {"tipo": "soco", "nome": ataque_nome + f" — {nome}", "atacante_id": atacante["id"], "defensor_id": defensor["id"], "magia": False, "usar_arma": True, "arma_id": str(arma.get("id", equipados[0]))}
        atacante["_ataque_atual"] = combate["ataque_pendente"]
        combate["fase"] = "defesa"
        await luta._anunciar_ataque(ctx)

    @commands.command(name="corte")
    async def corte(self, ctx):
        await self._ataque_com_arma(ctx, "corte")

    @commands.command(name="estocada")
    async def estocada(self, ctx):
        await self._ataque_com_arma(ctx, "estocada")

    @commands.command(name="golpear")
    async def golpear(self, ctx):
        await self._ataque_com_arma(ctx, "golpe")

    @commands.command(name="disparo")
    async def disparo(self, ctx):
        await self._ataque_com_arma(ctx, "disparo")

    @commands.command(name="atacar")
    async def atacar(self, ctx):
        await self._ataque_com_arma(ctx, "atacar")


async def setup(bot):
    await bot.add_cog(Inventario(bot))
