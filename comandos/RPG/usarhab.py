import asyncio
import json
import unicodedata
import random
import discord
from discord.ext import commands


ARQUIVO_DANOS = "database/json/habilidades/danos.json"


class UsarHabilidade(commands.Cog):
    """Execução universal das habilidades ativas Comuns e Únicas."""

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

    def _configuracao(self, habilidade):
        """Usa configuração específica; nenhuma ativa fica sem comportamento."""
        padrao = dict(self.danos.get("padrao", {}))
        especifica = self.danos.get("habilidades", {}).get(str(habilidade["id"]), {})
        config = dict(padrao)
        config.update(especifica)
        if especifica:
            return config

        nome = self._normalizar(habilidade.get("nome"))
        config.update({"dano": 15, "gasto_mana": 10, "chance_acerto": 0.90, "recarga_turnos": 2, "efeitos": []})
        if nome in {"chef", "cozinheiro", "comandante", "falsificador", "fusionista", "luxuria", "musico", "opressor", "confusao", "preguica", "reversor", "desviante"}:
            config["dano"] = 0
        elif nome in {"lutador", "mestre marcial", "assassino", "ceifador", "atacante das sombras", "separador", "separacao absoluta", "predador", "engolidor", "gula", "glutao"}:
            config["dano"] = 35
        elif nome in {"berserk", "besta real"}:
            config["dano"] = 20
        return config

    @staticmethod
    def _efeitos_para_combate(config):
        efeitos = []
        for efeito in config.get("efeitos", []) or []:
            if not isinstance(efeito, dict):
                continue
            efeitos.append({
                "nome": str(efeito.get("tipo", "habilidade")).strip().lower(),
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

        async def resolvedor(ctx):
            combate = luta._obter_combate(ctx.channel.id)
            ataque = combate.get("ataque_pendente") if combate else None
            if not ataque or ataque.get("tipo") != "habilidade":
                return await original(ctx)

            atacante = luta._obter_atacante(combate)
            defensor = luta._obter_defensor(combate)
            chance = float(ataque.get("chance_acerto", 1.0) or 1.0)

            if random.random() > chance:
                mensagem = f"💨 **{atacante['nome']}** falhou ao usar **{ataque['habilidade']['nome']}**!"
                dano = 0
            else:
                # Habilidades usam o poder mágico + inteligência como base,
                # somado ao valor específico da habilidade.
                poder = float(atacante.get("Magia", 0) or 0) + float(atacante.get("Inteligencia", 0) or 0)
                dano = max(0, int(poder + float(ataque.get("dano_base", 0) or 0)))

                if defensor.get("esquiva_ativa"):
                    defensor["esquiva_ativa"] = False
                    if random.random() < min(0.75, 0.10 + float(defensor.get("Velocidade", 0) or 0) / 500):
                        dano = 0
                        mensagem = f"💨 **{defensor['nome']}** esquivou da habilidade **{ataque['habilidade']['nome']}**!"
                    else:
                        mensagem = f"✨ **{atacante['nome']}** causou **{dano} de dano** com **{ataque['habilidade']['nome']}**!"
                else:
                    if defensor.get("defesa_ativa"):
                        defesa = float(defensor.get("defesa", 0) or 0)
                        dano = max(0, int(dano - defesa))
                    elif defensor.get("defesa_magica_ativa"):
                        dano = max(0, int(dano - float(defensor.get("defesa_magica_valor", 0) or 0)))
                        defensor["defesa_magica_ativa"] = False
                        defensor["defesa_magica_valor"] = 0
                    mensagem = f"✨ **{atacante['nome']}** causou **{dano} de dano** com **{ataque['habilidade']['nome']}**!"

                defensor["vida"] = max(0, defensor.get("vida", 0) - dano)

                # Efeitos configurados individualmente.
                efeitos_aplicados = []
                for efeito in ataque.get("efeitos", []):
                    if random.random() > float(efeito.get("chance", 1.0) or 0):
                        continue
                    nome = str(efeito.get("nome", "")).lower()
                    valor = efeito.get("valor", 0)
                    alvo = atacante if nome.startswith("buff_") else defensor
                    if nome == "escudo":
                        atacante["defesa_magica_ativa"] = True
                        atacante["defesa_magica_valor"] = int(valor or 0)
                        efeitos_aplicados.append(f"escudo {int(valor or 0)}")
                    elif nome == "cura_por_dano":
                        cura = int(dano * float(valor or 0))
                        atacante["vida"] = min(atacante.get("vida_maxima", atacante["vida"]), atacante["vida"] + cura)
                        efeitos_aplicados.append(f"cura {cura}")
                    elif nome.startswith("buff_"):
                        atributo = nome.removeprefix("buff_")
                        chave = {"forca": "Força", "defesa": "Defesa", "velocidade": "Velocidade", "destreza": "Destreza"}.get(atributo)
                        if chave:
                            alvo[chave] = int(float(alvo.get(chave, 0) or 0) * (1 + float(valor or 0)))
                            alvo["defesa"] = float(alvo.get("Força", 0)) + float(alvo.get("Defesa", 0))
                            efeitos_aplicados.append(f"+{int(float(valor or 0) * 100)}% {chave}")
                    elif nome.startswith("debuff_"):
                        atributo = nome.removeprefix("debuff_")
                        chave = {"defesa": "Defesa", "velocidade": "Velocidade", "forca": "Força"}.get(atributo)
                        if chave:
                            alvo[chave] = max(0, int(float(alvo.get(chave, 0) or 0) * (1 - float(valor or 0))))
                            alvo["defesa"] = float(alvo.get("Força", 0)) + float(alvo.get("Defesa", 0))
                            efeitos_aplicados.append(f"-{int(float(valor or 0) * 100)}% {chave}")
                    else:
                        alvo.setdefault("efeitos", []).append({"nome": nome, "turnos": int(efeito.get("turnos", 1) or 1), "valor": valor})
                        efeitos_aplicados.append(nome)
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
