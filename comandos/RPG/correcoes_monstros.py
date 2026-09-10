"""Correções para comandos de consulta de monstros."""

import discord

from database.python.luta import MONSTROS


async def _listar_monstros(self, ctx):
    if not MONSTROS:
        await ctx.send("❌ Nenhum monstro foi carregado.")
        return

    itens = list(MONSTROS.items())
    for inicio in range(0, len(itens), 25):
        embed = discord.Embed(
            title="🐉 Monstros Disponíveis",
            color=discord.Color.dark_red(),
        )
        for monstro_id, dados in itens[inicio:inicio + 25]:
            embed.add_field(
                name=f"{dados.get('emoji', '👹')} {dados.get('nome', monstro_id)}",
                value=(
                    f"ID: `{monstro_id}`\n"
                    f"❤️ Vida: {dados.get('vida_base', 0)}\n"
                    f"⚔️ Dano: {dados.get('dano_base', 0)}\n"
                    f"✨ XP: {dados.get('xp_recompensa', 0)}\n"
                    f"💰 Hunos: {dados.get('hunos_recompensa', 0)}"
                ),
                inline=True,
            )
        if len(itens) > 25:
            pagina = inicio // 25 + 1
            total_paginas = (len(itens) + 24) // 25
            embed.set_footer(text=f"Página {pagina}/{total_paginas} • Use !luta pve <id> para iniciar")
        await ctx.send(embed=embed)


async def setup(bot):
    comando = bot.get_command("luta monstros")
    if comando is not None:
        comando.callback = _listar_monstros
