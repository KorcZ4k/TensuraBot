import re
import time
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord.ext import commands
from database.python.mongodb import db, get_guild_config, update_guild_config

CONFIG = db["configuracoes_servidor"]

class AutoMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.message_history = defaultdict(deque)

    async def get_config(self, guild_id):
        return await get_guild_config(CONFIG, guild_id)

    async def update_config(self, guild_id, data):
        return await update_guild_config(CONFIG, guild_id, data)

    def is_exempt(self, member):
        return member.guild_permissions.administrator or member.bot

    async def log(self, guild, title, description):
        channel_id = (await self.get_config(guild.id)).get("log_channel_id")
        channel = guild.get_channel(channel_id) if channel_id else None
        if channel is None:
            return
        try:
            await channel.send(embed=discord.Embed(title=title, description=description, color=discord.Color.orange(), timestamp=discord.utils.utcnow()))
        except discord.HTTPException:
            pass

    @commands.group(name="automod", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def automod(self, ctx):
        c = await self.get_config(ctx.guild.id)
        embed = discord.Embed(title="🛡️ AutoMod", description="Sistema automático de proteção do servidor.", color=discord.Color.blue())
        embed.add_field(name="Status", value="✅ Ativado" if c.get("automod_enabled", False) else "❌ Desativado", inline=False)
        embed.add_field(name="Filtros", value=f"🔗 Links: {'ON' if c.get('filter_links', False) else 'OFF'}\n🤬 Palavras: {'ON' if c.get('filter_words', False) else 'OFF'}\n📨 Anti-spam: {'ON' if c.get('anti_spam', False) else 'OFF'}", inline=False)
        embed.add_field(name="Comandos", value="`!automod toggle`\n`!automod links`\n`!automod words`\n`!automod spam`\n`!automod addword <palavra>`\n`!automod delword <palavra>`\n`!automod listwords`", inline=False)
        await ctx.send(embed=embed)

    @automod.command(name="toggle")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def toggle(self, ctx):
        value = not (await self.get_config(ctx.guild.id)).get("automod_enabled", False)
        await self.update_config(ctx.guild.id, {"automod_enabled": value})
        await ctx.send(embed=discord.Embed(title="🛡️ AutoMod", description=f"Sistema {'ativado' if value else 'desativado'}.", color=discord.Color.green() if value else discord.Color.red()))

    @automod.command(name="links")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def links(self, ctx):
        value = not (await self.get_config(ctx.guild.id)).get("filter_links", False)
        await self.update_config(ctx.guild.id, {"filter_links": value})
        await ctx.send(embed=discord.Embed(title="🔗 Filtro de Links", description=f"Filtro {'ativado' if value else 'desativado'}.", color=discord.Color.green() if value else discord.Color.red()))

    @automod.command(name="words")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def words(self, ctx):
        value = not (await self.get_config(ctx.guild.id)).get("filter_words", False)
        await self.update_config(ctx.guild.id, {"filter_words": value})
        await ctx.send(embed=discord.Embed(title="🤬 Filtro de Palavras", description=f"Filtro {'ativado' if value else 'desativado'}.", color=discord.Color.green() if value else discord.Color.red()))

    @automod.command(name="spam")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def spam(self, ctx):
        value = not (await self.get_config(ctx.guild.id)).get("anti_spam", False)
        await self.update_config(ctx.guild.id, {"anti_spam": value})
        await ctx.send(embed=discord.Embed(title="📨 Anti-Spam", description=f"Sistema {'ativado' if value else 'desativado'}.", color=discord.Color.green() if value else discord.Color.red()))

    @automod.command(name="addword")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def addword(self, ctx, *, word):
        c = await self.get_config(ctx.guild.id)
        words = c.get("blocked_words", [])
        word = word.lower().strip()
        if not word:
            return await ctx.send("❌ Informe uma palavra válida.")
        if word not in words:
            words.append(word)
            await self.update_config(ctx.guild.id, {"blocked_words": words})
        await ctx.send(embed=discord.Embed(title="✅ Palavra Adicionada", description=f"`{word}` foi adicionada à lista.", color=discord.Color.green()))

    @automod.command(name="delword", aliases=["removeword"])
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def delword(self, ctx, *, word):
        c = await self.get_config(ctx.guild.id)
        words = c.get("blocked_words", [])
        word = word.lower().strip()
        if word in words:
            words.remove(word)
            await self.update_config(ctx.guild.id, {"blocked_words": words})
        await ctx.send(embed=discord.Embed(title="🗑️ Palavra Removida", description=f"`{word}` foi removida da lista.", color=discord.Color.orange()))

    @automod.command(name="listwords")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def listwords(self, ctx):
        words = (await self.get_config(ctx.guild.id)).get("blocked_words", [])
        await ctx.send(embed=discord.Embed(title="📋 Palavras Bloqueadas", description=("\n".join(f"• `{w}`" for w in words) or "Nenhuma palavra configurada.")[:4096], color=discord.Color.blue()))

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild is None or self.is_exempt(message.author):
            return
        c = await self.get_config(message.guild.id)
        if not c.get("automod_enabled", False):
            return
        content = message.content.lower()
        if c.get("filter_words", False) and any(word.lower() in content for word in c.get("blocked_words", [])):
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            await self.log(message.guild, "🛡️ AutoMod", f"Mensagem de {message.author.mention} removida por palavra bloqueada.")
            return
        if c.get("filter_links", False) and re.search(r"(?:https?://|www\.|discord\.gg/|discord\.com/invite/)", content):
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            await self.log(message.guild, "🛡️ AutoMod", f"Mensagem de {message.author.mention} removida por link.")
            return
        if c.get("anti_spam", False):
            key = (message.guild.id, message.author.id)
            now = time.monotonic()
            history = self.message_history[key]
            history.append(now)
            while history and now - history[0] > 8:
                history.popleft()
            if len(history) >= 6:
                try:
                    await message.delete()
                    await message.author.timeout(discord.utils.utcnow() + timedelta(seconds=60), reason="AutoMod: spam")
                except (discord.HTTPException, discord.Forbidden):
                    pass
                history.clear()
                await self.log(message.guild, "🛡️ Anti-Spam", f"{message.author.mention} foi detectado enviando mensagens rapidamente.")

async def setup(bot):
    await bot.add_cog(AutoMod(bot))
