import asyncio
import json
import unicodedata
import random
import discord
from discord.ext import commands

ARQUIVO_DANOS = "database/json/habilidades/danos.json"


class UsarHabilidade(commands.Cog):
    """Execução das habilidades ativas Comuns e Únicas e ações especiais."""

    def __init__(self, bot):
        self.bot = bot
        self.danos = self._carregar_danos()
        self._cooldowns = {}

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
            if str(habilidade.get("id", "")).strip() == str(nome).strip():
                return habilidade
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
            if str(item).strip() == str(habilidade_id).strip():
                return True
        return False

    @staticmethod
    def _arma_cortante(participante):
        nome = str(participante.get("arma_nome", participante.get("Arma", "")) or "").casefold()
        tipos = ("espada", "katana", "faca", "adaga", "machado", "machad", "foice", "lanca", "lança", "sabre", "cutelo", "navalha", "glaive", "rapiera", "rapieira")
        return bool(nome) and any(tipo in nome for tipo in tipos)

    @staticmethod
    def _recalcular_defesa(participante):
        participante["defesa"] = int(float(participante.get("Força", 0) or 0) + float(participante.get("Defesa", 0) or 0))

    @staticmethod
    def _aumentar_atributo(participante, chave, percentual):
        participante[chave] = int(float(participante.get(chave, 0) or 0) * (1 + percentual))

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
            ativa = self._normalizar(habilidade.get("ativa")) in {"sim", "true", "ativa", "yes", "1"}
            if not ativa and self._normalizar(habilidade.get("tipo")) != "ativa":
                continue
            if not self._jogador_possui(user_id, guild_id, habilidade.get("id")):
                candidatas.append(habilidade)
        return random.choice(candidatas) if candidatas else None

    def _configuracao(self, habilidade):
        padrao = dict(self.danos.get("padrao", {}))
        especifica = self.danos.get("habilidades", {}).get(str(habilidade["id"]), {})
        config = dict(padrao)
        config.update(especifica)
        return config

    @staticmethod
    def _efeitos_para_combate(config):
        efeitos = []
        for efeito in config.get("efeitos", []) or []:
            if isinstance(efeito, dict):
                efeitos.append({
                    "nome": str(efeito.get("tipo", "")).strip().lower(),
                    "turnos": max(1, int(efeito.get("duracao", 1) or 1)),
                    "valor": efeito.get("valor", 0),
                    "chance": max(0.0, min(1.0, float(efeito.get("chance", 1.0) or 0))),
                })
        return efeitos

    def _em_cooldown(self, user_id, habilidade_id, numero_turno):
        ultimo, recarga = self._cooldowns.get((str(user_id), str(habilidade_id)), (-999999, 0))
        restante = int(recarga) - (int(numero_turno) - int(ultimo))
        return max(0, restante)

    def _registrar_cooldown(self, user_id, habilidade_id, numero_turno, recarga):
        if recarga > 0:
            self._cooldowns[(str(user_id), str(habilidade_id))] = (int(numero_turno), int(recarga))

    @commands.command(name="usarhab")
    async def usarhab(self, ctx, *, nome: str = None):
        if not nome:
            await ctx.send("❌ Use: `!usarhab <ID ou nome da habilidade>`")
            return
        if ctx.guild is None:
            await ctx.send("❌ Este comando só pode ser usado em um servidor.")
            return

        habilidade = self._buscar_habilidade_por_nome(nome)
        if not habilidade:
            await ctx.send(f"❌ Não encontrei nenhuma habilidade chamada/ID **{nome}**.")
            return

        ativa = self._normalizar(habilidade.get("ativa")) in {"sim", "true", "ativa", "yes", "1"}
        tipo = self._normalizar(habilidade.get("tipo"))
        if not ativa and tipo != "ativa":
            await ctx.send(f"❌ **{habilidade['nome']}** é uma habilidade passiva e não pode ser usada diretamente.")
            return
        if not self._jogador_possui(ctx.author.id, ctx.guild.id, habilidade["id"]):
            await ctx.send(f"❌ Você não possui **{habilidade['nome']}** (`{habilidade['id']}`).")
            return

        luta = self.bot.get_cog("Luta")
        if not luta:
            await ctx.send("❌ Sistema de luta não está carregado.")
            return
        combate = luta._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            await ctx.send("❌ `!usarhab` só pode ser usado durante uma batalha.")
            return

        atacante = luta._obter_atacante(combate)
        defensor = luta._obter_defensor(combate)
        hid = str(habilidade["id"])
        ataques = {"00001", "00002", "00006", "00007", "00074", "00076", "00081", "00082", "00083", "00085", "00086", "00087", "00089", "00090", "00091", "00092", "00093", "00094", "00097", "00098", "00099"}
        defesas = {"00004", "00008", "00075", "00077", "00078", "00079", "00080", "00084", "00088", "00095", "00096"}

        if combate.get("fase") == "ataque":
            if hid in defesas:
                await ctx.send(f"❌ **{habilidade['nome']}** é defensiva. Use-a somente no turno de defesa.")
                return
            if hid not in ataques:
                await ctx.send(f"❌ **{habilidade['nome']}** não possui implementação ofensiva.")
                return
            if atacante.get("tipo") != "jogador" or str(atacante.get("id")) != str(ctx.author.id):
                await ctx.send("❌ Não é sua vez de atacar.")
                return

            config = self._configuracao(habilidade)
            restante = self._em_cooldown(ctx.author.id, hid, combate.get("numero_turno", 1))
            if restante:
                await ctx.send(f"⏳ **{habilidade['nome']}** está em recarga. Aguarde **{restante} turno(s)**.")
                return
            gasto = int(float(config.get("gasto_mana", 0) or 0))
            mana = int(float(atacante.get("mana", 0) or 0))
            if mana < gasto:
                await ctx.send(f"❌ Mana insuficiente. Necessário: **{gasto}** | Atual: **{mana}**")
                return
            atacante["mana"] = mana - gasto
            self._registrar_cooldown(ctx.author.id, hid, combate.get("numero_turno", 1), int(config.get("recarga_turnos", 0) or 0))
            efeitos = self._efeitos_para_combate(config)
            combate["ataque_pendente"] = {
                "tipo": "habilidade", "nome": f"✨ {habilidade['nome']}",
                "atacante_id": atacante["id"], "defensor_id": defensor["id"],
                "magia": False, "habilidade": habilidade,
                "dano_base": int(float(config.get("dano", 0) or 0)),
                "chance_acerto": float(config.get("chance_acerto", 1.0) or 1.0),
                "efeitos": efeitos, "efeito": efeitos[0] if efeitos else {}, "com_arma": False,
            }
            combate["fase"] = "defesa"
            await ctx.send(embed=discord.Embed(title=f"✨ {habilidade['nome']}", description=f"**{atacante['nome']}** usou **{habilidade['nome']}** (`{hid}`).\n\n🛡️ **{defensor['nome']}** deve defender.", color=discord.Color.purple()))
            if defensor.get("tipo") == "monstro":
                await asyncio.sleep(1)
                await luta._defesa_monstro(ctx)
            return

        if combate.get("fase") == "defesa":
            if hid in ataques:
                await ctx.send(f"❌ **{habilidade['nome']}** é ofensiva e não pode ser usada na defesa.")
                return
            if hid not in defesas:
                await ctx.send(f"❌ **{habilidade['nome']}** não possui implementação defensiva.")
                return
            if defensor.get("tipo") != "jogador" or str(defensor.get("id")) != str(ctx.author.id):
                await ctx.send("❌ Não é sua vez de defender.")
                return

            config = self._configuracao(habilidade)
            restante = self._em_cooldown(ctx.author.id, hid, combate.get("numero_turno", 1))
            if restante:
                await ctx.send(f"⏳ **{habilidade['nome']}** está em recarga. Aguarde **{restante} turno(s)**.")
                return
            gasto = int(float(config.get("gasto_mana", 0) or 0))
            mana = int(float(defensor.get("mana", 0) or 0))
            if mana < gasto:
                await ctx.send(f"❌ Mana insuficiente. Necessário: **{gasto}** | Atual: **{mana}**")
                return
            defensor["mana"] = mana - gasto
            self._registrar_cooldown(ctx.author.id, hid, combate.get("numero_turno", 1), int(config.get("recarga_turnos", 0) or 0))

            if hid == "00080":
                defensor["esquiva_ativa"] = True
                defensor["desviante_ativo"] = True
                atacante_vel = int(float(atacante.get("Velocidade", atacante.get("velocidade", 0)) or 0))
                proprio = int(float(defensor.get("Velocidade", defensor.get("velocidade", 0)) or 0)) + int(float(defensor.get("Destreza", 0) or 0))
                resultado = "Dodge garantido se Velocidade + Destreza (%d) >= Velocidade do atacante (%d)." % (proprio, atacante_vel)
            elif hid == "00008":
                defensor["defesa_magica_ativa"] = True
                defensor["defesa_magica_valor"] = int(config.get("escudo", 30) or 30)
                resultado = f"Barreira ativa: {defensor['defesa_magica_valor']} de absorção."
            elif hid == "00095":
                defensor["defesa_magica_ativa"] = True
                efeitos_cfg = config.get("efeitos", []) or []
                valor = efeitos_cfg[0].get("valor", 20) if efeitos_cfg and isinstance(efeitos_cfg[0], dict) else 20
                defensor["defesa_magica_valor"] = int(valor or 20)
                resultado = f"Reversão defensiva: {defensor['defesa_magica_valor']} de absorção."
            elif hid == "00078":
                if not combate.get("party"):
                    defensor["mana"] += gasto
                    self._cooldowns.pop((str(ctx.author.id), hid), None)
                    await ctx.send("❌ **Comandante** exige estar em uma party.")
                    return
                if not defensor.get("comandante_aplicado"):
                    for chave in ("Força", "Defesa", "Vitalidade", "Velocidade", "Destreza", "Magia", "Sorte", "Inteligencia"):
                        self._aumentar_atributo(defensor, chave, 0.20)
                    defensor["vida_maxima"] = int(float(defensor.get("Vitalidade", 0) or 0) * 10)
                    defensor["mana"] = int(float(defensor.get("Magia", 0) or 0))
                    self._recalcular_defesa(defensor)
                    defensor["comandante_aplicado"] = True
                resultado = "+20% em todos os atributos da personagem."
            elif hid == "00075":
                self._aumentar_atributo(defensor, "Força", 0.30)
                self._aumentar_atributo(defensor, "Defesa", -0.15)
                self._recalcular_defesa(defensor)
                resultado = "+30% Força / -15% Defesa."
            elif hid == "00096":
                self._aumentar_atributo(defensor, "Força", 0.25)
                self._aumentar_atributo(defensor, "Defesa", 0.15)
                self._recalcular_defesa(defensor)
                resultado = "+25% Força / +15% Defesa."
            elif hid == "00088":
                self._aumentar_atributo(defensor, "Velocidade", 0.15)
                self._aumentar_atributo(defensor, "Destreza", 0.15)
                resultado = "+15% Velocidade / +15% Destreza."
            elif hid == "00004":
                self._aumentar_atributo(defensor, "Velocidade", 0.15)
                self._aumentar_atributo(defensor, "Destreza", 0.20)
                resultado = "+15% Velocidade / +20% Destreza."
            elif hid in {"00077", "00079"}:
                defensor["preparacao_corte"] = True
                resultado = "Preparação para `!corte` ativada."
            elif hid == "00084":
                self._aumentar_atributo(defensor, "Força", 0.15)
                self._recalcular_defesa(defensor)
                resultado = "+15% Força."
            else:
                resultado = "Efeito defensivo ativado."

            combate["defesa_habilidade"] = habilidade
            combate["historico"].append(f"🛡️ **{defensor['nome']}** usou **{habilidade['nome']}**: {resultado}")
            await ctx.send(embed=discord.Embed(title=f"🛡️ {habilidade['nome']}", description=resultado, color=discord.Color.blue()))
            await luta._resolver_ataque(ctx)
            return

        await ctx.send("❌ O combate não está em uma fase que permita usar habilidades.")

    @commands.command(name="corte")
    async def corte(self, ctx):
        """Ataque de corte usado por Chef/Cozinheiro e armas cortantes."""
        if not ctx.guild:
            await ctx.send("❌ Este comando só pode ser usado em um servidor.")
            return
        luta = self.bot.get_cog("Luta")
        if not luta:
            await ctx.send("❌ Sistema de luta não está carregado.")
            return
        combate = luta._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            await ctx.send("❌ Você não está em combate.")
            return
        if combate.get("fase") != "ataque":
            await ctx.send("❌ `!corte` só pode ser usado na fase de ataque.")
            return
        atacante = luta._obter_atacante(combate)
        defensor = luta._obter_defensor(combate)
        if atacante.get("tipo") != "jogador" or str(atacante.get("id")) != str(ctx.author.id):
            await ctx.send("❌ Não é sua vez de atacar.")
            return
        if not self._arma_cortante(atacante):
            await ctx.send("❌ `!corte` exige uma arma cortante equipada.")
            return

        bonus = 0.0
        partes = []
        if atacante.get("preparacao_corte"):
            # A preparação é consumida no primeiro corte.
            if self._jogador_possui(ctx.author.id, ctx.guild.id, "00077"):
                bonus += 0.10
                partes.append("Chef +10%")
            if self._jogador_possui(ctx.author.id, ctx.guild.id, "00079"):
                bonus += 0.05
                partes.append("Cozinheiro +5%")
            atacante["preparacao_corte"] = False
        dano_arma = int(float(atacante.get("dano_arma", 0) or 0))
        dano_base = int(dano_arma * (1 + bonus))
        combate["ataque_pendente"] = {
            "tipo": "habilidade", "nome": "🗡️ Corte", "atacante_id": atacante["id"], "defensor_id": defensor["id"],
            "magia": False,
            "habilidade": {"id": "CORTE", "nome": "Corte"},
            "dano_base": dano_base, "chance_acerto": 1.0, "efeitos": [], "efeito": {}, "com_arma": True,
        }
        combate["fase"] = "defesa"
        descricao = f"**{atacante['nome']}** preparou um **Corte** com **{atacante.get('arma_nome', 'arma')}**."
        if partes:
            descricao += "\n🔥 Bônus: " + " / ".join(partes) + "."
        await ctx.send(embed=discord.Embed(title="🗡️ Corte", description=descricao + f"\n\n🛡️ **{defensor['nome']}** deve defender.", color=discord.Color.orange()))
        if defensor.get("tipo") == "monstro":
            await asyncio.sleep(1)
            await luta._defesa_monstro(ctx)


async def setup(bot):
    await bot.add_cog(UsarHabilidade(bot))
