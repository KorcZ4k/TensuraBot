import asyncio
import datetime

import discord
from discord.ext import commands

from database.python.mongodb import db


class Moderacao(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.avisos = db["Avisos"]

    def _embed(self, titulo, descricao, cor=discord.Color.blurple()):
        return discord.Embed(title=titulo, description=descricao, color=cor, timestamp=datetime.datetime.now(datetime.timezone.utc))

    async def _erro(self, ctx, texto):
        await ctx.send(embed=self._embed("❌ | Erro", texto, discord.Color.red()))

    async def _db(self, funcao, *args, **kwargs):
        return await asyncio.to_thread(funcao, *args, **kwargs)

    def _can_moderate(self, ctx, membro):
        return (
            membro != ctx.guild.owner
            and membro != ctx.author
            and (ctx.author == ctx.guild.owner or membro.top_role < ctx.author.top_role)
        )

    def _can_manage_role(self, ctx, cargo):
        return (
            cargo != ctx.guild.default_role
            and (ctx.author == ctx.guild.owner or cargo < ctx.author.top_role)
            and cargo < ctx.guild.me.top_role
        )

    @commands.command(name="kick")
    @commands.guild_only()
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, membro: discord.Member, *, motivo="Não informado"):
        if not self._can_moderate(ctx, membro):
            return await self._erro(ctx, "Você não pode expulsar esse membro.")
        try:
            await membro.kick(reason=f"{motivo} | Por {ctx.author}")
        except discord.Forbidden:
            return await self._erro(ctx, "Não tenho permissão ou posição suficiente para expulsar esse membro.")
        await ctx.send(embed=self._embed("👢 | Membro expulso", f"**{membro}** foi expulso.\n**Motivo:** {motivo}", discord.Color.orange()))

    @commands.command(name="ban")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, membro: discord.Member, *, motivo="Não informado"):
        if not self._can_moderate(ctx, membro):
            return await self._erro(ctx, "Você não pode banir esse membro.")
        try:
            await membro.ban(reason=f"{motivo} | Por {ctx.author}")
        except discord.Forbidden:
            return await self._erro(ctx, "Não tenho permissão ou posição suficiente para banir esse membro.")
        await ctx.send(embed=self._embed("🔨 | Membro banido", f"**{membro}** foi banido.\n**Motivo:** {motivo}", discord.Color.red()))

    @commands.command(name="unban")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: int, *, motivo="Não informado"):
        try:
            usuario = await self.bot.fetch_user(user_id)
            await ctx.guild.unban(usuario, reason=f"{motivo} | Por {ctx.author}")
        except discord.NotFound:
            return await self._erro(ctx, "Usuário não encontrado ou não está banido.")
        except discord.Forbidden:
            return await self._erro(ctx, "Não tenho permissão para remover esse banimento.")
        await ctx.send(embed=self._embed("🔓 | Banimento removido", f"**{usuario}** foi desbanido.\n**Motivo:** {motivo}", discord.Color.green()))

    @commands.command(name="timeout", aliases=["mute"])
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def timeout(self, ctx, membro: discord.Member, minutos: int, *, motivo="Não informado"):
        if minutos <= 0 or minutos > 40320:
            return await self._erro(ctx, "Informe uma duração entre 1 minuto e 28 dias.")
        if not self._can_moderate(ctx, membro):
            return await self._erro(ctx, "Você não pode aplicar timeout nesse membro.")
        try:
            await membro.timeout(datetime.timedelta(minutes=minutos), reason=f"{motivo} | Por {ctx.author}")
        except discord.Forbidden:
            return await self._erro(ctx, "Não tenho permissão para aplicar timeout nesse membro.")
        await ctx.send(embed=self._embed("🔇 | Timeout aplicado", f"**{membro.mention}** recebeu timeout por **{minutos} minuto(s)**.\n**Motivo:** {motivo}", discord.Color.orange()))

    @commands.command(name="untimeout", aliases=["unmute"])
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def untimeout(self, ctx, membro: discord.Member, *, motivo="Não informado"):
        if not self._can_moderate(ctx, membro):
            return await self._erro(ctx, "Você não pode remover o timeout desse membro.")
        try:
            await membro.timeout(None, reason=f"{motivo} | Por {ctx.author}")
        except discord.Forbidden:
            return await self._erro(ctx, "Não tenho permissão para remover o timeout.")
        await ctx.send(embed=self._embed("🔊 | Timeout removido", f"O timeout de **{membro.mention}** foi removido.\n**Motivo:** {motivo}", discord.Color.green()))

    @commands.command(name="clear", aliases=["purge", "limpar"])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, quantidade: int = 10):
        if quantidade < 1 or quantidade > 100:
            return await self._erro(ctx, "A quantidade deve estar entre 1 e 100.")
        apagadas = await ctx.channel.purge(limit=quantidade + 1)
        aviso = await ctx.send(embed=self._embed("🧹 | Mensagens removidas", f"Foram removidas **{len(apagadas) - 1}** mensagem(ns).", discord.Color.green()))
        await aviso.delete(delay=5)

    @commands.command(name="warn", aliases=["avisar"])
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def warn(self, ctx, membro: discord.Member, *, motivo="Não informado"):
        if not self._can_moderate(ctx, membro):
            return await self._erro(ctx, "Você não pode advertir esse membro.")
        documento = {
            "guild_id": str(ctx.guild.id),
            "user_id": str(membro.id),
            "moderador_id": str(ctx.author.id),
            "motivo": motivo,
            "data": datetime.datetime.now(datetime.timezone.utc),
        }
        await self._db(self.avisos.insert_one, documento)
        total = await self._db(self.avisos.count_documents, {"guild_id": str(ctx.guild.id), "user_id": str(membro.id)})
        await ctx.send(embed=self._embed("⚠️ | Aviso aplicado", f"**{membro.mention}** recebeu um aviso.\n**Motivo:** {motivo}\n**Total de avisos:** {total}", discord.Color.orange()))

    @commands.command(name="warnings", aliases=["avisos"])
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def warnings(self, ctx, membro: discord.Member):
        avisos = await self._db(lambda: list(self.avisos.find({"guild_id": str(ctx.guild.id), "user_id": str(membro.id)}).sort("data", -1).limit(10)))
        if not avisos:
            return await ctx.send(embed=self._embed("⚠️ | Avisos", f"{membro.mention} não possui avisos registrados.", discord.Color.green()))
        linhas = [f"**{i}.** {aviso.get('motivo', 'Sem motivo')}" for i, aviso in enumerate(avisos, 1)]
        await ctx.send(embed=self._embed("⚠️ | Histórico de avisos", f"**Membro:** {membro.mention}\n\n" + "\n".join(linhas), discord.Color.orange()))

    @commands.command(name="delwarn", aliases=["removeraviso"])
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def delwarn(self, ctx, membro: discord.Member, numero: int):
        if numero < 1:
            return await self._erro(ctx, "O número do aviso deve ser maior que zero.")
        avisos = await self._db(lambda: list(self.avisos.find({"guild_id": str(ctx.guild.id), "user_id": str(membro.id)}).sort("data", -1)))
        if numero > len(avisos):
            return await self._erro(ctx, "Esse aviso não existe.")
        await self._db(self.avisos.delete_one, {"_id": avisos[numero - 1]["_id"]})
        await ctx.send(embed=self._embed("🗑️ | Aviso removido", f"O aviso **#{numero}** de {membro.mention} foi removido.", discord.Color.green()))

    @commands.command(name="slowmode")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx, segundos: int = 0):
        if segundos < 0 or segundos > 21600:
            return await self._erro(ctx, "Informe um valor entre 0 e 21600 segundos.")
        await ctx.channel.edit(slowmode_delay=segundos, reason=f"Alterado por {ctx.author}")
        texto = "desativado" if segundos == 0 else f"definido para **{segundos} segundos**"
        await ctx.send(embed=self._embed("🐌 | Slowmode", f"O slowmode foi {texto}.", discord.Color.green()))

    @commands.command(name="lock")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx, canal: discord.TextChannel = None):
        canal = canal or ctx.channel
        overwrites = canal.overwrites_for(ctx.guild.default_role)
        overwrites.send_messages = False
        await canal.set_permissions(ctx.guild.default_role, overwrite=overwrites, reason=f"Canal bloqueado por {ctx.author}")
        await ctx.send(embed=self._embed("🔒 | Canal bloqueado", f"{canal.mention} foi bloqueado para mensagens.", discord.Color.red()))

    @commands.command(name="unlock")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx, canal: discord.TextChannel = None):
        canal = canal or ctx.channel
        overwrites = canal.overwrites_for(ctx.guild.default_role)
        overwrites.send_messages = None
        await canal.set_permissions(ctx.guild.default_role, overwrite=overwrites, reason=f"Canal desbloqueado por {ctx.author}")
        await ctx.send(embed=self._embed("🔓 | Canal desbloqueado", f"{canal.mention} foi desbloqueado.", discord.Color.green()))

    @commands.command(name="addrole")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def addrole(self, ctx, membro: discord.Member, cargo: discord.Role):
        if not self._can_moderate(ctx, membro) or not self._can_manage_role(ctx, cargo):
            return await self._erro(ctx, "Você não pode alterar esse membro ou esse cargo.")
        try:
            await membro.add_roles(cargo, reason=f"Adicionado por {ctx.author}")
        except discord.Forbidden:
            return await self._erro(ctx, "Não tenho posição/permissão suficiente para adicionar esse cargo.")
        await ctx.send(embed=self._embed("🎭 | Cargo adicionado", f"{cargo.mention} foi adicionado a {membro.mention}.", discord.Color.green()))

    @commands.command(name="removerole")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def removerole(self, ctx, membro: discord.Member, cargo: discord.Role):
        if not self._can_moderate(ctx, membro) or not self._can_manage_role(ctx, cargo):
            return await self._erro(ctx, "Você não pode alterar esse membro ou esse cargo.")
        try:
            await membro.remove_roles(cargo, reason=f"Removido por {ctx.author}")
        except discord.Forbidden:
            return await self._erro(ctx, "Não tenho posição/permissão suficiente para remover esse cargo.")
        await ctx.send(embed=self._embed("🎭 | Cargo removido", f"{cargo.mention} foi removido de {membro.mention}.", discord.Color.orange()))

    @commands.command(name="nickname", aliases=["nick"])
    @commands.guild_only()
    @commands.has_permissions(manage_nicknames=True)
    async def nickname(self, ctx, membro: discord.Member, *, nome: str = None):
        if not self._can_moderate(ctx, membro):
            return await self._erro(ctx, "Você não pode alterar o apelido desse membro.")
        try:
            await membro.edit(nick=nome, reason=f"Alterado por {ctx.author}")
        except discord.Forbidden:
            return await self._erro(ctx, "Não tenho posição/permissão suficiente para alterar esse apelido.")
        texto = "removido" if nome is None else f"alterado para **{nome}**"
        await ctx.send(embed=self._embed("✏️ | Apelido", f"O apelido de {membro.mention} foi {texto}.", discord.Color.green()))

    @commands.command(name="say")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def say(self, ctx, *, mensagem: str):
        await ctx.message.delete()
        await ctx.send(mensagem)

    @commands.command(name="announce", aliases=["anunciar"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def announce(self, ctx, canal: discord.TextChannel, *, mensagem: str):
        embed = self._embed("📢 | Anúncio", mensagem, discord.Color.blurple())
        embed.set_footer(text=f"Enviado por {ctx.author.display_name}")
        await canal.send(embed=embed)
        if canal.id != ctx.channel.id:
            await ctx.send(embed=self._embed("✅ | Anúncio enviado", f"O anúncio foi enviado para {canal.mention}.", discord.Color.green()))

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await self._erro(ctx, "Você não possui as permissões necessárias para usar esse comando.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await self._erro(ctx, f"Está faltando o argumento: `{error.param.name}`.")


async def setup(bot):
    await bot.add_cog(Moderacao(bot))
