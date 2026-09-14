"""Interface visual única das mensagens de combate e dos painéis RPG."""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import discord

FOOTER = "Tensura Moon - Korczak Technologies!"


def _carregar_imagens():
    caminho = Path(__file__).resolve().parents[3] / "database" / "json" / "Imagens.json"
    try:
        with caminho.open("r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        imagens = dados.get("Imagens", {})
        return imagens if isinstance(imagens, dict) else {}
    except (OSError, ValueError, TypeError) as erro:
        print(f"[LUTA][IMAGENS] Erro ao carregar Imagens.json: {erro}")
        return {}


IMAGENS = _carregar_imagens()


def _normalizar_nome(valor):
    texto = unicodedata.normalize("NFKD", str(valor or "")).casefold().strip()
    return "".join(c for c in texto if not unicodedata.combining(c))


def imagem_ataque(nome):
    # imagem_ataque é propositalmente ignorada; ataques não exibem imagem.
    return None


def imagem_monstro(monstro):
    """Retorna a imagem do monstro somente para a apresentação inicial do PvE."""
    if isinstance(monstro, dict):
        valor = monstro.get("id") or monstro.get("monstro_id") or monstro.get("nome")
    else:
        valor = monstro
    mapa = {
        "slime": "slime-luta-url", "goblin": "goblin-luta-url", "lobo": "lobo-luta-url",
        "orc": "orc-luta-url", "esqueleto": "esqueleto-luta-url", "dragao": "dragao-luta-url",
        "titan": "titan-luta-url", "fenix": "fenix-luta-url", "demonio": "demonio-luta-url",
    }
    url = IMAGENS.get(mapa.get(_normalizar_nome(valor)))
    return url if isinstance(url, str) and "discord" in url.lower() else None


def imagem_golpe(nome):
    # Imagens de golpes continuam desativadas na interface de combate.
    return None


def imagens_combate(nome_ataque, monstro=None):
    # A imagem do monstro é usada apenas na apresentação inicial do PvE.
    return None, imagem_monstro(monstro)


def _imagem_monstro(oponente):
    return None


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
    """Obtém nome de participante ou representa valores simples sem quebrar o embed."""
    if isinstance(p, dict):
        return str(p.get("nome") or padrao)
    if p is None:
        return str(padrao)
    return str(p)


def _linha(texto):
    return f"**{texto}**"


def _rotulo_acao(ataque):
    texto = str(ataque or "").strip()
    genericos = {
        "resultado": "📋 | Resultado",
        "ordem de velocidade": "📋 | Ordem de velocidade",
        "aguardando ação": "⏳ | Aguardando ação",
        "início do combate": "⚔️ | Início do combate",
        "finalização": "🏁 | Finalização",
        "resultado da defesa": "🛡️ | Resultado da defesa",
        "stun": "⛓️ | Stun",
        "⛓️ stun": "⛓️ | Stun",
        "apresentação do monstro": "👹 | Apresentação do monstro",
        "lista de monstros": "👹 | Lista de monstros",
        "comandos": "📖 | Comandos",
        "status": "📊 | Status",
        "🛌 descanso": "🛌 | Descanso",
        "🧘 meditação": "🧘 | Meditação",
        "⏰ recuperação": "⏰ | Recuperação",
        "⚔️ pvp": "⚔️ | PvP",
        "defenda-se": "🛡️ | Defesa",
    }
    return genericos.get(texto.casefold())


def _limpar_marcacao(texto):
    return str(texto).replace("**", "").strip()


def _campo_status(linhas, inicio, fim=None):
    trecho = linhas[inicio:fim]
    return "\n".join(_limpar_marcacao(linha) for linha in trecho if str(linha).strip())


def _painel_status(*, atacante, vida, mana, extra, cor, imagem_oponente=None):
    """Painel de ficha pensado para leitura rápida no Discord."""
    linhas = [str(linha) for linha in str(extra or "").splitlines()]
    linhas = [_limpar_marcacao(linha) for linha in linhas]

    if any("Este personagem está morto" in linha for linha in linhas):
        destaque = "💀 **Este personagem está morto!**"
    else:
        destaque = "✨ **Ficha de personagem**"

    nome = next((l.split(":", 1)[1].strip() for l in linhas if l.startswith("👤 Nome:")), atacante)
    personagem = next((l.split(":", 1)[1].strip() for l in linhas if l.startswith("🧬 Personagem:")), "Não definido")
    raca = next((l.split(":", 1)[1].strip() for l in linhas if l.startswith("🧬 Raça:")), "Não definida")
    nivel = next((l.split(":", 1)[1].strip() for l in linhas if l.startswith("📈 Nível:")), "0")
    situacao = next((l.split(":", 1)[1].strip() for l in linhas if l.startswith("📌 Situação:")), "ativo")
    xp = next((l.split(":", 1)[1].strip() for l in linhas if l.startswith("⭐ XP:")), "-")
    vida_txt = next((l.split(":", 1)[1].strip() for l in linhas if l.startswith("❤️ Vida:")), str(vida))
    mana_txt = next((l.split(":", 1)[1].strip() for l in linhas if l.startswith("💧 Mana:")), str(mana))
    magiculas = next((l.split(":", 1)[1].strip() for l in linhas if l.startswith("✨ Magículas:")), "0")
    tp = next((l.split(":", 1)[1].strip() for l in linhas if l.startswith("✨ TP:")), "0")

    atributos = []
    for linha in linhas:
        if any(linha.startswith(prefixo) for prefixo in ("Força:", "Vitalidade:", "Destreza:", "Magia:")):
            atributos.append(linha)
    # As linhas originais trazem dois atributos por linha.
    atributos = "\n".join(atributos) or "Nenhum atributo disponível."

    recuperacao = []
    for linha in linhas:
        if linha.startswith("Descanso:") or linha.startswith("Meditação:"):
            recuperacao.append(linha)
    recuperacao_txt = "\n".join(recuperacao) or "Sem informações de recuperação."

    barras = []
    for linha in linhas:
        if linha.startswith("XP visual:") or linha.startswith("Vida visual:") or linha.startswith("Mana visual:"):
            barras.append(linha)
    barras_txt = "\n".join(barras) or "Sem barras disponíveis."

    embed = discord.Embed(
        title="🌙 MOON TENSURA • STATUS",
        description=f"{destaque}\n\n👤 **{nome}**\n🎭 **{personagem}** • {raca}\n📈 **Nível {nivel}** • {situacao}",
        color=cor or discord.Color.blurple(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="❤️ Recursos", value=f"**Vida:** {vida_txt}\n**Mana:** {mana_txt}", inline=True)
    embed.add_field(name="⭐ Progressão", value=f"**XP:** {xp}\n**TP:** {tp}\n**Magículas:** {magiculas}", inline=True)
    embed.add_field(name="📊 Atributos", value=atributos, inline=False)
    embed.add_field(name="📈 Barras", value=barras_txt, inline=False)
    embed.add_field(name="🔄 Recuperação", value=recuperacao_txt, inline=False)
    embed.set_thumbnail(url=imagem_oponente) if imagem_oponente else None
    embed.set_footer(text=FOOTER)
    return embed


def painel(*, atacante="User", ataque="Ataque", vida="-", mana="-", dano="-", efeito="Nenhum", alvo="-", turno="-", oponente="-", vida_oponente="-", extra="", cor=None, imagem_ataque=None, imagem_oponente=None):
    if str(ataque or "").strip().casefold() == "status":
        return _painel_status(
            atacante=atacante,
            vida=vida,
            mana=mana,
            extra=extra,
            cor=cor,
            imagem_oponente=imagem_oponente,
        )

    nome_oponente = _nome(oponente, str(oponente) if not isinstance(oponente, dict) else "-")
    texto_ataque = str(ataque or "").strip()
    rotulo = _rotulo_acao(ataque)
    if "sua vez" in texto_ataque.casefold() or "vez do monstro" in texto_ataque.casefold():
        linha_acao = f"│ ⋮ → 👤 | Vez de {atacante}"
    elif rotulo:
        linha_acao = f"│ ⋮ → {rotulo}"
    elif texto_ataque.casefold().startswith("vez de"):
        linha_acao = f"│ ⋮ → 👤 | {ataque}"
    else:
        linha_acao = f"│ ⋮ → 👤 | {atacante} atacou usando {ataque}"
    linhas = [
        "╭────────────────────────────────────────────╮",
        "│              🌙  MOON TENSURA              │",
        "├────────────────────────────────────────────┤",
        linha_acao,
        f"│ ⋮ → ❤️ | Vida de {atacante}: {vida}",
        f"│ ⋮ → 🔷 | Mana de: {mana}",
        "├────────────────────────────────────────────┤",
        f"│ │ → ⚔️ | Dano: {dano}",
        f"│ │ → ✦  | Efeito: {efeito}",
        f"│ │ → 🎯 | Alvo: {alvo}",
        f"│ │ → 🔄 | Turno: {turno}",
        "├ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┤",
        f"│ │ → 👹 | Oponente: {nome_oponente}",
        f"│ │ → ❤️ | Vida: {vida_oponente}",
    ]
    if extra:
        linhas.extend(f"│ │ → ℹ️ | {linha}" for linha in str(extra).splitlines())
    linhas.append("╰────────────────────────────────────────────╯")
    texto = "\n".join(_linha(linha) for linha in linhas)
    mensagem = discord.Embed(title="🌙 MOON TENSURA", description=texto, color=cor or discord.Color.blurple(), timestamp=discord.utils.utcnow())
    mensagem.set_footer(text=FOOTER)
    return mensagem


def embed(titulo, descricao="", *, cor=None, imagem=None):
    return painel(extra=f"{titulo}: {descricao}" if descricao else titulo, cor=cor)


def resultado(texto, *, status=None):
    return painel(ataque="resultado", extra=f"Resultado: {texto}" + (f" | Status: {status}" if status else ""), cor=discord.Color.red())


def turno(numero, atacante, defensor):
    return painel(ataque="aguardando ação", alvo=defensor, turno=numero, oponente=defensor, extra="Escolha sua ação de combate.", cor=discord.Color.green())


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
