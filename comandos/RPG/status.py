"""Comandos de status com acesso ao MongoDB fora do event loop."""

import asyncio
import datetime
import json
import random
from pathlib import Path

import discord
from discord.ext import commands

from database.python.mongodb import db, run_db
from database.python import status_async as status_db
from comandos.RPG.barra_status import barra_mana, barra_vida, barra_xp
from comandos.RPG.luta import painel

fuso = datetime.timezone(datetime.timedelta(hours=-3))
BASE_DIR = Path(__file__).resolve().parents[2]
RACAS_FILE = BASE_DIR / "database" / "json" / "racas.json"
FOOTER = "Tensura Moon - Korczak Technologies!"


def carregar_racas():
    with open(RACAS_FILE, "r", encoding="utf-8") as arquivo:
        return json.load(arquivo)["racas"]


def sortear_raca():
    racas = carregar_racas()
    return random.choices([r["nome"] for r in racas], weights=[r["chance"] for r in racas], k=1)[0]


def obter_dados_raca(nome_raca):
    return next((r for r in carregar_racas() if r["nome"] == nome_raca), None)


def sortear_atributo():
    faixa = random.choice(["crianca", "muito_fraco", "fraco", "normal", "forte"])
    valores = {"crianca": (0, 50), "muito_fraco": (50, 80), "fraco": (80, 90), "normal": (90, 110), "forte": (110, 130)}
    return random.randint(*valores.get(faixa, (90, 110)))


def aplicar_bonus(valor, bonus):
    return int(valor * (1 + bonus))


def _interface_status(*, membro, titulo, extra, cor, vida="-", mana="-", efeito="Status", turno="-", oponente="-", vida_oponente="-"):
    """Cria a mesma moldura Moon Tensura usada nas telas de combate."""
    embed = painel(
        atacante=membro.display_name,
        ataque=titulo,
        vida=vida,
        mana=mana,
        dano="-",
        efeito=efeito,
        alvo="-",
        turno=turno,
        oponente=oponente,
        vida_oponente=vida_oponente,
        extra=extra,
        cor=cor,
    )
    embed.set_thumbnail(url=membro.display_avatar.url)
    embed.set_footer(text=FOOTER)
    return embed


class Status(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="status")
    async def status(self, ctx, membro: discord.Member = None):
        membro = membro or ctx.author
        jogador = await status_db.obter_status(membro.id, ctx.guild.id)
        if jogador is None:
            embed = _interface_status(
                membro=membro,
                titulo="resultado",
                extra=f"❌ {membro.mention} não possui um personagem registrado.",
                cor=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        vals = {k: jogador.get(k, d) for k, d in {
            "Magiculas": 0, "TP": 0, "Nome": "Não definido", "Raça": "Não definida", "Nivel": 0,
            "XP": 0, "XP_maximo": 0, "Força": 0, "Defesa": 0, "Vitalidade": 0, "Velocidade": 0,
            "Destreza": 0, "Magia": 0, "Sorte": 0, "Vida": 0, "Vida_Maxima": 0,
            "Mana": 0, "Mana Total": 0, "inteligencia": 0, "Situação": "ativo"
        }.items()}
        cor = 0x8B0000 if vals["Situação"] != "morto" else discord.Color.red()
        linhas = [
            f"**👤 Nome:** {membro.display_name}",
            f"**🧬 Personagem:** {vals['Nome']}",
            f"**🧬 Raça:** {vals['Raça']}",
            f"**📈 Nível:** {vals['Nivel']}",
            f"**📌 Situação:** {vals['Situação']}",
            f"**⭐ XP:** {vals['XP']}/{vals['XP_maximo']}",
            f"**❤️ Vida:** {vals['Vida']}/{vals['Vida_Maxima']}",
            f"**💧 Mana:** {vals['Mana']}/{vals['Mana Total']}",
            f"**✨ Magículas:** {vals['Magiculas']}",
            f"**✨ TP:** {vals['TP']}",
            "",
            "**⚔️ ATRIBUTOS**",
            f"**Força:** {vals['Força']} | **Defesa:** {vals['Defesa']}",
            f"**Vitalidade:** {vals['Vitalidade']} | **Velocidade:** {vals['Velocidade']}",
            f"**Destreza:** {vals['Destreza']} | **Inteligência:** {vals['inteligencia']}",
            f"**Magia:** {vals['Magia']} | **Sorte:** {vals['Sorte']}",
        ]
        if vals["Situação"] == "morto":
            linhas.insert(0, "**💀 Este personagem está morto!**")
        cd1 = await status_db.get_cooldown_recuperacao(str(membro.id), str(ctx.guild.id), "descanso")
        cd2 = await status_db.get_cooldown_recuperacao(str(membro.id), str(ctx.guild.id), "meditacao")
        fmt = lambda v: "✅ Disponível" if v == 0 else f"⏰ {int(v)}h"
        linhas.extend([
            "",
            "**🔄 RECUPERAÇÃO**",
            f"**Descanso:** {fmt(cd1)}",
            f"**Meditação:** {fmt(cd2)}",
            f"**XP visual:** {barra_xp(vals['XP'], vals['XP_maximo'])}",
            f"**Vida visual:** {barra_vida(vals['Vida'], vals['Vida_Maxima'])}",
            f"**Mana visual:** {barra_mana(vals['Mana'], vals['Mana Total'])}",
        ])
        embed = _interface_status(
            membro=membro,
            titulo="Status",
            extra="\n".join(linhas),
            cor=cor,
            vida=f"{vals['Vida']}/{vals['Vida_Maxima']}",
            mana=f"{vals['Mana']}/{vals['Mana Total']}",
            efeito=vals["Situação"],
            oponente="Ficha",
            vida_oponente="-",
        )
        await ctx.send(embed=embed)

    @commands.command(name="registrar")
    async def registrar(self, ctx):
        user_id, guild_id = str(ctx.author.id), str(ctx.guild.id)
        player = db["Jogadores"]
        jogador = await run_db(player.find_one, {"ID": user_id, "guild_id": guild_id})
        if jogador is None:
            await ctx.send(f"❌ Você não possui uma ficha pendente. Contate um Administrador.")
            return
        if jogador.get("Situação") == "ativo":
            await ctx.send("❌ Você já está registrado.")
            return
        if jogador.get("Situação") != "pendente":
            await ctx.send("❌ Sua ficha não está disponível para registro.")
            return
        try:
            raca = sortear_raca()
            dados_raca = obter_dados_raca(raca)
        except Exception as erro:
            print(f"Erro ao carregar raças: {erro}")
            await ctx.send("❌ **Não foi possível carregar os dados das raças.**")
            return
        if dados_raca is None:
            await ctx.send("❌ Erro: dados da raça não encontrados.")
            return
        base = {n: sortear_atributo() for n in ("Força", "Defesa", "Vitalidade", "Velocidade", "Destreza", "Magia", "Sorte", "inteligencia")}
        bonus = dados_raca.get("bonus", {})
        a = {n: aplicar_bonus(v, bonus.get(n, 0)) for n, v in base.items()}
        mag = random.randrange(0, 1001, 100)
        vm = a["Vitalidade"] * 10
        mm = mag * 0.1
        resultado = await run_db(player.update_one, {"_id": jogador["_id"], "Situação": "pendente"}, {"$set": {
            "Raça": raca, "Nivel": 1, "XP": 0, "XP_maximo": 100, "TP": 0,
            "Força": a["Força"], "Defesa": a["Defesa"], "Vitalidade": a["Vitalidade"], "Velocidade": a["Velocidade"],
            "Destreza": a["Destreza"], "Magia": a["Magia"], "Sorte": a["Sorte"], "inteligencia": a["inteligencia"],
            "Magiculas": mag, "Vida": vm, "Vida_Maxima": vm, "Mana": mm, "Mana Total": mm,
            "Situação": "ativo", "mortes": 0, "ultimo_treino": {}, "ultima_recuperacao": {}
        }})
        if resultado.modified_count == 0:
            await ctx.send("❌ Não foi possível registrar sua ficha. Ela pode já ter sido registrada.")
            return
        e = discord.Embed(title="| Registro concluído", description=f"**{ctx.author.mention}**, seu personagem foi criado!", color=discord.Color.green(), timestamp=discord.utils.utcnow())
        e.add_field(name="🧬 Raça", value=f"**{raca}**", inline=False)
        e.add_field(name="❤️ Vida", value=f"`{barra_vida(vm, vm)}`\n**{vm}/{vm}**", inline=False)
        e.add_field(name="💧 Mana", value=f"`{barra_mana(mm, mm)}`\n**{mm}/{mm}**", inline=False)
        e.add_field(name="✨ Magículas", value=f"**{mag}**", inline=False)
        e.add_field(name="⚔️ Atributos", value=f"**Força:** {a['Força']}\n**Defesa:** {a['Defesa']}\n**Vitalidade:** {a['Vitalidade']}\n**Velocidade:** {a['Velocidade']}\n**Destreza:** {a['Destreza']}\n**Magia:** {a['Magia']}\n**Sorte:** {a['Sorte']}\n**Inteligência:** {a['inteligencia']}", inline=False)
        e.add_field(name="📊 Informações", value="**Nível:** 1\n**XP:** 0\n**TP:** 0", inline=False)
        e.set_thumbnail(url=ctx.author.display_avatar.url)
        e.set_footer(text=FOOTER)
        await ctx.send(embed=e)

    @commands.command(name="desregistrar", aliases=["desregist", "dregistrar", "dregist"])
    @commands.has_permissions(manage_roles=True)
    async def desregistrar(self, ctx, membro: discord.Member = None):
        if membro is None:
            embed = discord.Embed(title="| Desregistrar", description="❌ Você precisa mencionar um jogador.\n\nUse: `!desregistrar @usuário`", color=discord.Color.red(), timestamp=discord.utils.utcnow())
            embed.set_footer(text=FOOTER)
            await ctx.send(embed=embed)
            return
        p = db["Jogadores"]
        j = await run_db(p.find_one, {"ID": str(membro.id), "guild_id": str(ctx.guild.id)})
        if j is None or j.get("Situação") != "ativo":
            embed = discord.Embed(title="| Desregistrar", description="❌ Esse jogador não possui um personagem ativo.", color=discord.Color.red(), timestamp=discord.utils.utcnow())
            embed.set_thumbnail(url=membro.display_avatar.url)
            embed.set_footer(text=FOOTER)
            await ctx.send(embed=embed)
            return
        r = await run_db(p.update_one, {"_id": j["_id"], "Situação": "ativo"}, {"$set": {"Nome": None, "Raça": None, "Nivel": 0, "XP": 0, "XP_maximo": 0, "TP": 0, "Força": 0, "Defesa": 0, "Vitalidade": 0, "Velocidade": 0, "Destreza": 0, "Magia": 0, "Sorte": 0, "inteligencia": 0, "Magiculas": 0, "Vida": 0, "Vida_Maxima": 0, "Mana": 0, "Mana Total": 0, "Situação": "pendente", "ultimo_treino": {}, "ultima_recuperacao": {}}})
        if r.modified_count == 0:
            embed = discord.Embed(title="| Desregistrar", description="❌ Não foi possível desregistrar esse jogador.", color=discord.Color.red(), timestamp=discord.utils.utcnow())
            embed.set_footer(text=FOOTER)
            await ctx.send(embed=embed)
            return
        embed = discord.Embed(title="| Desregistro concluído", description=f"🗑️ O personagem de **{membro.mention}** foi desregistrado com sucesso.\n\nA ficha voltou para o estado **pendente** e poderá ser registrada novamente.", color=discord.Color.orange(), timestamp=discord.utils.utcnow())
        embed.set_thumbnail(url=membro.display_avatar.url)
        embed.set_footer(text=FOOTER)
        await ctx.send(embed=embed)

    async def _recuperacao(self, ctx, tipo, titulo, cor, footer):
        uid, gid = str(ctx.author.id), str(ctx.guild.id)
        if await status_db.esta_morto(uid, gid):
            await ctx.send(embed=_interface_status(membro=ctx.author, titulo="resultado", extra=f"❌ Você está morto. Não pode {tipo}.", cor=discord.Color.red()))
            return
        r = await status_db.recuperar_mana(uid, gid, tipo)
        if not r["sucesso"]:
            await ctx.send(embed=_interface_status(membro=ctx.author, titulo="resultado", extra=f"❌ {r['mensagem']}", cor=discord.Color.red()))
            return
        extra = (
            f"**{r['mensagem']}**\n\n"
            f"**💙 Mana Recuperada:** +{r['mana_recuperada']} ({r['percentual']:.0f}% da mana total)\n"
            f"**💙 Mana Atual:** {r['mana_atual']}/{r['mana_maxima']}\n"
            f"**⏰ Cooldown:** {r['cooldown_horas']} horas"
        )
        e = _interface_status(
            membro=ctx.author,
            titulo=titulo,
            extra=extra,
            cor=cor,
            mana=f"{r['mana_atual']}/{r['mana_maxima']}",
            efeito="Recuperação",
            oponente="Mana",
            vida_oponente="-",
        )
        e.set_footer(text=footer)
        await ctx.send(embed=e)

    @commands.command(name="descanso", aliases=["desc"])
    async def descanso(self, ctx):
        await self._recuperacao(ctx, "descanso", "🛌 Descanso", discord.Color.blue(), "Use !meditacao para recuperar mais mana")

    @commands.command(name="meditacao", aliases=["meditar", "med"])
    async def meditacao(self, ctx):
        await self._recuperacao(ctx, "meditacao", "🧘 Meditação", discord.Color.purple(), "Use !descanso para uma recuperação mais rápida")

    @commands.command(name="recuperacao", aliases=["rec", "cooldownmana"])
    async def recuperacao(self, ctx):
        uid, gid = str(ctx.author.id), str(ctx.guild.id)
        a, b = await asyncio.gather(status_db.get_cooldown_recuperacao(uid, gid, "descanso"), status_db.get_cooldown_recuperacao(uid, gid, "meditacao"))
        fmt = lambda v: "✅ Disponível" if v == 0 else (f"⏰ {int(v*60)} minutos" if v < 1 else f"⏰ {int(v)} horas")
        extra = f"**🛌 Descanso:** {fmt(a)}\n**🧘 Meditação:** {fmt(b)}\n\n**Use !descanso ou !meditacao para recuperar mana.**"
        e = _interface_status(membro=ctx.author, titulo="⏰ Recuperação", extra=extra, cor=discord.Color.blue(), efeito="Cooldown", oponente="Recuperação")
        await ctx.send(embed=e)


async def setup(bot):
    await bot.add_cog(Status(bot))
