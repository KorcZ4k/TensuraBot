"""Interface visual do combate: textos, embeds e imagens.

O motor de luta deve chamar estas funções quando precisar apresentar um
resultado. Assim a aparência do combate pode mudar sem alterar as regras.
"""

from __future__ import annotations

import discord

FOOTER = "Tensura Moon - Korczak Technologies!"


def embed(titulo: str, descricao: str = "", *, cor=None, imagem: str | None = None) -> discord.Embed:
    """Cria o padrão visual usado pelas mensagens de combate."""
    mensagem = discord.Embed(
        title=titulo,
        description=descricao,
        color=cor or discord.Color.blurple(),
        timestamp=discord.utils.utcnow(),
    )
    mensagem.set_footer(text=FOOTER)
    if imagem:
        mensagem.set_image(url=imagem)
    return mensagem


def resultado(texto: str, *, status: str | None = None) -> discord.Embed:
    """Embed padrão para o resultado de uma ação de combate."""
    mensagem = embed("💥 Resultado", texto, cor=discord.Color.red())
    if status:
        mensagem.add_field(name="📋 Status", value=status, inline=False)
    return mensagem


def turno(numero: int, atacante: str, defensor: str) -> discord.Embed:
    """Mensagem que apresenta o início de um turno."""
    return embed(
        f"🔄 Turno {numero}",
        f"⚔️ **{atacante}** deve atacar **{defensor}**.",
        cor=discord.Color.green(),
    )


def ataque(numero: int, nome_ataque: str, atacante: str, defensor: str, status: str) -> discord.Embed:
    """Mensagem que anuncia um ataque e quem deve defendê-lo."""
    mensagem = embed(
        f"⚔️ Turno {numero}",
        f"{nome_ataque}\n\n⚔️ **{atacante}** atacou **{defensor}**!",
        cor=discord.Color.orange(),
    )
    mensagem.add_field(name="🛡️ Quem deve defender", value=f"**{defensor}**", inline=False)
    mensagem.add_field(name="📋 Status", value=status, inline=False)
    return mensagem


def finalizacao(descricao: str, status: str, xp: int = 0, hunos: int = 0, *, venceu: bool = False) -> discord.Embed:
    """Mensagem final do combate com recompensas e status."""
    mensagem = embed(
        "⚔️ Combate Finalizado",
        descricao,
        cor=discord.Color.green() if venceu else discord.Color.red(),
    )
    mensagem.add_field(name="🎁 Recompensas", value=f"✨ XP: **{xp}**\n💰 Hunos: **{hunos}**", inline=False)
    mensagem.add_field(name="📋 Status", value=status, inline=False)
    return mensagem


def inicio(*, pvp: bool, turno: int, atacante: str, defensor: str) -> discord.Embed:
    """Mensagem inicial de PvE/PvP."""
    return embed(
        "⚔️ Combate PvP" if pvp else "⚔️ Combate PvE",
        f"🔔 **Turno {turno}**\n\n⚡ **{atacante}** começa!\n🎯 Alvo: **{defensor}**",
        cor=discord.Color.red(),
    )


def ordem_velocidade(participantes) -> discord.Embed:
    """Tabela visual da ordem de velocidade."""
    descricao = "\n".join(
        f"{i + 1}. **{p.get('nome')}** — {int(float(p.get('Velocidade', p.get('velocidade', 0)) or 0))} Vel."
        for i, p in enumerate(participantes)
    ) or "Nenhum participante."
    return embed("📋 Ordem de velocidade", descricao, cor=discord.Color.blurple())
