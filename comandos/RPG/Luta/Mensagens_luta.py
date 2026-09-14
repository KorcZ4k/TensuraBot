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
    return None


def imagens_combate(nome_ataque, monstro=None):
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
        "resultado": "📋 | Resultado", "ordem de velocidade": "📋 | Ordem de velocidade",
        "aguardando ação": "⏳ | Aguardando ação", "início do combate": "⚔️ | Início do combate",
        "finalização": "🏁 | Finalização", "resultado da defesa": "🛡️ | Resultado da defesa",
        "stun": "⛓️ | Stun", "⛓️ stun": "⛓️ | Stun",
        "apresentação do monstro": "👹 | Apresentação do monstro", "lista de monstros": "👹 | Lista de monstros",
        "comandos": "📖 | Comandos", "status": "📊 | Status", "🛌 descanso": "🛌 | Descanso",
        "🧘 meditação": "🧘 | Meditação", "⏰ recuperação": "⏰ | Recuperação",
        "⚔️ pvp": "⚔️ | PvP", "defenda-se": "🛡️ | Defesa",
    }
    return genericos.get(texto.casefold())


def _limpar_marcacao(texto):
    return str(texto).replace("**", "").strip()


def _extrair_valor(linhas, prefixos, padrao="-"):
    if isinstance(prefixos, str):
        prefixos = (prefixos,)
    for linha in linhas:
        linha = _limpar_marcacao(linha)
        for prefixo in prefixos:
            if linha.startswith(prefixo):
                return linha.split(":", 1)[1].strip() if ":" in linha else linha
    return padrao


def _painel_status(*, atacante, vida, mana, extra, cor, imagem_oponente=None):
    """Ficha pública: moldura obrigatória, negrito e leitura rápida no Discord."""
    linhas = [_limpar_marcacao(l) for l in str(extra or "").splitlines() if str(l).strip()]

    nome = _extrair_valor(linhas, "👤 Nome:", atacante)
    personagem = _extrair_valor(linhas, "🧬 Personagem:", "Não definido")
    raca = _extrair_valor(linhas, "🧬 Raça:", "Não definida")
    nivel = _extrair_valor(linhas, "📈 Nível:", "0")
    situacao = _extrair_valor(linhas, "📌 Situação:", "ativo")
    experiencia = _extrair_valor(linhas, ("⭐ XP:", "⭐ Experiência:"), "-")
    vida_txt = _extrair_valor(linhas, "❤️ Vida:", str(vida))
    mana_txt = _extrair_valor(linhas, "💧 Mana:", str(mana))
    magiculas = _extrair_valor(linhas, "✨ Magículas:", "0")
    tp = _extrair_valor(linhas, "✨ TP:", "0")

    # Cada atributo fica obrigatoriamente em sua própria linha.
    mapa_atributos = (
        ("💪", "Força"), ("🛡️", "Defesa"), ("❤️", "Vitalidade"), ("⚡", "Velocidade"),
        ("🎯", "Destreza"), ("✨", "Magia"), ("🍀", "Sorte"), ("🧠", "Inteligência"),
    )
    atributos = []
    for emoji, nome_atributo in mapa_atributos:
        valor = None
        for linha in linhas:
            partes = [parte.strip() for parte in linha.split("|")]
            for parte in partes:
                limpo = _limpar_marcacao(parte)
                if limpo.startswith(f"{nome_atributo}:"):
                    valor = limpo.split(":", 1)[1].strip()
                    break
            if valor is not None:
                break
        atributos.append((emoji, nome_atributo, valor if valor is not None else "0"))

    recuperacao = []
    for emoji, nome_rec in (("🛌", "Descanso"), ("🧘", "Meditação")):
        valor = _extrair_valor(linhas, f"{nome_rec}:", None)
        if valor is not None:
            recuperacao.append((emoji, nome_rec, valor))

    if not recuperacao:
        recuperacao = [("🔄", "Status", "Disponível para consulta")]

    linhas_saida = [
        "╭────────────────────────────────────────────╮",
        "│              🌙 MOON TENSURA               │",
        "├────────────────────────────────────────────┤",
        f"│ ⋮ → 👤 | Jogador: {nome}",
        f"│ ⋮ → 🧬 | Personagem: {personagem}",
        f"│ ⋮ → 🧬 | Raça: {raca}",
        f"│ ⋮ → 🎚️ | Nível: {nivel}",
        f"│ ⋮ → 📌 | Situação: {situacao}",
        f"│ ⋮ → ⭐ | Experiência: {experiencia}",
        f"│ ⋮ → ❤️ | Vida: {vida_txt}",
        f"│ ⋮ → 💧 | Mana: {mana_txt}",
        f"│ ⋮ → ✨ | Magículas: {magiculas}",
        f"│ ⋮ → 🔷 | TP: {tp}",
        "├────────────────────────────────────────────┤",
        "│ │ → 📊 | ATRIBUTOS DO PERSONAGEM",
    ]
    linhas_saida.extend(f"│ │ → {emoji} | {nome_atributo}: {valor}" for emoji, nome_atributo, valor in atributos)
    linhas_saida.extend([
        "├────────────────────────────────────────────┤",
        "│ │ → 🔄 | RECUPERAÇÃO",
    ])
    linhas_saida.extend(f"│ │ → {emoji} | {nome_rec}: {valor}" for emoji, nome_rec, valor in recuperacao)
    linhas_saida.append("╰────────────────────────────────────────────╯")

    descricao = "\n".join(_linha(linha) for linha in linhas_saida)
    embed = discord.Embed(
        title="🌙 MOON TENSURA",
        description=descricao,
        color=cor or discord.Color.blurple(),
        timestamp=discord.utils.utcnow(),
    )
    embed.set_footer(text=FOOTER)
    return embed


def painel(*, atacante="User", ataque="Ataque", vida="-", mana="-", dano="-", efeito="Nenhum", alvo="-", turno="-", oponente="-", vida_oponente="-", extra="", cor=None, imagem_ataque=None, imagem_oponente=None):
    if str(ataque or "").strip().casefold() == "status":
        return _painel_status(atacante=atacante, vida=vida, mana=mana, extra=extra, cor=cor, imagem_oponente=imagem_oponente)

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
        f"│ │ → ✦ | Efeito: {efeito}",
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
