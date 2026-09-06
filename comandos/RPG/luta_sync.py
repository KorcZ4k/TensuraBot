import asyncio
import random

import discord
from discord.ext import commands

from database.python.mongodb import db
from database.python.luta import (
    MONSTROS,
    pode_lutar,
    criar_participante_jogador,
    criar_monstro,
    calcular_dano,
    obter_vencedores,
)


class Luta(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.combates = {}

    # ==========================================================
    # UTILIDADES
    # ==========================================================

    @staticmethod
    def _normalizar_nome_monstro(nome):
        """Normaliza nomes para aceitar qualquer combinação de maiúsculas/minúsculas."""
        return str(nome or "").strip().casefold()

    def _encontrar_monstro(self, nome):
        nome_normalizado = self._normalizar_nome_monstro(nome)

        for monstro_id, dados in MONSTROS.items():
            if self._normalizar_nome_monstro(monstro_id) == nome_normalizado:
                return monstro_id

            if self._normalizar_nome_monstro(dados.get("nome", "")) == nome_normalizado:
                return monstro_id

        return None

    def _combate_ativo(self, channel_id):
        combate = self.combates.get(channel_id)
        return bool(combate and combate.get("ativo", False))

    def _obter_combate(self, channel_id):
        return self.combates.get(channel_id)

    def _obter_atacante(self, combate):
        return combate["participantes"][combate["turno"]]

    def _obter_defensor(self, combate):
        indice = (combate["turno"] + 1) % len(combate["participantes"])
        return combate["participantes"][indice]

    def _texto_status(self, participantes):
        linhas = []
        for participante in participantes:
            if participante["tipo"] == "jogador":
                linhas.append(
                    f"👤 **{participante['nome']}**\n"
                    f"❤️ {participante['vida']}/{participante['vida_maxima']}\n"
                    f"💙 {participante.get('mana', 0)}"
                )
            else:
                linhas.append(
                    f"{participante.get('emoji', '👹')} **{participante['nome']}**\n"
                    f"❤️ {participante['vida']}/{participante['vida_maxima']}"
                )
        return "\n\n".join(linhas)

    def _atualizar_situacao(self, user_id, guild_id, situacao):
        if db is None:
            return
        db["Jogadores"].update_one(
            {"ID": str(user_id), "guild_id": str(guild_id)},
            {"$set": {"Situação": situacao}},
        )

    # ==========================================================
    # COMANDO PRINCIPAL
    # ==========================================================

    @commands.group(name="luta", aliases=["fight", "combate"], invoke_without_command=True)
    async def luta(self, ctx):
        embed = discord.Embed(title="⚔️ Sistema de Combate", color=discord.Color.red())
        embed.add_field(
            name="🎮 Iniciar",
            value=(
                "`!luta pve <monstro>`\n"
                "`!luta pvp @jogador`\n"
                "`!luta monstros`"
            ),
            inline=False,
        )
        embed.add_field(
            name="⚔️ Durante o combate",
            value=(
                "`!soco`\n`!chute`\n`!defesa`\n`!esquiva`\n"
                "`!usarmagia <forma> <elemento>`\n`!fugir`"
            ),
            inline=False,
        )
        embed.add_field(
            name="☠️ PvP",
            value=(
                "Quando um jogador chegar a 0 de vida, o vencedor deverá escolher:\n"
                "`!matar`\n`!desmaiar`"
            ),
            inline=False,
        )
        await ctx.send(embed=embed)

    @luta.command(name="monstros")
    async def luta_monstros(self, ctx):
        if not MONSTROS:
            await ctx.send("❌ Nenhum monstro foi carregado.")
            return

        embed = discord.Embed(title="🐉 Monstros Disponíveis", color=discord.Color.dark_red())
        for monstro_id, dados in list(MONSTROS.items())[:25]:
            xp = dados.get("xp_recompensa", 0)
            hunos = dados.get("hunos_recompensa", 0)
            embed.add_field(
                name=f"{dados.get('emoji', '👹')} {dados.get('nome', monstro_id)}",
                value=(
                    f"ID: `{monstro_id}`\n"
                    f"❤️ Vida: {dados.get('vida_base', 0)}\n"
                    f"⚔️ Dano: {dados.get('dano_base', 0)}\n"
                    f"✨ XP: {xp}\n"
                    f"💰 Hunos: {hunos}"
                ),
                inline=True,
            )
        await ctx.send(embed=embed)

    @luta.command(name="pve")
    async def luta_pve(self, ctx, monstro_tipo: str):
        if not ctx.guild:
            return
        if self._combate_ativo(ctx.channel.id):
            await ctx.send("❌ Já existe um combate ativo neste canal.")
            return

        monstro_id = self._encontrar_monstro(monstro_tipo)
        if not monstro_id:
            await ctx.send(f"❌ Monstro `{monstro_tipo}` não encontrado.")
            return

        guild_id = str(ctx.guild.id)
        user_id = str(ctx.author.id)
        verificacao = pode_lutar(user_id, guild_id)
        if not verificacao.get("pode", False):
            await ctx.send(verificacao.get("mensagem", "❌ Você não pode lutar."))
            return

        jogador = criar_participante_jogador(user_id, guild_id)
        if not jogador:
            await ctx.send("❌ Você não possui um personagem registrado.")
            return

        jogador["nome"] = jogador.get("nome") or ctx.author.display_name
        monstro = criar_monstro(monstro_id, 1)
        if not monstro:
            await ctx.send("❌ Não foi possível criar esse monstro.")
            return

        participantes = [jogador, monstro]
        participantes.sort(key=lambda p: p.get("velocidade", 0), reverse=True)
        self.combates[ctx.channel.id] = {
            "participantes": participantes,
            "turno": 0,
            "numero_turno": 1,
            "fase": "ataque",
            "ativo": True,
            "pvp": False,
            "guild_id": guild_id,
            "ataque_pendente": None,
            "historico": [],
            "aguardando_finalizacao": False,
            "vencedor_id": None,
            "perdedor_id": None,
        }
        self._atualizar_situacao(jogador["id"], guild_id, "ativo_combate")
        await self._mostrar_inicio(ctx)

    @luta.command(name="pvp")
    async def luta_pvp(self, ctx, membro: discord.Member):
        if not ctx.guild:
            return
        if membro.bot:
            await ctx.send("❌ Você não pode lutar contra bots.")
            return
        if membro.id == ctx.author.id:
            await ctx.send("❌ Você não pode lutar contra si mesmo.")
            return
        if self._combate_ativo(ctx.channel.id):
            await ctx.send("❌ Já existe um combate ativo neste canal.")
            return

        guild_id = str(ctx.guild.id)
        for usuario in [ctx.author, membro]:
            verificacao = pode_lutar(str(usuario.id), guild_id)
            if not verificacao.get("pode", False):
                await ctx.send(
                    f"❌ {usuario.display_name}: "
                    f"{verificacao.get('mensagem', 'não pode lutar.')}"
                )
                return

        jogador_1 = criar_participante_jogador(str(ctx.author.id), guild_id)
        jogador_2 = criar_participante_jogador(str(membro.id), guild_id)
        if not jogador_1 or not jogador_2:
            await ctx.send("❌ Um dos jogadores não possui personagem registrado.")
            return

        jogador_1["nome"] = jogador_1.get("nome") or ctx.author.display_name
        jogador_2["nome"] = jogador_2.get("nome") or membro.display_name
        participantes = [jogador_1, jogador_2]
        participantes.sort(key=lambda p: p.get("velocidade", 0), reverse=True)
        self.combates[ctx.channel.id] = {
            "participantes": participantes,
            "turno": 0,
            "numero_turno": 1,
            "fase": "ataque",
            "ativo": True,
            "pvp": True,
            "guild_id": guild_id,
            "ataque_pendente": None,
            "historico": [],
            "aguardando_finalizacao": False,
            "vencedor_id": None,
            "perdedor_id": None,
        }
        for jogador in participantes:
            self._atualizar_situacao(jogador["id"], guild_id, "ativo_combate")
        await self._mostrar_inicio(ctx)

    # O restante das rotinas de combate permanece compatível com o motor existente.
