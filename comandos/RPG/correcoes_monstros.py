"""Correcoes de combate: cooldown PvE e apresentacao padronizada."""

import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

from database.python.luta import MONSTROS
from database.python import luta as luta_db

COOLDOWN_MONSTRO_HORAS = 6
ARQUIVO_IMAGENS = "database/json/Imagens.json"
BOX_WIDTH = 42


def _formatar_tempo(segundos):
    segundos = max(0, int(segundos or 0))
    horas, resto = divmod(segundos, 3600)
    minutos, segundos = divmod(resto, 60)
    if horas:
        return f"{horas}h {minutos:02d}min"
    if minutos:
        return f"{minutos}min {segundos:02d}s"
    return f"{segundos}s"


def _slug(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-zA-Z0-9]+", "-", texto).strip("-").lower()


def _carregar_imagens():
    try:
        with open(ARQUIVO_IMAGENS, "r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        return dados.get("Imagens", {}) if isinstance(dados, dict) else {}
    except Exception as erro:
        print(f"[LUTA][IMAGENS][ERRO] {type(erro).__name__}: {erro}")
        return {}


IMAGENS = _carregar_imagens()


def _imagem(*chaves):
    for chave in chaves:
        valor = IMAGENS.get(chave)
        if isinstance(valor, str) and valor.startswith(("http://", "https://")):
            return valor
    return None


def _imagem_para_ataque(ataque, atacante=None):
    nome = ataque.get("nome", "") if ataque else ""
    tipo = str(ataque.get("tipo", "")) if ataque else ""
    slug = _slug(nome)
    if tipo == "magia":
        return _imagem(f"{slug}-luta-url", "magia-luta-url")
    if tipo in {"habilidade", "skill"}:
        return _imagem(f"{slug}-luta-url", "habilidade-luta-url")
    if tipo == "ataque_monstro" or (atacante and atacante.get("tipo") == "monstro"):
        monstro = _slug(atacante.get("nome", "monstro"))
        return _imagem(f"{monstro}-luta-url", "ataque-monstro-luta-url", "monstro-luta-url")
    return _imagem(f"{slug}-luta-url", "ataque-luta-url")


def _imagem_para_defesa(acao):
    return _imagem(f"{_slug(acao)}-luta-url", "defesa-luta-url")


def _texto_linha(texto):
    texto = str(texto)
    if len(texto) > BOX_WIDTH:
        texto = texto[:BOX_WIDTH - 1] + "…"
    return f"│ {texto:<{BOX_WIDTH}} │"


def _box_luta(linhas):
    topo = "╭" + "─" * (BOX_WIDTH + 2) + "╮"
    separador = "├" + "─" * (BOX_WIDTH + 2) + "┤"
    pontilhado = "├" + "┄" * (BOX_WIDTH + 2) + "┤"
    base = "╰" + "─" * (BOX_WIDTH + 2) + "╯"
    titulo = _texto_linha("🌙  MOON TENSURA".center(BOX_WIDTH))
    corpo = [topo, titulo, separador]
    corpo.extend(_texto_linha(linha) for linha in linhas[:3])
    corpo.append(separador)
    corpo.extend(_texto_linha(linha) for linha in linhas[3:7])
    corpo.append(pontilhado)
    corpo.extend(_texto_linha(linha) for linha in linhas[7:9])
    corpo.append(base)
    return "\n".join(corpo)


def _embed_luta(linhas, imagem=None, cor=None):
    embed = discord.Embed(description=f"```text\n{_box_luta(linhas)}\n```", color=cor or discord.Color.dark_theme())
    if imagem:
        embed.set_image(url=imagem)
    return embed


def _dados_luta(combate, atacante, defensor, ataque=None, dano=0, efeito="Nenhum", alvo=None, acao="ataque"):
    nome_atacante = atacante.get("nome", "Desconhecido")
    nome_defensor = defensor.get("nome", "Desconhecido") if defensor else "Nenhum"
    ataque_nome = (ataque or {}).get("nome", "Ataque")
    primeira = (
        f"⋮ → 👤 | {nome_atacante} defendeu usando {ataque_nome}"
        if acao == "defesa"
        else f"⋮ → 👤 | {nome_atacante} atacou usando {ataque_nome}"
    )
    return [
        primeira,
        f"⋮ → ❤️ | Vida de {nome_atacante}: {max(0, int(atacante.get('vida', 0)))}",
        f"⋮ → 🔷 | Mana: {max(0, int(atacante.get('mana', 0)))}",
        f"│ → ⚔️ | Dano: {int(dano)}",
        f"│ → ✦  | Efeito: {efeito or 'Nenhum'}",
        f"│ → 🎯 | Alvo: {alvo or nome_defensor}",
        f"│ → 🔄 | Turno: {int(combate.get('numero_turno', 1))}",
        f"│ → 👹 | Oponente: {nome_defensor}",
        f"│ → ❤️ | Vida: {max(0, int(defensor.get('vida', 0))) if defensor else 0}",
    ]


async def _enviar_resultado(ctx, combate, atacante, defensor, ataque, dano, efeito, acao="ataque"):
    imagem = _imagem_para_ataque(ataque, atacante) if acao == "ataque" else _imagem_para_defesa(acao)
    linhas = _dados_luta(combate, atacante, defensor, ataque, dano, efeito, defensor.get("nome") if defensor else None, acao=acao)
    await ctx.send(embed=_embed_luta(linhas, imagem, discord.Color.red() if acao == "ataque" else discord.Color.blurple()))


async def _listar_monstros(self, ctx):
    if not MONSTROS:
        await ctx.send("❌ Nenhum monstro foi carregado.")
        return
    itens = list(MONSTROS.items())
    total_paginas = (len(itens) + 24) // 25
    for inicio in range(0, len(itens), 25):
        pagina = inicio // 25 + 1
        embed = discord.Embed(title="🐉 Monstros Disponíveis", color=discord.Color.dark_red())
        for monstro_id, dados in itens[inicio:inicio + 25]:
            embed.add_field(
                name=f"{dados.get('emoji', '👹')} {dados.get('nome', monstro_id)}",
                value=(
                    f"ID: `{monstro_id}`\n❤️ Vida: {dados.get('vida_base', 0)}\n"
                    f"⚔️ Dano: {dados.get('dano_base', 0)}\n✨ XP: {dados.get('xp_recompensa', 0)}\n"
                    f"💰 Hunos: {dados.get('hunos_recompensa', 0)}\n⏱️ Cooldown: **6h**"
                ), inline=True,
            )
            imagem = _imagem(f"{_slug(dados.get('nome', monstro_id))}-luta-url", "monstro-luta-url")
            if imagem:
                embed.set_thumbnail(url=imagem)
        embed.set_footer(text=f"Página {pagina}/{total_paginas} • Use !luta pve <id> para iniciar")
        await ctx.send(embed=embed)


class CooldownMonstros(commands.Cog):
    """Bloqueia o mesmo monstro por 6 horas para cada jogador e padroniza o combate."""

    async def _verificar_e_reservar(self, ctx):
        comando = getattr(ctx.command, "name", "").casefold()
        parent = getattr(ctx.command, "parent", None)
        if comando != "pve" or getattr(parent, "name", "").casefold() != "luta" or ctx.guild is None:
            return True
        kwargs = getattr(ctx, "kwargs", {}) or {}
        monstro_tipo = kwargs.get("monstro_tipo")
        if not monstro_tipo:
            partes = str(getattr(getattr(ctx, "message", None), "content", "")).split()
            if len(partes) >= 3 and partes[0].casefold() == "!luta" and partes[1].casefold() == "pve":
                monstro_tipo = " ".join(partes[2:])
        luta = ctx.bot.get_cog("Luta")
        monstro_id = luta._encontrar_monstro(monstro_tipo) if luta and monstro_tipo else None
        if not monstro_id:
            return True
        cooldown = await luta_db.run_db(luta_db.verificar_cooldown_monstro, str(ctx.author.id), str(ctx.guild.id), str(monstro_id))
        if cooldown.get("em_cooldown"):
            await ctx.send(f"⏳ Você já enfrentou **{MONSTROS[monstro_id].get('nome', monstro_id)}**. Tente novamente em **{_formatar_tempo(cooldown.get('segundos_restantes', 0))}**.")
            return False
        reserva = await luta_db.run_db(luta_db.iniciar_cooldown_monstro, str(ctx.author.id), str(ctx.guild.id), str(monstro_id))
        if not reserva.get("sucesso"):
            await ctx.send(f"⏳ Você já enfrentou **{MONSTROS[monstro_id].get('nome', monstro_id)}**. Tente novamente em **{_formatar_tempo(reserva.get('segundos_restantes', 0))}**.")
            return False
        fim = reserva.get("fim")
        if fim is not None and luta_db.db is not None:
            agora = datetime.now(timezone.utc)
            fim_forcado = agora + timedelta(hours=COOLDOWN_MONSTRO_HORAS)
            campo = f"Cooldowns_Monstros.{str(monstro_id)}"
            await luta_db.run_db(luta_db.db["Jogadores"].update_one, {"ID": str(ctx.author.id), "guild_id": str(ctx.guild.id), campo: fim}, {"$set": {campo: fim_forcado}})
            fim = fim_forcado
        ctx._monstro_cooldown_reserva = (str(monstro_id), fim)
        return True

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        reserva = getattr(ctx, "_monstro_cooldown_reserva", None)
        if not reserva or ctx.guild is None:
            return
        monstro_id, fim = reserva
        await luta_db.run_db(luta_db.cancelar_cooldown_monstro, str(ctx.author.id), str(ctx.guild.id), monstro_id, fim)

    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        if hasattr(ctx, "_monstro_cooldown_reserva"):
            delattr(ctx, "_monstro_cooldown_reserva")


def _instalar_formatacao_combate(cog):
    """Substitui as mensagens visuais sem duplicar a lógica de dano do motor."""
    original_resolver = cog._resolver_ataque

    async def anunciar(ctx):
        combate = cog._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return
        ataque = combate.get("ataque_pendente")
        atacante = cog._participante(combate, ataque.get("atacante_id")) if ataque else cog._obter_atacante(combate)
        defensor = cog._participante(combate, ataque.get("defensor_id")) if ataque else cog._obter_defensor(combate)
        if not ataque or not atacante or not defensor:
            return
        linhas = _dados_luta(combate, atacante, defensor, ataque, 0, "Aguardando defesa", defensor.get("nome"))
        await ctx.send(embed=_embed_luta(linhas, _imagem_para_ataque(ataque, atacante), discord.Color.orange()))
        if defensor.get("tipo") == "monstro":
            import asyncio
            await asyncio.sleep(0.25)
            await cog._defesa_monstro(ctx)

    async def resolver(ctx):
        combate = cog._obter_combate(ctx.channel.id)
        ataque = (combate or {}).get("ataque_pendente") or {}
        atacante = cog._participante(combate, ataque.get("atacante_id")) if combate else None
        defensor = cog._participante(combate, ataque.get("defensor_id")) if combate else None
        vida_antes = int(defensor.get("vida", 0)) if defensor else 0
        historico_antes = len(combate.get("historico", [])) if combate else 0
        original_send = ctx.send

        async def silenciar(*args, **kwargs):
            return None

        ctx.send = silenciar
        try:
            await original_resolver(ctx)
        finally:
            ctx.send = original_send

        if not combate or not atacante or not defensor:
            return
        dano = max(0, vida_antes - int(defensor.get("vida", 0)))
        efeito = "Nenhum"
        novos = defensor.get("efeitos", [])
        if novos:
            efeito = str(novos[-1].get("nome", "Nenhum")).title()
        elif len(combate.get("historico", [])) > historico_antes and "esquivou" in combate["historico"][-1].lower():
            efeito = "Esquiva"
        acao = str(ataque.get("_acao", "ataque"))
        await _enviar_resultado(ctx, combate, atacante, defensor, ataque, dano, efeito, acao=acao)
        if combate.get("ativo") and combate.get("fase") == "ataque" and not combate.get("aguardando_finalizacao"):
            await anunciar(ctx)

    async def defesa_jogador(ctx, acao):
        combate = cog._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo") or combate.get("fase") != "defesa":
            await ctx.send("❌ Não há ataque pendente para defender.")
            return
        defensor = cog._obter_defensor(combate)
        if not defensor or defensor.get("tipo") != "jogador" or str(defensor.get("id")) != str(ctx.author.id):
            nome = defensor.get("nome", "outro jogador") if defensor else "outro jogador"
            await ctx.send(f"❌ É **{nome}** quem deve defender este ataque.")
            return
        defensor["defesa_ativa"] = acao == "defesa"
        defensor["esquiva_ativa"] = acao == "esquiva"
        ataque = combate.get("ataque_pendente") or {}
        ataque["nome"] = f"🛡️ {acao.title()}"
        ataque["_acao"] = "defesa"
        await resolver(ctx)

    async def defesa_monstro(ctx):
        combate = cog._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo") or combate.get("fase") != "defesa":
            return
        defensor = cog._obter_defensor(combate)
        if not defensor or defensor.get("tipo") != "monstro":
            return
        import random
        escolha = random.choice(("defesa", "esquiva", "normal"))
        defensor["defesa_ativa"] = escolha == "defesa"
        defensor["esquiva_ativa"] = escolha == "esquiva"
        ataque = combate.get("ataque_pendente") or {}
        ataque["nome"] = f"🛡️ {escolha.title()}"
        ataque["_acao"] = "defesa"
        await resolver(ctx)

    cog._anunciar_ataque = anunciar
    cog._resolver_ataque = resolver
    cog._defesa_jogador = defesa_jogador
    cog._defesa_monstro = defesa_monstro


async def setup(bot):
    grupo = bot.get_command("luta")
    if grupo is None:
        raise RuntimeError("O comando !luta não foi encontrado para aplicar as correções.")
    comando = grupo.get_command("monstros")
    if comando is not None:
        comando.callback = _listar_monstros
    pve = grupo.get_command("pve")
    if pve is None:
        raise RuntimeError("O comando !luta pve não foi encontrado para aplicar o cooldown.")
    cog = CooldownMonstros(bot)
    await bot.add_cog(cog)
    pve.add_check(cog._verificar_e_reservar)
    luta = bot.get_cog("Luta")
    if luta is not None:
        _instalar_formatacao_combate(luta)
