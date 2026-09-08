import asyncio
import random
import unicodedata

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

    @commands.group(name="luta", aliases=["fight", "combate"], invoke_without_command=True)
    async def luta(self, ctx):
        embed = discord.Embed(title="⚔️ Sistema de Combate", color=discord.Color.red())
        embed.add_field(name="🎮 Iniciar", value="`!luta pve <monstro>`\n`!luta pvp @jogador`\n`!luta monstros`", inline=False)
        embed.add_field(name="⚔️ Durante o combate", value="`!soco`\n`!chute`\n`!defesa`\n`!esquiva`\n`!usarmagia <forma> <elemento>`\n`!fugir`", inline=False)
        embed.add_field(name="☠️ PvP", value="Quando um jogador chegar a 0 de vida, o vencedor deverá escolher:\n`!matar`\n`!desmaiar`", inline=False)
        await ctx.send(embed=embed)

    @luta.command(name="monstros")
    async def luta_monstros(self, ctx):
        if not MONSTROS:
            await ctx.send("❌ Nenhum monstro foi carregado.")
            return
        embed = discord.Embed(title="🐉 Monstros Disponíveis", color=discord.Color.dark_red())
        for monstro_id, dados in list(MONSTROS.items())[:25]:
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
        await ctx.send(embed=embed)

    @luta.command(name="pve")
    async def luta_pve(self, ctx, monstro_tipo: str = None):
        # O argumento é opcional de propósito: assim o Discord.py não dispara
        # MissingRequiredArgument antes de chegarmos à validação amigável.
        if not monstro_tipo:
            embed = discord.Embed(
                title="⚔️ PvE — Monstro não informado",
                description="Informe o nome do monstro que deseja enfrentar.\n\nExemplo: `!luta pve slime`",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        if not ctx.guild:
            return

        if self._combate_ativo(ctx.channel.id):
            await ctx.send("❌ Já existe um combate ativo neste canal.")
            return

        monstro_id = self._encontrar_monstro(monstro_tipo)
        if not monstro_id:
            embed = discord.Embed(
                title="❌ Monstro não encontrado",
                description=f"Não encontrei **{monstro_tipo}**. Use `!luta monstros` para ver os nomes válidos.",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
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
                await ctx.send(f"❌ {usuario.display_name}: {verificacao.get('mensagem', 'não pode lutar.')}")
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

    def _combate_ativo(self, channel_id):
        combate = self.combates.get(channel_id)
        return bool(combate and combate.get("ativo", False))

    def _encontrar_monstro(self, nome):
        alvo = unicodedata.normalize("NFKD", str(nome or "")).encode("ascii", "ignore").decode("ascii").casefold().strip()
        for monstro_id, dados in MONSTROS.items():
            candidatos = (monstro_id, dados.get("nome", ""))
            for candidato in candidatos:
                normalizado = unicodedata.normalize("NFKD", str(candidato or "")).encode("ascii", "ignore").decode("ascii").casefold().strip()
                if normalizado == alvo:
                    return monstro_id
        return None

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
                linhas.append(f"👤 **{participante['nome']}**\n❤️ {participante['vida']}/{participante['vida_maxima']}\n💙 {participante.get('mana', 0)}")
            else:
                linhas.append(f"{participante.get('emoji', '👹')} **{participante['nome']}**\n❤️ {participante['vida']}/{participante['vida_maxima']}")
        return "\n\n".join(linhas)

    def _atualizar_situacao(self, user_id, guild_id, situacao):
        if db is None:
            return
        db["Jogadores"].update_one({"ID": str(user_id), "guild_id": str(guild_id)}, {"$set": {"Situação": situacao}})

    async def _mostrar_inicio(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate:
            return
        monstro_id = None
        for participante in combate["participantes"]:
            if participante.get("tipo") == "monstro":
                monstro_id = str(participante.get("monstro_id", participante.get("id", participante.get("nome", "")))).lower()
                break
        imagens_monstros = {
            "slime": "https://media.discordapp.net/attachments/1543040901251596288/1544815327240519782/slime.gif?ex=6a99e0e3&is=6a988f63&hm=763d05b99502422b5e76c968f8c6f465bb7ad333b099e1e602cbdd20190919e4&=",
            "goblin": "https://cdn.discordapp.com/attachments/1543040901251596288/1544816403427893320/gobliin.gif?ex=6a99e1e3&is=6a989063&hm=3579e0d0458eb91d64b6b070a7be4a7a9a778d26b1fbc7a2cc3c0d95a22013fe",
            "lobo": "https://cdn.discordapp.com/attachments/1543040901251596288/1544816878139088987/lobo.gif?ex=6a99e255&is=6a9890d5&hm=6c7354f01627ca36f892b0563c1e08e98ca27faf8b5d689ca8bc4acbe168a90b",
            "orc": "https://media.discordapp.net/attachments/1543040901251596288/1544817591028023296/orc.gif?ex=6a99e2ff&is=6a98917f&hm=e9ba67ff8155bf4d8b6c33869df24997cdca325f139430fb77acb95144788b11&=&width=384&height=216",
            "esqueleto": "https://media.discordapp.net/attachments/1543040901251596288/1544818041093886013/skeleton.gif?ex=6a99e36a&is=6a9891ea&hm=044b77d69fabc81492646d1cfd94fb7eef548056a1cf624e641dd62f3ca08db6&=",
            "dragao": "https://cdn.discordapp.com/attachments/1543040901251596288/1544818435312193626/dragao.gif?ex=6a99e3c8&is=6a989248&hm=e9fd1cc99ed0a96857abc75124bf9c3920a2aa7100f38e2210d9003a273d68be",
            "drago": "https://cdn.discordapp.com/attachments/1543040901251596288/1544818435312193626/dragao.gif?ex=6a99e3c8&is=6a989248&hm=e9fd1cc99ed0a96857abc75124bf9c3920a2aa7100f38e2210d9003a273d68be",
            "demonio": "https://media.discordapp.net/attachments/1543040901251596288/1544819046606966895/demonio.gif",
            "fenix": "https://media.discordapp.net/attachments/1543040901251596288/1544819569273866240/fenix.gif",
            "tita": "https://media.discordapp.net/attachments/1543040901251596288/1544819828795543552/tita.gif",
        }
        embed = discord.Embed(title="⚔️ Combate PvE iniciado!", description=self._texto_status(combate["participantes"]), color=discord.Color.dark_red())
        embed.set_footer(text="Tensura Moon - Korczak Technologies!")
        if monstro_id in imagens_monstros:
            embed.set_image(url=imagens_monstros[monstro_id])
        await ctx.send(embed=embed)
        await asyncio.sleep(1)
        if combate["participantes"][0].get("tipo") == "monstro":
            await self._ataque_monstro(ctx)

    async def _ataque_monstro(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo") or combate["fase"] != "ataque":
            return
        atacante = self._obter_atacante(combate)
        defensor = self._obter_defensor(combate)
        if atacante["tipo"] != "monstro":
            return
        golpe = random.choice([g for g in atacante.get("golpes", [])]) if atacante.get("golpes") else {"nome": "Ataque do Monstro", "emoji": "👹", "efeito": {}, "dano_base": 0}
        if isinstance(golpe, str):
            golpe = {"nome": golpe, "emoji": "👹", "efeito": {}, "dano_base": 0}
        ataque = {"tipo": "ataque_monstro", "nome": f"{golpe.get('emoji', '👹')} {golpe.get('nome', 'Ataque do Monstro')}", "atacante_id": atacante.get("id"), "defensor_id": defensor.get("id"), "magia": False, "dano_base": float(golpe.get("dano_base", 0) or 0), "efeito": golpe.get("efeito", {}), "com_arma": bool(golpe.get("com_arma", False))}
        combate["ataque_pendente"] = ataque
        combate["fase"] = "defesa"
        await self._anunciar_ataque(ctx)

    async def _ataque_jogador(self, ctx, tipo_ataque):
        await self._resolver_ataque(ctx)

    async def _resolver_ataque(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate:
            return
        ataque = combate.get("ataque_pendente")
        if ataque:
            atacante = self._obter_atacante(combate)
            defensor = self._obter_defensor(combate)
            dano, resultado = calcular_dano(atacante, defensor)
            defensor["vida"] = max(0, defensor.get("vida", 0) - dano)
            embed = discord.Embed(title="⚔️ Resultado do ataque", description=f"**{atacante['nome']}** causou **{dano}** de dano em **{defensor['nome']}**.", color=discord.Color.red())
            await ctx.send(embed=embed)
            combate["ataque_pendente"] = None
            combate["fase"] = "ataque"
            await self._proximo_turno(ctx)

    async def _proximo_turno(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return
        combate["turno"] = (combate["turno"] + 1) % len(combate["participantes"])
        await self._mostrar_turno(ctx)

    async def _mostrar_turno(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return
        atacante = self._obter_atacante(combate)
        embed = discord.Embed(title=f"⚔️ Vez de {atacante['nome']}", description=self._texto_status(combate["participantes"]), color=discord.Color.blurple())
        await ctx.send(embed=embed)
