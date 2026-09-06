"""Comandos de status com acesso ao MongoDB fora do event loop."""

import datetime
import json
import random
from pathlib import Path

import discord
from discord.ext import commands

from database.python.mongodb import db, run_db
from database.python import status_async as status_db
from comandos.RPG.barra_status import barra_mana, barra_vida, barra_xp

fuso = datetime.timezone(datetime.timedelta(hours=-3))
BASE_DIR = Path(__file__).resolve().parents[2]
RACAS_FILE = BASE_DIR / "database" / "json" / "racas.json"


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


class Status(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="status")
    async def status(self, ctx, membro: discord.Member = None):
        if membro is None:
            membro = ctx.author
        jogador = await status_db.obter_status(membro.id, ctx.guild.id)
        if jogador is None:
            embed = discord.Embed(title="| Erro", description=f"**{membro.mention} não possui um personagem registrado.**", color=discord.Color.red(), timestamp=discord.utils.utcnow())
            embed.set_thumbnail(url=membro.display_avatar.url)
            embed.set_footer(text="Tensura Moon - Korczak Technologies!")
            await ctx.send(embed=embed)
            return
        magiculas = jogador.get("Magiculas", 0); nome = jogador.get("Nome", "Não definido"); raca = jogador.get("Raça", "Não definida")
        nivel = jogador.get("Nivel", 0); xp = jogador.get("XP", 0); xp_max = jogador.get("XP_maximo", 0)
        forca = jogador.get("Força", 0); defesa = jogador.get("Defesa", 0); velocidade = jogador.get("Velocidade", 0); destreza = jogador.get("Destreza", 0)
        magia = jogador.get("Magia", 0); sorte = jogador.get("Sorte", 0); vida = jogador.get("Vida", 0); vida_maxima = jogador.get("Vida_Maxima", 0)
        mana = jogador.get("Mana", 0); mana_maxima = jogador.get("Mana Total", 0); inteligencia = jogador.get("inteligencia", 0); situacao = jogador.get("Situação", "ativo")
        embed = discord.Embed(title="📊 Status do Personagem", color=0x8B0000 if situacao != "morto" else discord.Color.red(), timestamp=discord.utils.utcnow())
        embed.set_thumbnail(url=membro.display_avatar.url)
        if situacao == "morto": embed.description = "💀 **Este personagem está morto!**"
        embed.add_field(name="👤 Personagem", value=f"**Nome:** {nome}\n**Raça:** {raca}\n**Nível:** {nivel}\n**Situação:** {situacao}", inline=False)
        embed.add_field(name=":star: XP", value=f"{barra_xp(xp, xp_max)}\n**{xp}/{xp_max}**", inline=False)
        embed.add_field(name="❤️ Vida", value=f"{barra_vida(vida, vida_maxima)}\n**{vida}/{vida_maxima}**", inline=False)
        embed.add_field(name="💧 Mana", value=f"{barra_mana(mana, mana_maxima)}\n**{mana}/{mana_maxima}**", inline=False)
        embed.add_field(name="✨ Magiculas", value=f"**{magiculas}**", inline=False)
        embed.add_field(name="⚔️ Atributos", value=f"**Força:** {forca}\n**Defesa:** {defesa}\n**Destreza:** {destreza}\n**Velocidade:** {velocidade}\n**Inteligência:** {inteligencia}\n**Magia:** {magia}\n**Sorte:** {sorte}", inline=False)
        cd1 = await status_db.get_cooldown_recuperacao(str(membro.id), str(ctx.guild.id), "descanso"); cd2 = await status_db.get_cooldown_recuperacao(str(membro.id), str(ctx.guild.id), "meditacao")
        s1 = "✅ Disponível" if cd1 == 0 else f"⏰ {int(cd1)}h"; s2 = "✅ Disponível" if cd2 == 0 else f"⏰ {int(cd2)}h"
        embed.add_field(name="🔄 Recuperação", value=f"**Descanso:** {s1}\n**Meditação:** {s2}", inline=False)
        embed.set_footer(text="Tensura Moon - Korczak Technologies!")
        embed.set_image(url="https://media.discordapp.net/attachments/1543063886939299962/1543811582537105478/ChatGPT_Image_29_de_ago._de_2026_18_39_01.png?ex=6a96e2d3&is=6a959153&hm=400fd5cd195a8a13aa97386a0208a39b675b93e657b1b1afeeba08a4533cc335&=&format=webp&quality=lossless&width=1280&height=511")
        await ctx.send(embed=embed)

    @commands.command(name="registrar")
    async def registrar(self, ctx):
        user_id, guild_id = str(ctx.author.id), str(ctx.guild.id); player = db["Jogadores"]
        jogador = await run_db(player.find_one, {"ID": user_id, "guild_id": guild_id})
        if jogador is None: await ctx.send("❌ Você não possui uma ficha pendente. Contate um Administrador."); return
        if jogador.get("Situação") == "ativo": await ctx.send("❌ Você já está registrado."); return
        if jogador.get("Situação") != "pendente": await ctx.send("❌ Sua ficha não está disponível para registro."); return
        try: raca = sortear_raca(); dados_raca = obter_dados_raca(raca)
        except Exception as erro: print(f"Erro ao carregar raças: {erro}"); await ctx.send("❌ **Não foi possível carregar os dados das raças.**"); return
        if dados_raca is None: await ctx.send("❌ Erro: dados da raça não encontrados."); return
        base = {n: sortear_atributo() for n in ("Força", "Defesa", "Vitalidade", "Velocidade", "Destreza", "Magia", "Sorte", "inteligencia")}; bonus = dados_raca.get("bonus", {})
        atributos = {n: aplicar_bonus(v, bonus.get(n, 0)) for n, v in base.items()}; magiculas = random.randrange(0, 1001, 100); vida_maxima = atributos["Vitalidade"] * 10; vida = vida_maxima; mana_maxima = magiculas * 0.1; mana = mana_maxima
        resultado = await run_db(player.update_one, {"_id": jogador["_id"], "Situação": "pendente"}, {"$set": {"Raça": raca, "Nivel": 1, "XP": 0, "Força": atributos["Força"], "Defesa": atributos["Defesa"], "Vitalidade": atributos["Vitalidade"], "Velocidade": atributos["Velocidade"], "Destreza": atributos["Destreza"], "Magia": atributos["Magia"], "Sorte": atributos["Sorte"], "inteligencia": atributos["inteligencia"], "Magiculas": magiculas, "Vida": vida, "Vida_Maxima": vida_maxima, "Mana": mana, "Mana Total": mana_maxima, "Situação": "ativo", "mortes": 0, "ultimo_treino": {}, "ultima_recuperacao": {}}})
        if resultado.modified_count == 0: await ctx.send("❌ Não foi possível registrar sua ficha. Ela pode já ter sido registrada."); return
        embed = discord.Embed(title="| Registro concluído", description=f"**{ctx.author.mention}**, seu personagem foi criado!", color=discord.Color.green(), timestamp=discord.utils.utcnow())
        embed.add_field(name="🧬 Raça", value=f"**{raca}**", inline=False); embed.add_field(name="❤️ Vida", value=f"`{barra_vida(vida, vida_maxima)}`\n**{vida}/{vida_maxima}**", inline=False); embed.add_field(name="💧 Mana", value=f"`{barra_mana(mana, mana_maxima)}`\n**{mana}/{mana_maxima}**", inline=False); embed.add_field(name="✨ Magículas", value=f"**{magiculas}**", inline=False)
        embed.add_field(name="⚔️ Atributos", value=f"**Força:** {atributos['Força']}\n**Defesa:** {atributos['Defesa']}\n**Vitalidade:** {atributos['Vitalidade']}\n**Velocidade:** {atributos['Velocidade']}\n**Destreza:** {atributos['Destreza']}\n**Magia:** {atributos['Magia']}\n**Sorte:** {atributos['Sorte']}\n**Inteligência:** {atributos['inteligencia']}", inline=False); embed.add_field(name="📊 Informações", value="**Nível:** 1\n**XP:** 0", inline=False); embed.set_thumbnail(url=ctx.author.display_avatar.url); embed.set_footer(text="Tensura Moon - Korczak Technologies!"); await ctx.send(embed=embed)

    @commands.command(name="desregistrar", aliases=["desregist", "dregistrar", "dregist"])
    @commands.has_permissions(manage_roles=True)
    async def desregistrar(self, ctx, membro: discord.Member = None):
        if membro is None: await ctx.send("❌ Você precisa mencionar um jogador.\nUse: `!desregistrar @usuário`"); return
        player = db["Jogadores"]; jogador = await run_db(player.find_one, {"ID": str(membro.id), "guild_id": str(ctx.guild.id)})
        if jogador is None: await ctx.send("❌ Esse usuário não possui uma ficha."); return
        if jogador.get("Situação") != "ativo": await ctx.send("❌ Esse jogador não está registrado."); return
        resultado = await run_db(player.update_one, {"_id": jogador["_id"], "Situação": "ativo"}, {"$set": {"Nome": None, "Raça": None, "Nivel": 0, "XP": 0, "Força": 0, "Defesa": 0, "Velocidade": 0, "Destreza": 0, "Magia": 0, "Sorte": 0, "Situação": "pendente"}})
        if resultado.modified_count == 0: await ctx.send("❌ Não foi possível desregistrar esse jogador."); return
        embed = discord.Embed(title="| Jogador desregistrado", description=f"**{membro.mention}** foi desregistrado com sucesso.", color=discord.Color.orange(), timestamp=discord.utils.utcnow()); embed.add_field(name="📋 Situação", value="**Pendente**", inline=False); embed.add_field(name="👤 Registrador", value=ctx.author.mention, inline=False); embed.set_thumbnail(url=membro.display_avatar.url); embed.set_footer(text="Tensura Moon - Korczak Technologies!"); await ctx.send(embed=embed)

    async def _recuperacao(self, ctx, tipo, titulo, cor, footer):
        user_id, guild_id = str(ctx.author.id), str(ctx.guild.id)
        if await status_db.esta_morto(user_id, guild_id): await ctx.send(embed=discord.Embed(title="| Erro", description=f"❌ Você está morto. Não pode {tipo}.", color=discord.Color.red(), timestamp=discord.utils.utcnow())); return
        resultado = await status_db.recuperar_mana(user_id, guild_id, tipo)
        if not resultado["sucesso"]: await ctx.send(embed=discord.Embed(title="| Erro", description=resultado["mensagem"], color=discord.Color.red(), timestamp=discord.utils.utcnow())); return
        embed = discord.Embed(title=titulo, description=resultado["mensagem"], color=cor, timestamp=discord.utils.utcnow()); embed.add_field(name="💙 Mana Recuperada", value=f"+{resultado['mana_recuperada']} mana ({resultado['percentual']:.0f}% da mana total)", inline=True); embed.add_field(name="💙 Mana Atual", value=f"{resultado['mana_atual']}/{resultado['mana_maxima']}", inline=True); embed.add_field(name="⏰ Cooldown", value=f"{resultado['cooldown_horas']} horas", inline=True); embed.set_footer(text=footer); await ctx.send(embed=embed)

    @commands.command(name="descanso", aliases=["desc"])
    async def descanso(self, ctx): await self._recuperacao(ctx, "descanso", "🛌 Descanso", discord.Color.blue(), "Use !meditacao para recuperar mais mana")

    @commands.command(name="meditacao", aliases=["meditar", "med"])
    async def meditacao(self, ctx): await self._recuperacao(ctx, "meditacao", "🧘 Meditação", discord.Color.purple(), "Use !descanso para uma recuperação mais rápida")

    @commands.command(name="recuperacao", aliases=["rec", "cooldownmana"])
    async def recuperacao(self, ctx):
        user_id, guild_id = str(ctx.author.id), str(ctx.guild.id); cd1 = await status_db.get_cooldown_recuperacao(user_id, guild_id, "descanso"); cd2 = await status_db.get_cooldown_recuperacao(user_id, guild_id, "meditacao")
        def fmt(v): return "✅ Disponível" if v == 0 else (f"⏰ {int(v * 60)} minutos" if v < 1 else f"⏰ {int(v)} horas")
        embed = discord.Embed(title="⏰ Cooldowns de Recuperação", description="Tempo restante para cada comando", color=discord.Color.blue(), timestamp=discord.utils.utcnow()); embed.add_field(name="🛌 Descanso", value=fmt(cd1), inline=True); embed.add_field(name="🧘 Meditação", value=fmt(cd2), inline=True); embed.set_footer(text="Use !descanso ou !meditacao para recuperar mana"); await ctx.send(embed=embed)


async def setup(bot): await bot.add_cog(Status(bot))
