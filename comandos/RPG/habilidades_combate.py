"""Resolver final das habilidades ativas dentro do fluxo de combate."""

import asyncio
import random

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


def _dano_habilidade_fisica(atacante, defensor, ataque):
    if defensor.get("esquiva_ativa"):
        defensor["esquiva_ativa"] = False
        velocidade = _valor(defensor, "Velocidade")
        destreza = _valor(defensor, "Destreza")
        if velocidade + destreza >= _valor(atacante, "Velocidade"):
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


async def _resolver_habilidade(self, ctx, combate, ataque):
    atacante = self._obter_atacante(combate)
    defensor = self._obter_defensor(combate)
    habilidade = ataque.get("habilidade", {})
    hid = str(habilidade.get("id", habilidade.get("ID", "")))
    nome = habilidade.get("nome", ataque.get("nome", "Habilidade"))

    dano, resultado = _dano_habilidade_fisica(atacante, defensor, ataque)

    # Gula e Glutão: execução somente se o alvo estiver no limiar indicado.
    if hid in {"00085", "00086"}:
        limite = 0.10 if hid == "00085" else 0.05
        if _valor(defensor, "vida_maxima", 1) > 0 and _valor(defensor, "vida") / _valor(defensor, "vida_maxima") <= limite:
            defensor["vida"] = 0
            chance = 0.30 if hid == "00085" else 0.20
            msg = f"🍴 **{atacante['nome']}** executou **{nome}** e derrotou **{defensor['nome']}**!"
            if random.random() < chance:
                cog = self.bot.get_cog("UsarHabilidade")
                if cog:
                    nova = cog._sortear_habilidade(atacante.get("id"), combate.get("guild_id"))
                    if nova and cog._incorporar_habilidade(atacante.get("id"), combate.get("guild_id"), nova):
                        msg += f"\n🧠 Incorporou a habilidade **{nova['nome']}** (`{nova['id']}`)."
            return await _finalizar_resultado(self, ctx, combate, atacante, defensor, msg)

    if resultado == "esquivou":
        mensagem = f"💨 **{defensor['nome']}** esquivou de **{nome}**!"
    else:
        # Chef/Cozinheiro só dão bônus em corte com arma cortante.
        if hid in {"00077", "00079"}:
            dano = 0
        defensor["vida"] = max(0, _valor(defensor, "vida") - dano)
        mensagem = f"⚔️ **{atacante['nome']}** causou **{dano} de dano** com **{nome}** em **{defensor['nome']}**."
        aplicados = _aplicar_efeitos(defensor, ataque.get("efeitos", []))
        if aplicados:
            mensagem += "\n⚠️ Efeitos: " + ", ".join(x.title() for x in aplicados)

    return await _finalizar_resultado(self, ctx, combate, atacante, defensor, mensagem)


async def _finalizar_resultado(self, ctx, combate, atacante, defensor, mensagem):
    defensor["defesa_ativa"] = False
    defensor["esquiva_ativa"] = False
    combate["historico"].append(mensagem)
    await ctx.send(mensagem)

    if defensor.get("vida", 0) <= 0:
        if combate.get("pvp"):
            combate["aguardando_finalizacao"] = True
            combate["vencedor_id"] = atacante.get("id")
            combate["perdedor_id"] = defensor.get("id")
            combate["fase"] = "finalizacao"
            await ctx.send(
                f"⚠️ **{defensor['nome']}** está incapacitado!\n\n"
                f"🏆 **{atacante['nome']}**, escolha:\n`!matar`\n`!desmaiar`"
            )
            return
        combate["ativo"] = False
        await self._finalizar(ctx, motivo="vida")
        return

    await asyncio.sleep(1)
    await self._proximo_turno(ctx)


async def _resolver_ataque(self, ctx):
    combate = self._obter_combate(ctx.channel.id)
    ataque = combate.get("ataque_pendente") if combate else None
    if ataque and ataque.get("tipo") == "habilidade":
        return await _resolver_habilidade(self, ctx, combate, ataque)
    return await luta_mod._RESOLVER_ATAQUE_ORIGINAL(self, ctx)


async def setup(bot):
    base.Luta._resolver_ataque = _resolver_ataque
    luta = bot.get_cog("Luta")
    if luta:
        luta._resolver_ataque = _resolver_ataque.__get__(luta, base.Luta)
    print("✅ Resolver de habilidades integrado ao fluxo de combate.")
