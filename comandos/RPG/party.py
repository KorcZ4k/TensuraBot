import asyncio

import discord
from discord.ext import commands

from database.python.luta_async import (
    pode_lutar,
    criar_participante_jogador,
    atualizar_situacao,
)
from database.python.luta import criar_monstro


class PartyCombate(commands.Cog):
    """Sistema de grupos integrado ao cog principal de luta."""

    def __init__(self, bot):
        self.bot = bot
        self.parties = {}
        self.convites = {}

    def _party_do_usuario(self, guild_id, user_id):
        for party_id, party in self.parties.items():
            if party["guild_id"] == str(guild_id) and str(user_id) in party["membros"]:
                return party_id, party
        return None, None

    @commands.group(name="party", aliases=["grupo"], invoke_without_command=True)
    @commands.guild_only()
    async def party(self, ctx):
        party_id, party = self._party_do_usuario(ctx.guild.id, ctx.author.id)
        if not party:
            await ctx.send("❌ Você não está em uma party. Use `!party criar`.")
            return
        membros = []
        for membro_id in party["membros"]:
            membro = ctx.guild.get_member(int(membro_id))
            membros.append(membro.mention if membro else f"`{membro_id}`")
        embed = discord.Embed(title=f"👥 Party de {party['lider_nome']}", color=discord.Color.blue())
        embed.add_field(name="👑 Líder", value=f"<@{party['lider_id']}>", inline=False)
        embed.add_field(name="👥 Membros", value="\n".join(membros) or "Nenhum", inline=False)
        embed.add_field(name="📊 Capacidade", value=f"{len(party['membros'])}/{party['limite']}", inline=True)
        embed.add_field(name="🆔 ID", value=f"`{party_id}`", inline=True)
        await ctx.send(embed=embed)

    @party.command(name="criar")
    @commands.guild_only()
    async def party_criar(self, ctx):
        _, existente = self._party_do_usuario(ctx.guild.id, ctx.author.id)
        if existente:
            await ctx.send("❌ Você já pertence a uma party.")
            return
        party_id = f"{ctx.guild.id}:{ctx.author.id}"
        self.parties[party_id] = {
            "guild_id": str(ctx.guild.id),
            "lider_id": str(ctx.author.id),
            "lider_nome": ctx.author.display_name,
            "membros": [str(ctx.author.id)],
            "limite": 4,
        }
        await ctx.send(f"👥 {ctx.author.mention} criou uma party. Convide alguém com `!party convidar @membro`.")

    @party.command(name="convidar", aliases=["invite"])
    @commands.guild_only()
    async def party_convidar(self, ctx, membro: discord.Member):
        party_id, party = self._party_do_usuario(ctx.guild.id, ctx.author.id)
        if not party:
            await ctx.send("❌ Crie uma party primeiro com `!party criar`.")
            return
        if party["lider_id"] != str(ctx.author.id):
            await ctx.send("❌ Apenas o líder pode convidar membros.")
            return
        if membro.bot or membro.id == ctx.author.id:
            await ctx.send("❌ Este membro não pode ser convidado.")
            return
        if len(party["membros"]) >= party["limite"]:
            await ctx.send("❌ A party já está cheia.")
            return
        _, party_destino = self._party_do_usuario(ctx.guild.id, membro.id)
        if party_destino:
            await ctx.send("❌ Este membro já pertence a uma party.")
            return
        convite_id = f"{party_id}:{membro.id}"
        self.convites[convite_id] = party_id
        await ctx.send(f"📨 {membro.mention}, você foi convidado para a party de {ctx.author.mention}. Use `!party aceitar` ou `!party recusar`.")

    @party.command(name="aceitar")
    @commands.guild_only()
    async def party_aceitar(self, ctx):
        prefixo = f"{ctx.guild.id}:"
        convite_id = next((k for k in self.convites if k.startswith(prefixo) and k.endswith(f":{ctx.author.id}")), None)
        if not convite_id:
            await ctx.send("❌ Você não possui um convite pendente.")
            return
        party_id = self.convites.pop(convite_id)
        party = self.parties.get(party_id)
        if not party:
            await ctx.send("❌ Esta party não existe mais.")
            return
        if len(party["membros"]) >= party["limite"]:
            await ctx.send("❌ A party ficou cheia.")
            return
        party["membros"].append(str(ctx.author.id))
        await ctx.send(f"✅ {ctx.author.mention} entrou na party.")

    @party.command(name="recusar")
    @commands.guild_only()
    async def party_recusar(self, ctx):
        convite_id = next((k for k in self.convites if k.startswith(f"{ctx.guild.id}:") and k.endswith(f":{ctx.author.id}")), None)
        if not convite_id:
            await ctx.send("❌ Você não possui um convite pendente.")
            return
        self.convites.pop(convite_id, None)
        await ctx.send("❌ Convite recusado.")

    @party.command(name="sair", aliases=["leave"])
    @commands.guild_only()
    async def party_sair(self, ctx):
        party_id, party = self._party_do_usuario(ctx.guild.id, ctx.author.id)
        if not party:
            await ctx.send("❌ Você não está em uma party.")
            return
        party["membros"].remove(str(ctx.author.id))
        if not party["membros"]:
            self.parties.pop(party_id, None)
        elif party["lider_id"] == str(ctx.author.id):
            party["lider_id"] = party["membros"][0]
            novo_lider = ctx.guild.get_member(int(party["lider_id"]))
            party["lider_nome"] = novo_lider.display_name if novo_lider else party["lider_id"]
        await ctx.send(f"🚪 {ctx.author.mention} saiu da party.")

    @party.command(name="expulsar", aliases=["kick"])
    @commands.guild_only()
    async def party_expulsar(self, ctx, membro: discord.Member):
        party_id, party = self._party_do_usuario(ctx.guild.id, ctx.author.id)
        if not party or party["lider_id"] != str(ctx.author.id):
            await ctx.send("❌ Apenas o líder pode expulsar membros.")
            return
        if str(membro.id) not in party["membros"] or membro.id == ctx.author.id:
            await ctx.send("❌ Este membro não pode ser expulso.")
            return
        party["membros"].remove(str(membro.id))
        await ctx.send(f"🚫 {membro.mention} foi removido da party.")

    @commands.command(name="luta_party", aliases=["party_luta", "partyfight"])
    @commands.guild_only()
    async def luta_party(self, ctx, monstro_tipo: str):
        party_id, party = self._party_do_usuario(ctx.guild.id, ctx.author.id)
        if not party:
            await ctx.send("❌ Você precisa estar em uma party para iniciar uma luta em grupo.")
            return
        if party["lider_id"] != str(ctx.author.id):
            await ctx.send("❌ Apenas o líder da party pode iniciar a luta.")
            return

        luta_cog = self.bot.get_cog("Luta")
        if not luta_cog:
            await ctx.send("❌ O sistema principal de luta não está carregado.")
            return
        if luta_cog._combate_ativo(ctx.channel.id):
            await ctx.send("❌ Já existe um combate ativo neste canal.")
            return

        monstro_id = luta_cog._encontrar_monstro(monstro_tipo)
        if not monstro_id:
            await ctx.send(f"❌ Monstro `{monstro_tipo}` não encontrado.")
            return

        guild_id = str(ctx.guild.id)
        participantes = []
        for membro_id in party["membros"]:
            membro = ctx.guild.get_member(int(membro_id))
            verificacao = await pode_lutar(str(membro_id), guild_id)
            if not verificacao.get("pode", False):
                await ctx.send(f"❌ <@{membro_id}> não pode participar: {verificacao.get('mensagem', 'indisponível')}")
                return
            jogador = await criar_participante_jogador(str(membro_id), guild_id)
            if not jogador:
                await ctx.send(f"❌ <@{membro_id}> não possui personagem registrado.")
                return
            jogador["nome"] = jogador.get("nome") or (membro.display_name if membro else membro_id)
            jogador["equipe"] = "party"
            participantes.append(jogador)

        monstro = criar_monstro(monstro_id, 1)
        if not monstro:
            await ctx.send("❌ Não foi possível criar esse monstro.")
            return
        monstro["equipe"] = "inimigos"
        participantes.append(monstro)
        participantes.sort(key=lambda p: p.get("velocidade", 0), reverse=True)

        luta_cog.combates[ctx.channel.id] = {
            "participantes": participantes,
            "turno": 0,
            "numero_turno": 1,
            "fase": "ataque",
            "ativo": True,
            "pvp": False,
            "party": True,
            "party_id": party_id,
            "guild_id": guild_id,
            "ataque_pendente": None,
            "historico": [],
            "aguardando_finalizacao": False,
            "vencedor_id": None,
            "perdedor_id": None,
        }

        for jogador in participantes:
            if jogador.get("tipo") == "jogador":
                await atualizar_situacao(jogador["id"], guild_id, "ativo_combate")

        await ctx.send(f"⚔️ A party com **{len(party['membros'])} membro(s)** iniciou uma luta contra **{monstro.get('nome', monstro_id)}**!")
        await luta_cog._mostrar_inicio(ctx)


async def setup(bot):
    await bot.add_cog(PartyCombate(bot))
