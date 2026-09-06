import asyncio
import discord
from discord.ext import commands
from database.python.mongodb import db, get_guild_config, update_guild_config

CONFIG = db["configuracoes_servidor"]


class BoasVindas(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _config(self, guild_id):
        return await get_guild_config(CONFIG, guild_id)

    async def _update(self, guild_id, data):
        return await update_guild_config(CONFIG, guild_id, data)

    @commands.group(name="welcome", aliases=["boasvindas"], invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def welcome(self, ctx):
        config = await self._config(ctx.guild.id)
        channel_id = config.get("welcome_channel_id")
        channel = ctx.guild.get_channel(channel_id) if channel_id else None
        embed = discord.Embed(title="👋 Boas-vindas", description="Configure as mensagens de entrada e saída do servidor.", color=discord.Color.green())
        embed.add_field(name="Canal de entrada", value=channel.mention if channel else "Não configurado", inline=False)
        embed.add_field(name="Comandos", value="`!welcome channel #canal`\n`!welcome message <mensagem>`\n`!welcome toggle`\n`!goodbye channel #canal`\n`!goodbye message <mensagem>`\n`!goodbye toggle`\n\nVariáveis: `{member}`, `{user}`, `{server}`, `{count}`", inline=False)
        await ctx.send(embed=embed)

    @welcome.command(name="channel")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def welcome_channel(self, ctx, channel: discord.TextChannel):
        await self._update(ctx.guild.id, {"welcome_channel_id": channel.id})
        await ctx.send(embed=discord.Embed(title="✅ Canal configurado", description=f"As boas-vindas serão enviadas em {channel.mention}.", color=discord.Color.green()))

    @welcome.command(name="message")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def welcome_message(self, ctx, *, message: str):
        await self._update(ctx.guild.id, {"welcome_message": message})
        await ctx.send(embed=discord.Embed(title="✏️ Mensagem atualizada", description="A mensagem de boas-vindas foi salva.", color=discord.Color.green()))

    @welcome.command(name="toggle")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def welcome_toggle(self, ctx):
        config = await self._config(ctx.guild.id)
        enabled = not config.get("welcome_enabled", False)
        await self._update(ctx.guild.id, {"welcome_enabled": enabled})
        await ctx.send(embed=discord.Embed(title="👋 Boas-vindas", description=f"Sistema {'ativado' if enabled else 'desativado'}.", color=discord.Color.green() if enabled else discord.Color.red()))

    @commands.group(name="goodbye", aliases=["despedida"], invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def goodbye(self, ctx):
        await ctx.send("Use `!goodbye channel`, `!goodbye message` ou `!goodbye toggle`.")

    @goodbye.command(name="channel")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def goodbye_channel(self, ctx, channel: discord.TextChannel):
        await self._update(ctx.guild.id, {"goodbye_channel_id": channel.id})
        await ctx.send(embed=discord.Embed(title="👋 Canal de despedida", description=f"As despedidas serão enviadas em {channel.mention}.", color=discord.Color.orange()))

    @goodbye.command(name="message")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def goodbye_message(self, ctx, *, message: str):
        await self._update(ctx.guild.id, {"goodbye_message": message})
        await ctx.send(embed=discord.Embed(title="✏️ Mensagem atualizada", description="A mensagem de despedida foi salva.", color=discord.Color.orange()))

    @goodbye.command(name="toggle")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def goodbye_toggle(self, ctx):
        config = await self._config(ctx.guild.id)
        enabled = not config.get("goodbye_enabled", False)
        await self._update(ctx.guild.id, {"goodbye_enabled": enabled})
        await ctx.send(embed=discord.Embed(title="👋 Despedidas", description=f"Sistema {'ativado' if enabled else 'desativado'}.", color=discord.Color.green() if enabled else discord.Color.red()))

    def format_message(self, template, guild, member):
        try:
            return template.format(
                member=member.mention,
                user=member.display_name,
                server=guild.name,
                count=guild.member_count,
            )
        except (KeyError, ValueError):
            return template

    @commands.Cog.listener(name="on_member_join")
    async def _on_member_join(self, member: discord.Member):
        """Evento real de entrada: envia a mensagem de boas-vindas automaticamente."""
        config = await self._config(member.guild.id)
        if not config.get("welcome_enabled", False):
            return

        channel_id = config.get("welcome_channel_id")
        channel = member.guild.get_channel(channel_id) if channel_id else None
        if channel is None:
            return

        template = config.get(
            "welcome_message",
            "👋 Seja bem-vindo(a), {member}, ao **{server}**! Você é o membro número **{count}**.",
        )
        embed = discord.Embed(
            title="🎉 Bem-vindo(a)!",
            description=self.format_message(template, member.guild, member),
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.Cog.listener(name="on_member_remove")
    async def _on_member_remove(self, member: discord.Member):
        """Evento real de saída: envia a mensagem de despedida automaticamente."""
        config = await self._config(member.guild.id)
        if not config.get("goodbye_enabled", False):
            return

        channel_id = config.get("goodbye_channel_id")
        channel = member.guild.get_channel(channel_id) if channel_id else None
        if channel is None:
            return

        template = config.get("goodbye_message", "👋 **{user}** saiu de **{server}**.")
        embed = discord.Embed(
            title="👋 Até logo",
            description=self.format_message(template, member.guild, member),
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass


async def setup(bot):
    await bot.add_cog(BoasVindas(bot))
