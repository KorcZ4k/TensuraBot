"""Resolver final das habilidades ativas dentro do fluxo de combate."""

import asyncio
import random
import discord

from . import luta as luta_mod
from . import luta_sync as base

_OBTER_DEFENSOR_ORIGINAL = base.Luta._obter_defensor
_RESOLVER_ANTES_DE_HABILIDADES = base.Luta._resolver_ataque


def _valor(p, chave, padrao=0):
    try:
        return float(p.get(chave, padrao) or 0)
    except (TypeError, ValueError):
        return float(padrao)


def _efeitos_validos(efeitos):
    return [efeito for efeito in (efeitos or []) if isinstance(efeito, dict)]


def _aplicar_efeitos(defensor, efeitos):
    aplicados = []
    lista = defensor.setdefault("efeitos", [])
    for efeito in _efeitos_validos(efeitos):
        chance = max(0.0, min(1.0, _valor(efeito, "chance", 1)))
        if random.random() > chance:
            continue
        nome = str(efeito.get("nome", efeito.get("tipo", ""))).strip().lower()
        if not nome:
            continue
        lista.append({"nome": nome, "turnos": max(1, int(_valor(efeito, "turnos", efeito.get("duracao", 1)) or 1)), "valor": int(_valor(efeito, "valor", 0))})
        aplicados.append(nome)
    return aplicados


def _aplicar_buffs(atacante, efeitos):
    aplicados = []
    fatores = {"buff_forca": "Força", "buff_defesa": "Defesa", "buff_velocidade": "Velocidade", "buff_destreza": "Destreza"}
    ativos = atacante.setdefault("buffs_ativos", {})
    for efeito in _efeitos_validos(efeitos):
        nome = str(efeito.get("nome", efeito.get("tipo", ""))).strip().lower()
        chave = fatores.get(nome)
        if not chave or nome in ativos:
            continue
        percentual = _valor(efeito, "valor", 0)
        original = _valor(atacante, chave)
        atacante[chave] = int(original * (1 + percentual))
        ativos[nome] = {"chave": chave, "original": original, "turnos": max(1, int(_valor(efeito, "turnos", efeito.get("duracao", 1)) or 1))}
        aplicados.append(f"+{int(percentual * 100)}% {chave}")
    if aplicados:
        atacante["defesa"] = int(_valor(atacante, "Força") + _valor(atacante, "Defesa"))
    return aplicados


def _processar_buffs(participantes):
    for participante in participantes:
        ativos = participante.get("buffs_ativos", {})
        expirados = []
        for nome, dados in list(ativos.items()):
            dados["turnos"] = int(dados.get("turnos", 1)) - 1
            if dados["turnos"] <= 0:
                participante[dados.get("chave", "")] = int(float(dados.get("original", 0)))
                expirados.append(nome)
        for nome in expirados:
            ativos.pop(nome, None)
        if expirados:
            participante["defesa"] = int(_valor(participante, "Força") + _valor(participante, "Defesa"))


def _desviante_esquiva(defensor, atacante):
    return _valor(defensor, "Velocidade") + _valor(defensor, "Destreza") >= _valor(atacante, "Velocidade")


def _dano_habilidade_fisica(atacante, defensor, ataque):
    if defensor.get("esquiva_ativa"):
        defensor["esquiva_ativa"] = False
        if defensor.get("desviante_ativo") and _desviante_esquiva(defensor, atacante):
            defensor["desviante_ativo"] = False
            return 0, "esquivou_desviante"
        if random.random() < 0.40:
            return 0, "esquivou"
    dano = _valor(atacante, "Força") + _valor(atacante, "Velocidade") + _valor(ataque, "dano_base")
    if defensor.get("defesa_magica_ativa"):
        dano -= _valor(defensor, "defesa_magica_valor")
        defensor["defesa_magica_ativa"] = False
        defensor["defesa_magica_valor"] = 0
    else:
        dano -= _valor(defensor, "Força") + _valor(defensor, "Defesa")
        if defensor.get("defesa_ativa"):
            defensor["defesa_ativa"] = False
    return max(0, int(dano)), "atingiu"


async def _finalizar_resultado(self, ctx, combate, atacante, defensor, mensagem):
    combate["historico"].append(mensagem)
    defensor["defesa_ativa"] = False
    defensor["esquiva_ativa"] = False
    embed = discord.Embed(title="💥 Resultado", description=mensagem, color=discord.Color.red())
    embed.add_field(name="📋 Status", value=self._texto_status(combate["participantes"]), inline=False)
    await ctx.send(embed=embed)
    if defensor.get("vida", 0) <= 0:
        if combate.get("pvp"):
            combate["aguardando_finalizacao"] = True
            combate["vencedor_id"] = atacante.get("id")
            combate["perdedor_id"] = defensor.get("id")
            combate["fase"] = "finalizacao"
            combate["ataque_pendente"] = None
            await ctx.send(f"⚠️ **{defensor.get('nome', 'Defensor')}** está incapacitado!\n\n🏆 **{atacante.get('nome', 'Vencedor')}**, escolha:\n`!matar`\n`!desmaiar`")
            return
        combate["ativo"] = False
        combate["ataque_pendente"] = None
        await self._finalizar(ctx, motivo="vida")
        return
    combate["ataque_pendente"] = None
    _processar_buffs(combate["participantes"])
    await asyncio.sleep(1)
    await self._proximo_turno(ctx)


async def _resolver_habilidade(self, ctx, combate, ataque):
    atacante = self._obter_atacante(combate)
    defensor = self._obter_defensor(combate)
    habilidade = ataque.get("habilidade") if isinstance(ataque.get("habilidade"), dict) else {}
    hid = str(habilidade.get("id", habilidade.get("ID", "")))
    nome = habilidade.get("nome", ataque.get("nome", "Habilidade"))
    chance_acerto = max(0.0, min(1.0, _valor(ataque, "chance_acerto", 1.0)))
    if random.random() > chance_acerto:
        return await _finalizar_resultado(self, ctx, combate, atacante, defensor, f"❌ **{atacante.get('nome', 'Atacante')}** errou **{nome}**!")
    dano, resultado = _dano_habilidade_fisica(atacante, defensor, ataque)
    if hid in {"00085", "00086"}:
        limite = 0.10 if hid == "00085" else 0.05
        vida_maxima = max(1, _valor(defensor, "vida_maxima", 1))
        if _valor(defensor, "vida") / vida_maxima <= limite:
            defensor["vida"] = 0
            chance = 0.30 if hid == "00085" else 0.20
            msg = f"🍴 **{atacante.get('nome', 'Atacante')}** executou **{nome}** e derrotou **{defensor.get('nome', 'Defensor')}**!"
            if random.random() < chance:
                cog = self.bot.get_cog("UsarHabilidade")
                if cog:
                    nova = cog._sortear_habilidade(atacante.get("id"), combate.get("guild_id"))
                    if nova and cog._incorporar_habilidade(atacante.get("id"), combate.get("guild_id"), nova):
                        msg += f"\n🧠 Incorporou **{nova.get('nome', 'Habilidade')}** (`{nova.get('id', '?')}`)."
            return await _finalizar_resultado(self, ctx, combate, atacante, defensor, msg)
    if resultado == "esquivou_desviante":
        mensagem = f"💨 **{defensor.get('nome', 'Defensor')}** desviou de **{nome}** graças ao **Desviante**!"
    elif resultado == "esquivou":
        mensagem = f"💨 **{defensor.get('nome', 'Defensor')}** esquivou de **{nome}**!"
    else:
        defensor["vida"] = max(0, int(_valor(defensor, "vida") - dano))
        efeitos = _efeitos_validos(ataque.get("efeitos"))
        buffs = _aplicar_buffs(atacante, efeitos)
        debuffs = _aplicar_efeitos(defensor, [e for e in efeitos if not str(e.get("nome", e.get("tipo", ""))).lower().startswith("buff_")])
        mensagem = f"⚔️ **{atacante.get('nome', 'Atacante')}** causou **{dano} de dano** com **{nome}** em **{defensor.get('nome', 'Defensor')}**."
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
        if defensor.get("esquiva_ativa") and defensor.get("tipo") == "jogador" and defensor.get("desviante_ativo") and _desviante_esquiva(defensor, atacante):
            defensor["esquiva_ativa"] = False
            defensor["desviante_ativo"] = False
            mensagem = f"💨 **{defensor.get('nome', 'Defensor')}** desviou do ataque graças ao **Desviante**!"
            combate["historico"].append(mensagem)
            combate["ataque_pendente"] = None
            await ctx.send(embed=discord.Embed(title="💨 Desviante", description=mensagem, color=discord.Color.green()))
            await asyncio.sleep(1)
            return await self._proximo_turno(ctx)
    return await _RESOLVER_ANTES_DE_HABILIDADES(self, ctx)


async def _defesa_monstro_corrigida(self, ctx):
    combate = self._obter_combate(ctx.channel.id)
    if not combate or not combate.get("ativo") or combate.get("fase") != "defesa":
        return
    defensor = self._obter_defensor(combate)
    if defensor.get("tipo") != "monstro" or _valor(defensor, "vida", 1) <= 0:
        return
    escolha = random.choice(("defesa", "esquiva", "normal"))
    defensor["defesa_ativa"] = escolha == "defesa"
    defensor["esquiva_ativa"] = escolha == "esquiva"
    rotulos = {"defesa": "🛡️ defesa", "esquiva": "💨 esquiva", "normal": "⚔️ reação normal"}
    await ctx.send(f"🤖 **{defensor.get('nome', 'Monstro')}** escolheu **{rotulos[escolha]}** como reação.")
    await asyncio.sleep(0.5)
    combate_atual = self._obter_combate(ctx.channel.id)
    if not combate_atual or not combate_atual.get("ativo") or combate_atual.get("fase") != "defesa" or not combate_atual.get("ataque_pendente"):
        return
    await self._resolver_ataque(ctx)


def _obter_defensor_corrigido(self, combate):
    participantes = combate.get("participantes", [])
    atacante = self._obter_atacante(combate)
    vivos = [p for p in participantes if p is not atacante and _valor(p, "vida", 1) > 0]
    if not combate.get("party"):
        if not vivos:
            return atacante
        indice_atual = participantes.index(atacante)
        for deslocamento in range(1, len(participantes) + 1):
            candidato = participantes[(indice_atual + deslocamento) % len(participantes)]
            if candidato in vivos:
                return candidato
        return vivos[0]
    equipe_atacante = atacante.get("equipe")
    inimigos = [p for p in vivos if p.get("equipe") != equipe_atacante]
    if inimigos:
        return inimigos[0]
    return _OBTER_DEFENSOR_ORIGINAL(self, combate)


async def _resolver_ataque(self, ctx):
    combate = self._obter_combate(ctx.channel.id)
    if not combate or not combate.get("ativo"):
        return
    ataque = combate.get("ataque_pendente")
    if not ataque or ataque.get("_resolvendo"):
        return
    ataque["_resolvendo"] = True
    if ataque.get("tipo") == "habilidade":
        return await _resolver_habilidade(self, ctx, combate, ataque)
    return await _resolver_ataque_com_desviante(self, ctx)


def _texto_status_com_efeitos(self, participantes):
    linhas = []
    for participante in participantes:
        tipo = participante.get("tipo", "jogador")
        if tipo == "jogador":
            linha = f"👤 **{participante.get('nome', 'Jogador')}**\n❤️ {int(_valor(participante, 'vida'))}/{int(_valor(participante, 'vida_maxima'))}\n💙 {int(_valor(participante, 'mana'))}"
        else:
            linha = f"{participante.get('emoji', '👹')} **{participante.get('nome', 'Monstro')}**\n❤️ {int(_valor(participante, 'vida'))}/{int(_valor(participante, 'vida_maxima'))}"
        estados = []
        for efeito in _efeitos_validos(participante.get("efeitos")):
            nome = str(efeito.get("nome", "")).strip()
            turnos = int(_valor(efeito, "turnos", 0) or 0)
            if nome:
                estados.append(f"{nome.title()} ({turnos}t)")
        if participante.get("desviante_ativo"):
            estados.append("Desviante ativo")
        if participante.get("defesa_magica_ativa"):
            estados.append(f"Barreira {int(_valor(participante, 'defesa_magica_valor'))}")
        if estados:
            linha += "\n⚠️ " + " • ".join(estados)
        linhas.append(linha)
    texto = "\n\n".join(linhas)
    return texto if len(texto) <= 1000 else texto[:997] + "..."


async def setup(bot):
    base.Luta._resolver_ataque = _resolver_ataque
    base.Luta._defesa_monstro = _defesa_monstro_corrigida
    base.Luta._obter_defensor = _obter_defensor_corrigido
    base.Luta._texto_status = _texto_status_com_efeitos
    luta = bot.get_cog("Luta")
    if luta:
        luta._resolver_ataque = _resolver_ataque.__get__(luta, base.Luta)
        luta._defesa_monstro = _defesa_monstro_corrigida.__get__(luta, base.Luta)
        luta._obter_defensor = _obter_defensor_corrigido.__get__(luta, base.Luta)
        luta._texto_status = _texto_status_com_efeitos.__get__(luta, base.Luta)
    print("✅ Resolver de habilidades, defesa PvE e alvos de party integrados ao fluxo de combate.")
