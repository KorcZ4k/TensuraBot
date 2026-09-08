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
            embed.add_field(name=f"{dados.get('emoji', '👹')} {dados.get('nome', monstro_id)}", value=(f"ID: `{monstro_id}`\n" f"❤️ Vida: {dados.get('vida_base', 0)}\n" f"⚔️ Dano: {dados.get('dano_base', 0)}\n" f"✨ XP: {dados.get('xp_recompensa', 0)}\n" f"💰 Hunos: {dados.get('hunos_recompensa', 0)}"), inline=True)
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
        self.combates[ctx.channel.id] = {"participantes": participantes, "turno": 0, "numero_turno": 1, "fase": "ataque", "ativo": True, "pvp": False, "guild_id": guild_id, "ataque_pendente": None, "historico": [], "aguardando_finalizacao": False, "vencedor_id": None, "perdedor_id": None}
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
        self.combates[ctx.channel.id] = {"participantes": participantes, "turno": 0, "numero_turno": 1, "fase": "ataque", "ativo": True, "pvp": True, "guild_id": guild_id, "ataque_pendente": None, "historico": [], "aguardando_finalizacao": False, "vencedor_id": None, "perdedor_id": None}
        for jogador in participantes:
            self._atualizar_situacao(jogador["id"], guild_id, "ativo_combate")
        await self._mostrar_inicio(ctx)

    def _combate_ativo(self, channel_id):
        combate = self.combates.get(channel_id)
        return bool(combate and combate.get("ativo", False))

    def _encontrar_monstro(self, nome):
        nome = str(nome).strip().lower()
        for monstro_id, dados in MONSTROS.items():
            if str(monstro_id).lower() == nome:
                return monstro_id
            if str(dados.get("nome", "")).lower() == nome:
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
        atacante = self._obter_atacante(combate)
        defensor = self._obter_defensor(combate)
        embed = discord.Embed(title="⚔️ Combate PvP" if combate["pvp"] else "⚔️ Combate PvE", description=f"🔔 **Turno 1**\n\n⚔️ **{atacante['nome']}** começa atacando!", color=discord.Color.red())
        embed.add_field(name="🎯 Defensor", value=f"🛡️ **{defensor['nome']}**", inline=False)
        embed.add_field(name="📋 Status", value=self._texto_status(combate["participantes"]), inline=False)
        embed.set_footer(text="Tensura Moon • Korczak Technologies")
        await ctx.send(embed=embed)
        if atacante["tipo"] != "jogador":
            await asyncio.sleep(1)
            await self._ataque_monstro(ctx)

    async def _ataque_monstro(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo") or combate["fase"] != "ataque":
            return
        atacante = self._obter_atacante(combate)
        defensor = self._obter_defensor(combate)
        if atacante["tipo"] != "monstro":
            return
        combate["ataque_pendente"] = {"tipo": "ataque_monstro", "nome": "👹 Ataque do Monstro", "atacante_id": atacante.get("id"), "defensor_id": defensor.get("id"), "magia": False}
        combate["fase"] = "defesa"
        await self._anunciar_ataque(ctx)

    async def _ataque_jogador(self, ctx, tipo_ataque):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            await ctx.send("❌ Não há combate ativo.")
            return
        if combate.get("aguardando_finalizacao"):
            await ctx.send("❌ O vencedor precisa escolher `!matar` ou `!desmaiar`.")
            return
        if combate["fase"] != "ataque":
            await ctx.send("❌ O ataque anterior ainda precisa ser resolvido.")
            return
        atacante = self._obter_atacante(combate)
        defensor = self._obter_defensor(combate)
        if atacante["tipo"] != "jogador":
            await ctx.send(f"⏳ É a vez de **{atacante['nome']}**.")
            return
        if atacante["id"] != str(ctx.author.id):
            await ctx.send("❌ Não é sua vez de atacar.")
            return
        nomes = {"soco": "👊 Soco", "chute": "🦵 Chute"}
        combate["ataque_pendente"] = {"tipo": tipo_ataque, "nome": nomes.get(tipo_ataque, "⚔️ Ataque"), "atacante_id": atacante.get("id"), "defensor_id": defensor.get("id"), "magia": False}
        combate["fase"] = "defesa"
        await self._anunciar_ataque(ctx)

    @commands.command(name="soco")
    async def soco(self, ctx):
        await self._ataque_jogador(ctx, "soco")

    @commands.command(name="chute")
    async def chute(self, ctx):
        await self._ataque_jogador(ctx, "chute")

    async def usar_magia_no_combate(self, ctx, dados_magia):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return False
        if combate.get("aguardando_finalizacao"):
            await ctx.send("❌ O combate está aguardando a finalização.")
            return True
        if combate["fase"] != "ataque":
            await ctx.send("❌ O ataque anterior ainda precisa ser resolvido.")
            return True
        atacante = self._obter_atacante(combate)
        defensor = self._obter_defensor(combate)
        if atacante["tipo"] != "jogador" or atacante["id"] != str(ctx.author.id):
            await ctx.send("❌ Não é sua vez de usar magia.")
            return True
        mana_base = int(dados_magia.get("mana_base", 0) or 0)
        if int(atacante.get("mana", 0) or 0) < mana_base:
            await ctx.send(f"❌ Mana insuficiente. Necessário: {mana_base}.")
            return True
        atacante["mana"] = int(atacante.get("mana", 0) or 0) - mana_base
        combate["ataque_pendente"] = {"tipo": "magia", "nome": f"✨ {dados_magia.get('nome', 'Magia')}", "atacante_id": atacante.get("id"), "defensor_id": defensor.get("id"), "magia": True, "dano_base": float(dados_magia.get("dano_base", 0) or 0), "mana_base": mana_base, "elemento": dados_magia.get("elemento", ""), "efeito": dados_magia.get("efeito", {})}
        combate["fase"] = "defesa"
        await self._anunciar_ataque(ctx)
        return True

    async def _anunciar_ataque(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate:
            return
        ataque = combate.get("ataque_pendente")
        atacante = self._obter_atacante(combate)
        defensor = self._obter_defensor(combate)
        mensagem = f"{ataque['nome']}\n\n⚔️ **{atacante['nome']}** atacou **{defensor['nome']}**!"
        embed = discord.Embed(title=f"⚔️ Turno {combate['numero_turno']}", description=mensagem, color=discord.Color.orange())
        embed.add_field(name="📋 Status", value=self._texto_status(combate["participantes"]), inline=False)
        await ctx.send(embed=embed)
        if defensor["tipo"] == "monstro":
            await asyncio.sleep(1)
            await self._defesa_monstro(ctx)

    async def _defesa_jogador(self, ctx, acao):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or combate["fase"] != "defesa":
            await ctx.send("❌ Não existe um ataque para defender.")
            return
        defensor = self._obter_defensor(combate)
        if defensor["tipo"] != "jogador" or defensor["id"] != str(ctx.author.id):
            await ctx.send(f"❌ É **{defensor['nome']}** quem deve defender.")
            return
        defensor["defesa_ativa"] = acao == "defesa"
        defensor["esquiva_ativa"] = acao == "esquiva"
        await ctx.send(embed=discord.Embed(title="🛡️ Defesa" if acao == "defesa" else "💨 Esquiva", description=f"**{defensor['nome']}** escolheu {acao}.", color=discord.Color.blue()))
        await asyncio.sleep(0.5)
        await self._resolver_ataque(ctx)

    @commands.command(name="defesa", aliases=["defender", "def", "shield", "block", "bloquear", "bloqueio"])
    async def defesa(self, ctx):
        await self._defesa_jogador(ctx, "defesa")

    @commands.command(name="esquiva", aliases=["esquivar", "desviar", "dodge", "desvio"])
    async def esquiva(self, ctx):
        await self._defesa_jogador(ctx, "esquiva")

    async def _defesa_monstro(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or combate["fase"] != "defesa":
            return
        defensor = self._obter_defensor(combate)
        if defensor["tipo"] != "monstro":
            return
        escolha = random.choice(["defesa", "esquiva", "normal"])
        defensor["defesa_ativa"] = escolha == "defesa"
        defensor["esquiva_ativa"] = escolha == "esquiva"
        await asyncio.sleep(0.5)
        await self._resolver_ataque(ctx)

    def _calcular_dano_magia(self, atacante, defensor, ataque):
        dano = float(ataque.get("dano_base", 0) or 0) + float(atacante.get("Magia", atacante.get("magia", 0)) or 0) * 0.10
        if defensor.get("esquiva_ativa") and random.random() < min(0.75, 0.10 + float(defensor.get("velocidade", defensor.get("Velocidade", 0)) or 0) / 500):
            defensor["esquiva_ativa"] = False
            return 0, "esquivou"
        if defensor.get("defesa_ativa"):
            dano -= float(defensor.get("defesa", defensor.get("Defesa", 0)) or 0) * 0.20
        return max(0, int(dano)), "atingiu"

    def _aplicar_efeito(self, defensor, efeito):
        if not isinstance(efeito, dict) or not efeito.get("nome"):
            return None
        defensor.setdefault("efeitos", []).append({"nome": str(efeito.get("nome")).lower(), "turnos": int(efeito.get("turnos", 1) or 1), "valor": efeito.get("valor", 0)})
        return str(efeito.get("nome"))

    def _processar_efeitos(self, participante):
        novos, dano_total, bloqueado, mensagens = [], 0, False, []
        for efeito in participante.get("efeitos", []):
            nome = str(efeito.get("nome", "")).lower()
            turnos = int(efeito.get("turnos", 0) or 0)
            valor = abs(int(efeito.get("valor", 0) or 0))
            if nome in ["veneno", "queimadura", "sangramento"]:
                dano_total += valor or 5
                mensagens.append(f"{nome.title()} causou {valor or 5} de dano.")
            elif nome in ["paralisia", "stun", "prisão", "prisao"]:
                bloqueado = True
            turnos -= 1
            if turnos > 0:
                efeito["turnos"] = turnos
                novos.append(efeito)
        participante["efeitos"] = novos
        participante["vida"] = max(0, participante.get("vida", 0) - dano_total)
        return dano_total, bloqueado, mensagens

    async def _resolver_ataque(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate:
            return
        ataque = combate.get("ataque_pendente")
        if not ataque:
            return
        atacante = self._obter_atacante(combate)
        defensor = self._obter_defensor(combate)
        if ataque.get("tipo") == "magia":
            if ataque.get("dano_base", 0) < 0:
                cura = abs(int(ataque.get("dano_base", 0)))
                atacante["vida"] = min(atacante["vida_maxima"], atacante["vida"] + cura)
                mensagem = f"✨ **{atacante['nome']}** recuperou **{cura} de vida**!"
            else:
                dano, resultado = self._calcular_dano_magia(atacante, defensor, ataque)
                if resultado == "esquivou":
                    mensagem = f"💨 **{defensor['nome']}** esquivou completamente da magia!"
                else:
                    defensor["vida"] = max(0, defensor["vida"] - dano)
                    mensagem = f"✨ **{atacante['nome']}** causou **{dano} de dano mágico** em **{defensor['nome']}**!"
                    efeito = self._aplicar_efeito(defensor, ataque.get("efeito", {}))
                    if efeito:
                        mensagem += f"\n⚠️ Efeito aplicado: **{efeito.title()}**"
        else:
            dano, resultado = calcular_dano(atacante, defensor)
            if resultado == "esquivou":
                mensagem = f"💨 **{defensor['nome']}** esquivou do ataque de **{atacante['nome']}**!"
            else:
                defensor["vida"] = max(0, defensor["vida"] - dano)
                mensagem = f"⚔️ **{atacante['nome']}** causou **{dano} de dano** em **{defensor['nome']}**!"
        defensor["defesa_ativa"] = False
        defensor["esquiva_ativa"] = False
        combate["historico"].append(mensagem)
        embed = discord.Embed(title="💥 Resultado", description=mensagem, color=discord.Color.red())
        embed.add_field(name="📋 Status", value=self._texto_status(combate["participantes"]), inline=False)
        await ctx.send(embed=embed)
        if defensor["vida"] <= 0:
            if combate["pvp"]:
                combate["aguardando_finalizacao"] = True
                combate["vencedor_id"] = atacante["id"]
                combate["perdedor_id"] = defensor["id"]
                combate["fase"] = "finalizacao"
                await ctx.send(f"⚠️ **{defensor['nome']}** está incapacitado!\n\n🏆 **{atacante['nome']}**, escolha:\n`!matar`\n`!desmaiar`")
                return
            combate["ativo"] = False
            await self._finalizar(ctx, motivo="vida")
            return
        await asyncio.sleep(1)
        await self._proximo_turno(ctx)

    async def _proximo_turno(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return
        combate["turno"] = (combate["turno"] + 1) % len(combate["participantes"])
        combate["numero_turno"] += 1
        combate["fase"] = "ataque"
        combate["ataque_pendente"] = None
        atacante = self._obter_atacante(combate)
        dano_efeitos, bloqueado, _ = self._processar_efeitos(atacante)
        if dano_efeitos:
            await ctx.send(f"⚠️ **{atacante['nome']}** sofreu **{dano_efeitos} de dano** por efeitos.")
        if atacante["vida"] <= 0:
            combate["ativo"] = False
            await self._finalizar(ctx, motivo="efeitos")
            return
        if bloqueado:
            await ctx.send(f"⚠️ **{atacante['nome']}** não consegue agir neste turno!")
            await asyncio.sleep(1)
            await self._proximo_turno(ctx)
            return
        defensor = self._obter_defensor(combate)
        embed = discord.Embed(title=f"🔄 Turno {combate['numero_turno']}", description=f"⚔️ Agora é a vez de **{atacante['nome']}** atacar!", color=discord.Color.green())
        embed.add_field(name="🎯 Defensor", value=f"🛡️ **{defensor['nome']}**", inline=False)
        embed.add_field(name="📋 Status", value=self._texto_status(combate["participantes"]), inline=False)
        await ctx.send(embed=embed)
        if atacante["tipo"] == "monstro":
            await asyncio.sleep(1)
            await self._ataque_monstro(ctx)

    @commands.command(name="fugir", aliases=["fuga", "escape", "escapar", "run"])
    async def fugir(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            await ctx.send("❌ Você não está em combate.")
            return
        jogador = next((p for p in combate["participantes"] if p["tipo"] == "jogador" and p.get("id") == str(ctx.author.id)), None)
        if not jogador:
            await ctx.send("❌ Você não participa deste combate.")
            return
        if random.random() > (0.15 if not combate["pvp"] else 0.10):
            await ctx.send("❌ Você não conseguiu fugir!")
            return
        combate["ativo"] = False
        self._salvar_participantes(combate, situacao_padrao="ativo")
        await ctx.send(f"🏃 **{jogador['nome']}** conseguiu fugir!")
        del self.combates[ctx.channel.id]

    @commands.command(name="matar")
    async def matar(self, ctx):
        await self._finalizar_pvp(ctx, "morte")

    @commands.command(name="desmaiar")
    async def desmaiar(self, ctx):
        await self._finalizar_pvp(ctx, "desmaio")

    async def _finalizar_pvp(self, ctx, motivo):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("aguardando_finalizacao"):
            await ctx.send("❌ Nenhuma finalização pendente.")
            return
        if str(ctx.author.id) != str(combate.get("vencedor_id")):
            await ctx.send("❌ Apenas o vencedor pode decidir.")
            return
        vencedor = self._buscar_participante(combate, combate["vencedor_id"])
        perdedor = self._buscar_participante(combate, combate["perdedor_id"])
        if not vencedor or not perdedor:
            return
        perdedor["vida"] = 0 if motivo == "morte" else 1
        combate["ativo"] = False
        combate["aguardando_finalizacao"] = False
        await self._finalizar(ctx, motivo=motivo, vencedor=vencedor, perdedor=perdedor)

    def _buscar_participante(self, combate, user_id):
        return next((p for p in combate["participantes"] if str(p.get("id")) == str(user_id)), None)

    def _obter_recompensas_pve(self, combate):
        monstro = next((p for p in combate["participantes"] if p.get("tipo") == "monstro"), None)
        if not monstro:
            return {"xp": 0, "hunos": 0}
        monstro_id = str(monstro.get("monstro_id", monstro.get("id", ""))).lower().strip()
        dados = MONSTROS.get(monstro_id, {})
        xp = int(monstro.get("xp_recompensa", dados.get("xp_recompensa", 0)) or 0)
        hunos = int(monstro.get("hunos_recompensa", dados.get("hunos_recompensa", 0)) or 0)
        return {"xp": xp, "hunos": hunos}

    def _dar_recompensas(self, user_id, guild_id, xp, hunos):
        if db is None:
            return
        db["Jogadores"].update_one({"ID": str(user_id), "guild_id": str(guild_id)}, {"$inc": {"XP": int(xp or 0)}})
        if int(hunos or 0) > 0:
            db["Hunos"].update_one({"ID": str(user_id), "guild_id": str(guild_id)}, {"$inc": {"carteira": int(hunos)}}, upsert=True)

    def _salvar_participantes(self, combate, situacao_padrao="ativo", morto_id=None):
        if db is None:
            return
        for participante in combate["participantes"]:
            if participante["tipo"] != "jogador":
                continue
            situacao = "morto" if morto_id is not None and str(participante["id"]) == str(morto_id) else situacao_padrao
            db["Jogadores"].update_one({"ID": str(participante["id"]), "guild_id": str(combate["guild_id"])}, {"$set": {"Vida": int(participante.get("vida", 0)), "Mana": int(participante.get("mana", 0)), "Situação": situacao}})

    async def _finalizar(self, ctx, motivo="vida", vencedor=None, perdedor=None):
        combate = self._obter_combate(ctx.channel.id)
        if not combate:
            return
        combate["ativo"] = False
        recompensas = {"xp": 0, "hunos": 0}
        if combate["pvp"]:
            self._salvar_participantes(combate, situacao_padrao="ativo", morto_id=perdedor["id"] if motivo == "morte" and perdedor else None)
            descricao = f"💀 **{vencedor['nome']}** matou **{perdedor['nome']}**." if motivo == "morte" and vencedor and perdedor else "😵 O combate PvP terminou com desmaio."
        else:
            resultado = obter_vencedores(combate)
            if isinstance(resultado, dict) and resultado.get("tipo") == "vitoria" and resultado.get("lado") == "jogadores":
                recompensas = self._obter_recompensas_pve(combate)
                jogador = next((p for p in combate["participantes"] if p["tipo"] == "jogador"), None)
                if jogador:
                    self._dar_recompensas(jogador["id"], combate["guild_id"], recompensas["xp"], recompensas["hunos"])
                descricao = "🏆 O jogador venceu o combate!"
            else:
                descricao = "💀 O jogador foi derrotado."
            self._salvar_participantes(combate, situacao_padrao="ativo")
        embed = discord.Embed(title="⚔️ Combate Finalizado", description=descricao, color=discord.Color.green() if recompensas["xp"] else discord.Color.red())
        embed.add_field(name="🎁 Recompensas", value=f"✨ XP recebido: **{recompensas['xp']}**\n💰 Hunos recebidos: **{recompensas['hunos']}**", inline=False)
        embed.add_field(name="📋 Status Final", value=self._texto_status(combate["participantes"]), inline=False)
        await ctx.send(embed=embed)
        self.combates.pop(ctx.channel.id, None)

    @commands.command(name="rluta", aliases=["resetarluta"])
    async def rluta(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate:
            await ctx.send("❌ Não existe combate ativo neste canal.")
            return
        self._salvar_participantes(combate, situacao_padrao="ativo")
        del self.combates[ctx.channel.id]
        await ctx.send("🔄 Combate resetado.")


async def setup(bot):
    await bot.add_cog(Luta(bot))
