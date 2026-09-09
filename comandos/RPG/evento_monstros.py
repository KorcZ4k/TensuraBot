"""Eventos automáticos de monstros integrados ao sistema de combate."""

import asyncio
import random
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

from database.python import luta as luta_db
from database.python.mongodb import run_db
from .monstros_balanceamento import criar_monstro_balanceado


GUILD_ID = 1543039757146136586
CANAIS_EVENTO = (
    1544165036854083665,
    1544163892203094098,
    1544164898823733268,
    1544166559658942465,
    1544166582698115142,
    1544167266877440131,
    1544168060942811207,
    1544168089766338612,
    1544168880040321134,
    1544169368727068672,
    1544168921375047811,
    1544168939800633384,
    1544169183066067014,
    1544169244533719102,
    1544169275085037660,
    1544169302205145119,
    1544169612986425394,
    1544170134736863252,
    1544170024472944710,
    1544171048830767126,
    1544170169289547777,
    1544170064981401721,
    1544169989924323459,
    1544165513909772329,
    1544165856341262446,
    1544165901224513566,
    1544169591192682747,
)

MONSTROS_COMUNS = (
    "slime",
    "goblin",
    "lobo",
    "orc",
    "esqueleto",
    "fenix",
    "demonio",
)

MAX_NIVEIS = {
    "slime": 7,
    "goblin": 15,
    "lobo": 20,
    "orc": 25,
    "esqueleto": 30,
    "fenix": 20,
    "demonio": 70,
    "titan": 80,
    "dragao": 70,
}


class EventoContexto:
    """Contexto mínimo compatível com os métodos assíncronos de Luta."""

    def __init__(self, channel, guild, author):
        self.channel = channel
        self.guild = guild
        self.author = author
        self.message = None

    async def send(self, content=None, *, embed=None, **kwargs):
        return await self.channel.send(content=content, embed=embed, **kwargs)


class MonstroView(discord.ui.View):
    def __init__(self, cog, evento_id, monster_id, nivel, expires_at):
        super().__init__(timeout=300)
        self.cog = cog
        self.evento_id = evento_id
        self.monster_id = monster_id
        self.nivel = nivel
        self.expires_at = expires_at
        self.consumido = False

    @discord.ui.button(label="⚔️ Lutar", style=discord.ButtonStyle.danger)
    async def lutar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.consumido:
            await interaction.response.send_message("❌ Este evento já foi encerrado.", ephemeral=True)
            return

        evento = self.cog.eventos.get(self.evento_id)
        if not evento or evento.get("encerrado"):
            self.consumido = True
            button.disabled = True
            await interaction.response.edit_message(view=self)
            return

        if datetime.now(timezone.utc) >= self.expires_at:
            await self.cog.encerrar_evento(self.evento_id, motivo="tempo")
            await interaction.response.send_message("⌛ O monstro já desapareceu.", ephemeral=True)
            return

        luta = self.cog.bot.get_cog("Luta")
        if luta is None:
            await interaction.response.send_message("❌ O sistema de luta não está disponível no momento.", ephemeral=True)
            return

        if not interaction.guild or interaction.guild.id != GUILD_ID:
            await interaction.response.send_message("❌ Este evento não está disponível aqui.", ephemeral=True)
            return

        if luta._combate_ativo(interaction.channel.id):
            await interaction.response.send_message("❌ Já existe um combate ativo neste canal.", ephemeral=True)
            return

        verificacao = await run_db(luta_db.pode_lutar, str(interaction.user.id), str(interaction.guild.id))
        if not verificacao.get("pode", False):
            await interaction.response.send_message(verificacao.get("mensagem", "❌ Você não pode lutar."), ephemeral=True)
            return

        self.consumido = True
        button.disabled = True
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        sucesso = await self.cog.iniciar_luta_evento(
            luta,
            interaction.channel,
            interaction.guild,
            interaction.user,
            self.evento_id,
            self.monster_id,
            self.nivel,
        )

        if not sucesso:
            self.consumido = False
            for item in self.children:
                item.disabled = False
            evento = self.cog.eventos.get(self.evento_id)
            if evento and evento.get("mensagem"):
                try:
                    await evento["mensagem"].edit(view=self)
                except discord.HTTPException:
                    pass

    async def on_timeout(self):
        await self.cog.encerrar_evento(self.evento_id, motivo="tempo")


class EventoMonstros(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.eventos = {}
        self._tarefas = set()
        self._proximo_comum = None
        self._proximo_dragao = None
        self._proximo_titan = None
        self._iniciado = False

    async def cog_load(self):
        if self._iniciado:
            return
        self._iniciado = True
        self._criar_tarefa(self._loop_comum())
        self._criar_tarefa(self._loop_dragao())
        self._criar_tarefa(self._loop_titan())
        print("[EVENTOS][MONSTROS] Spawns automáticos carregados.")

    def cog_unload(self):
        for tarefa in tuple(self._tarefas):
            tarefa.cancel()
        for evento in tuple(self.eventos.values()):
            view = evento.get("view")
            if view:
                view.stop()
        self.eventos.clear()

    def _criar_tarefa(self, coroutine):
        tarefa = asyncio.create_task(coroutine)
        self._tarefas.add(tarefa)
        tarefa.add_done_callback(self._tarefas.discard)
        return tarefa

    def _canal_aleatorio(self):
        return self.bot.get_channel(random.choice(CANAIS_EVENTO))

    def _novo_nivel(self, monster_id):
        dados = luta_db.MONSTROS.get(monster_id, {})
        minimo = max(1, int(dados.get("nivel_minimo", 1) or 1))
        maximo = min(MAX_NIVEIS.get(monster_id, minimo), int(dados.get("nivel_maximo", MAX_NIVEIS.get(monster_id, minimo)) or minimo))
        return random.randint(minimo, maximo)

    async def _loop_comum(self):
        await asyncio.sleep(random.randint(10, 30))
        while True:
            try:
                await self.criar_evento(random.choice(MONSTROS_COMUNS), "comum")
            except asyncio.CancelledError:
                raise
            except Exception as erro:
                print(f"[EVENTOS][ERRO][COMUM] {type(erro).__name__}: {erro}")
            await asyncio.sleep(random.randint(600, 1800))

    async def _loop_dragao(self):
        await asyncio.sleep(43200)
        while True:
            try:
                if random.random() < 0.50:
                    await self.criar_evento("dragao", "dragao")
            except asyncio.CancelledError:
                raise
            except Exception as erro:
                print(f"[EVENTOS][ERRO][DRAGAO] {type(erro).__name__}: {erro}")
            await asyncio.sleep(43200)

    async def _loop_titan(self):
        await asyncio.sleep(86400)
        while True:
            try:
                if random.random() < 0.35:
                    await self.criar_evento("titan", "titan")
            except asyncio.CancelledError:
                raise
            except Exception as erro:
                print(f"[EVENTOS][ERRO][TITAN] {type(erro).__name__}: {erro}")
            await asyncio.sleep(86400)

    async def criar_evento(self, monster_id, categoria):
        # Um único evento pode ocupar um canal; não interfere em outros combates.
        canal = self._canal_aleatorio()
        if canal is None or canal.guild is None or canal.guild.id != GUILD_ID:
            print(f"[EVENTOS][AVISO] Canal de evento indisponível para {monster_id}.")
            return False

        # Não cria evento sobre uma luta já ativa.
        luta = self.bot.get_cog("Luta")
        if luta and luta._combate_ativo(canal.id):
            return False

        # Evita dois eventos simultâneos no mesmo canal.
        for evento in self.eventos.values():
            if evento.get("channel_id") == canal.id and not evento.get("encerrado"):
                return False

        nivel = self._novo_nivel(monster_id)
        monstro = criar_monstro_balanceado(monster_id, nivel)
        if not monstro:
            return False

        evento_id = f"{canal.id}:{datetime.now(timezone.utc).timestamp()}"
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        view = MonstroView(self, evento_id, monster_id, nivel, expires_at)

        if categoria == "titan":
            titulo = "🗿 | UM TITÃ SURGIU!"
            cor = discord.Color.dark_gold()
            descricao = "Um **Titã** apareceu! Enfrente-o antes que desapareça."
        elif categoria == "dragao":
            titulo = "🐉 | UM DRAGÃO SURGIU!"
            cor = discord.Color.red()
            descricao = "Um **Dragão** apareceu! Enfrente-o antes que desapareça."
        else:
            titulo = f"{monstro['emoji']} | Um monstro surgiu!"
            cor = discord.Color.blurple()
            descricao = "Um monstro apareceu neste canal. Quem será o primeiro a enfrentá-lo?"

        embed = discord.Embed(title=titulo, description=descricao, color=cor, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👹 Monstro", value=f"**{monstro['nome']}**", inline=True)
        embed.add_field(name="⭐ Nível", value=f"**{nivel}**", inline=True)
        embed.add_field(name="❤️ Vida", value=f"**{monstro['vida']:,} / {monstro['vida_maxima']:,}**", inline=True)
        embed.add_field(name="⚔️ Atributos", value=f"Força: **{monstro['Força']}** • Defesa: **{monstro['Defesa']}**\nVelocidade: **{monstro['Velocidade']}** • Destreza: **{monstro['Destreza']}**", inline=False)
        embed.add_field(name="🎁 Recompensa", value=f"TP/XP: **{monstro['tp_recompensa']}** • Hunos: **{monstro['hunos_recompensa']}**", inline=False)
        embed.set_footer(text="⏳ O monstro desaparece em 5 minutos se ninguém lutar.")

        mensagem = await canal.send(embed=embed, view=view)
        self.eventos[evento_id] = {
            "channel_id": canal.id,
            "guild_id": GUILD_ID,
            "monster_id": monster_id,
            "nivel": nivel,
            "categoria": categoria,
            "mensagem": mensagem,
            "view": view,
            "encerrado": False,
            "expires_at": expires_at,
        }
        return True

    async def encerrar_evento(self, evento_id, motivo="tempo"):
        evento = self.eventos.get(evento_id)
        if not evento or evento.get("encerrado"):
            return
        evento["encerrado"] = True
        view = evento.get("view")
        if view:
            for item in view.children:
                item.disabled = True
            view.stop()

        mensagem = evento.get("mensagem")
        if mensagem:
            try:
                embed = mensagem.embeds[0].copy() if mensagem.embeds else discord.Embed()
                if motivo == "tempo":
                    embed.title = "⌛ | O monstro desapareceu"
                    embed.description = "Ninguém o enfrentou a tempo. O monstro desapareceu."
                else:
                    embed.title = "⚔️ | Monstro capturado para combate"
                    embed.description = "O evento foi convertido em um combate."
                embed.set_footer(text="Tensura Moon • Korczak Technologies")
                await mensagem.edit(embed=embed, view=view)
            except discord.HTTPException:
                pass

        if motivo == "tempo":
            self.eventos.pop(evento_id, None)

    async def iniciar_luta_evento(self, luta, channel, guild, membro, evento_id, monster_id, nivel):
        evento = self.eventos.get(evento_id)
        if not evento or evento.get("encerrado"):
            return False

        try:
            jogador = await luta._criar_participante(str(membro.id), str(guild.id))
            if not jogador:
                return False

            monstro = criar_monstro_balanceado(monster_id, nivel)
            if not monstro:
                return False

            jogador["nome"] = jogador.get("nome") or membro.display_name
            participantes = [jogador, monstro]
            participantes.sort(
                key=lambda p: p.get("Velocidade", p.get("velocidade", 0)),
                reverse=True,
            )

            if luta._combate_ativo(channel.id):
                return False

            combate = {
                "participantes": participantes,
                "turno": 0,
                "numero_turno": 1,
                "fase": "ataque",
                "ativo": True,
                "pvp": False,
                "guild_id": str(guild.id),
                "ataque_pendente": None,
                "historico": [],
                "aguardando_finalizacao": False,
                "vencedor_id": None,
                "perdedor_id": None,
                "evento_monstro": True,
                "evento_id": evento_id,
            }
            luta.combates[channel.id] = combate
            luta._atualizar_situacao(jogador["id"], str(guild.id), "ativo_combate")

            evento["encerrado"] = True
            view = evento.get("view")
            if view:
                for item in view.children:
                    item.disabled = True
                view.stop()

            mensagem = evento.get("mensagem")
            if mensagem:
                try:
                    embed = mensagem.embeds[0].copy() if mensagem.embeds else discord.Embed()
                    embed.title = f"⚔️ | {monstro['nome']} foi desafiado!"
                    embed.description = f"**{membro.display_name}** aceitou o desafio. O combate começou!"
                    embed.set_footer(text="Tensura Moon • Combate integrado")
                    await mensagem.edit(embed=embed, view=view)
                except discord.HTTPException:
                    pass

            ctx = EventoContexto(channel, guild, membro)
            await luta._mostrar_inicio(ctx)
            self.eventos.pop(evento_id, None)
            return True
        except Exception as erro:
            print(f"[EVENTOS][ERRO][LUTA] {type(erro).__name__}: {erro}")
            combate = luta.combates.get(channel.id)
            if combate and combate.get("evento_id") == evento_id:
                luta.combates.pop(channel.id, None)
            return False


async def setup(bot):
    await bot.add_cog(EventoMonstros(bot))
