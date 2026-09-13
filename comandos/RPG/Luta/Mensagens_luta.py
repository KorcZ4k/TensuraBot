"""Interface visual unica das mensagens de combate.

Todas as mensagens de luta usam o mesmo painel Moon Tensura. O motor de
combate continua separado desta camada para que regras e visual possam ser
alterados independentemente.
"""

from __future__ import annotations

import discord

FOOTER = "Tensura Moon - Korczak Technologies!"


def painel(*, atacante: str = "User", ataque: str = "Ataque", vida: str | int = "-", mana: str | int = "-", dano: str | int = "-", efeito: str = "Nenhum", alvo: str = "-", turno: str | int = "-", oponente: str = "-", vida_oponente: str | int = "-", extra: str = "", cor=None) -> discord.Embed:
    """Monta o painel padrão Moon Tensura usado em qualquer mensagem de luta."""
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
        f"│ │ → 👹 | Oponente: {oponente}\n"
        f"│ │ → ❤️ | Vida: {vida_oponente}\n"
    )
    if extra:
        texto += f"│ │ → ℹ️ | {extra}\n"
    texto += "╰────────────────────────────────────────────╯"
    mensagem = discord.Embed(title="🌙 MOON TENSURA", description=f"```text\n{texto}\n```", color=cor or discord.Color.blurple(), timestamp=discord.utils.utcnow())
    mensagem.set_footer(text=FOOTER)
    return mensagem


def embed(titulo: str, descricao: str = "", *, cor=None, imagem: str | None = None) -> discord.Embed:
    """Compatibilidade: chamadas antigas também recebem o novo painel."""
    mensagem = painel(extra=f"{titulo}: {descricao}" if descricao else titulo, cor=cor)
    if imagem:
        mensagem.set_image(url=imagem)
    return mensagem


def _vida(p: dict | None) -> str:
    if not p:
        return "-"
    vida = int(float(p.get("vida", 0) or 0))
    maxima = int(float(p.get("vida_maxima", vida) or vida or 1))
    return f"{max(0, vida)}/{max(1, maxima)}"


def _mana(p: dict | None) -> str:
    if not p:
        return "-"
    return str(int(float(p.get("mana", 0) or 0)))


def _nome(p: dict | None, padrao: str = "-") -> str:
    return str((p or {}).get("nome") or padrao)


def resultado(texto: str, *, status: str | None = None) -> discord.Embed:
    return painel(extra=f"Resultado: {texto}" + (f" | Status: {status}" if status else ""), cor=discord.Color.red())


def turno(numero: int, atacante: str, defensor: str) -> discord.Embed:
    return painel(atacante=atacante, ataque="aguardando ação", alvo=defensor, turno=numero, oponente=defensor, extra="Escolha sua ação de combate.", cor=discord.Color.green())


def ataque(numero: int, nome_ataque: str, atacante: str, defensor: str, status: str) -> discord.Embed:
    return painel(atacante=atacante, ataque=nome_ataque, alvo=defensor, turno=numero, oponente=defensor, vida_oponente=status, cor=discord.Color.orange())


def finalizacao(descricao: str, status: str, xp: int = 0, hunos: int = 0, *, venceu: bool = False) -> discord.Embed:
    return painel(ataque="finalização", efeito=f"XP +{xp} | Hunos +{hunos}", turno="fim", extra=descricao, oponente="Combate encerrado", vida_oponente=status, cor=discord.Color.green() if venceu else discord.Color.red())


def inicio(*, pvp: bool, turno: int, atacante: str, defensor: str) -> discord.Embed:
    return painel(atacante=atacante, ataque="início do combate", alvo=defensor, turno=turno, oponente=defensor, extra="Combate PvP iniciado." if pvp else "Combate PvE iniciado.", cor=discord.Color.red())


def ordem_velocidade(participantes) -> discord.Embed:
    ordem = " | ".join(f"{i + 1}. {p.get('nome')} ({int(float(p.get('Velocidade', p.get('velocidade', 0)) or 0))})" for i, p in enumerate(participantes)) or "Nenhum participante."
    return painel(ataque="ordem de velocidade", turno=1, oponente="Todos", extra=ordem, cor=discord.Color.blurple())


def acao(*, atacante: dict | None, defensor: dict | None, nome_ataque: str, dano=0, efeito="Nenhum", turno="-", extra="", cor=None) -> discord.Embed:
    """Painel completo para uma ação resolvida."""
    return painel(atacante=_nome(atacante, "User"), ataque=nome_ataque, vida=_vida(atacante), mana=_mana(atacante), dano=dano, efeito=efeito or "Nenhum", alvo=_nome(defensor), turno=turno, oponente=_nome(defensor), vida_oponente=_vida(defensor), extra=extra, cor=cor)
