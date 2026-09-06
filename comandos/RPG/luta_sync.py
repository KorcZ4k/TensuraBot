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
    # COMANDO PRINCIPAL
    # ==========================================================

    @commands.group(
        name="luta",
        aliases=["fight", "combate"],
        invoke_without_command=True
    )
    async def luta(self, ctx):

        embed = discord.Embed(
            title="⚔️ Sistema de Combate",
            color=discord.Color.red()
        )

        embed.add_field(
            name="🎮 Iniciar",
            value=(
                "`!luta pve <monstro>`\n"
                "`!luta pvp @jogador`\n"
                "`!luta monstros`"
            ),
            inline=False
        )

        embed.add_field(
            name="⚔️ Durante o combate",
            value=(
                "`!soco`\n"
                "`!chute`\n"
                "`!defesa`\n"
                "`!esquiva`\n"
                "`!usarmagia <forma> <elemento>`\n"
                "`!fugir`"
            ),
            inline=False
        )

        embed.add_field(
            name="☠️ PvP",
            value=(
                "Quando um jogador chegar a 0 de vida, "
                "o vencedor deverá escolher:\n"
                "`!matar`\n"
                "`!desmaiar`"
            ),
            inline=False
        )

        await ctx.send(embed=embed)

    # ==========================================================
    # LISTAR MONSTROS
    # ==========================================================

    @luta.command(name="monstros")
    async def luta_monstros(self, ctx):

        if not MONSTROS:

            await ctx.send(
                "❌ Nenhum monstro foi carregado."
            )

            return

        embed = discord.Embed(
            title="🐉 Monstros Disponíveis",
            color=discord.Color.dark_red()
        )

        for monstro_id, dados in list(MONSTROS.items())[:25]:

            xp = dados.get(
                "xp_recompensa",
                0
            )

            hunos = dados.get(
                "hunos_recompensa",
                0
            )

            embed.add_field(
                name=(
                    f"{dados.get('emoji', '👹')} "
                    f"{dados.get('nome', monstro_id)}"
                ),
                value=(
                    f"ID: `{monstro_id}`\n"
                    f"❤️ Vida: {dados.get('vida_base', 0)}\n"
                    f"⚔️ Dano: {dados.get('dano_base', 0)}\n"
                    f"✨ XP: {xp}\n"
                    f"💰 Hunos: {hunos}"
                ),
                inline=True
            )

        await ctx.send(embed=embed)

    # ==========================================================
    # INICIAR PVE
    # ==========================================================

    @luta.command(name="pve")
    async def luta_pve(
        self,
        ctx,
        monstro_tipo: str
    ):

        if not ctx.guild:
            return

        if self._combate_ativo(
            ctx.channel.id
        ):

            await ctx.send(
                "❌ Já existe um combate ativo neste canal."
            )

            return

        monstro_id = self._encontrar_monstro(
            monstro_tipo
        )

        if not monstro_id:

            await ctx.send(
                f"❌ Monstro `{monstro_tipo}` não encontrado."
            )

            return

        guild_id = str(
            ctx.guild.id
        )

        user_id = str(
            ctx.author.id
        )

        verificacao = pode_lutar(
            user_id,
            guild_id
        )

        if not verificacao.get(
            "pode",
            False
        ):

            await ctx.send(
                verificacao.get(
                    "mensagem",
                    "❌ Você não pode lutar."
                )
            )

            return

        jogador = criar_participante_jogador(
            user_id,
            guild_id
        )

        if not jogador:

            await ctx.send(
                "❌ Você não possui um personagem registrado."
            )

            return

        jogador["nome"] = (
            jogador.get("nome")
            or ctx.author.display_name
        )

        monstro = criar_monstro(
            monstro_id,
            1
        )

        if not monstro:

            await ctx.send(
                "❌ Não foi possível criar esse monstro."
            )

            return

        participantes = [
            jogador,
            monstro
        ]

        participantes.sort(
            key=lambda p: p.get(
                "velocidade",
                0
            ),
            reverse=True
        )

        self.combates[
            ctx.channel.id
        ] = {

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

        self._atualizar_situacao(
            jogador["id"],
            guild_id,
            "ativo_combate"
        )

        await self._mostrar_inicio(ctx)

    # ==========================================================
    # INICIAR PVP
    # ==========================================================

    @luta.command(name="pvp")
    async def luta_pvp(
        self,
        ctx,
        membro: discord.Member
    ):

        if not ctx.guild:
            return

        if membro.bot:

            await ctx.send(
                "❌ Você não pode lutar contra bots."
            )

            return

        if membro.id == ctx.author.id:

            await ctx.send(
                "❌ Você não pode lutar contra si mesmo."
            )

            return

        if self._combate_ativo(
            ctx.channel.id
        ):

            await ctx.send(
                "❌ Já existe um combate ativo neste canal."
            )

            return

        guild_id = str(
            ctx.guild.id
        )

        for usuario in [
            ctx.author,
            membro
        ]:

            verificacao = pode_lutar(
                str(usuario.id),
                guild_id
            )

            if not verificacao.get(
                "pode",
                False
            ):

                await ctx.send(
                    f"❌ {usuario.display_name}: "
                    f"{verificacao.get('mensagem', 'não pode lutar.')}"
                )

                return

        jogador_1 = criar_participante_jogador(
            str(ctx.author.id),
            guild_id
        )

        jogador_2 = criar_participante_jogador(
            str(membro.id),
            guild_id
        )

        if not jogador_1 or not jogador_2:

            await ctx.send(
                "❌ Um dos jogadores não possui personagem registrado."
            )

            return

        jogador_1["nome"] = (
            jogador_1.get("nome")
            or ctx.author.display_name
        )

        jogador_2["nome"] = (
            jogador_2.get("nome")
            or membro.display_name
        )

        participantes = [
            jogador_1,
            jogador_2
        ]

        participantes.sort(
            key=lambda p: p.get(
                "velocidade",
                0
            ),
            reverse=True
        )

        self.combates[
            ctx.channel.id
        ] = {

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

            self._atualizar_situacao(
                jogador["id"],
                guild_id,
                "ativo_combate"
            )

        await self._mostrar_inicio(ctx)

    # ==========================================================
    # UTILIDADES
    # ==========================================================

    def _combate_ativo(
        self,
        channel_id
    ):

        combate = self.combates.get(
            channel_id
        )

        return bool(
            combate
            and combate.get(
                "ativo",
                False
            )
        )

    def _encontrar_monstro(
        self,
        nome
    ):

        nome = str(
            nome
        ).strip().lower()

        for monstro_id, dados in MONSTROS.items():

            if str(
                monstro_id
            ).lower() == nome:

                return monstro_id

            if str(
                dados.get(
                    "nome",
                    ""
                )
            ).lower() == nome:

                return monstro_id

        return None

    def _obter_combate(
        self,
        channel_id
    ):

        return self.combates.get(
            channel_id
        )

    def _obter_atacante(
        self,
        combate
    ):

        return combate["participantes"][
            combate["turno"]
        ]

    def _obter_defensor(
        self,
        combate
    ):

        indice = (
            combate["turno"] + 1
        ) % len(
            combate["participantes"]
        )

        return combate["participantes"][
            indice
        ]

    def _texto_status(
        self,
        participantes
    ):

        linhas = []

        for participante in participantes:

            if participante["tipo"] == "jogador":

                linhas.append(
                    f"👤 **{participante['nome']}**\n"
                    f"❤️ {participante['vida']}"
                    f"/{participante['vida_maxima']}\n"
                    f"💙 {participante.get('mana', 0)}"
                )

            else:

                linhas.append(
                    f"{participante.get('emoji', '👹')} "
                    f"**{participante['nome']}**\n"
                    f"❤️ {participante['vida']}"
                    f"/{participante['vida_maxima']}"
                )

        return "\n\n".join(
            linhas
        )

    def _atualizar_situacao(
        self,
        user_id,
        guild_id,
        situacao
    ):

        if db is None:
            return

        db["Jogadores"].update_one(
            {
                "ID": str(user_id),
                "guild_id": str(guild_id)
            },
            {
                "$set": {
                    "Situação": situacao
                }
            }
        )

    # ==========================================================
    # MOSTRAR INÍCIO
    # ==========================================================

    async def _mostrar_inicio(
        self,
        ctx
    ):

        combate = self._obter_combate(
            ctx.channel.id
        )

        if not combate:
            return

        monstro_id = None

        for participante in combate["participantes"]:

            if participante.get("tipo") == "monstro":

                monstro_id = str(
                    participante.get(
                        "monstro_id",
                        participante.get(
                            "nome",
                            ""
                        )
                    )
                ).lower()

                break

        imagens_monstros = {

            "slime":
            "https://media.discordapp.net/attachments/1543040901251596288/1544815327240519782/slime.gif?ex=6a99e0e3&is=6a988f63&hm=763d05b99502422b5e76c968f8c6f465bb7ad333b099e1e602cbdd20190919e4&=",

            "goblin":
            "https://cdn.discordapp.com/attachments/1543040901251596288/1544816403427893320/gobliin.gif?ex=6a99e1e3&is=6a989063&hm=3579e0d0458eb91d64b6b070a7be4a7a9a778d26b1fbc7a2cc3c0d95a22013fe",

            "lobo":
            "https://cdn.discordapp.com/attachments/1543040901251596288/1544816878139088987/lobo.gif?ex=6a99e255&is=6a9890d5&hm=6c7354f01627ca36f892b0563c1e08e98ca27faf8b5d689ca8bc4acbe168a90b",

            "orc":
            "https://media.discordapp.net/attachments/1543040901251596288/1544817591028023296/orc.gif?ex=6a99e2ff&is=6a98917f&hm=e9ba67ff8155bf4d8b6c33869df24997cdca325f139430fb77acb95144788b11&=&width=384&height=216",

            "esqueleto":
            "https://media.discordapp.net/attachments/1543040901251596288/1544818041093886013/skeleton.gif?ex=6a99e36a&is=6a9891ea&hm=044b77d69fabc81492646d1cfd94fb7eef548056a1cf624e641dd62f3ca08db6&=",

            "dragao":
            "https://cdn.discordapp.com/attachments/1543040901251596288/1544818435312193626/dragao.gif?ex=6a99e3c8&is=6a989248&hm=e9fd1cc99ed0a96857abc75124bf9c3920a2aa7100f38e2210d9003a273d68be",

            "drago":
            "https://cdn.discordapp.com/attachments/1543040901251596288/1544818435312193626/dragao.gif?ex=6a99e3c8&is=6a989248&hm=e9fd1cc99ed0a96857abc75124bf9c3920a2aa7100f38e2210d9003a273d68be",

            "demonio":
            "https://media.discordapp.net/attachments/1543040901251596288/1544819046606966895/demonio.gif?ex=6a99e45a&is=6a9892da&hm=33410b8c70395bd11edcdea525820068cc4d1b7c8630df16cd694526f1510532&=&width=512&height=287"
        }

        imagem = imagens_monstros.get(
            monstro_id
        )

        atacante = self._obter_atacante(
            combate
        )

        defensor = self._obter_defensor(
            combate
        )

        titulo = (
            "⚔️ Combate PvP"
            if combate["pvp"]
            else "⚔️ Combate PvE"
        )

        embed = discord.Embed(
            title=titulo,
            description=(
                "🔔 **Turno 1**\n\n"
                f"⚔️ **{atacante['nome']}** "
                "começa atacando!"
            ),
            color=discord.Color.red()
        )

        embed.add_field(
            name="🎯 Defensor",
            value=(
                f"🛡️ **{defensor['nome']}**"
            ),
            inline=False
        )

        embed.add_field(
            name="📋 Status",
            value=self._texto_status(
                combate["participantes"]
            ),
            inline=False
        )

        if imagem:

            embed.set_image(
                url=imagem
            )

        embed.set_footer(
            text="Tensura Moon • Korczak Technologies"
        )

        await ctx.send(
            embed=embed
        )

        if atacante["tipo"] == "jogador":
            return

        await asyncio.sleep(
            1
        )

        await self._ataque_monstro(
            ctx
        )

    # ==========================================================
    # ATAQUE NORMAL
    # ==========================================================

    async def _ataque_jogador(
        self,
        ctx,
        tipo_ataque
    ):

        combate = self._obter_combate(
            ctx.channel.id
        )

        if not combate or not combate.get("ativo"):

            await ctx.send(
                "❌ Não há combate ativo."
            )

            return

        if combate.get(
            "aguardando_finalizacao"
        ):

            await ctx.send(
                "❌ O vencedor precisa escolher "
                "`!matar` ou `!desmaiar`."
            )

            return

        if combate["fase"] != "ataque":

            await ctx.send(
                "❌ O ataque anterior ainda precisa ser resolvido."
            )

            return

        atacante = self._obter_atacante(
            combate
        )

        defensor = self._obter_defensor(
            combate
        )

        if atacante["tipo"] != "jogador":

            await ctx.send(
                f"⏳ É a vez de **{atacante['nome']}**."
            )

            return

        if atacante["id"] != str(
            ctx.author.id
        ):

            await ctx.send(
                "❌ Não é sua vez de atacar."
            )

            return

        nomes = {
            "soco": "👊 Soco",
            "chute": "🦵 Chute",
        }

        nome_ataque = nomes.get(
            tipo_ataque,
            "⚔️ Ataque"
        )

        combate["ataque_pendente"] = {

            "tipo": tipo_ataque,
            "nome": nome_ataque,
            "atacante_id": atacante.get("id"),
            "defensor_id": defensor.get("id"),
            "magia": False,
        }

        combate["fase"] = "defesa"

        await self._anunciar_ataque(
            ctx
        )

    @commands.command(name="soco")
    async def soco(
        self,
        ctx
    ):

        await self._ataque_jogador(
            ctx,
            "soco"
        )

    @commands.command(name="chute")
    async def chute(
        self,
        ctx
    ):

        await self._ataque_jogador(
            ctx,
            "chute"
        )

    # ==========================================================
    # MAGIA
    # ==========================================================

    async def usar_magia_no_combate(
        self,
        ctx,
        dados_magia
    ):

        combate = self._obter_combate(
            ctx.channel.id
        )

        if not combate:
            return False

        if not combate.get("ativo"):
            return False

        if combate.get(
            "aguardando_finalizacao"
        ):

            await ctx.send(
                "❌ O combate está aguardando a finalização."
            )

            return True

        if combate["fase"] != "ataque":

            await ctx.send(
                "❌ O ataque anterior ainda precisa ser resolvido."
            )

            return True

        atacante = self._obter_atacante(
            combate
        )

        defensor = self._obter_defensor(
            combate
        )

        if atacante["tipo"] != "jogador":

            await ctx.send(
                "❌ Não é a vez de um jogador usar magia."
            )

            return True

        if atacante["id"] != str(
            ctx.author.id
        ):

            await ctx.send(
                "❌ Não é sua vez de atacar."
            )

            return True

        mana_base = int(
            dados_magia.get(
                "mana_base",
                0
            )
            or 0
        )

        mana_atual = int(
            atacante.get(
                "mana",
                0
            )
            or 0
        )

        if mana_atual < mana_base:

            await ctx.send(
                f"❌ Mana insuficiente. "
                f"Necessário: {mana_base}."
            )

            return True

        atacante["mana"] = (
            mana_atual - mana_base
        )

        nome = dados_magia.get(
            "nome",
            "Magia"
        )

        elemento = dados_magia.get(
            "elemento",
            ""
        )

        dano_base = float(
            dados_magia.get(
                "dano_base",
                0
            )
            or 0
        )

        efeito = dados_magia.get(
            "efeito",
            {}
        )

        combate["ataque_pendente"] = {

            "tipo": "magia",

            "nome": (
                f"✨ {nome}"
                + (
                    f" — {elemento.title()}"
                    if elemento
                    else ""
                )
            ),

            "atacante_id": atacante.get("id"),
            "defensor_id": defensor.get("id"),
            "magia": True,
            "dano_base": dano_base,
            "mana_base": mana_base,
            "elemento": elemento,
            "efeito": efeito,
        }

        combate["fase"] = "defesa"

        await self._anunciar_ataque(
            ctx
        )

        return True

    # ==========================================================
    # ANUNCIAR ATAQUE
    # ==========================================================

    async def _anunciar_ataque(
        self,
        ctx
    ):

        combate = self._obter_combate(
            ctx.channel.id
        )

        if not combate:
            return

        ataque = combate.get(
            "ataque_pendente"
        )

        atacante = self._obter_atacante(
            combate
        )

        defensor = self._obter_defensor(
            combate
        )

        mensagem = (
            f"{ataque['nome']}\n\n"
            f"⚔️ **{atacante['nome']}** atacou "
            f"**{defensor['nome']}**!"
        )

        if ataque.get("magia"):

            mensagem += (
                f"\n🌈 Elemento: "
                f"**{ataque.get('elemento', 'Nenhum')}**"
            )

            mensagem += (
                f"\n💙 Mana gasta: "
                f"**{ataque.get('mana_base', 0)}**"
            )

        combate["historico"].append(
            mensagem
        )

        embed = discord.Embed(
            title=(
                f"⚔️ Turno "
                f"{combate['numero_turno']}"
            ),
            description=mensagem,
            color=discord.Color.orange()
        )

        embed.add_field(
            name="📋 Status",
            value=self._texto_status(
                combate["participantes"]
            ),
            inline=False
        )

        if defensor["tipo"] == "monstro":

            embed.set_footer(
                text="O monstro está reagindo..."
            )

            await ctx.send(
                embed=embed
            )

            await asyncio.sleep(
                1
            )

            await self._defesa_monstro(
                ctx
            )

        else:

            embed.set_footer(
                text=(
                    f"{defensor['nome']}: "
                    "!defesa ou !esquiva"
                )
            )

            await ctx.send(
                embed=embed
            )

    # ==========================================================
    # ATAQUE DO MONSTRO
    # ==========================================================

    async def _ataque_monstro(
        self,
        ctx
    ):

        combate = self._obter_combate(
            ctx.channel.id
        )

        if not combate or not combate.get("ativo"):
            return

        if combate["fase"] != "ataque":
            return

        atacante = self._obter_atacante(
            combate
        )

        defensor = self._obter_defensor(
            combate
        )

        if atacante["tipo"] != "monstro":
            return

        combate["ataque_pendente"] = {

            "tipo": "ataque_monstro",
            "nome": "👹 Ataque do Monstro",
            "atacante_id": atacante.get("id"),
            "defensor_id": defensor.get("id"),
            "magia": False,
        }

        combate["fase"] = "defesa"

        await self._anunciar_ataque(
            ctx
        )

    # ==========================================================
    # DEFESA
    # ==========================================================

    async def _defesa_jogador(
        self,
        ctx,
        acao
    ):

        combate = self._obter_combate(
            ctx.channel.id
        )

        if not combate or not combate.get("ativo"):

            await ctx.send(
                "❌ Não há combate ativo."
            )

            return

        if combate["fase"] != "defesa":

            await ctx.send(
                "❌ Não existe um ataque para defender."
            )

            return

        defensor = self._obter_defensor(
            combate
        )

        if defensor["tipo"] != "jogador":

            await ctx.send(
                "❌ O defensor atual não é um jogador."
            )

            return

        if defensor["id"] != str(
            ctx.author.id
        ):

            await ctx.send(
                f"❌ É **{defensor['nome']}** "
                "quem deve defender."
            )

            return

        if acao == "defesa":

            defensor["defesa_ativa"] = True
            defensor["esquiva_ativa"] = False

            descricao = (
                f"🛡️ **{defensor['nome']}** "
                "preparou sua defesa!"
            )

        else:

            defensor["defesa_ativa"] = False
            defensor["esquiva_ativa"] = True

            descricao = (
                f"💨 **{defensor['nome']}** "
                "tentou esquivar!"
            )

        await ctx.send(
            embed=discord.Embed(
                title=(
                    "🛡️ Defesa"
                    if acao == "defesa"
                    else "💨 Esquiva"
                ),
                description=descricao,
                color=discord.Color.blue()
            )
        )

        await asyncio.sleep(
            0.5
        )

        await self._resolver_ataque(
            ctx
        )

    @commands.command(
        name="defesa",
        aliases=[
            "defender",
            "def",
            "shield",
            "block",
            "bloquear",
            "bloqueio"
        ]
    )
    async def defesa(
        self,
        ctx
    ):

        await self._defesa_jogador(
            ctx,
            "defesa"
        )

    @commands.command(
        name="esquiva",
        aliases=[
            "esquivar",
            "desviar",
            "dodge",
            "desvio"
        ]
    )
    async def esquiva(
        self,
        ctx
    ):

        await self._defesa_jogador(
            ctx,
            "esquiva"
        )

    # ==========================================================
    # DEFESA DO MONSTRO
    # ==========================================================

    async def _defesa_monstro(
        self,
        ctx
    ):

        combate = self._obter_combate(
            ctx.channel.id
        )

        if not combate:
            return

        if combate["fase"] != "defesa":
            return

        defensor = self._obter_defensor(
            combate
        )

        if defensor["tipo"] != "monstro":
            return

        escolha = random.choice(
            [
                "defesa",
                "esquiva",
                "normal"
            ]
        )

        defensor["defesa_ativa"] = (
            escolha == "defesa"
        )

        defensor["esquiva_ativa"] = (
            escolha == "esquiva"
        )

        await asyncio.sleep(
            0.5
        )

        await self._resolver_ataque(
            ctx
        )

    # ==========================================================
    # CALCULAR MAGIA
    # ==========================================================

    def _calcular_dano_magia(
        self,
        atacante,
        defensor,
        ataque
    ):

        dano = float(
            ataque.get(
                "dano_base",
                0
            )
            or 0
        )

        atributo_magia = float(
            atacante.get(
                "magia",
                atacante.get(
                    "Magia",
                    0
                )
            )
            or 0
        )

        dano += atributo_magia * 0.10

        if defensor.get("esquiva_ativa"):

            velocidade = float(
                defensor.get(
                    "velocidade",
                    defensor.get(
                        "Velocidade",
                        0
                    )
                )
                or 0
            )

            chance = min(
                0.75,
                0.10 + velocidade / 500
            )

            if random.random() < chance:

                return 0, "esquivou"

        if defensor.get("defesa_ativa"):

            defesa = float(
                defensor.get(
                    "defesa",
                    defensor.get(
                        "Defesa",
                        0
                    )
                )
                or 0
            )

            dano -= defesa * 0.20

        return max(
            0,
            int(dano)
        ), "atingiu"

    # ==========================================================
    # EFEITOS
    # ==========================================================

    def _aplicar_efeito(
        self,
        defensor,
        efeito
    ):

        if not isinstance(
            efeito,
            dict
        ):

            return None

        nome = str(
            efeito.get(
                "nome",
                ""
            )
        ).lower().strip()

        if not nome:
            return None

        turnos = int(
            efeito.get(
                "turnos",
                1
            )
            or 1
        )

        valor = efeito.get(
            "valor",
            0
        )

        if nome in [
            "dano",
            "explosão"
        ]:

            return None

        defensor.setdefault(
            "efeitos",
            []
        )

        defensor["efeitos"].append(
            {
                "nome": nome,
                "turnos": turnos,
                "valor": valor,
            }
        )

        return nome

    def _processar_efeitos(
        self,
        participante
    ):

        efeitos = participante.get(
            "efeitos",
            []
        )

        novos = []
        dano_total = 0
        bloqueado = False
        mensagens = []

        for efeito in efeitos:

            nome = str(
                efeito.get(
                    "nome",
                    ""
                )
            ).lower()

            turnos = int(
                efeito.get(
                    "turnos",
                    0
                )
                or 0
            )

            valor = abs(
                int(
                    efeito.get(
                        "valor",
                        0
                    )
                    or 0
                )
            )

            if nome in [
                "veneno",
                "queimadura",
                "sangramento"
            ]:

                dano = valor or 5

                dano_total += dano

                mensagens.append(
                    f"{nome.title()} causou "
                    f"{dano} de dano."
                )

            elif nome in [
                "paralisia",
                "stun",
                "prisão",
                "prisao"
            ]:

                bloqueado = True

                mensagens.append(
                    f"{nome.title()} impede a ação."
                )

            turnos -= 1

            if turnos > 0:

                efeito["turnos"] = turnos

                novos.append(
                    efeito
                )

        participante["efeitos"] = novos

        if dano_total > 0:

            participante["vida"] = max(
                0,
                participante["vida"] - dano_total
            )

        return (
            dano_total,
            bloqueado,
            mensagens
        )

    # ==========================================================
    # RESOLVER ATAQUE
    # ==========================================================

    async def _resolver_ataque(
        self,
        ctx
    ):

        combate = self._obter_combate(
            ctx.channel.id
        )

        if not combate:
            return

        ataque = combate.get(
            "ataque_pendente"
        )

        if not ataque:
            return

        atacante = self._obter_atacante(
            combate
        )

        defensor = self._obter_defensor(
            combate
        )

        # ------------------------------------------------------
        # CURA
        # ------------------------------------------------------

        if (
            ataque.get("tipo") == "magia"
            and ataque.get("dano_base", 0) < 0
        ):

            cura = abs(
                int(
                    ataque.get(
                        "dano_base",
                        0
                    )
                )
            )

            atacante["vida"] = min(
                atacante["vida_maxima"],
                atacante["vida"] + cura
            )

            mensagem = (
                f"✨ **{atacante['nome']}** "
                f"recuperou **{cura} de vida**!"
            )

        # ------------------------------------------------------
        # MAGIA
        # ------------------------------------------------------

        elif ataque.get("tipo") == "magia":

            dano, resultado = (
                self._calcular_dano_magia(
                    atacante,
                    defensor,
                    ataque
                )
            )

            if resultado == "esquivou":

                mensagem = (
                    f"💨 **{defensor['nome']}** "
                    "esquivou completamente da magia!"
                )

            else:

                defensor["vida"] = max(
                    0,
                    defensor["vida"] - dano
                )

                mensagem = (
                    f"✨ **{atacante['nome']}** "
                    f"causou **{dano} de dano mágico** "
                    f"em **{defensor['nome']}**!"
                )

                efeito = self._aplicar_efeito(
                    defensor,
                    ataque.get(
                        "efeito",
                        {}
                    )
                )

                if efeito:

                    mensagem += (
                        f"\n⚠️ Efeito aplicado: "
                        f"**{efeito.title()}**"
                    )

        # ------------------------------------------------------
        # ATAQUE NORMAL
        # ------------------------------------------------------

        else:

            dano, resultado = calcular_dano(
                atacante,
                defensor
            )

            if resultado == "esquivou":

                mensagem = (
                    f"💨 **{defensor['nome']}** "
                    f"esquivou do ataque de "
                    f"**{atacante['nome']}**!"
                )

            else:

                defensor["vida"] = max(
                    0,
                    defensor["vida"] - dano
                )

                mensagem = (
                    f"⚔️ **{atacante['nome']}** "
                    f"causou **{dano} de dano** "
                    f"em **{defensor['nome']}**!"
                )

        defensor["defesa_ativa"] = False
        defensor["esquiva_ativa"] = False

        combate["historico"].append(
            mensagem
        )

        embed = discord.Embed(
            title="💥 Resultado",
            description=mensagem,
            color=discord.Color.red()
        )

        embed.add_field(
            name="📋 Status",
            value=self._texto_status(
                combate["participantes"]
            ),
            inline=False
        )

        await ctx.send(
            embed=embed
        )

        # ======================================================
        # VIDA 0
        # ======================================================

        if defensor["vida"] <= 0:

            if combate["pvp"]:

                combate[
                    "aguardando_finalizacao"
                ] = True

                combate[
                    "vencedor_id"
                ] = atacante["id"]

                combate[
                    "perdedor_id"
                ] = defensor["id"]

                combate["fase"] = "finalizacao"

                await ctx.send(
                    f"⚠️ **{defensor['nome']}** "
                    "está incapacitado!\n\n"
                    f"🏆 **{atacante['nome']}**, "
                    "escolha o destino do adversário:\n"
                    "`!matar`\n"
                    "`!desmaiar`"
                )

                return

            combate["ativo"] = False

            await self._finalizar(
                ctx,
                motivo="vida"
            )

            return

        await asyncio.sleep(
            1
        )

        await self._proximo_turno(
            ctx
        )

    # ==========================================================
    # PRÓXIMO TURNO
    # ==========================================================

    async def _proximo_turno(
        self,
        ctx
    ):

        combate = self._obter_combate(
            ctx.channel.id
        )

        if not combate or not combate.get("ativo"):
            return

        combate["turno"] = (
            combate["turno"] + 1
        ) % len(
            combate["participantes"]
        )

        combate["numero_turno"] += 1

        combate["fase"] = "ataque"

        combate["ataque_pendente"] = None

        atacante = self._obter_atacante(
            combate
        )

        dano_efeitos, bloqueado, mensagens = (
            self._processar_efeitos(
                atacante
            )
        )

        if dano_efeitos > 0:

            await ctx.send(
                f"⚠️ **{atacante['nome']}** sofreu "
                f"**{dano_efeitos} de dano** por efeitos."
            )

        if atacante["vida"] <= 0:

            defensor = self._obter_defensor(
                combate
            )

            if combate["pvp"]:

                combate[
                    "aguardando_finalizacao"
                ] = True

                combate[
                    "vencedor_id"
                ] = defensor["id"]

                combate[
                    "perdedor_id"
                ] = atacante["id"]

                combate["fase"] = "finalizacao"

                await ctx.send(
                    f"💀 **{atacante['nome']}** "
                    "caiu devido aos efeitos!\n\n"
                    f"🏆 **{defensor['nome']}**: "
                    "`!matar` ou `!desmaiar`."
                )

                return

            combate["ativo"] = False

            await self._finalizar(
                ctx,
                motivo="efeitos"
            )

            return

        if bloqueado:

            await ctx.send(
                f"⚠️ **{atacante['nome']}** "
                "não consegue agir neste turno!"
            )

            await asyncio.sleep(
                1
            )

            await self._proximo_turno(
                ctx
            )

            return

        defensor = self._obter_defensor(
            combate
        )

        embed = discord.Embed(
            title=(
                f"🔄 Turno "
                f"{combate['numero_turno']}"
            ),
            description=(
                f"⚔️ Agora é a vez de "
                f"**{atacante['nome']}** atacar!"
            ),
            color=discord.Color.green()
        )

        embed.add_field(
            name="🎯 Defensor",
            value=(
                f"🛡️ **{defensor['nome']}**"
            ),
            inline=False
        )

        embed.add_field(
            name="📋 Status",
            value=self._texto_status(
                combate["participantes"]
            ),
            inline=False
        )

        if atacante["tipo"] == "jogador":

            embed.set_footer(
                text=(
                    "Use !soco, !chute ou "
                    "!usarmagia."
                )
            )

            await ctx.send(
                embed=embed
            )

        else:

            embed.set_footer(
                text="O monstro está preparando seu ataque..."
            )

            await ctx.send(
                embed=embed
            )

            await asyncio.sleep(
                1
            )

            await self._ataque_monstro(
                ctx
            )

    # ==========================================================
    # FUGIR
    # ==========================================================

    @commands.command(
        name="fugir",
        aliases=[
            "fuga",
            "escape",
            "escapar",
            "run"
        ]
    )
    async def fugir(
        self,
        ctx
    ):

        combate = self._obter_combate(
            ctx.channel.id
        )

        if not combate or not combate.get("ativo"):

            await ctx.send(
                "❌ Você não está em combate."
            )

            return

        jogador = None

        for participante in combate["participantes"]:

            if (
                participante["tipo"] == "jogador"
                and participante.get("id")
                == str(ctx.author.id)
            ):

                jogador = participante

                break

        if not jogador:

            await ctx.send(
                "❌ Você não participa deste combate."
            )

            return

        chance = (
            0.15
            if not combate["pvp"]
            else 0.10
        )

        if random.random() > chance:

            await ctx.send(
                "❌ Você não conseguiu fugir!"
            )

            return

        combate["ativo"] = False

        self._salvar_participantes(
            combate,
            situacao_padrao="ativo"
        )

        await ctx.send(
            f"🏃 **{jogador['nome']}** conseguiu fugir!"
        )

        del self.combates[
            ctx.channel.id
        ]

    # ==========================================================
    # MATAR
    # ==========================================================

    @commands.command(name="matar")
    async def matar(
        self,
        ctx
    ):

        combate = self._obter_combate(
            ctx.channel.id
        )

        if not combate:

            await ctx.send(
                "❌ Não existe um combate ativo."
            )

            return

        if not combate.get(
            "aguardando_finalizacao"
        ):

            await ctx.send(
                "❌ Ninguém está aguardando finalização."
            )

            return

        if str(ctx.author.id) != str(
            combate.get("vencedor_id")
        ):

            await ctx.send(
                "❌ Apenas o vencedor pode decidir."
            )

            return

        vencedor = self._buscar_participante(
            combate,
            combate["vencedor_id"]
        )

        perdedor = self._buscar_participante(
            combate,
            combate["perdedor_id"]
        )

        if not vencedor or not perdedor:
            return

        perdedor["vida"] = 0

        combate["ativo"] = False

        combate[
            "aguardando_finalizacao"
        ] = False

        await self._finalizar(
            ctx,
            motivo="morte",
            vencedor=vencedor,
            perdedor=perdedor
        )

    # ==========================================================
    # DESMAIAR
    # ==========================================================

    @commands.command(name="desmaiar")
    async def desmaiar(
        self,
        ctx
    ):

        combate = self._obter_combate(
            ctx.channel.id
        )

        if not combate:

            await ctx.send(
                "❌ Não existe um combate ativo."
            )

            return

        if not combate.get(
            "aguardando_finalizacao"
        ):

            await ctx.send(
                "❌ Ninguém está aguardando finalização."
            )

            return

        if str(ctx.author.id) != str(
            combate.get("vencedor_id")
        ):

            await ctx.send(
                "❌ Apenas o vencedor pode decidir."
            )

            return

        vencedor = self._buscar_participante(
            combate,
            combate["vencedor_id"]
        )

        perdedor = self._buscar_participante(
            combate,
            combate["perdedor_id"]
        )

        if not vencedor or not perdedor:
            return

        perdedor["vida"] = 1

        combate["ativo"] = False

        combate[
            "aguardando_finalizacao"
        ] = False

        await self._finalizar(
            ctx,
            motivo="desmaio",
            vencedor=vencedor,
            perdedor=perdedor
        )

    # ==========================================================
    # BUSCAR PARTICIPANTE
    # ==========================================================

    def _buscar_participante(
        self,
        combate,
        user_id
    ):

        for participante in combate["participantes"]:

            if str(
                participante.get("id")
            ) == str(user_id):

                return participante

        return None

    # ==========================================================
    # RECOMPENSAS
    # ==========================================================

    def _obter_recompensas_pve(
        self,
        combate
    ):
        monstro = None

        for participante in combate["participantes"]:

            if participante.get("tipo") == "monstro":

                monstro = participante

                break

        if not monstro:

            return {
                "xp": 0,
                "hunos": 0
            }

        # O monstro criado pelo sistema usa a chave "id".
        monstro_id = str(
            monstro.get(
                "monstro_id",
                monstro.get("id", "")
            )
        ).lower().strip()

        dados = MONSTROS.get(
            monstro_id,
            {}
        )

        # Caso o ID não seja encontrado,
        # tenta localizar pelo nome do monstro.
        if not dados:

            nome_monstro = str(
                monstro.get(
                    "nome",
                    ""
                )
            ).lower().strip()

            for chave, dados_monstro in MONSTROS.items():

                if (
                    str(chave).lower()
                    == nome_monstro
                ):

                    dados = dados_monstro

                    break

                if (
                    str(
                        dados_monstro.get(
                            "nome",
                            ""
                        )
                    ).lower()
                    == nome_monstro
                ):

                    dados = dados_monstro

                    break

        # Prioriza os valores que já pertencem
        # ao participante criado.
        xp = int(
            monstro.get(
                "xp_recompensa",
                dados.get(
                    "xp_recompensa",
                    0
                )
            )
            or 0
        )

        hunos = int(
            monstro.get(
                "hunos_recompensa",
                dados.get(
                    "hunos_recompensa",
                    0
                )
            )
            or 0
        )

        return {
            "xp": xp,
            "hunos": hunos
        }

    def _dar_recompensas(
        self,
        user_id,
        guild_id,
        xp,
        hunos
    ):

        if db is None:
            return

        xp = int(
            xp
            or 0
        )

        hunos = int(
            hunos
            or 0
        )

        # ======================================================
        # XP
        # ======================================================

        if xp > 0:

            db["Jogadores"].update_one(
                {
                    "ID": str(user_id),
                    "guild_id": str(guild_id)
                },
                {
                    "$inc": {
                        "XP": xp
                    }
                }
            )

        # ======================================================
        # HUNOS
        # ======================================================

        if hunos > 0:

            db["Hunos"].update_one(
                {
                    "ID": str(user_id),
                    "guild_id": str(guild_id)
                },
                {
                    "$inc": {
                        "carteira": hunos
                    }
                },
                upsert=True
            )

    # ==========================================================
    # SALVAR PARTICIPANTES
    # ==========================================================

    def _salvar_participantes(
        self,
        combate,
        situacao_padrao="ativo",
        morto_id=None
    ):

        if db is None:
            return

        guild_id = combate[
            "guild_id"
        ]

        for participante in combate[
            "participantes"
        ]:

            if participante["tipo"] != "jogador":
                continue

            situacao = situacao_padrao

            if (
                morto_id is not None
                and str(participante["id"])
                == str(morto_id)
            ):

                situacao = "morto"

            db["Jogadores"].update_one(
                {
                    "ID": str(
                        participante["id"]
                    ),
                    "guild_id": str(
                        guild_id
                    )
                },
                {
                    "$set": {
                        "Vida": int(
                            participante.get(
                                "vida",
                                0
                            )
                        ),
                        "Mana": int(
                            participante.get(
                                "mana",
                                0
                            )
                        ),
                        "Situação": situacao
                    }
                }
            )

    # ==========================================================
    # FINALIZAR
    # ==========================================================

    async def _finalizar(
        self,
        ctx,
        motivo="vida",
        vencedor=None,
        perdedor=None
    ):

        combate = self._obter_combate(
            ctx.channel.id
        )

        if not combate:
            return

        combate["ativo"] = False

        guild_id = combate[
            "guild_id"
        ]

        # IMPORTANTE:
        # As chaves devem ser "xp" e "hunos".
        recompensas = {
            "xp": 0,
            "hunos": 0
        }

        descricao = ""

        cor = discord.Color.greyple()

        # ======================================================
        # PVP
        # ======================================================

        if combate["pvp"]:

            if vencedor and perdedor:

                if motivo == "morte":

                    descricao = (
                        f"💀 **{vencedor['nome']}** "
                        f"matou **{perdedor['nome']}**."
                    )

                    self._salvar_participantes(
                        combate,
                        situacao_padrao="ativo",
                        morto_id=perdedor["id"]
                    )

                    cor = discord.Color.dark_red()

                else:

                    descricao = (
                        f"😵 **{vencedor['nome']}** "
                        f"derrotou **{perdedor['nome']}**, "
                        "mas decidiu deixá-lo desmaiado."
                    )

                    self._salvar_participantes(
                        combate,
                        situacao_padrao="ativo"
                    )

                    cor = discord.Color.gold()

            else:

                self._salvar_participantes(
                    combate,
                    situacao_padrao="ativo"
                )

                descricao = (
                    "⚔️ O combate PvP terminou."
                )

        # ======================================================
        # PVE
        # ======================================================

        else:

            resultado = obter_vencedores(
                combate
            )

            if (
    isinstance(resultado, dict)
    and resultado.get("tipo") == "vitoria"
    and resultado.get("lado") == "jogadores"
):
                # ==================================================
                # OBTER RECOMPENSAS DO MONSTRO
                # ==================================================

                recompensas = (
                    self._obter_recompensas_pve(
                        combate
                    )
                )

                vencedor_jogador = None

                for participante in combate[
                    "participantes"
                ]:

                    if participante["tipo"] == "jogador":

                        vencedor_jogador = participante

                        break

                # ==================================================
                # ENTREGAR RECOMPENSAS
                # ==================================================

                if vencedor_jogador:

                    self._dar_recompensas(
                        vencedor_jogador["id"],
                        guild_id,
                        recompensas["xp"],
                        recompensas["hunos"]
                    )

                descricao = (
                    "🏆 O jogador venceu o combate!"
                )

                cor = discord.Color.green()

                self._salvar_participantes(
                    combate,
                    situacao_padrao="ativo"
                )

            else:

                descricao = (
                    "💀 O jogador foi derrotado."
                )

                cor = discord.Color.red()

                self._salvar_participantes(
                    combate,
                    situacao_padrao="ativo"
                )

        # ======================================================
        # EMBED FINAL
        # ======================================================

        embed = discord.Embed(
            title="⚔️ Combate Finalizado",
            description=descricao,
            color=cor
        )

        # ======================================================
        # MOSTRAR RECOMPENSAS
        # ======================================================

        embed.add_field(
            name="🎁 Recompensas",
            value=(
                f"✨ XP recebido: "
                f"**{recompensas['xp']}**\n"
                f"💰 Hunos recebidos: "
                f"**{recompensas['hunos']}**"
            ),
            inline=False
        )

        # ======================================================
        # STATUS FINAL
        # ======================================================

        embed.add_field(
            name="📋 Status Final",
            value=self._texto_status(
                combate["participantes"]
            ),
            inline=False
        )

        await ctx.send(
            embed=embed
        )

        if ctx.channel.id in self.combates:

            del self.combates[
                ctx.channel.id
            ]

    # ==========================================================
    # RESETAR
    # ==========================================================

    @commands.command(
        name="rluta",
        aliases=[
            "resetarluta"
        ]
    )
    async def rluta(
        self,
        ctx
    ):

        combate = self._obter_combate(
            ctx.channel.id
        )

        if not combate:

            await ctx.send(
                "❌ Não existe combate ativo neste canal."
            )

            return

        self._salvar_participantes(
            combate,
            situacao_padrao="ativo"
        )

        del self.combates[
            ctx.channel.id
        ]

        await ctx.send(
            "🔄 Combate resetado."
        )


# ==========================================================
# SETUP
# ==========================================================

async def setup(bot):

    await bot.add_cog(
        Luta(bot)
    )