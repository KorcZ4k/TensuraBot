import discord
from discord.ext import commands

from database.python.mongodb import db, run_db


class DesregistroGeral(commands.Cog):
    """Sobrescreve temporariamente !desregistrar para limpar todas as fichas do servidor."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="desregistrar", aliases=["desregist", "dregistrar", "dregist"])
    @commands.has_permissions(manage_roles=True)
    async def desregistrar(self, ctx):
        guild_id = str(ctx.guild.id)
        filtro = {"guild_id": guild_id}

        jogadores = db["Jogadores"]
        habilidades = db["Habilidades"]
        magias = db["Magias"]
        hunos = db["Hunos"]
        unicas = db["HabilidadesUnicas"]

        # Os campos de identificação (_id, guild_id, ID, Nome do Discord
        # e nome de usuário) não entram no $set e, portanto, nunca são alterados.
        resultado = await run_db(
            jogadores.update_many,
            filtro,
            {"$set": {
                "Defesa": 0,
                "Destreza": 0,
                "Força": 0,
                "Magia": 0,
                "Magiculas": 0,
                "Mana": 100,
                "Mana Total": 100,
                "Nivel": 1,
                "Nome": None,
                "Raça": None,
                "Situação": "pendente",
                "Sorte": 0,
                "Velocidade": 0,
                "Vida": 100,
                "Vida_Maxima": 100,
                "Vitalidade": 0,
                "XP": 0,
                "XP_maximo": 100,
                "inteligencia": 0,
                "TP": 0,
                "ultimo_treino": {},
                "ultima_recuperacao": {},
            }},
        )

        # Libera habilidades únicas que estavam ocupadas por fichas deste servidor.
        docs = await run_db(
            lambda: list(habilidades.find(filtro, {"habilidades": 1, "_id": 0}))
        )
        ids_habilidades = []
        for doc in docs:
            for habilidade_id in doc.get("habilidades", []):
                if habilidade_id is not None:
                    ids_habilidades.append(str(habilidade_id))

        if ids_habilidades:
            await run_db(
                unicas.delete_many,
                {
                    "guild_id": guild_id,
                    "$or": [
                        {"ID": {"$in": ids_habilidades}},
                        {"_id": {"$in": ids_habilidades}},
                    ],
                },
            )

        # Fichas auxiliares voltam ao estado pendente/zerado para que um novo
        # !registrar possa sortear tudo novamente.
        await run_db(
            habilidades.update_many,
            filtro,
            {"$set": {"Situação": "pendente", "habilidades": []}},
        )
        await run_db(
            magias.update_many,
            filtro,
            {"$set": {"Situação": "pendente", "magias": [], "tipos": []}},
        )
        await run_db(hunos.delete_many, filtro)

        embed = discord.Embed(
            title="| Desregistro geral",
            description=(
                f"🧹 **{resultado.modified_count} fichas** foram desregistradas.\n\n"
                "Todos os dados de personagem voltaram ao estado inicial:\n"
                "• Nível 1 e XP 0/100\n"
                "• Atributos, Magículas e TP zerados\n"
                "• Vida 100/100 e Mana 100/100\n"
                "• Nome e raça removidos\n"
                "• Situação `pendente`\n\n"
                "🔒 `_id`, `guild_id`, `ID`, nome do Discord e nome de usuário "
                "foram preservados."
            ),
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="Tensura Moon - Korczak Technologies!")
        await ctx.send(embed=embed)


async def setup(bot):
    # O comando original já foi carregado por status.py. Removemos a versão
    # anterior para instalar temporariamente esta versão de desregistro geral.
    bot.remove_command("desregistrar")
    for alias in ("desregist", "dregistrar", "dregist"):
        bot.remove_command(alias)
    await bot.add_cog(DesregistroGeral(bot))
