"""Resolver final das habilidades ativas dentro do fluxo de combate."""

import asyncio
import random
import discord

from . import luta as luta_mod
from . import luta_sync as base


def _valor(p, chave, padrao=0):
    return float(p.get(chave, padrao) or 0)


def _aplicar_efeitos(defensor, efeitos):
    aplicados = []
    for efeito in efeitos or []:
        if not isinstance(efeito, dict):
            continue
        chance = max(0.0, min(1.0, float(efeito.get("chance", 1) or 0)))
        if random.random() > chance:
            continue
        nome = str(efeito.get("nome", efeito.get("tipo", ""))).strip().lower()
        if not nome:
            continue
        defensor.setdefault("efeitos", []).append({
            "nome": nome,
            "turnos": max(1, int(efeito.get("turnos", efeito.get("duracao", 1)) or 1)),
            "valor": int(float(efeito.get("valor", 0) or 0)),
        })
        aplicados.append(nome)
    return aplicados


def _aplicar_buffs(atacante, efeitos):
    aplicados = []
    fatores = {"buff_forca": "Força", "buff_defesa": "Defesa", "buff_velocidade": "Velocidade", "buff_destreza": "Destreza"}
    for efeito in efeitos or []:
        if not isinstance(efeito, dict):
            continue
        nome = str(efeito.get("nome", efeito.get("tipo", ""))).strip().lower()
        chave = fatores.get(nome)
        if not chave:
            continue
        percentual = float(efeito.get("valor", 0) or 0)
        atacante[chave] = int(_valor(atacante, chave) * (1 + percentual))
        aplicados.append(f"+{int(percentual * 100)}% {chave}")
    if aplicados:
        atacante["defesa"] = int(_valor(atacante, "Força") + _valor(atacante, "Defesa"))
    return aplicados


def _desviante_esquiva(defensor, atacante):
    return _valor(defensor, "Velocidade") + _valor(defensor, "Destreza") >= _valor(atacante, "Velocidade")


def _dano_habilidade_fisica(atacante, defensor, ataque):
    if defensor.get("esquiva_ativa"):
        defensor["esquiva_ativa"] = False
        if defensor.get("desviante_ativo") and _desviante_esquiva(defensor, atacante):
            return 0, "esquivou_desviante"
        if random.random() < 0.40:
            return 0, "esquivou"

    dano = _valor(atacante, "Força") + _valor(atacante, "Velocidade") + _valor(ataque, "dano_base")
    dano -= _valor(defensor, "Força") + _valor(defensor, "Defesa")

    if defensor.get("defesa_magica_ativa"):
        dano -= _valor(defensor, "defesa_magica_valor")
        defensor["defesa_magica_ativa"] = False
        defensor["defesa_magica_valor"] = 0

    if defensor.get("defesa_ativa"):
        dano -= _valor(defensor, "Força") + _valor(defensor, "Defesa")
        defensor["defesa_ativa"] = False

    return max(0, int(dano)), "atingiu"


async def _finalizar_resultado(self, ctx, combate, atacante, defensor, mensagem):
    combate["historico"].append(mensagem)
    defensor["defesa_ativa"] = False
    defensor["esquiva_ativa"] = False

    embed = discord.Embed(title="💥 Resultado", description=mensagem, color=discord.Color.red())
    embed.add_field(name="📋 Status", value=self._texto_status(combate["participantes"]), inline=False)
    await ctx.send(embed=embed)

    if defensor["vida"] <= 0:
        if combate.get("pvp"):
            combate["aguardando_finalizacao"] = True
            combate["vencedor_id"] = atacante["id"]
            combate["perdedor_id"] = defensor["id"]
            combate["fase"] = "finalizacao"
            await ctx.send(
                f"⚠️ **{defensor['nome']}** está incapacitado!\n\n"
                f"🏆 **{atacante['nome']}**, escolha:\n"
                "`!matar`\n"
                "`!desmaiar`"
            )
            return
        combate["ativo"] = False
        await self._finalizar(ctx, motivo="vida")
        return

    await asyncio.sleep(1)
    await self._proximo_turno(ctx)


async def _resolver_habilidade(self, ctx, combate, ataque):
    atacante = self._obter_atacante(combate)
    defensor = self._obter_defensor(combate)
    habilidade = ataque.get("habilidade", {})
    hid = str(habilidade.get("id", habilidade.get("ID", "")))
    nome = habilidade.get("nome", ataque.get("nome", "Habilidade"))

    chance_acerto = max(0.0, min(1.0, float(ataque.get("chance_acerto", 1.0) or 0)))
    if random.random() > chance_acerto:
        return await _finalizar_resultado(self, ctx, combate, atacante, defensor, f"❌ **{atacante['nome']}** errou **{nome}**!")

    dano, resultado = _dano_habilidade_fisica(atacante, defensor, ataque)

    if hid in {"00085", "00086"}:
        limite = 0.10 if hid == "00085" else 0.05
        vida_maxima = _valor(defensor, "vida_maxima", 1)
        vida_atual = _valor(defensor, "vida")
        if vida_maxima > 0 and vida_atual / vida_maxima <= limite:
            defensor["vida"] = 0
            chance = 0.30 if hid == "00085" else 0.20
            msg = f"🍴 **{atacante['nome']}** executou **{nome}** e derrotou **{defensor['nome']}**!"
            if random.random() < chance:
                cog = self.bot.get_cog("UsarHabilidade")
                if cog:
                    nova = cog._sortear_habilidade(atacante.get("id"), combate.get("guild_id"))
                    if nova and cog._incorporar_habilidade(atacante.get("id"), combate.get("guild_id"), nova):
                        msg += f"\n🧠 Incorporou **{nova['nome']}** (`{nova['id']}`)."
            return await _finalizar_resultado(self, ctx, combate, atacante, defensor, msg)

    if resultado == "esquivou_desviante":
        mensagem = f"💨 **{defensor['nome']}** desviou de **{nome}** graças ao **Desviante**!"
    elif resultado == "esquivou":
        mensagem = f"💨 **{defensor['nome']}** esquivou de **{nome}**!"
    else:
        defensor["vida"] = max(0, int(_valor(defensor, "vida") - dano))
        buffs = _aplicar_buffs(atacante, ataque.get("efeitos", []))
        debuffs = _aplicar_efeitos(defensor, [e for e in ataque.get("efeitos", []) if not str(e.get("nome", e.get("tipo", ""))).lower().startswith("buff_")])
        mensagem = f"⚔️ **{atacante['nome']}** causou **{dano} de dano** com **{nome}** em **{defensor['nome']}`."
        if buffs:
            mensagem += "\n💪 " + ", ".join(buffs) + "."
        if debuffs:
            mensagem += "\n⚠️ Efeitos: " + ", ".join(x.title() for x in debuffs) + "."

    return await _finalizar_resultado(self, ctx, combate, atacante, defensor, mensagem)


async def _resolver_ataque_com_desviante(self, ctx):
    combate = self._obter_combate(ctx.channel.id)
    ataque = combate.get("ataque_pendente") if combate else None
    if combate and ataque and ataque.get("tipo") != "habilidade":
        defensor = self._obter_defensor(combate)
        atacante = self._obter_atacante(combate)
        if defensor.get("esquiva_ativa") and defensor.get("tipo") == "jogador" and defensor.get("desviante_ativo"):
            if _desviante_esquiva(defensor, atacante):
                defensor["esquiva_ativa"] = False
                combate["historico"].append(f"💨 **{defensor['nome']}** desviou do ataque graças ao **Desviante**!")
                await ctx.send(embed=discord.Embed(title="💨 Desviante", description=combate["historico"][-1], color=discord.Color.green()))
                await asyncio.sleep(1)
                return await self._proximo_turno(ctx)
    return await luta_mod._resolver_ataque(self, ctx)


async def _defesa_monstro_corrigida(self, ctx):
    """Resolve a reação do monstro explicitamente, sem deixar a fase presa."""
    combate = self._obter_combate(ctx.channel.id)
    if not combate or not combate.get("ativo") or combate.get("fase") != "defesa":
        return
    if combate.get("_resolvendo_ataque"):
        return
    defensor = self._obter_defensor(combate)
    if defensor.get("tipo") != "monstro":
        return

    escolha = random.choice(("defesa", "esquiva", "normal"))
    defensor["defesa_ativa"] = escolha == "defesa"
    defensor["esquiva_ativa"] = escolha == "esquiva"
    rotulos = {"defesa": "🛡️ defesa", "esquiva": "💨 esquiva", "normal": "⚔️ ataque normal"}
    await ctx.send(f"🤖 **{defensor['nome']}** escolheu **{rotulos[escolha]}** como reação.")
    await asyncio.sleep(0.5)

    combate_atual = self._obter_combate(ctx.channel.id)
    if not combate_atual or not combate_atual.get("ativo") or combate_atual.get("fase") != "defesa":
        return
    if not combate_atual.get("ataque_pendente"):
        return
    await self._resolver_ataque(ctx)


async def _resolver_ataque(self, ctx):
    combate = self._obter_combate(ctx.channel.id)
    if not combate or not combate.get("ativo"):
        return
    if combate.get("_resolvendo_ataque"):
        return
    combate["_resolvendo_ataque"] = True
    try:
        ataque = combate.get("ataque_pendente")
        if ataque and ataque.get("tipo") == "habilidade":
            return await _resolver_habilidade(self, ctx, combate, ataque)
        return await _resolver_ataque_com_desviante(self, ctx)
    finally:
        combate.pop("_resolvendo_ataque", None)


def _texto_status_com_efeitos(self, participantes):
    linhas = []
    for participante in participantes:
        if participante["tipo"] == "jogador":
            linha = f"👤 **{participante['nome']}**\n❤️ {int(participante.get('vida', 0))}/{int(participante.get('vida_maxima', 0))}\n💙 {int(participante.get('mana', 0))}"
        else:
            linha = f"{participante.get('emoji', '👹')} **{participante['nome']}**\n❤️ {int(participante.get('vida', 0))}/{int(participante.get('vida_maxima', 0))}"
        efeitos = participante.get("efeitos", [])
        estados = []
        for efeito in efeitos:
            nome = str(efeito.get("nome", "")).strip()
            turnos = int(efeito.get("turnos", 0) or 0)
            if nome:
                estados.append(f"{nome.title()} ({turnos}t)")
        if participante.get("desviante_ativo"):
            estados.append("Desviante ativo")
        if participante.get("defesa_magica_ativa"):
            estados.append(f"Barreira {int(_valor(participante, 'defesa_magica_valor'))}")
        if estados:
            linha += "\n⚠️ " + " • ".join(estados)
        linhas.append(linha)
    return "\n\n".join(linhas)


async def setup(bot):
    base.Luta._resolver_ataque = _resolver_ataque
    base.Luta._defesa_monstro = _defesa_monstro_corrigida
    base.Luta._texto_status = _texto_status_com_efeitos
    luta = bot.get_cog("Luta")
    if luta:
        luta._resolver_ataque = _resolver_ataque.__get__(luta, base.Luta)
        luta._defesa_monstro = _defesa_monstro_corrigida.__get__(luta, base.Luta)
        luta._texto_status = _texto_status_com_efeitos.__get__(luta, base.Luta)
    print("✅ Resolver de habilidades, defesa do monstro e proteção contra dupla resolução integrados ao fluxo de combate.")
