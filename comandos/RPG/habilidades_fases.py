"""Integração das habilidades ativas com as fases de ataque e defesa."""

import asyncio
import random

import discord
from discord.ext import commands


# Habilidades que representam uma ação ofensiva.
HABILIDADES_ATAQUE = {
    "00001", "00002", "00006", "00007",
    "00074", "00076", "00081", "00082", "00083",
    "00085", "00086", "00087", "00089", "00090", "00091",
    "00092", "00093", "00094", "00097", "00098", "00099",
}

# Habilidades que podem substituir !defesa / !esquiva.
HABILIDADES_DEFESA = {
    "00004", "00008", "00075", "00077", "00078", "00079",
    "00080", "00084", "00088", "00095", "00096",
}


def _int(valor):
    return int(float(valor or 0))


def _pct(valor):
    return float(valor or 0)


def _recalcular_defesa(p):
    p["defesa"] = _pct(p.get("Força")) + _pct(p.get("Defesa"))


def _buff(p, atributo, percentual):
    p[atributo] = _int(_pct(p.get(atributo)) * (1 + percentual))


def _config(cog, habilidade):
    return cog._configuracao(habilidade)


async def _usar_defesa(cog, ctx, luta, combate, atacante, defensor, habilidade):
    """Executa uma habilidade classificada como defensiva no turno de defesa."""
    hid = str(habilidade.get("ID", habilidade.get("id", "")))
    nome = cog._normalizar(habilidade.get("nome"))
    config = _config(cog, habilidade)
    gasto = _int(config.get("gasto_mana", 0))
    mana = _int(defensor.get("mana", 0))
    if mana < gasto:
        await ctx.send(f"❌ Mana insuficiente. Necessário: **{gasto}** | Atual: **{mana}**")
        return

    defensor["mana"] = mana - gasto
    efeitos = []

    if hid == "00004":  # Voo gravitacional
        _buff(defensor, "Velocidade", 0.15)
        _buff(defensor, "Destreza", 0.20)
        efeitos.append("+15% Velocidade e +20% Destreza por 3 turnos")

    elif hid == "00008":  # Barreira à Distância
        valor = _int(config.get("escudo", 30))
        defensor["defesa_magica_ativa"] = True
        defensor["defesa_magica_valor"] = valor
        efeitos.append(f"barreira de **{valor}** de absorção")

    elif hid == "00075":  # Berserk
        _buff(defensor, "Força", 0.30)
        efeitos.append("+30% Força")
        # O custo defensivo do Berserk afeta a própria defesa, nunca o adversário.
        defensor["Defesa"] = max(0, _int(_pct(defensor.get("Defesa")) * 0.85))
        efeitos.append("-15% Defesa")
        _recalcular_defesa(defensor)

    elif hid == "00077":  # Chef
        defensor["preparacao_corte"] = True
        efeitos.append("preparação culinária ativa; bônus de Chef será aplicado em !corte")

    elif hid == "00078":  # Comandante
        if not combate.get("party"):
            defensor["mana"] += gasto
            await ctx.send("❌ **Comandante** só pode ser usada enquanto você estiver em uma party.")
            return
        if not defensor.get("comandante_aplicado"):
            for atributo in ("Força", "Defesa", "Vitalidade", "Velocidade", "Destreza", "Magia", "Sorte", "Inteligencia"):
                _buff(defensor, atributo, 0.20)
            defensor["vida_maxima"] = _int(_pct(defensor.get("Vitalidade")) * 10)
            defensor["vida"] = min(defensor["vida_maxima"], _int(defensor.get("vida")))
            defensor["mana"] = _int(defensor.get("Magia"))
            defensor["comandante_aplicado"] = True
            _recalcular_defesa(defensor)
            efeitos.append("+20% em todos os atributos")
        else:
            efeitos.append("efeito de Comandante já aplicado")

    elif hid == "00079":  # Cozinheiro
        defensor["preparacao_corte"] = True
        efeitos.append("preparação culinária ativa; bônus de Cozinheiro será aplicado em !corte")

    elif hid == "00080":  # Desviante
        defensor["esquiva_ativa"] = True
        efeitos.append("esquiva automática: Velocidade + Destreza >= Velocidade do atacante")

    elif hid == "00084":  # Fusionista
        _buff(defensor, "Força", 0.15)
        efeitos.append("+15% Força por 3 turnos")

    elif hid == "00088":  # Luxúria
        _buff(defensor, "Velocidade", 0.15)
        _buff(defensor, "Destreza", 0.15)
        efeitos.append("+15% Velocidade e +15% Destreza")

    elif hid == "00095":  # Reversor
        valor = _int(config.get("escudo", 20))
        defensor["defesa_magica_ativa"] = True
        defensor["defesa_magica_valor"] = valor
        efeitos.append(f"reversão defensiva: escudo de **{valor}**")

    elif hid == "00096":  # Besta Real
        _buff(defensor, "Força", 0.25)
        _buff(defensor, "Defesa", 0.15)
        _recalcular_defesa(defensor)
        efeitos.append("+25% Força e +15% Defesa")

    else:
        # Segurança: nenhuma habilidade desconhecida vira uma defesa silenciosa.
        defensor["mana"] += gasto
        await ctx.send("❌ Esta habilidade não possui uma implementação defensiva válida.")
        return

    combate["historico"].append(f"🛡️ **{defensor['nome']}** usou **{habilidade['nome']}** na defesa: {', '.join(efeitos)}.")
    await ctx.send(embed=discord.Embed(
        title="🛡️ Habilidade defensiva",
        description=f"**{defensor['nome']}** usou **{habilidade['nome']}**.\n\n" + "\n".join(f"• {e}" for e in efeitos),
        color=discord.Color.blue(),
    ))
    await asyncio.sleep(0.5)
    await luta._resolver_ataque(ctx)


async def setup(bot):
    cog = bot.get_cog("UsarHabilidade")
    if cog is None:
        raise RuntimeError("UsarHabilidade precisa ser carregada antes de habilidades_fases")

    comando = bot.get_command("usarhab")
    if comando is None:
        raise RuntimeError("Comando !usarhab não encontrado")
    if getattr(comando, "_fases_patched", False):
        return

    original = comando.callback

    async def callback(cog_self, ctx, *, nome=None):
        if not nome:
            await original(cog_self, ctx, nome=nome)
            return
        habilidade = cog_self._buscar_habilidade_por_nome(nome)
        if not habilidade:
            await original(cog_self, ctx, nome=nome)
            return

        hid = str(habilidade.get("ID", habilidade.get("id", "")))
        luta = bot.get_cog("Luta")
        combate = luta._obter_combate(ctx.channel.id) if luta else None

        if not combate or not combate.get("ativo"):
            await original(cog_self, ctx, nome=nome)
            return

        # Fase de ataque: somente habilidades ofensivas.
        if combate.get("fase") == "ataque":
            if hid in HABILIDADES_DEFESA:
                await ctx.send(f"❌ **{habilidade['nome']}** é uma habilidade defensiva e só pode ser usada no turno de defesa.")
                return
            if hid not in HABILIDADES_ATAQUE:
                await ctx.send(f"❌ **{habilidade['nome']}** não pode ser usada como ataque.")
                return
            await original(cog_self, ctx, nome=nome)
            return

        # Fase de defesa: somente habilidades defensivas.
        if combate.get("fase") == "defesa":
            if hid in HABILIDADES_ATAQUE:
                await ctx.send(f"❌ **{habilidade['nome']}** é uma habilidade de ataque e não pode ser usada no turno de defesa.")
                return
            if hid not in HABILIDADES_DEFESA:
                await ctx.send(f"❌ **{habilidade['nome']}** não possui função defensiva e não pode ser usada neste turno.")
                return
            defensor = luta._obter_defensor(combate)
            if defensor.get("tipo") != "jogador" or str(defensor.get("id")) != str(ctx.author.id):
                await ctx.send(f"❌ É **{defensor.get('nome', 'outro participante')}** quem deve defender.")
                return
            atacante = luta._obter_atacante(combate)
            await _usar_defesa(cog_self, ctx, luta, combate, atacante, defensor, habilidade)
            return

        await ctx.send("❌ Não é possível usar uma habilidade nesta fase do combate.")

    comando.callback = callback
    comando._fases_patched = True
