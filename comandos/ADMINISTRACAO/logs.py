import discord
from discord.ext import commands
from database.python.mongodb import db, mongo_find_one, mongo_update_one

CONFIG = db["configuracoes_servidor"]
CANAL_LOGS_PADRAO = 1545142627547091057

class Logs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _config(self, guild_id):
        return await mongo_find_one(CONFIG, {"guild_id": guild_id}) or {}

    async def _send_log(self, guild, embed):
        config = await self._config(guild.id)
        channel_id = config.get("logs_channel_id", CANAL_LOGS_PADRAO)
        channel = guild.get_channel(channel_id)
        if channel:
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass

    @commands.group(name="logs", aliases=["log"], invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def logs(self, ctx):
        config = await self._config(ctx.guild.id)
        channel_id = config.get("logs_channel_id", CANAL_LOGS_PADRAO)
        channel = ctx.guild.get_channel(channel_id)
        embed = discord.Embed(title="📜 Sistema de Logs", description="Configure o canal que receberá os registros administrativos do servidor.", color=discord.Color.blue())
        embed.add_field(name="Canal atual", value=channel.mention if channel else f"`{channel_id}`", inline=False)
        embed.add_field(name="Comandos", value="`!logs channel #canal`\n`!logs disable`", inline=False)
        await ctx.send(embed=embed)

    @logs.command(name="channel")
    async def logs_channel(self, ctx, channel: discord.TextChannel):
        await mongo_update_one(CONFIG, {"guild_id": ctx.guild.id}, {"$set": {"logs_channel_id": channel.id}}, upsert=True)
        await ctx.send(embed=discord.Embed(title="✅ Logs configurados", description=f"Os registros serão enviados para {channel.mention}.", color=discord.Color.green()))

    @logs.command(name="disable", aliases=["off"])
    async def logs_disable(self, ctx):
        await mongo_update_one(CONFIG, {"guild_id": ctx.guild.id}, {"$set": {"logs_channel_id": None}}, upsert=True)
        await ctx.send(embed=discord.Embed(title="🛑 Logs desativados", description="Nenhum novo registro será enviado pelo sistema de logs.", color=discord.Color.red()))

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not message.guild or message.author.bot:
            return
        content = message.content or "Sem conteúdo textual."
        if len(content) > 1000:
            content = content[:997] + "..."
        embed = discord.Embed(title="🗑️ Mensagem apagada", color=discord.Color.red(), timestamp=discord.utils.utcnow())
        embed.add_field(name="Autor", value=f"{message.author.mention} (`{message.author.id}`)", inline=False)
        embed.add_field(name="Canal", value=message.channel.mention, inline=False)
        embed.add_field(name="Conteúdo", value=content, inline=False)
        await self._send_log(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if not after.guild or after.author.bot or before.content == after.content:
            return
        before_content = before.content or "Sem conteúdo textual."
        after_content = after.content or "Sem conteúdo textual."
        if len(before_content) > 500:
            before_content = before_content[:497] + "..."
        if len(after_content) > 500:
            after_content = after_content[:497] + "..."
        embed = discord.Embed(title="✏️ Mensagem editada", color=discord.Color.orange(), timestamp=discord.utils.utcnow())
        embed.add_field(name="Autor", value=f"{after.author.mention} (`{after.author.id}`)", inline=False)
        embed.add_field(name="Canal", value=after.channel.mention, inline=False)
        embed.add_field(name="Antes", value=before_content, inline=False)
        embed.add_field(name="Depois", value=after_content, inline=False)
        await self._send_log(after.guild, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        embed = discord.Embed(title="📥 Membro entrou", description=f"{member.mention} entrou no servidor.", color=discord.Color.green(), timestamp=discord.utils.utcnow())
        embed.add_field(name="ID", value=str(member.id), inline=True)
        embed.add_field(name="Membros", value=str(member.guild.member_count), inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        await self._send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        embed = discord.Embed(title="📤 Membro saiu", description=f"**{member}** saiu do servidor.", color=discord.Color.dark_orange(), timestamp=discord.utils.utcnow())
        embed.add_field(name="ID", value=str(member.id), inline=True)
        embed.add_field(name="Membros restantes", value=str(member.guild.member_count), inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        await self._send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.roles != after.roles:
            before_roles = {role.id: role for role in before.roles if not role.is_default()}
            after_roles = {role.id: role for role in after.roles if not role.is_default()}
            added = [role.mention for role_id, role in after_roles.items() if role_id not in before_roles]
            removed = [role.mention for role_id, role in before_roles.items() if role_id not in after_roles]
            if added or removed:
                embed = discord.Embed(title="🛡️ Cargos alterados", description=f"Alteração de cargos em {after.mention}.", color=discord.Color.gold(), timestamp=discord.utils.utcnow())
                if added:
                    embed.add_field(name="Adicionados", value="\n".join(added), inline=False)
                if removed:
                    embed.add_field(name="Removidos", value="\n".join(removed), inline=False)
                await self._send_log(after.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        embed = discord.Embed(title="➕ Canal criado", description=f"{channel.mention} foi criado.", color=discord.Color.green(), timestamp=discord.utils.utcnow())
        embed.add_field(name="Tipo", value=str(channel.type), inline=True)
        await self._send_log(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        embed = discord.Embed(title="➖ Canal apagado", description=f"`{channel.name}` foi apagado.", color=discord.Color.red(), timestamp=discord.utils.utcnow())
        embed.add_field(name="Tipo", value=str(channel.type), inline=True)
        await self._send_log(channel.guild, embed)

async def setup(bot):
    await bot.add_cog(Logs(bot))
