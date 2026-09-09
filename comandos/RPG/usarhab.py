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
        # Permite !usarhab 00001 e !usarhab Coerção.
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

    def _tem_habilidade(self, participante, combate, nome):
        if participante.get("tipo") != "jogador" or not combate.get("guild_id"):
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

        # ATAQUE: habilidades ofensivas somente.
        if combate.get("fase") == "ataque":
            if hid in defesas:
                await ctx.send(f"❌ **{habilidade['nome']}** é defensiva. Use-a somente no turno de defesa.")
                return
            if hid not in ataques:
                await ctx.send(f"❌ **{habilidade['nome']}** não é uma habilidade de ataque.")
                return
            if atacante.get("tipo") != "jogador" or str(atacante.get("id")) != str(ctx.author.id):
                await ctx.send("❌ Não é sua vez de atacar.")
                return

            config = self._configuracao(habilidade)
            gasto = int(float(config.get("gasto_mana", 0) or 0))
            mana = int(float(atacante.get("mana", 0) or 0))
            if mana < gasto:
                await ctx.send(f"❌ Mana insuficiente. Necessário: **{gasto}** | Atual: **{mana}**")
                return
            atacante["mana"] = mana - gasto
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
            await ctx.send(embed=discord.Embed(
                title=f"✨ {habilidade['nome']}",
                description=f"**{atacante['nome']}** usou **{habilidade['nome']}** (`{hid}`).\n\n🛡️ **{defensor['nome']}** deve defender.",
                color=discord.Color.purple()))
            if defensor.get("tipo") == "monstro":
                await asyncio.sleep(1)
                await luta._defesa_monstro(ctx)
            return

        # DEFESA: habilidades defensivas somente.
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
            gasto = int(float(config.get("gasto_mana", 0) or 0))
            mana = int(float(defensor.get("mana", 0) or 0))
            if mana < gasto:
                await ctx.send(f"❌ Mana insuficiente. Necessário: **{gasto}** | Atual: **{mana}**")
                return
            defensor["mana"] = mana - gasto

            efeitos = self._efeitos_para_combate(config)
            nome_norm = self._normalizar(habilidade.get("nome"))
            if hid == "00080":
                defensor["esquiva_ativa"] = True
                efeito_txt = "Esquiva automática ativada (Velocidade + Destreza >= Velocidade do atacante)."
            elif hid == "00008":
                defensor["defesa_magica_ativa"] = True
                defensor["defesa_magica_valor"] = int(config.get("escudo", 30) or 30)
                efeito_txt = f"Barreira ativa: {defensor['defesa_magica_valor']} de absorção."
            elif hid == "00095":
                defensor["defesa_magica_ativa"] = True
                defensor["defesa_magica_valor"] = int(config.get("efeitos", [{}])[0].get("valor", 20) or 20)
                efeito_txt = f"Reversão defensiva: {defensor['defesa_magica_valor']} de absorção."
            elif hid == "00078":
                if not combate.get("party"):
                    defensor["mana"] += gasto
                    await ctx.send("❌ **Comandante** exige estar em uma party.")
                    return
                if not defensor.get("comandante_aplicado"):
                    for chave in ("Força", "Defesa", "Vitalidade", "Velocidade", "Destreza", "Magia", "Sorte", "Inteligencia"):
                        self._aumentar_atributo(defensor, chave, 0.20)
                    defensor["vida_maxima"] = int(float(defensor.get("Vitalidade", 0) or 0) * 10)
                    defensor["mana"] = int(float(defensor.get("Magia", 0) or 0))
                    self._recalcular_defesa(defensor)
                    defensor["comandante_aplicado"] = True
                efeito_txt = "+20% em todos os atributos."
            elif hid == "00075":
                self._aumentar_atributo(defensor, "Força", 0.30)
                self._aumentar_atributo(defensor, "Defesa", -0.15)
                self._recalcular_defesa(defensor)
                efeito_txt = "+30% Força / -15% Defesa."
            elif hid == "00096":
                self._aumentar_atributo(defensor, "Força", 0.25)
                self._aumentar_atributo(defensor, "Defesa", 0.15)
                self._recalcular_defesa(defensor)
                efeito_txt = "+25% Força / +15% Defesa."
            elif hid == "00088":
                self._aumentar_atributo(defensor, "Velocidade", 0.15)
                self._aumentar_atributo(defensor, "Destreza", 0.15)
                efeito_txt = "+15% Velocidade / +15% Destreza."
            elif hid == "00004":
                self._aumentar_atributo(defensor, "Velocidade", 0.15)
                self._aumentar_atributo(defensor, "Destreza", 0.20)
                efeito_txt = "+15% Velocidade / +20% Destreza."
            elif hid in {"00077", "00079"}:
                defensor["preparacao_corte"] = True
                efeito_txt = "Preparação para !corte ativada."
            elif hid == "00084":
                self._aumentar_atributo(defensor, "Força", 0.15)
                self._recalcular_defesa(defensor)
                efeito_txt = "+15% Força."
            else:
                efeito_txt = "Efeito defensivo ativado."

            combate["defesa_habilidade"] = habilidade
            combate["historico"].append(f"🛡️ **{defensor['nome']}** usou **{habilidade['nome']}**: {efeito_txt}")
            await ctx.send(embed=discord.Embed(title=f"🛡️ {habilidade['nome']}", description=efeito_txt, color=discord.Color.blue()))
            await luta._resolver_ataque(ctx)
            return

        await ctx.send("❌ O combate não está em uma fase que permita usar habilidades.")


@commands.command(name="corte")
async def _dummy():
    pass


async def setup(bot):
    await bot.add_cog(UsarHabilidade(bot))
