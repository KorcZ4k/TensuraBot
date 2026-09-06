"""
Sistema de RPG - Status dos Personagens
Módulo que gerencia status, registro e desregistro de personagens.
"""

import datetime
import json
import random
from pathlib import Path

import discord
from discord.ext import commands
from database.python.mongodb import db
from database.python.status import (
    obter_status,
    obter_atributo,
    alterar_atributo,
    aumentar_atributo,
    reduzir_atributo,
    adicionar_xp,
    remover_xp,
    alterar_nivel,
    alterar_nome,
    alterar_raca,
    verificar_morte,
    reviver,
    aplicar_dano,
    aplicar_cura,
    recuperar_mana,
    get_cooldown_recuperacao,
    esta_morto
)
from comandos.RPG.barra_status import barra_mana, barra_vida, barra_xp

# ==========================================
# CONFIGURAÇÃO
# ==========================================

fuso = datetime.timezone(datetime.timedelta(hours=-3))
horario = datetime.datetime.now(fuso)

jogadores = db["Jogadores"]

BASE_DIR = Path(__file__).resolve().parents[2]
RACAS_FILE = BASE_DIR / "database" / "json" / "racas.json"


# ==========================================
# FUNÇÕES UTILITÁRIAS
# ==========================================

def carregar_racas():
    """Carrega as raças do arquivo JSON."""
    with open(RACAS_FILE, "r", encoding="utf-8") as arquivo:
        dados = json.load(arquivo)
    return dados["racas"]


def sortear_raca():
    """Sorteia uma raça aleatória baseado nas chances."""
    racas = carregar_racas()
    nomes = [raca["nome"] for raca in racas]
    pesos = [raca["chance"] for raca in racas]
    return random.choices(nomes, weights=pesos, k=1)[0]


def obter_dados_raca(nome_raca):
    """Obtém os dados de uma raça específica."""
    racas = carregar_racas()
    for raca in racas:
        if raca["nome"] == nome_raca:
            return raca
    return None


def sortear_atributo():
    """Sorteia um atributo baseado em faixas de força."""
    faixa = random.choice([
        "crianca",
        "muito_fraco",
        "fraco",
        "normal",
        "forte"
    ])

    faixa_valores = {
        "crianca": (0, 50),
        "muito_fraco": (50, 80),
        "fraco": (80, 90),
        "normal": (90, 110),
        "forte": (110, 130)
    }

    min_val, max_val = faixa_valores.get(faixa, (90, 110))
    return random.randint(min_val, max_val)


def aplicar_bonus(valor, bonus):
    """Aplica bônus racial ao atributo."""
    return int(valor * (1 + bonus))


# ==========================================
# COG STATUS
# ==========================================

class Status(commands.Cog):
    """Cog para gerenciar status de personagens do RPG."""

    def __init__(self, bot):
        self.bot = bot

    # ==========================================
    # COMANDO STATUS
    # ==========================================

    @commands.command(name="status")
    async def status(self, ctx, membro: discord.Member = None):
        """Exibe o status do personagem do usuário ou de outro jogador."""
        if membro is None:
            membro = ctx.author

        jogador = obter_status(membro.id, ctx.guild.id)

        if jogador is None:
            embed = discord.Embed(
                title="| Erro",
                description=(
                    f"**{membro.mention} "
                    "não possui um personagem registrado.**"
                ),
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_thumbnail(url=membro.display_avatar.url)
            embed.set_footer(text="Tensura Moon - Korczak Technologies!")
            await ctx.send(embed=embed)
            return

        # Dados do personagem
        magiculas = jogador.get("Magiculas", 0)
        nome = jogador.get("Nome", "Não definido")
        raca = jogador.get("Raça", "Não definida")
        nivel = jogador.get("Nivel", 0)
        xp = jogador.get("XP", 0)
        xp_max = jogador.get("XP_maximo", 0)
        forca = jogador.get("Força", 0)
        defesa = jogador.get("Defesa", 0)
        velocidade = jogador.get("Velocidade", 0)
        destreza = jogador.get("Destreza", 0)
        magia = jogador.get("Magia", 0)
        sorte = jogador.get("Sorte", 0)
        vida = jogador.get("Vida", 0)
        vida_maxima = jogador.get("Vida_Maxima", 0)
        mana = jogador.get("Mana", 0)
        mana_maxima = jogador.get("Mana Total", 0)
        inteligencia = jogador.get("inteligencia", 0)
        situacao = jogador.get("Situação", "ativo")

        # Criar embed
        avatar = ctx.author.display_avatar
        embed = discord.Embed(
            title="📊 Status do Personagem",
            color=0x8B0000 if situacao != "morto" else discord.Color.red(),
            timestamp=horario
        )
        embed.set_thumbnail(url=avatar)

        # Verifica se está morto
        if situacao == "morto":
            embed.description = "💀 **Este personagem está morto!**"

        embed.add_field(
            name="👤 Personagem",
            value=(
                f"**Nome:** {nome}\n"
                f"**Raça:** {raca}\n"
                f"**Nível:** {nivel}\n"
                f"**Situação:** {situacao}"
            ),
            inline=False
        )
        embed.add_field(
            name=":star: XP",
            value=f'{barra_xp(xp, xp_max)}\n**{xp}/{xp_max}**',
            inline=False
        )
        embed.add_field(
            name="❤️ Vida",
            value=(
                f"{barra_vida(vida, vida_maxima)}\n"
                f"**{vida}/{vida_maxima}**"
            ),
            inline=False
        )

        embed.add_field(
            name="💧 Mana",
            value=(
                f"{barra_mana(mana, mana_maxima)}\n"
                f"**{mana}/{mana_maxima}**"
            ),
            inline=False
        )

        embed.add_field(
            name="✨ Magiculas",
            value=f"**{magiculas}**",
            inline=False
        )

        embed.add_field(
            name="⚔️ Atributos",
            value=(
                f"**Força:** {forca}\n"
                f"**Defesa:** {defesa}\n"
                f"**Destreza:** {destreza}\n"
                f"**Velocidade:** {velocidade}\n"
                f"**Inteligência:** {inteligencia}\n"
                f"**Magia:** {magia}\n"
                f"**Sorte:** {sorte}"
            ),
            inline=False
        )

        # Mostra cooldowns de recuperação
        cooldown_descanso = get_cooldown_recuperacao(str(membro.id), str(ctx.guild.id), "descanso")
        cooldown_meditacao = get_cooldown_recuperacao(str(membro.id), str(ctx.guild.id), "meditacao")
        
        status_descanso = "✅ Disponível" if cooldown_descanso == 0 else f"⏰ {int(cooldown_descanso)}h"
        status_meditacao = "✅ Disponível" if cooldown_meditacao == 0 else f"⏰ {int(cooldown_meditacao)}h"
        
        embed.add_field(
            name="🔄 Recuperação",
            value=(
                f"**Descanso:** {status_descanso}\n"
                f"**Meditação:** {status_meditacao}"
            ),
            inline=False
        )

        embed.set_footer(text="Tensura Moon - Korczak Technologies!")
        embed.set_image(
            url='https://media.discordapp.net/attachments/1543063886939299962/1543811582537105478/ChatGPT_Image_29_de_ago._de_2026_18_39_01.png?ex=6a96e2d3&is=6a959153&hm=400fd5cd195a8a13aa97386a0208a39b675b93e657b1b1afeeba08a4533cc335&=&format=webp&quality=lossless&width=1280&height=511'
        )

        await ctx.send(embed=embed)

    # ==========================================
    # COMANDO REGISTRAR
    # ==========================================

    @commands.command(name="registrar")
    async def registrar(self, ctx):
        """Registra um personagem para um usuário pendente."""
        user_id = str(ctx.author.id)
        guild_id = str(ctx.guild.id)

        player = db["Jogadores"]
        jogador = player.find_one({"ID": user_id, "guild_id": guild_id})

        if jogador is None:
            await ctx.send(
                "❌ Você não possui uma ficha pendente. "
                "Contate um Administrador."
            )
            return

        if jogador.get("Situação") == "ativo":
            await ctx.send("❌ Você já está registrado.")
            return

        if jogador.get("Situação") != "pendente":
            await ctx.send(
                "❌ Sua ficha não está disponível para registro."
            )
            return

        # Sortear raça
        try:
            raca = sortear_raca()
            dados_raca = obter_dados_raca(raca)
        except Exception as erro:
            print(f"Erro ao carregar raças: {erro}")
            embed = discord.Embed(
                title="| Erro",
                description=(
                    "❌ **Não foi possível "
                    "carregar os dados das raças.**"
                ),
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            await ctx.send(embed=embed)
            return

        if dados_raca is None:
            await ctx.send(
                "❌ Erro: dados da raça não encontrados."
            )
            return

        # Sortear atributos
        atributos_base = {
            "Força": sortear_atributo(),
            "Defesa": sortear_atributo(),
            "Vitalidade": sortear_atributo(),
            "Velocidade": sortear_atributo(),
            "Destreza": sortear_atributo(),
            "Magia": sortear_atributo(),
            "Sorte": sortear_atributo(),
            "inteligencia": sortear_atributo()
        }

        # Aplicar bônus racial
        bonus = dados_raca.get("bonus", {})
        atributos = {}

        for atributo, valor in atributos_base.items():
            bonus_atributo = bonus.get(atributo, 0)
            atributos[atributo] = aplicar_bonus(valor, bonus_atributo)

        # Gerar magículas
        magiculas = random.randrange(0, 1001, 100)
        
        # Calcular vida
        vitalidade = atributos["Vitalidade"]
        vida_maxima = vitalidade * 10
        vida = vida_maxima

        # Calcular mana
        mana_maxima = magiculas * 0.1
        mana = mana_maxima

        # Atualizar ficha
        resultado = player.update_one(
            {
                "_id": jogador["_id"],
                "Situação": "pendente"
            },
            {
                "$set": {
                    "Raça": raca,
                    "Nivel": 1,
                    "XP": 0,
                    "Força": atributos["Força"],
                    "Defesa": atributos["Defesa"],
                    "Vitalidade": atributos["Vitalidade"],
                    "Velocidade": atributos["Velocidade"],
                    "Destreza": atributos["Destreza"],
                    "Magia": atributos["Magia"],
                    "Sorte": atributos["Sorte"],
                    "inteligencia": atributos["inteligencia"],
                    "Magiculas": magiculas,
                    "Vida": vida,
                    "Vida_Maxima": vida_maxima,
                    "Mana": mana,
                    "Mana Total": mana_maxima,
                    "Situação": "ativo",
                    "mortes": 0,
                    "ultimo_treino": {},
                    "ultima_recuperacao": {}
                }
            }
        )

        if resultado.modified_count == 0:
            await ctx.send(
                "❌ Não foi possível registrar sua ficha. "
                "Ela pode já ter sido registrada."
            )
            return

        # Criar embed de sucesso
        embed = discord.Embed(
            title="| Registro concluído",
            description=(
                f"**{ctx.author.mention}**, "
                "seu personagem foi criado!"
            ),
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )

        embed.add_field(
            name="🧬 Raça",
            value=f"**{raca}**",
            inline=False
        )

        embed.add_field(
            name="❤️ Vida",
            value=(
                f"`{barra_vida(vida, vida_maxima)}`\n"
                f"**{vida}/{vida_maxima}**"
            ),
            inline=False
        )

        embed.add_field(
            name="💧 Mana",
            value=(
                f"`{barra_mana(mana, mana_maxima)}`\n"
                f"**{mana}/{mana_maxima}**"
            ),
            inline=False
        )

        embed.add_field(
            name="✨ Magículas",
            value=f"**{magiculas}**",
            inline=False
        )

        embed.add_field(
            name="⚔️ Atributos",
            value=(
                f"**Força:** {atributos['Força']}\n"
                f"**Defesa:** {atributos['Defesa']}\n"
                f"**Vitalidade:** {atributos['Vitalidade']}\n"
                f"**Velocidade:** {atributos['Velocidade']}\n"
                f"**Destreza:** {atributos['Destreza']}\n"
                f"**Magia:** {atributos['Magia']}\n"
                f"**Sorte:** {atributos['Sorte']}\n"
                f"**Inteligência:** {atributos['inteligencia']}"
            ),
            inline=False
        )

        embed.add_field(
            name="📊 Informações",
            value=(
                "**Nível:** 1\n"
                "**XP:** 0"
            ),
            inline=False
        )

        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="Tensura Moon - Korczak Technologies!")

        await ctx.send(embed=embed)

    # ==========================================
    # COMANDO DESREGISTRAR
    # ==========================================

    @commands.command(name="desregistrar", aliases=['desregist', 'dregistrar', 'dregist'])
    @commands.has_permissions(manage_roles=True)
    async def desregistrar(self, ctx, membro: discord.Member = None):
        """Desregistra um personagem (Admin)."""
        if membro is None:
            await ctx.send(
                "❌ Você precisa mencionar um jogador.\n"
                "Use: `!desregistrar @usuário`"
            )
            return

        player = db["Jogadores"]
        user_id = str(membro.id)
        guild_id = str(ctx.guild.id)

        jogador = player.find_one({
            "ID": user_id,
            "guild_id": guild_id
        })

        if jogador is None:
            await ctx.send(
                "❌ Esse usuário não possui uma ficha."
            )
            return

        if jogador.get("Situação") != "ativo":
            await ctx.send(
                "❌ Esse jogador não está registrado."
            )
            return

        # Desregistrar
        resultado = player.update_one(
            {
                "_id": jogador["_id"],
                "Situação": "ativo"
            },
            {
                "$set": {
                    "Nome": None,
                    "Raça": None,
                    "Nivel": 0,
                    "XP": 0,
                    "Força": 0,
                    "Defesa": 0,
                    "Velocidade": 0,
                    "Destreza": 0,
                    "Magia": 0,
                    "Sorte": 0,
                    "Situação": "pendente"
                }
            }
        )

        if resultado.modified_count == 0:
            await ctx.send(
                "❌ Não foi possível desregistrar "
                "esse jogador."
            )
            return

        # Embed de sucesso
        embed = discord.Embed(
            title="| Jogador desregistrado",
            description=(
                f"**{membro.mention}** foi "
                "desregistrado com sucesso."
            ),
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow()
        )

        embed.add_field(
            name="📋 Situação",
            value="**Pendente**",
            inline=False
        )

        embed.add_field(
            name="👤 Registrador",
            value=ctx.author.mention,
            inline=False
        )

        embed.set_thumbnail(url=membro.display_avatar.url)
        embed.set_footer(text="Tensura Moon - Korczak Technologies!")

        await ctx.send(embed=embed)

    # ==========================================
    # COMANDO DESCANSO
    # ==========================================

    @commands.command(name="descanso", aliases=["desc"])
    async def descanso(self, ctx):
        """Descansa para recuperar mana (10%-25% da mana total) - Cooldown: 6h"""
        user_id = str(ctx.author.id)
        guild_id = str(ctx.guild.id)

        if esta_morto(user_id, guild_id):
            embed = discord.Embed(
                title="| Erro",
                description="❌ Você está morto. Não pode descansar.",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            await ctx.send(embed=embed)
            return

        resultado = recuperar_mana(user_id, guild_id, "descanso")

        if not resultado["sucesso"]:
            embed = discord.Embed(
                title="| Erro",
                description=resultado["mensagem"],
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            await ctx.send(embed=embed)
            return

        embed = discord.Embed(
            title="🛌 Descanso",
            description=resultado["mensagem"],
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(
            name="💙 Mana Recuperada",
            value=f"+{resultado['mana_recuperada']} mana ({resultado['percentual']:.0f}% da mana total)",
            inline=True
        )
        embed.add_field(
            name="💙 Mana Atual",
            value=f"{resultado['mana_atual']}/{resultado['mana_maxima']}",
            inline=True
        )
        embed.add_field(
            name="⏰ Cooldown",
            value=f"{resultado['cooldown_horas']} horas",
            inline=True
        )
        embed.set_footer(text="Use !meditacao para recuperar mais mana")
        await ctx.send(embed=embed)

    # ==========================================
    # COMANDO MEDITAÇÃO
    # ==========================================

    @commands.command(name="meditacao", aliases=["meditar", "med"])
    async def meditacao(self, ctx):
        """Medita para recuperar mana (35%-50% da mana total) - Cooldown: 12h"""
        user_id = str(ctx.author.id)
        guild_id = str(ctx.guild.id)

        if esta_morto(user_id, guild_id):
            embed = discord.Embed(
                title="| Erro",
                description="❌ Você está morto. Não pode meditar.",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            await ctx.send(embed=embed)
            return

        resultado = recuperar_mana(user_id, guild_id, "meditacao")

        if not resultado["sucesso"]:
            embed = discord.Embed(
                title="| Erro",
                description=resultado["mensagem"],
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow()
            )
            await ctx.send(embed=embed)
            return

        embed = discord.Embed(
            title="🧘 Meditação",
            description=resultado["mensagem"],
            color=discord.Color.purple(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(
            name="💙 Mana Recuperada",
            value=f"+{resultado['mana_recuperada']} mana ({resultado['percentual']:.0f}% da mana total)",
            inline=True
        )
        embed.add_field(
            name="💙 Mana Atual",
            value=f"{resultado['mana_atual']}/{resultado['mana_maxima']}",
            inline=True
        )
        embed.add_field(
            name="⏰ Cooldown",
            value=f"{resultado['cooldown_horas']} horas",
            inline=True
        )
        embed.set_footer(text="Use !descanso para uma recuperação mais rápida")
        await ctx.send(embed=embed)

    # ==========================================
    # COMANDO RECUPERACAO (VER COOLDOWNS)
    # ==========================================

    @commands.command(name="recuperacao", aliases=["rec", "cooldownmana"])
    async def recuperacao(self, ctx):
        """Mostra o status de cooldown dos comandos de recuperação de mana"""
        user_id = str(ctx.author.id)
        guild_id = str(ctx.guild.id)

        cooldown_descanso = get_cooldown_recuperacao(user_id, guild_id, "descanso")
        cooldown_meditacao = get_cooldown_recuperacao(user_id, guild_id, "meditacao")

        embed = discord.Embed(
            title="⏰ Cooldowns de Recuperação",
            description="Tempo restante para cada comando",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )

        if cooldown_descanso == 0:
            status_descanso = "✅ Disponível"
        elif cooldown_descanso < 1:
            minutos = int(cooldown_descanso * 60)
            status_descanso = f"⏰ {minutos} minutos"
        else:
            status_descanso = f"⏰ {int(cooldown_descanso)} horas"

        if cooldown_meditacao == 0:
            status_meditacao = "✅ Disponível"
        elif cooldown_meditacao < 1:
            minutos = int(cooldown_meditacao * 60)
            status_meditacao = f"⏰ {minutos} minutos"
        else:
            status_meditacao = f"⏰ {int(cooldown_meditacao)} horas"

        embed.add_field(
            name="🛌 Descanso",
            value=status_descanso,
            inline=True
        )
        embed.add_field(
            name="🧘 Meditação",
            value=status_meditacao,
            inline=True
        )

        embed.set_footer(text="Use !descanso ou !meditacao para recuperar mana")
        await ctx.send(embed=embed)

# ==========================================
# SETUP
# ==========================================

async def setup(bot):
    """Função de setup do cog."""
    await bot.add_cog(Status(bot))