# events/autorole_events.py
import discord
from discord.ext import commands
from .autorole_manager import AutoroleManager


class AutoroleEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.autorole_manager = AutoroleManager()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Evento executado quando um membro entra no servidor."""
        if not self.autorole_manager.is_enabled(member.guild.id):
            return

        role_ids = self.autorole_manager.get_auto_assign_roles(member.guild.id)
        roles_to_add = []
        role_names = []

        for role_id in role_ids:
            role = member.guild.get_role(role_id)
            if role:
                roles_to_add.append(role)
                role_names.append(role.mention)

        if roles_to_add:
            try:
                await member.add_roles(*roles_to_add, reason="Autorole - Moon Tensura")
                print(f"✅ Cargos atribuídos a {member}: {', '.join(role_names)}")
            except discord.Forbidden:
                print(f"❌ Sem permissão para adicionar cargos a {member}")
            except Exception as e:
                print(f"❌ Erro ao adicionar cargos: {e}")

        if self.autorole_manager.is_dm_enabled(member.guild.id):
            await self.send_welcome_dm(member)

    async def send_welcome_dm(self, member: discord.Member):
        """Envia DM personalizada para o novo membro."""
        try:
            dm_config = self.autorole_manager.get_dm_config(member.guild.id)
            config = self.autorole_manager.get_guild_config(member.guild.id)
            roles_info = ""

            for role_name, role_id in config.get("roles", {}).items():
                role = member.guild.get_role(int(role_id))
                if role:
                    roles_info += f"• {role.mention} - Cargo: {role_name.capitalize()}\n"

            if not roles_info:
                roles_info = "• Nenhum cargo especial configurado"

            embed = discord.Embed(
                title=dm_config.get("title", "🌙 Bem-vindo ao Moon Tensura!"),
                description=dm_config.get("description", "").format(
                    user=member.display_name,
                    guild=member.guild.name,
                    roles_info=roles_info,
                    member_count=member.guild.member_count
                ),
                color=discord.Color.blue()
            )

            thumbnail_url = dm_config.get("thumbnail_url")
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)

            footer = dm_config.get("footer", "Moon Tensura • Korczak Technologies")
            embed.set_footer(text=footer)
            await member.send(embed=embed)
            print(f"📨 DM enviada para {member}")

        except discord.Forbidden:
            print(f"❌ Não foi possível enviar DM para {member} (DM bloqueada)")
        except Exception as e:
            print(f"❌ Erro ao enviar DM: {e}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        print(f"👋 {member} saiu do servidor {member.guild}")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Atribui o cargo de booster somente quando o Autorole está habilitado."""
        if before.premium_since or not after.premium_since:
            return
        if not self.autorole_manager.is_enabled(after.guild.id):
            return

        config = self.autorole_manager.get_guild_config(after.guild.id)
        booster_role_id = config.get("roles", {}).get("booster")
        if not booster_role_id:
            return

        role = after.guild.get_role(int(booster_role_id))
        if role and role not in after.roles:
            try:
                await after.add_roles(role, reason="Booster do servidor")
                print(f"🚀 Cargo de booster adicionado a {after}")
            except discord.Forbidden:
                print(f"❌ Sem permissão para adicionar cargo de booster a {after}")
            except Exception as e:
                print(f"❌ Erro ao adicionar cargo de booster: {e}")


async def setup(bot):
    await bot.add_cog(AutoroleEvents(bot))
