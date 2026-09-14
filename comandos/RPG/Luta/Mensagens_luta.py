"""Interface visual unica das mensagens de combate."""

from __future__ import annotations

import json
from pathlib import Path

import discord

FOOTER = "Tensura Moon - Korczak Technologies!"


def _carregar_imagens():
    caminho = Path(__file__).resolve().parents[3] / "database" / "json" / "Imagens.json"
    try:
        with caminho.open("r", encoding="utf-8") as arquivo:
            return json.load(arquivo).get("Imagens", {})
    except (OSError, ValueError, TypeError) as erro:
        print(f"[LUTA][IMAGENS] Erro ao carregar Imagens.json: {erro}")
        return {}


IMAGENS = _carregar_imagens()


def imagem_ataque(nome):
    nome = str(nome or "").lower().strip()

    if nome == "soco":
        return IMAGENS.get("soco-luta-url")
    elif nome == "chute":
        return IMAGENS.get("chute-luta-url")
    elif nome == "golpe pesado":
        return IMAGENS.get("golpe-pesado-luta-url")
    elif nome == "golpe rapido":
        return IMAGENS.get("golpe-rapido-luta-url")
    elif nome == "golpe magico":
        return IMAGENS.get("golpe-magico-luta-url")
    elif nome == "golpe supremo":
        return IMAGENS.get("golpe-supremo-luta-url")
    elif nome == "defesa":
        return IMAGENS.get("defesa-luta-url")
    elif nome == "esquiva":
        return IMAGENS.get("esquiva-luta-url")
    elif nome == "magia":
        return IMAGENS.get("magia-luta-url")
    elif nome == "habilidade":
        return IMAGENS.get("habilidade-luta-url")
    else:
        return IMAGENS.get("ataque-luta-url")


def imagem_monstro(monstro):
    """Escolha direta: monstro -> URL correspondente no Imagens.json."""
    monstro = str(monstro or "").lower().strip()

    if monstro == "slime":
        imagem = IMAGENS.get("slime-luta-url")
    elif monstro == "goblin":
        imagem = IMAGENS.get("goblin-luta-url")
    elif monstro == "lobo":
        imagem = IMAGENS.get("lobo-luta-url")
    elif monstro == "orc":
        imagem = IMAGENS.get("orc-luta-url")
    elif monstro == "esqueleto":
        imagem = IMAGENS.get("esqueleto-luta-url")
    elif monstro == "dragao":
        imagem = IMAGENS.get("dragao-luta-url")
    elif monstro == "titan":
        imagem = IMAGENS.get("titan-luta-url")
    elif monstro == "fenix":
        imagem = IMAGENS.get("fenix-luta-url")
    elif monstro == "demonio":
        imagem = IMAGENS.get("demonio-luta-url")
    else:
        imagem = None

    return imagem


def imagens_combate(nome_ataque, monstro=None):
    imagem = imagem_monstro(monstro)
    return imagem_ataque(nome_ataque), imagem


def _imagem_ataque(nome):
    return imagem_ataque(nome)


def _imagem_monstro(oponente):
    if isinstance(oponente, dict):
        monstro = oponente.get("id") or oponente.get("monstro_id") or oponente.get("nome")
    else:
        monstro = oponente
    return imagem_monstro(monstro)


def _vida(p):
    if not p:
        return "-"
    vida = int(float(p.get("vida", 0) or 0))
    maxima = int(float(p.get("vida_maxima", vida) or vida or 1))
    return f"{max(0, vida)}/{max(1, maxima)}"


def _mana(p):
    if not p:
        return "-"
    return str(int(float(p.get("mana", 0) or 0)))


def _nome(p, padrao="-"):
    return str((p or {}).get("nome") or padrao)


def painel(*, atacante="User", ataque="Ataque", vida="-", mana="-", dano="-", efeito="Nenhum", alvo="-", turno="-", oponente="-", vida_oponente="-", extra="", cor=None, imagem_ataque=None, imagem_oponente=None):
    nome_oponente = _nome(oponente, str(oponente) if not isinstance(oponente, dict) else "-")

    texto = (
        "╭────────────────────────────────────────────╮\n"
        "│              🌙  MOON TENSURA              │\n"
        "├────────────────────────────────────────────┤\n"
        f"│ ⋮ → 👤 | {atacante} atacou usando {ataque}\n"
        f"│ ⋮ → ❤️ | Vida de {atacante}: {vida}\n"
        f"│ ⋮ → 🔷 | Mana de: {mana}\n"
        "├────────────────────────────────────────────┤\n"
        f"│ │ → ⚔️ | Dano: {dano}\n"
        f"│ │ → ✦  | Efeito: {efeito}\n"
        f"│ │ → 🎯 | Alvo: {alvo}\n"
        f"│ │ → 🔄 | Turno: {turno}\n"
        "├ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┤\n"
        f"│ │ → 👹 | Oponente: {nome_oponente}\n"
        f"│ │ → ❤️ | Vida: {vida_oponente}\n"
    )
    if extra:
        texto += f"│ │ → ℹ️ | {extra}\n"
    texto += "╰────────────────────────────────────────────╯"

    mensagem = discord.Embed(
        title="🌙 MOON TENSURA",
        description=texto,
        color=cor or discord.Color.blurple(),
        timestamp=discord.utils.utcnow(),
    )

    url_ataque = imagem_ataque if imagem_ataque is not None else _imagem_ataque(ataque)
    url_monstro = imagem_oponente if imagem_oponente is not None else _imagem_monstro(oponente)

    if url_monstro:
        mensagem.set_image(url=url_monstro)
    elif url_ataque:
        mensagem.set_image(url=url_ataque)

    mensagem.set_footer(text=FOOTER)
    return mensagem


def embed(titulo, descricao="", *, cor=None, imagem=None):
    mensagem = painel(extra=f"{titulo}: {descricao}" if descricao else titulo, cor=cor)
    if imagem:
        mensagem.set_image(url=imagem)
    return mensagem


def resultado(texto, *, status=None):
    return painel(extra=f"Resultado: {texto}" + (f" | Status: {status}" if status else ""), cor=discord.Color.red())


def turno(numero, atacante, defensor):
    return painel(atacante=atacante, ataque="aguardando ação", alvo=defensor, turno=numero, oponente=defensor, extra="Escolha sua ação de combate.", cor=discord.Color.green())


def ataque(numero, nome_ataque, atacante, defensor, status):
    return painel(atacante=atacante, ataque=nome_ataque, alvo=defensor, turno=numero, oponente=defensor, vida_oponente=status, cor=discord.Color.orange())


def finalizacao(descricao, status, xp=0, hunos=0, *, venceu=False):
    return painel(ataque="finalização", efeito=f"XP +{xp} | Hunos +{hunos}", turno="fim", extra=descricao, oponente="Combate encerrado", vida_oponente=status, cor=discord.Color.green() if venceu else discord.Color.red())


def inicio(*, pvp, turno, atacante, defensor):
    return painel(atacante=atacante, ataque="início do combate", alvo=defensor, turno=turno, oponente=defensor, extra="Combate PvP iniciado." if pvp else "Combate PvE iniciado.", cor=discord.Color.red())


def ordem_velocidade(participantes):
    ordem = " | ".join(f"{i + 1}. {p.get('nome')} ({int(float(p.get('Velocidade', p.get('velocidade', 0)) or 0))})" for i, p in enumerate(participantes)) or "Nenhum participante."
    return painel(ataque="ordem de velocidade", turno=1, oponente="Todos", extra=ordem, cor=discord.Color.blurple())


def acao(*, atacante, defensor, nome_ataque, dano=0, efeito="Nenhum", turno="-", extra="", cor=None):
    return painel(
        atacante=_nome(atacante, "User"),
        ataque=nome_ataque,
        vida=_vida(atacante),
        mana=_mana(atacante),
        dano=dano,
        efeito=efeito or "Nenhum",
        alvo=_nome(defensor),
        turno=turno,
        oponente=defensor or "-",
        vida_oponente=_vida(defensor),
        extra=extra,
        cor=cor,
    )
