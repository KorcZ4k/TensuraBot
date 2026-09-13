"""Cooldown PvE e apresentacao padronizada do combate Moon Tensura."""
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
        return dados.get("Imagens", {})
    except Exception as erro:
        print(f"[LUTA][IMAGENS] {type(erro).__name__}: {erro}")
        return {}


IMAGENS = _carregar_imagens()


def _imagem(*chaves):
    for chave in chaves:
        url = IMAGENS.get(chave)
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            return url
    return None


def _imagem_ataque(ataque, atacante):
    tipo = str((ataque or {}).get("tipo", ""))
    nome = _slug((ataque or {}).get("nome", ""))
    if tipo == "magia":
        return _imagem(f"{nome}-luta-url", "magia-luta-url")
    if tipo in {"habilidade", "skill"}:
        return _imagem(f"{nome}-luta-url", "habilidade-luta-url")
    if tipo == "ataque_monstro" or atacante.get("tipo") == "monstro":
        monstro = _slug(atacante.get("nome", "monstro"))
        return _imagem(f"{monstro}-luta-url", "ataque-monstro-luta-url", "monstro-luta-url")
    return _imagem(f"{nome}-luta-url", "ataque-luta-url")


def _texto_linha(texto):
    texto = str(texto)
    if len(texto) > BOX_WIDTH:
        texto = texto[:BOX_WIDTH - 1] + "…"
    return f"│ {texto:<{BOX_WIDTH}} │"


def _box(linhas):
    topo = "╭" + "─" * (BOX_WIDTH + 2) + "╮"
    sep = "├" + "─" * (BOX_WIDTH + 2) + "┤"
    pont = "├" + "┄" * (BOX_WIDTH + 2) + "┤"
    base = "╰" + "─" * (BOX_WIDTH + 2) + "╯"
    titulo = _texto_linha("🌙  MOON TENSURA".center(BOX_WIDTH))
    return "\n".join([
        topo, titulo, sep,
        *[_texto_linha(x) for x in linhas[:3]],
        sep,
        *[_texto_linha(x) for x in linhas[3:7]],
        pont,
        *[_texto_linha(x) for x in linhas[7:9]],
        base,
    ])


def _embed(linhas, imagem=None, cor=None):
    embed = discord.Embed(description=f"```text\n{_box(linhas)}\n```", color=cor or discord.Color.dark_theme())
    if imagem:
        embed.set_image(url=imagem)
    return embed


def _linhas(combate, ator, oponente, ataque, dano, efeito, acao):
    nome_ator = ator.get("nome", "Desconhecido")
    nome_oponente = oponente.get("nome", "Desconhecido")
    nome_acao = ataque.get("nome", "Ataque")
    primeira = (
        f"⋮ → 👤 | {nome_ator} defendeu usando {nome_acao}"
        if acao == "defesa"
        else f"⋮ → 👤 | {nome_ator} atacou usando {nome_acao}"
    )
    return [
        primeira,
        f"⋮ → ❤️ | Vida de {nome_ator}: {max(0, int(ator.get('vida', 0)))}",
        f"⋮ → 🔷 | Mana: {max(0, int(ator.get('mana', 0)))}",
        f"│ → ⚔️ | Dano: {int(dano)}",
        f"│ → ✦  | Efeito: {efeito or 'Nenhum'}",
        f"│ → 🎯 | Alvo: {nome_oponente}",
        f"│ → 🔄 | Turno: {int(combate.get('numero_turno', 1))}",
        f"│ → 👹 | Oponente: {nome_oponente}",
        f"│ → ❤️ | Vida: {max(0, int(oponente.get('vida', 0)))}",
    ]


async def _resultado(ctx, combate, atacante, defensor, ataque, dano, efeito, acao="ataque"):
    if acao == "defesa":
        imagem = _imagem(f"{ataque.get('_defesa_tipo', 'defesa')}-luta-url", "defesa-luta-url")
        linhas = _linhas(combate, defensor, atacante, ataque, dano, efeito, acao)
        cor = discord.Color.blurple()
    else:
        imagem = _imagem_ataque(ataque, atacante)
        linhas = _linhas(combate, atacante, defensor, ataque, dano, efeito, acao)
        cor = discord.Color.red()
    await ctx.send(embed=_embed(linhas, imagem, cor))


async def _listar_monstros(self, ctx):
    if not MONSTROS:
        await ctx.send("❌ Nenhum monstro foi carregado.")
        return
    for monstro_id, dados in MONSTROS.items():
        embed = discord.Embed(
            title=f"🌙 MOON TENSURA • {dados.get('emoji', '👹')} {dados.get('nome', monstro_id)}",
            description=(
                f"**ID:** `{monstro_id}`\n"
                f"❤️ **Vida:** {dados.get('vida_base', 0)}\n"
                f"⚔️ **Dano:** {dados.get('dano_base', 0)}\n"
                f"✨ **XP:** {dados.get('xp_recompensa', 0)}\n"
                f"💰 **Hunos:** {dados.get('hunos_recompensa', 0)}\n"
                f"⏱️ **Cooldown:** 6h"
            ),
            color=discord.Color.dark_red(),
        )
        imagem = _imagem(f"{_slug(dados.get('nome', monstro_id))}-luta-url", "monstro-luta-url")
        if imagem:
            embed.set_image(url=imagem)
        await ctx.send(embed=embed)


class CooldownMonstros(commands.Cog):
    """Cooldown de 6h por jogador/monstro e camada visual do combate."""

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
        args = (str(ctx.author.id), str(ctx.guild.id), str(monstro_id))
        cooldown = await luta_db.run_db(luta_db.verificar_cooldown_monstro, *args)
        if cooldown.get("em_cooldown"):
            nome = MONSTROS[monstro_id].get("nome", monstro_id)
            await ctx.send(f"⏳ Você já enfrentou **{nome}**. Tente novamente em **{_formatar_tempo(cooldown.get('segundos_restantes', 0))}**.")
            return False
        reserva = await luta_db.run_db(luta_db.iniciar_cooldown_monstro, *args)
        if not reserva.get("sucesso"):
            nome = MONSTROS[monstro_id].get("nome", monstro_id)
            await ctx.send(f"⏳ Você já enfrentou **{nome}**. Tente novamente em **{_formatar_tempo(reserva.get('segundos_restantes', 0))}**.")
            return False
        fim = reserva.get("fim")
        if fim is not None and luta_db.db is not None:
            agora = datetime.now(timezone.utc)
            fim_forcado = agora + timedelta(hours=COOLDOWN_MONSTRO_HORAS)
            campo = f"Cooldowns_Monstros.{monstro_id}"
            await luta_db.run_db(
                luta_db.db["Jogadores"].update_one,
                {"ID": str(ctx.author.id), "guild_id": str(ctx.guild.id), campo: fim},
                {"$set": {campo: fim_forcado}},
            )
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


def _instalar_formatacao(cog):
    original_resolver = cog._resolver_ataque
    original_mostrar_inicio = cog._mostrar_inicio

    async def anunciar(ctx):
        combate = cog._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return
        ataque = combate.get("ataque_pendente")
        atacante = cog._participante(combate, ataque.get("atacante_id")) if ataque else cog._obter_atacante(combate)
        defensor = cog._participante(combate, ataque.get("defensor_id")) if ataque else cog._obter_defensor(combate)
        if not ataque or not atacante or not defensor:
            return
        linhas = _linhas(combate, atacante, defensor, ataque, 0, "Aguardando defesa", "ataque")
        await ctx.send(embed=_embed(linhas, _imagem_ataque(ataque, atacante), discord.Color.orange()))
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
        if defensor.get("efeitos"):
            efeito = str(defensor["efeitos"][-1].get("nome", "Nenhum")).title()
        elif len(combate.get("historico", [])) > historico_antes and "esquivou" in combate["historico"][-1].lower():
            efeito = "Esquiva"
        await _resultado(ctx, combate, atacante, defensor, ataque, dano, efeito, str(ataque.get("_acao", "ataque")))
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
        ataque["_defesa_tipo"] = acao
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
        ataque["_defesa_tipo"] = escolha
        await resolver(ctx)

    async def mostrar_inicio(ctx):
        combate = cog._obter_combate(ctx.channel.id)
        if not combate:
            return await original_mostrar_inicio(ctx)
        atacante = cog._obter_atacante(combate)
        defensor = cog._obter_defensor(combate)
        if not atacante or not defensor:
            return
        if defensor.get("tipo") == "monstro":
            imagem = _imagem(f"{_slug(defensor.get('nome', 'monstro'))}-luta-url", "monstro-luta-url")
            embed = discord.Embed(
                title=f"🌙 MOON TENSURA • {defensor.get('emoji', '👹')} {defensor.get('nome', 'Monstro')}",
                description=(
                    f"❤️ **Vida:** {int(defensor.get('vida', 0))}\n"
                    f"⚔️ **Dano:** {int(defensor.get('dano_base', 0))}\n"
                    f"🎯 **Alvo:** {atacante.get('nome', 'Jogador')}\n"
                    f"⏱️ **Cooldown:** 6h"
                ),
                color=discord.Color.dark_red(),
            )
            if imagem:
                embed.set_image(url=imagem)
            await ctx.send(embed=embed)
        await anunciar(ctx)

    cog._anunciar_ataque = anunciar
    cog._resolver_ataque = resolver
    cog._defesa_jogador = defesa_jogador
    cog._defesa_monstro = defesa_monstro
    cog._mostrar_inicio = mostrar_inicio


async def setup(bot):
    grupo = bot.get_command("luta")
    if grupo is None:
        raise RuntimeError("O comando !luta não foi encontrado para aplicar as correções.")
    monstros = grupo.get_command("monstros")
    if monstros is not None:
        monstros.callback = _listar_monstros
    pve = grupo.get_command("pve")
    if pve is None:
        raise RuntimeError("O comando !luta pve não foi encontrado para aplicar o cooldown.")
    cog = CooldownMonstros(bot)
    await bot.add_cog(cog)
    pve.add_check(cog._verificar_e_reservar)
    luta = bot.get_cog("Luta")
    if luta is not None:
        _instalar_formatacao(luta)
