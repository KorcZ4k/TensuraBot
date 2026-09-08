import json
import os
import unicodedata
import discord
from discord.ext import commands


ARQUIVO_DANOS = "database/json/habilidades/danos.json"
ARQUIVOS_HABILIDADES = [
    "database/json/habilidades/habs_comuns.json",
    "database/json/habilidades/habs_unicas.json",
]


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
        """Config explícita; se não existir, cria uma configuração funcional."""
        padrao = dict(self.danos.get("padrao", {}))
        especifica = self.danos.get("habilidades", {}).get(str(habilidade["id"]), {})
        config = dict(padrao)
        config.update(especifica)

        if especifica:
            return config

        # Nenhuma habilidade ativa Comum/Única fica sem ação funcional.
        nome = self._normalizar(habilidade.get("nome"))
        config.update({
            "dano": 15,
            "gasto_mana": 10,
            "chance_acerto": 0.90,
            "recarga_turnos": 2,
            "efeitos": [],
        })

        if nome in {"chef", "cozinheiro", "comandante", "falsificador", "fusionista"}:
            config["dano"] = 0
        elif nome in {"lutador", "mestre marcial", "assassino", "ceifador", "atacante das sombras", "separador", "separacao absoluta", "predador", "engolidor", "gula", "glutao"}:
            config["dano"] = 35
        elif nome in {"berserk", "besta real"}:
            config["dano"] = 20
        elif nome in {"luxuria", "comandante", "musico", "opressor", "confusao", "preguica", "reversor", "desviante"}:
            config["dano"] = 0

        return config

    @staticmethod
    def _efeitos_para_combate(config):
        efeitos = []
        for efeito in config.get("efeitos", []) or []:
            if not isinstance(efeito, dict):
                continue
            tipo = str(efeito.get("tipo", "habilidade")).strip().lower()
            chance = float(efeito.get("chance", 1.0) or 0)
            duracao = int(efeito.get("duracao", 1) or 1)
            valor = efeito.get("valor", 0)
            efeitos.append({
                "nome": tipo,
                "turnos": max(1, duracao),
                "valor": valor,
                "chance": max(0.0, min(1.0, chance)),
            })
        return efeitos

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
            "tipo": "habilidade",
            "nome": f"✨ {habilidade['nome']}",
            "atacante_id": atacante["id"],
            "defensor_id": defensor["id"],
            "magia": False,
            "habilidade": habilidade,
            "dano_base": int(float(configuracao.get("dano", 0) or 0)),
            "chance_acerto": float(configuracao.get("chance_acerto", 1.0) or 1.0),
            "efeitos": efeitos,
            "efeito": efeitos[0] if efeitos else {},
            "com_arma": False,
        }
        combate["fase"] = "defesa"

        embed = discord.Embed(
            title=f"✨ Turno {combate['numero_turno']} — Habilidade",
            description=(
                f"**{atacante['nome']}** usou **{habilidade['nome']}** contra **{defensor['nome']}**!\n"
                f"💙 Mana gasta: **{gasto}**\n"
                f"⚡ Poder da habilidade: **{int(float(configuracao.get('dano', 0) or 0))}**\n\n"
                f"🛡️ **{defensor['nome']}** deve usar `!defesa` ou `!esquiva`."
            ),
            color=discord.Color.purple(),
        )
        await ctx.send(embed=embed)

        if defensor.get("tipo") == "monstro":
            import asyncio
            await asyncio.sleep(1)
            await luta._defesa_monstro(ctx)


async def setup(bot):
    await bot.add_cog(UsarHabilidade(bot))
