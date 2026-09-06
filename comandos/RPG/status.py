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
    def __init__(self, bot): self.bot = bot

    @commands.command(name="status")
    async def status(self, ctx, membro: discord.Member = None):
        if membro is None: membro = ctx.author
        jogador = await status_db.obter_status(membro.id, ctx.guild.id)
        if jogador is None:
            embed = discord.Embed(title="| Erro", description=f"**{membro.mention} não possui um personagem registrado.**", color=discord.Color.red(), timestamp=discord.utils.utcnow())
            embed.set_thumbnail(url=membro.display_avatar.url); embed.set_footer(text="Tensura Moon - Korczak Technologies!"); await ctx.send(embed=embed); return
        vals = {k: jogador.get(k, d) for k, d in {"Magiculas":0,"Nome":"Não definido","Raça":"Não definida","Nivel":0,"XP":0,"XP_maximo":0,"Força":0,"Defesa":0,"Velocidade":0,"Destreza":0,"Magia":0,"Sorte":0,"Vida":0,"Vida_Maxima":0,"Mana":0,"Mana Total":0,"inteligencia":0,"Situação":"ativo"}.items()}
        embed = discord.Embed(title="📊 Status do Personagem", color=0x8B0000 if vals["Situação"] != "morto" else discord.Color.red(), timestamp=discord.utils.utcnow()); embed.set_thumbnail(url=membro.display_avatar.url)
        if vals["Situação"] == "morto": embed.description = "💀 **Este personagem está morto!**"
        embed.add_field(name="👤 Personagem", value=f"**Nome:** {vals['Nome']}\n**Raça:** {vals['Raça']}\n**Nível:** {vals['Nivel']}\n**Situação:** {vals['Situação']}", inline=False)
        embed.add_field(name=":star: XP", value=f"{barra_xp(vals['XP'], vals['XP_maximo'])}\n**{vals['XP']}/{vals['XP_maximo']}**", inline=False); embed.add_field(name="❤️ Vida", value=f"{barra_vida(vals['Vida'], vals['Vida_Maxima'])}\n**{vals['Vida']}/{vals['Vida_Maxima']}**", inline=False); embed.add_field(name="💧 Mana", value=f"{barra_mana(vals['Mana'], vals['Mana Total'])}\n**{vals['Mana']}/{vals['Mana Total']}**", inline=False); embed.add_field(name="✨ Magiculas", value=f"**{vals['Magiculas']}**", inline=False)
        embed.add_field(name="⚔️ Atributos", value=f"**Força:** {vals['Força']}\n**Defesa:** {vals['Defesa']}\n**Destreza:** {vals['Destreza']}\n**Velocidade:** {vals['Velocidade']}\n**Inteligência:** {vals['inteligencia']}\n**Magia:** {vals['Magia']}\n**Sorte:** {vals['Sorte']}", inline=False)
        cd1 = await status_db.get_cooldown_recuperacao(str(membro.id), str(ctx.guild.id), "descanso"); cd2 = await status_db.get_cooldown_recuperacao(str(membro.id), str(ctx.guild.id), "meditacao")
        fmt = lambda v: "✅ Disponível" if v == 0 else f"⏰ {int(v)}h"; embed.add_field(name="🔄 Recuperação", value=f"**Descanso:** {fmt(cd1)}\n**Meditação:** {fmt(cd2)}", inline=False); embed.set_footer(text="Tensura Moon - Korczak Technologies!"); embed.set_image(url="https://media.discordapp.net/attachments/1543063886939299962/1543811582537105478/ChatGPT_Image_29_de_ago._de_2026_18_39_01.png?ex=6a96e2d3&is=6a959153&hm=400fd5cd195a8a13aa97386a0208a39b675b93e657b1b1afeeba08a4533cc335&=&format=webp&quality=lossless&width=1280&height=511"); await ctx.send(embed=embed)

    @commands.command(name="registrar")
    async def registrar(self, ctx):
        user_id, guild_id = str(ctx.author.id), str(ctx.guild.id); player = db["Jogadores"]; jogador = await run_db(player.find_one, {"ID": user_id, "guild_id": guild_id})
        if jogador is None: await ctx.send("❌ Você não possui uma ficha pendente. Contate um Administrador."); return
        if jogador.get("Situação") == "ativo": await ctx.send("❌ Você já está registrado."); return
        if jogador.get("Situação") != "pendente": await ctx.send("❌ Sua ficha não está disponível para registro."); return
        try: raca = sortear_raca(); dados_raca = obter_dados_raca(raca)
        except Exception as erro: print(f"Erro ao carregar raças: {erro}"); await ctx.send("❌ **Não foi possível carregar os dados das raças.**"); return
        if dados_raca is None: await ctx.send("❌ Erro: dados da raça não encontrados."); return
        base = {n: sortear_atributo() for n in ("Força","Defesa","Vitalidade","Velocidade","Destreza","Magia","Sorte","inteligencia")}; bonus = dados_raca.get("bonus", {}); a = {n: aplicar_bonus(v, bonus.get(n, 0)) for n,v in base.items()}; mag = random.randrange(0,1001,100); vm = a["Vitalidade"]*10; mm = mag*0.1
        resultado = await run_db(player.update_one, {"_id":jogador["_id"],"Situação":"pendente"}, {"$set":{"Raça":raca,"Nivel":1,"XP":0,"Força":a["Força"],"Defesa":a["Defesa"],"Vitalidade":a["Vitalidade"],"Velocidade":a["Velocidade"],"Destreza":a["Destreza"],"Magia":a["Magia"],"Sorte":a["Sorte"],"inteligencia":a["inteligencia"],"Magiculas":mag,"Vida":vm,"Vida_Maxima":vm,"Mana":mm,"Mana Total":mm,"Situação":"ativo","mortes":0,"ultimo_treino":{},"ultima_recuperacao":{}}})
        if resultado.modified_count == 0: await ctx.send("❌ Não foi possível registrar sua ficha. Ela pode já ter sido registrada."); return
        e=discord.Embed(title="| Registro concluído",description=f"**{ctx.author.mention}**, seu personagem foi criado!",color=discord.Color.green(),timestamp=discord.utils.utcnow()); e.add_field(name="🧬 Raça",value=f"**{raca}**",inline=False); e.add_field(name="❤️ Vida",value=f"`{barra_vida(vm,vm)}`\n**{vm}/{vm}**",inline=False); e.add_field(name="💧 Mana",value=f"`{barra_mana(mm,mm)}`\n**{mm}/{mm}**",inline=False); e.add_field(name="✨ Magículas",value=f"**{mag}**",inline=False); e.add_field(name="⚔️ Atributos",value=f"**Força:** {a['Força']}\n**Defesa:** {a['Defesa']}\n**Vitalidade:** {a['Vitalidade']}\n**Velocidade:** {a['Velocidade']}\n**Destreza:** {a['Destreza']}\n**Magia:** {a['Magia']}\n**Sorte:** {a['Sorte']}\n**Inteligência:** {a['inteligencia']}",inline=False); e.add_field(name="📊 Informações",value="**Nível:** 1\n**XP:** 0",inline=False); e.set_thumbnail(url=ctx.author.display_avatar.url); e.set_footer(text="Tensura Moon - Korczak Technologies!"); await ctx.send(embed=e)

    @commands.command(name="desregistrar", aliases=["desregist","dregistrar","dregist"])
    @commands.has_permissions(manage_roles=True)
    async def desregistrar(self,ctx,membro:discord.Member=None):
        if membro is None: await ctx.send("❌ Você precisa mencionar um jogador.\nUse: `!desregistrar @usuário`"); return
        p=db["Jogadores"]; j=await run_db(p.find_one,{"ID":str(membro.id),"guild_id":str(ctx.guild.id)})
        if j is None: await ctx.send("❌ Esse usuário não possui uma ficha."); return
        if j.get("Situação")!="ativo": await ctx.send("❌ Esse jogador não está registrado."); return
        r=await run_db(p.update_one,{"_id":j["_id"],"Situação":"ativo"},{"$set":{"Nome":None,"Raça":None,"Nivel":0,"XP":0,"Força":0,"Defesa":0,"Velocidade":0,"Destreza":0,"Magia":0,"Sorte":0,"Situação":"pendente"}})
        if r.modified_count==0: await ctx.send("❌ Não foi possível desregistrar esse jogador."); return
        e=discord.Embed(title="| Jogador desregistrado",description=f"**{membro.mention}** foi desregistrado com sucesso.",color=discord.Color.orange(),timestamp=discord.utils.utcnow()); e.add_field(name="📋 Situação",value="**Pendente**",inline=False); e.add_field(name="👤 Registrador",value=ctx.author.mention,inline=False); e.set_thumbnail(url=membro.display_avatar.url); e.set_footer(text="Tensura Moon - Korczak Technologies!"); await ctx.send(embed=e)

    async def _recuperacao(self,ctx,tipo,titulo,cor,footer):
        uid,gid=str(ctx.author.id),str(ctx.guild.id)
        if await status_db.esta_morto(uid,gid): await ctx.send(embed=discord.Embed(title="| Erro",description=f"❌ Você está morto. Não pode {tipo}.",color=discord.Color.red(),timestamp=discord.utils.utcnow())); return
        r=await status_db.recuperar_mana(uid,gid,tipo)
        if not r["sucesso"]: await ctx.send(embed=discord.Embed(title="| Erro",description=r["mensagem"],color=discord.Color.red(),timestamp=discord.utils.utcnow())); return
        e=discord.Embed(title=titulo,description=r["mensagem"],color=cor,timestamp=discord.utils.utcnow()); e.add_field(name="💙 Mana Recuperada",value=f"+{r['mana_recuperada']} mana ({r['percentual']:.0f}% da mana total)",inline=True); e.add_field(name="💙 Mana Atual",value=f"{r['mana_atual']}/{r['mana_maxima']}",inline=True); e.add_field(name="⏰ Cooldown",value=f"{r['cooldown_horas']} horas",inline=True); e.set_footer(text=footer); await ctx.send(embed=e)
    @commands.command(name="descanso",aliases=["desc"])
    async def descanso(self,ctx): await self._recuperacao(ctx,"descanso","🛌 Descanso",discord.Color.blue(),"Use !meditacao para recuperar mais mana")
    @commands.command(name="meditacao",aliases=["meditar","med"])
    async def meditacao(self,ctx): await self._recuperacao(ctx,"meditacao","🧘 Meditação",discord.Color.purple(),"Use !descanso para uma recuperação mais rápida")
    @commands.command(name="recuperacao",aliases=["rec","cooldownmana"])
    async def recuperacao(self,ctx):
        uid,gid=str(ctx.author.id),str(ctx.guild.id); a=await status_db.get_cooldown_recuperacao(uid,gid,"descanso"); b=await status_db.get_cooldown_recuperacao(uid,gid,"meditacao"); fmt=lambda v:"✅ Disponível" if v==0 else (f"⏰ {int(v*60)} minutos" if v<1 else f"⏰ {int(v)} horas")
        e=discord.Embed(title="⏰ Cooldowns de Recuperação",description="Tempo restante para cada comando",color=discord.Color.blue(),timestamp=discord.utils.utcnow()); e.add_field(name="🛌 Descanso",value=fmt(a),inline=True); e.add_field(name="🧘 Meditação",value=fmt(b),inline=True); e.set_footer(text="Use !descanso ou !meditacao para recuperar mana"); await ctx.send(embed=e)

async def setup(bot): await bot.add_cog(Status(bot))
