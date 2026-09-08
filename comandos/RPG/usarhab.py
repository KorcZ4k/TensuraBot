import asyncio
import json
import unicodedata
import random
import discord
from discord.ext import commands


ARQUIVO_DANOS = "database/json/habilidades/danos.json"


class UsarHabilidade(commands.Cog):
    """Execução das habilidades ativas Comuns e Únicas e efeitos especiais de combate."""

    def __init__(self, bot):
        self.bot = bot
        self.danos = self._carregar_danos()

    def _carregar_danos(self):
        try:
            with open(ARQUIVO_DANOS, "r", encoding="utf-8") as f:
                dados = json.load(f)
            dados.setdefault("padrao", {})
            dados.setdefault("habilidades", {})
            return dados
        except Exception as e:
            print(f"❌ Erro ao carregar danos.json: {e}")
            return {"padrao": {}, "habilidades": {}}

    @staticmethod
    def _normalizar(texto):
        texto = unicodedata.normalize("NFKD", str(texto or ""))
        return "".join(c for c in texto if not unicodedata.combining(c)).casefold().strip()

    def _buscar_habilidade_por_nome(self, nome):
        cog = self.bot.get_cog("Habilidades")
        if not cog:
            return None
        procurado = self._normalizar(nome)
        for habilidade in cog.cache_habilidades.values():
            if self._normalizar(habilidade.get("nome")) == procurado:
                return habilidade
        return None

    def _jogador_possui(self, user_id, guild_id, habilidade_id):
        from database.python.mongodb import db
        if db is None:
            return False
        doc = db["Habilidades"].find_one({"ID": str(user_id), "guild_id": str(guild_id)})
        if not doc:
            return False
        habilidades = doc.get("habilidades", [])
        if isinstance(habilidades, str):
            habilidades = [x.strip().strip("\"'") for x in habilidades.replace("[", "").replace("]", "").split(",")]
        for item in habilidades:
            if isinstance(item, dict):
                item = item.get("id") or item.get("ID")
            if str(item).strip() == str(habilidade_id):
                return True
        return False

    def _tem_habilidade(self, participante, combate, nome):
        if participante.get("tipo") != "jogador") or not combate.get("guild_id"):
            return False
        habilidade = self._buscar_habilidade_por_nome(nome)
        return bool(habilidade and self._jogador_possui(participante.get("id"), combate.get("guild_id"), habilidade.get("id")))

    @staticmethod
    def _arma_cortante(participante):
        nome = str(participante.get("arma_nome", participante.get("Arma", "")) or "").casefold()
        tipos = ("espada", "katana", "faca", "adaga", "machado", "machad", "foice", "lanca", "lança", "sabre", "cutelo", "navalha", "glaive", "rapiera", "rapieira")
        return bool(nome) and any(tipo in nome for tipo in tipos)

    @staticmethod
    def _recalcular_defesa(participante):
        participante["defesa"] = float(participante.get("Força", 0) or 0) + float(participante.get("Defesa", 0) or 0)

    @staticmethod
    def _aumentar_atributo(participante, chave, percentual):
        participante[chave] = int(float(participante.get(chave, 0) or 0) * (1 + percentual))

    def _aplicar_buff_comandante(self, atacante, combate):
        if not combate.get("party") or atacante.get("comandante_aplicado"):
            return False
        for chave in ("Força", "Defesa", "Vitalidade", "Velocidade", "Destreza", "Magia", "Sorte", "Inteligencia"):
            self._aumentar_atributo(atacante, chave, 0.20)
        atacante["vida_maxima"] = int(float(atacante.get("Vitalidade", 0) or 0) * 10)
        atacante["vida"] = min(atacante["vida_maxima"], int(atacante.get("vida", 0) or 0))
        atacante["mana"] = int(float(atacante.get("Magia", 0) or 0))
        self._recalcular_defesa(atacante)
        atacante["comandante_aplicado"] = True
        return True

    def _incorporar_habilidade(self, user_id, guild_id, habilidade):
        from database.python.mongodb import db
        if db is None or not habilidade:
            return False
        resultado = db["Habilidades"].update_one(
            {"ID": str(user_id), "guild_id": str(guild_id)},
            {"$addToSet": {"habilidades": str(habilidade.get("id"))}},
        )
        return bool(resultado.modified_count)

    def _sortear_habilidade(self, user_id, guild_id):
        cog = self.bot.get_cog("Habilidades")
        if not cog:
            return None
        candidatas = []
        for habilidade in cog.cache_habilidades.values():
            if self._normalizar(habilidade.get("ativa")) not in {"sim", "true", "ativa", "yes", "1"} and self._normalizar(habilidade.get("tipo")) != "ativa":
                continue
            if not self._jogador_possui(user_id, guild_id, habilidade.get("id")):
                candidatas.append(habilidade)
        return random.choice(candidatas) if candidatas else None

    def _configuracao(self, habilidade):
        padrao = dict(self.danos.get("padrao", {}))
        especifica = self.danos.get("habilidades", {}).get(str(habilidade["id"]), {})
        config = dict(padrao)
        config.update(especifica)
        if especifica:
            return config
        config.update({"dano": 15, "gasto_mana": 10, "chance_acerto": 0.90, "recarga_turnos": 2, "efeitos": []})
        return config

    @staticmethod
    def _efeitos_para_combate(config):
        efeitos = []
        for efeito in config.get("efeitos", []) or []:
            if not isinstance(efeito, dict):
                continue
            efeitos.append({
                "nome": str(efeito.get("tipo", "")).strip().lower(),
                "turnos": max(1, int(efeito.get("duracao", 1) or 1)),
                "valor": efeito.get("valor", 0),
                "chance": max(0.0, min(1.0, float(efeito.get("chance", 1.0) or 0))),
            })
        return efeitos

    def _instalar_resolvedor(self, luta):
        if getattr(luta, "_usarhab_resolvedor", False):
            return
        original = luta._resolver_ataque
        cog = self

        async def resolver_corte(ctx, combate, ataque, atacante, defensor):
            if not cog._arma_cortante(atacante):
                await ctx.send("❌ `!corte` exige uma arma cortante equipada.")
                combate["fase"] = "ataque"
                combate["ataque_pendente"] = None
                return True
            dano = float(atacante.get("Força", 0) or 0) + float(atacante.get("Velocidade", 0) or 0)
            if defensor.get("defesa_ativa"):
                dano -= float(defensor.get("defesa", 0) or 0)
            dano = max(0, int(dano))
            multiplicador = 1.0
            if cog._tem_habilidade(atacante, combate, "chef"):
                multiplicador += 0.10
            if cog._tem_habilidade(atacante, combate, "cozinheiro"):
                multiplicador += 0.05
            dano = int(dano * multiplicador)
            if defensor.get("esquiva_ativa"):
                defensor["esquiva_ativa"] = False
                if random.random() < min(0.75, 0.10 + float(defensor.get("Velocidade", 0) or 0) / 500):
                    dano = 0
            defensor["vida"] = max(0, int(defensor.get("vida", 0)) - dano)
            defensor["defesa_ativa"] = False
            mensagem = f"⚔️ **{atacante['nome']}** causou **{dano} de dano** com **Corte**!"
            if multiplicador > 1:
                mensagem += f"\n🔪 Bônus de armas cortantes: **+{int((multiplicador - 1) * 100)}%**."
            combate["historico"].append(mensagem)
            embed = discord.Embed(title="💥 Resultado do Corte", description=mensagem, color=discord.Color.red())
            embed.add_field(name="📋 Status", value=luta._texto_status(combate["participantes"]), inline=False)
            await ctx.send(embed=embed)
            if defensor["vida"] <= 0:
                combate["ativo"] = False
                await luta._finalizar(ctx, motivo="vida")
            else:
                await asyncio.sleep(1)
                await luta._proximo_turno(ctx)
            return True

        async def resolvedor(ctx):
            combate = luta._obter_combate(ctx.channel.id)
            ataque = combate.get("ataque_pendente") if combate else None
            if not ataque:
                return await original(ctx)

            atacante = luta._obter_atacante(combate)
            defensor = luta._obter_defensor(combate)

            # Desviante: esquiva automática quando Velocidade + Destreza >= Velocidade do atacante.
            if defensor.get("tipo") == "jogador" and cog._tem_habilidade(defensor, combate, "desviante"):
                soma = float(defensor.get("Velocidade", 0) or 0) + float(defensor.get("Destreza", 0) or 0)
                velocidade_atacante = float(atacante.get("Velocidade", 0) or 0)
                if soma >= velocidade_atacante:
                    defensor["defesa_ativa"] = False
                    defensor["esquiva_ativa"] = False
                    mensagem = f"💨 **{defensor['nome']}** ativou **Desviante** e desviou automaticamente do ataque!"
                    combate["historico"].append(mensagem)
                    await ctx.send(embed=discord.Embed(title="💨 Desviante", description=mensagem, color=discord.Color.blue()))
                    await asyncio.sleep(1)
                    await luta._proximo_turno(ctx)
                    return

            if ataque.get("tipo") == "corte":
                await resolver_corte(ctx, combate, ataque, atacante, defensor)
                return

            if ataque.get("tipo") != "habilidade":
                return await original(ctx)

            habilidade = ataque["habilidade"]
            nome = cog._normalizar(habilidade.get("nome"))

            # Gula e Glutão: execução por limiar de vida e sorteio de habilidade.
            if nome in {"gula", "glutao"}:
                percentual = 0.10 if nome == "gula" else 0.05
                vida_maxima = float(defensor.get("vida_maxima", 0) or 0)
                if vida_maxima > 0 and float(defensor.get("vida", 0) or 0) <= vida_maxima * percentual:
                    defensor["vida"] = 0
                    chance = 0.30 if nome == "gula" else 0.20
                    sorteada = cog._sortear_habilidade(atacante.get("id"), combate.get("guild_id")) if random.random() < chance else None
                    if sorteada:
                        cog._incorporar_habilidade(atacante.get("id"), combate.get("guild_id"), sorteada)
                        mensagem = f"🍴 **{atacante['nome']}** executou **{habilidade['nome']}** e incorporou **{sorteada.get('nome')}**!"
                    else:
                        mensagem = f"🍴 **{atacante['nome']}** executou **{habilidade['nome']}** e devorou **{defensor['nome']}**, mas não incorporou uma habilidade."
                    combate["historico"].append(mensagem)
                    await ctx.send(embed=discord.Embed(title="🍴 Predação", description=mensagem, color=discord.Color.dark_red()))
                    combate["ativo"] = False
                    await luta._finalizar(ctx, motivo="vida")
                    return

            chance = float(ataque.get("chance_acerto", 1.0) or 1.0)
            if random.random() > chance:
                mensagem = f"💨 **{atacante['nome']}** falhou ao usar **{habilidade['nome']}**!"
                dano = 0
            else:
                poder = float(atacante.get("Magia", 0) or 0) + float(atacante.get("Inteligencia", 0) or 0)
                dano = max(0, int(poder + float(ataque.get("dano_base", 0) or 0)))
                if defensor.get("esquiva_ativa"):
                    defensor["esquiva_ativa"] = False
                    if random.random() < min(0.75, 0.10 + float(defensor.get("Velocidade", 0) or 0) / 500):
                        dano = 0
                elif defensor.get("defesa_ativa"):
                    dano = max(0, int(dano - float(defensor.get("defesa", 0) or 0)))
                elif defensor.get("defesa_magica_ativa"):
                    dano = max(0, int(dano - float(defensor.get("defesa_magica_valor", 0) or 0)))
                    defensor["defesa_magica_ativa"] = False
                    defensor["defesa_magica_valor"] = 0

                # Falsificador recebe dano adicional.
                if nome == "falsificador" and dano > 0:
                    dano += 20

                defensor["vida"] = max(0, int(defensor.get("vida", 0)) - dano)
                mensagem = f"✨ **{atacante['nome']}** causou **{dano} de dano** com **{habilidade['nome']}**!"

                efeitos_aplicados = []
                if nome == "comandante":
                    if combate.get("party"):
                        if cog._aplicar_buff_comandante(atacante, combate):
                            efeitos_aplicados.append("+20% em todos os atributos")
                    else:
                        efeitos_aplicados.append("requer uma party")

                for efeito in ataque.get("efeitos", []):
                    if random.random() > float(efeito.get("chance", 1.0) or 0):
                        continue
                    enome = str(efeito.get("nome", "")).lower()
                    valor = efeito.get("valor", 0)
                    alvo = atacante if enome.startswith("buff_") else defensor
                    if enome == "escudo":
                        atacante["defesa_magica_ativa"] = True
                        atacante["defesa_magica_valor"] = int(valor or 0)
                        efeitos_aplicados.append(f"escudo {int(valor or 0)}")
                    elif enome == "cura_por_dano":
                        cura = int(dano * float(valor or 0))
                        atacante["vida"] = min(int(atacante.get("vida_maxima", atacante.get("vida", 0))), int(atacante.get("vida", 0)) + cura)
                        efeitos_aplicados.append(f"cura {cura}")
                    elif enome.startswith("buff_"):
                        chave = {"forca": "Força", "defesa": "Defesa", "velocidade": "Velocidade", "destreza": "Destreza"}.get(enome.removeprefix("buff_"))
                        if chave:
                            cog._aumentar_atributo(alvo, chave, float(valor or 0))
                            cog._recalcular_defesa(alvo)
                            efeitos_aplicados.append(f"+{int(float(valor or 0) * 100)}% {chave}")
                    elif enome.startswith("debuff_"):
                        chave = {"defesa": "Defesa", "velocidade": "Velocidade", "forca": "Força"}.get(enome.removeprefix("debuff_"))
                        if chave:
                            alvo[chave] = max(0, int(float(alvo.get(chave, 0) or 0) * (1 - float(valor or 0))))
                            cog._recalcular_defesa(alvo)
                            efeitos_aplicados.append(f"-{int(float(valor or 0) * 100)}% {chave}")
                    else:
                        alvo.setdefault("efeitos", []).append({"nome": enome, "turnos": int(efeito.get("turnos", 1) or 1), "valor": valor})
                        efeitos_aplicados.append(enome)

                if nome == "desviante":
                    efeitos_aplicados.append("esquiva automática: Velocidade + Destreza")
                if nome == "luxuria":
                    efeitos_aplicados.append("+15% Velocidade e +15% Destreza")
                if nome == "mestre marcial":
                    efeitos_aplicados.append("+20% Força e +20% Defesa")
                if nome == "lutador":
                    efeitos_aplicados.append("25 de dano +10% Força e +10% Defesa")
                if efeitos_aplicados:
                    mensagem += "\n⚠️ Efeitos: " + ", ".join(efeitos_aplicados)

            defensor["defesa_ativa"] = False
            defensor["esquiva_ativa"] = False
            combate["historico"].append(mensagem)
            embed = discord.Embed(title="💥 Resultado da Habilidade", description=mensagem, color=discord.Color.purple())
            embed.add_field(name="📋 Status", value=luta._texto_status(combate["participantes"]), inline=False)
            await ctx.send(embed=embed)

            if defensor["vida"] <= 0:
                if combate.get("pvp"):
                    combate["aguardando_finalizacao"] = True
                    combate["vencedor_id"] = atacante["id"]
                    combate["perdedor_id"] = defensor["id"]
                    combate["fase"] = "finalizacao"
                    await ctx.send(f"⚠️ **{defensor['nome']}** está incapacitado!\n\n🏆 **{atacante['nome']}**, escolha:\n`!matar`\n`!desmaiar`")
                    return
                combate["ativo"] = False
                await luta._finalizar(ctx, motivo="vida")
                return

            await asyncio.sleep(1)
            await luta._proximo_turno(ctx)

        luta._resolver_ataque = resolvedor
        luta._usarhab_resolvedor = True

    @commands.command(name="corte")
    async def corte(self, ctx):
        luta = self.bot.get_cog("Luta")
        if not luta:
            await ctx.send("❌ Sistema de luta não está carregado.")
            return
        if ctx.channel.id not in getattr(luta, "combates", {}):
            await ctx.send("❌ `!corte` só pode ser usado durante uma batalha.")
            return
        self._instalar_resolvedor(luta)
        combate = luta._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            await ctx.send("❌ Não há combate ativo.")
            return
        if combate.get("fase") != "ataque":
            await ctx.send("❌ O ataque anterior ainda precisa ser resolvido.")
            return
        atacante = luta._obter_atacante(combate)
        if atacante.get("tipo") != "jogador" or str(atacante.get("id")) != str(ctx.author.id):
            await ctx.send("❌ Não é sua vez de atacar.")
            return
        if not self._arma_cortante(atacante):
            await ctx.send("❌ Você precisa estar equipado com uma arma cortante para usar `!corte`.")
            return
        defensor = luta._obter_defensor(combate)
        combate["ataque_pendente"] = {
            "tipo": "corte", "nome": "⚔️ Corte", "atacante_id": atacante.get("id"),
            "defensor_id": defensor.get("id"), "magia": False, "com_arma": True,
        }
        combate["fase"] = "defesa"
        await luta._anunciar_ataque(ctx)

    @commands.command(name="usarhab")
    async def usarhab(self, ctx, *, nome: str = None):
        if not nome:
            await ctx.send("❌ Use: `!usarhab <nome da habilidade>`")
            return
        if ctx.guild is None:
            await ctx.send("❌ Este comando só pode ser usado em um servidor.")
            return

        habilidade = self._buscar_habilidade_por_nome(nome)
        if not habilidade:
            await ctx.send(f"❌ Não encontrei nenhuma habilidade chamada **{nome}**.")
            return
        ativa = self._normalizar(habilidade.get("ativa")) in {"sim", "true", "ativa", "yes", "1"}
        tipo = self._normalizar(habilidade.get("tipo"))
        if not ativa and tipo != "ativa":
            await ctx.send(f"❌ **{habilidade['nome']}** é uma habilidade passiva e não pode ser usada diretamente em combate.")
            return
        if not self._jogador_possui(ctx.author.id, ctx.guild.id, habilidade["id"]):
            await ctx.send("❌ Você não possui essa habilidade.")
            return

        luta = self.bot.get_cog("Luta")
        if not luta:
            await ctx.send("❌ Sistema de luta não está carregado.")
            return
        self._instalar_resolvedor(luta)
        combate = luta.combates.get(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            await ctx.send("❌ `!usarhab` só pode ser usado durante uma batalha.")
            return
        if combate.get("fase") != "ataque":
            await ctx.send("❌ O ataque anterior ainda precisa ser defendido.")
            return
        atacante = luta._obter_atacante(combate)
        defensor = luta._obter_defensor(combate)
        if atacante.get("tipo") != "jogador" or str(atacante.get("id")) != str(ctx.author.id):
            await ctx.send(f"❌ Não é sua vez. Agora é a vez de **{atacante.get('nome', 'outro participante')}**.")
            return

        configuracao = self._configuracao(habilidade)
        mana = int(float(atacante.get("mana", 0) or 0))
        gasto = int(float(configuracao.get("gasto_mana", 0) or 0))
        if mana < gasto:
            await ctx.send(f"❌ Mana insuficiente. Necessário: **{gasto}** | Atual: **{mana}**")
            return
        atacante["mana"] = mana - gasto
        efeitos = self._efeitos_para_combate(configuracao)
        combate["ataque_pendente"] = {
            "tipo": "habilidade", "nome": f"✨ {habilidade['nome']}",
            "atacante_id": atacante["id"], "defensor_id": defensor["id"],
            "magia": False, "habilidade": habilidade,
            "dano_base": int(float(configuracao.get("dano", 0) or 0)),
            "chance_acerto": float(configuracao.get("chance_acerto", 1.0) or 1.0),
            "efeitos": efeitos, "efeito": efeitos[0] if efeitos else {}, "com_arma": False,
        }
        combate["fase"] = "defesa"
        embed = discord.Embed(
            title=f"✨ Turno {combate['numero_turno']} — Habilidade",
            description=(f"**{atacante['nome']}** usou **{habilidade['nome']}** contra **{defensor['nome']}**!\n"
                         f"💙 Mana gasta: **{gasto}**\n"
                         f"⚡ Poder da habilidade: **{int(float(configuracao.get('dano', 0) or 0))}**\n\n"
                         f"🛡️ **{defensor['nome']}** deve usar `!defesa` ou `!esquiva`."),
            color=discord.Color.purple())
        await ctx.send(embed=embed)
        if defensor.get("tipo") == "monstro":
            await asyncio.sleep(1)
            await luta._defesa_monstro(ctx)


async def setup(bot):
    await bot.add_cog(UsarHabilidade(bot))
