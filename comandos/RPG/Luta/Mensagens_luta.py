"""Interface visual única das mensagens de combate."""

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
    return None


def imagem_monstro(monstro):
    monstro = str(monstro or "").lower().strip()
    if monstro == "slime":
        return IMAGENS.get("slime-luta-url")
    elif monstro == "goblin":
        return IMAGENS.get("goblin-luta-url")
    elif monstro == "lobo":
        return IMAGENS.get("lobo-luta-url")
    elif monstro == "orc":
        return IMAGENS.get("orc-luta-url")
    elif monstro == "esqueleto":
        return IMAGENS.get("esqueleto-luta-url")
    elif monstro == "dragao":
        return IMAGENS.get("dragao-luta-url")
    elif monstro == "titan":
        return IMAGENS.get("titan-luta-url")
    elif monstro == "fenix":
        return IMAGENS.get("fenix-luta-url")
    elif monstro == "demonio":
        return IMAGENS.get("demonio-luta-url")
    return None


def imagens_combate(nome_ataque, monstro=None):
    return None, imagem_monstro(monstro)


def _imagem_monstro(oponente):
    if isinstance(oponente, dict):
        return imagem_monstro(oponente.get("id") or oponente.get("monstro_id") or oponente.get("nome"))
    return imagem_monstro(oponente)


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

    mensagem = discord.Embed(title="🌙 MOON TENSURA", description=texto, color=cor or discord.Color.blurple(), timestamp=discord.utils.utcnow())

    # SOMENTE a imagem do monstro pode ser exibida no combate.
    url_monstro = imagem_oponente
    if url_monstro is None and isinstance(oponente, dict) and oponente.get("tipo") == "monstro":
        url_monstro = _imagem_monstro(oponente)
    if url_monstro:
        mensagem.set_image(url=url_monstro)

    mensagem.set_footer(text=FOOTER)
    return mensagem


def embed(titulo, descricao="", *, cor=None, imagem=None):
    return painel(extra=f"{titulo}: {descricao}" if descricao else titulo, cor=cor)


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
    return painel(atacante=_nome(atacante, "User"), ataque=nome_ataque, vida=_vida(atacante), mana=_mana(atacante), dano=dano, efeito=efeito or "Nenhum", alvo=_nome(defensor), turno=turno, oponente=defensor or "-", vida_oponente=_vida(defensor), extra=extra, cor=cor)
