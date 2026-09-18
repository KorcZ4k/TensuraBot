"""Comandos públicos do sistema de luta com interface Moon Tensura padronizada."""

from __future__ import annotations

import asyncio
import io
import random
from typing import Optional

import aiohttp
import discord
from discord.ext import commands

from database.python.mongodb import run_db
from database.python import luta as luta_db
from ..luta import _criar_participante
from .Mensagens_luta import imagem_monstro, painel
from .hardening_final import Luta

FOOTER = "Tensura Moon - Korczak Technologies!"


def _vida(p):
    p = p or {}
    try:
        vida = int(float(p.get("vida", 0) or 0))
        maxima = int(float(p.get("vida_maxima", vida) or vida or 1))
    except (TypeError, ValueError):
        vida, maxima = 0, 1
    return f"{max(0, vida)}/{max(1, maxima)}"


def _mana(p):
    try:
        return str(int(float((p or {}).get("mana", 0) or 0)))
    except (TypeError, ValueError):
        return "0"


def _valor_int(v, padrao=0):
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return int(padrao)


def _efeito_texto(efeito):
    if isinstance(efeito, dict):
        return str(efeito.get("nome", efeito.get("tipo", "Nenhum")) or "Nenhum")
    return str(efeito or "Nenhum")


def _embed_erro(titulo: str, descricao: str) -> discord.Embed:
    return painel(ataque="resultado", efeito="Erro", alvo="-", turno="-", oponente="-", extra=f"**❌ {titulo}:** {descricao}", cor=discord.Color.red())


def _embed_acao(titulo, atacante, defensor, turno, *, dano=0, mana=0, efeito="Nenhum", extra="", cor=None):
    return painel(
        atacante=atacante.get("nome", "User"), ataque=titulo, vida=_vida(atacante), mana=mana,
        dano=dano, efeito=efeito, alvo=defensor.get("nome", "-"), turno=turno,
        oponente=defensor, vida_oponente=_vida(defensor), extra=extra, cor=cor or discord.Color.blurple(),
    )


async def _baixar_imagem_monstro(url):
    if not url:
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as sessao:
            async with sessao.get(url) as resposta:
                if resposta.status != 200:
                    return None
                dados = await resposta.read()
                if not dados:
                    return None
        return discord.File(io.BytesIO(dados), filename="monstro.webp")
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError):
        return None


def _kwargs_embed(embed, arquivo=None):
    kwargs = {"embed": embed}
    if arquivo is not None:
        kwargs["file"] = arquivo
    return kwargs


async def _cog(ctx) -> Optional[Luta]:
    cog = ctx.bot.get_cog("Luta")
    if cog is None:
        await ctx.send(embed=_embed_erro("Combate", "O sistema de combate não foi carregado."))
    return cog


async def luta(ctx):
    embed = painel(
        atacante=ctx.author.display_name, ataque="Comandos", vida="-", mana="-", dano="-", efeito="Ajuda",
        alvo="-", turno="-", oponente="-", vida_oponente="-",
        extra=("**`!luta monstros`** — lista os monstros\n"
               "**`!luta pve <monstro>`** — inicia PvE\n"
               "**`!luta pvp @jogador`** — inicia PvP\n"
               "**`!soco` · `!chute` · `!defesa` · `!esquiva` · `!fugir`**"),
        cor=discord.Color.blurple(),
    )
    await ctx.send(embed=embed)


async def monstros(ctx):
    if not luta_db.MONSTROS:
        await ctx.send(embed=_embed_erro("Monstros", "Nenhum monstro foi carregado."))
        return
    itens = list(luta_db.MONSTROS.items())
    for inicio in range(0, len(itens), 10):
        linhas = []
        for monstro_id, dados in itens[inicio:inicio + 10]:
            linhas.append(
                f"**{dados.get('emoji', '👹')} {dados.get('nome', monstro_id)}** — "
                f"**ID:** `{monstro_id}` | **❤️ Vida:** {dados.get('vida_base', 0)} | "
                f"**⚔️ Dano:** {dados.get('dano_base', 0)} | **✨ XP:** {dados.get('xp_recompensa', 0)} | "
                f"**💰 Hunos:** {dados.get('hunos_recompensa', 0)} | **🔷 TP:** {dados.get('tp_recompensa', 0)}"
            )
        embed = painel(
            atacante=ctx.author.display_name, ataque="Lista de monstros", vida="-", mana="-", dano="-",
            efeito="Consulta", alvo="Todos", turno="-", oponente="Monstros", vida_oponente="-",
            extra="\n".join(linhas), cor=discord.Color.dark_red(),
        )
        await ctx.send(embed=embed)


async def pve(ctx, *, monstro_tipo: str = ""):
    if ctx.guild is None:
        await ctx.send(embed=_embed_erro("PvE", "Este comando só funciona em servidor."))
        return
    monstro_tipo = str(monstro_tipo or "").strip()
    if not monstro_tipo:
        await ctx.send(embed=_embed_erro("PvE", "Informe o monstro. Exemplo: `!luta pve slime`"))
        return
    cog = await _cog(ctx)
    if cog is None:
        return
    async with cog._lock(ctx.channel.id):
        if cog._combate_ativo(ctx.channel.id):
            await ctx.send(embed=_embed_erro("PvE", "Já existe um combate ativo neste canal."))
            return
        monstro_id = cog._encontrar_monstro(monstro_tipo)
        if not monstro_id:
            await ctx.send(embed=_embed_erro("PvE", f"Monstro `{monstro_tipo}` não encontrado. Use `!luta monstros`."))
            return
        guild_id, user_id = str(ctx.guild.id), str(ctx.author.id)
        verificacao = await run_db(luta_db.pode_lutar, user_id, guild_id)
        if not verificacao.get("pode"):
            await ctx.send(embed=_embed_erro("PvE", verificacao.get("mensagem", "Você não pode lutar.")))
            return
        jogador = await _criar_participante(user_id, guild_id)
        if not jogador:
            await ctx.send(embed=_embed_erro("PvE", "Você precisa ter um personagem registrado para lutar."))
            return
        jogador["nome"] = ctx.author.display_name
        reserva = await run_db(luta_db.iniciar_cooldown_monstro, user_id, guild_id, str(monstro_id))
        if not reserva.get("sucesso"):
            segundos = max(0, _valor_int(reserva.get("segundos_restantes")))
            horas, resto = divmod(segundos, 3600)
            minutos = resto // 60
            restante = f"{horas}h {minutos}min" if horas else f"{max(1, minutos)}min"
            nome = luta_db.MONSTROS.get(str(monstro_id), {}).get("nome", str(monstro_id))
            await ctx.send(embed=_embed_erro("PvE", f"Você já lutou contra **{nome}**. Tente novamente em **{restante}**."))
            return
        fim_cooldown = reserva.get("fim")
        try:
            monstro = await run_db(luta_db.criar_monstro, str(monstro_id), 1)
            if not monstro:
                raise RuntimeError("criar_monstro retornou vazio")
            combate = cog._novo_combate([jogador, monstro], guild_id)
            cog.combates[ctx.channel.id] = combate
            await cog._marcar_combate([jogador], guild_id, "ativo_combate")
            atacante = cog._obter_atacante(combate)
            defensor = cog._obter_defensor(combate)
            if not atacante or not defensor:
                raise RuntimeError("combate criado sem atacante ou defensor")
            dados = luta_db.MONSTROS.get(str(monstro_id), {})
            atributos = dados.get("atributos_base", {}) or {}
            linhas = [
                f"**👤 Jogador:** {ctx.author.display_name}", f"**👹 Monstro:** {defensor.get('nome', monstro_id)}",
                f"**❤️ Vida:** {_vida(defensor)}", f"**⚔️ Dano base:** {dados.get('dano_base', 0)}",
                f"**🎚️ Nível:** {defensor.get('nivel', 1)}", "", "**📊 ATRIBUTOS DO MONSTRO**",
                f"**💪 Força:** {atributos.get('Força', 0)}", f"**🛡️ Defesa:** {atributos.get('Defesa', 0)}",
                f"**❤️ Vitalidade:** {atributos.get('Vitalidade', 0)}", f"**⚡ Velocidade:** {atributos.get('Velocidade', 0)}",
                f"**🎯 Destreza:** {atributos.get('Destreza', 0)}", f"**✨ Magia:** {atributos.get('Magia', 0)}",
                f"**🍀 Sorte:** {atributos.get('Sorte', 0)}", f"**🧠 Inteligência:** {atributos.get('Inteligencia', atributos.get('Inteligência', 0))}", "",
                f"**👊 Golpes:** {', '.join(str(g) for g in dados.get('golpes', [])) or 'Nenhum'}",
                f"**✨ XP:** {dados.get('xp_recompensa', 0)} | **💰 Hunos:** {dados.get('hunos_recompensa', 0)} | **🔷 TP:** {dados.get('tp_recompensa', 0)}",
            ]
            panel = painel(
                atacante=ctx.author.display_name, ataque="Apresentação do monstro", vida=_vida(atacante), mana=_mana(atacante),
                dano=dados.get("dano_base", 0), efeito="Apresentação", alvo=defensor.get("nome", monstro_id),
                turno=combate.get("numero_turno", 1), oponente=defensor, vida_oponente=_vida(defensor),
                extra="\n".join(linhas), cor=discord.Color.red(),
            )
            url = imagem_monstro(monstro)
            arquivo = await _baixar_imagem_monstro(url)
            if arquivo is not None:
                filename = arquivo.filename
                panel.set_image(url=f"attachment://{filename}")
            elif url:
                panel.set_image(url=url)
            cog.preparar_embed(ctx, panel, arquivo=arquivo)
            await cog._mostrar_inicio(ctx)
        except Exception:
            try:
                if "combate" in locals():
                    await cog._marcar_combate([jogador], guild_id, "ativo")
            except Exception as erro_estado:
                print("[LUTA][PVE][ROLLBACK][ERRO]", type(erro_estado).__name__, erro_estado)
            if fim_cooldown is not None:
                try:
                    await run_db(luta_db.cancelar_cooldown_monstro, user_id, guild_id, str(monstro_id), fim_cooldown)
                except Exception as erro:
                    print(f"[LUTA][PVE][COOLDOWN][ERRO] {type(erro).__name__}: {erro}")
            cog.combates.pop(ctx.channel.id, None)
            cog._embeds_acao.pop(ctx.channel.id, None)
            raise


async def pvp(ctx, membro: Optional[discord.Member] = None):
    if ctx.guild is None:
        await ctx.send(embed=_embed_erro("PvP", "Este comando só funciona em servidor."))
        return
    if membro is None:
        membro = next((m for m in ctx.message.mentions if not m.bot and m.id != ctx.author.id), None)
    if membro is None or membro.bot or membro.id == ctx.author.id:
        await ctx.send(embed=_embed_erro("PvP", "Mencione um membro válido. Exemplo: `!luta pvp @jogador`"))
        return
    cog = await _cog(ctx)
    if cog is None:
        return
    async with cog._lock(ctx.channel.id):
        if cog._combate_ativo(ctx.channel.id):
            await ctx.send(embed=_embed_erro("PvP", "Já existe um combate ativo neste canal."))
            return
        guild_id = str(ctx.guild.id)
        jogadores = []
        for usuario in (ctx.author, membro):
            verificacao = await run_db(luta_db.pode_lutar, str(usuario.id), guild_id)
            if not verificacao.get("pode"):
                await ctx.send(embed=_embed_erro("PvP", f"{usuario.display_name}: {verificacao.get('mensagem', 'não pode lutar.') }"))
                return
            jogador = await _criar_participante(usuario.id, guild_id)
            if not jogador:
                await ctx.send(embed=_embed_erro("PvP", f"{usuario.display_name} não possui personagem registrado."))
                return
            jogador["nome"] = usuario.display_name
            jogadores.append(jogador)
        combate = cog._novo_combate(jogadores, guild_id, pvp=True)
        cog.combates[ctx.channel.id] = combate
        try:
            await cog._marcar_combate(jogadores, guild_id, "ativo_combate")
        except Exception:
            cog.combates.pop(ctx.channel.id, None)
            await cog._marcar_combate(jogadores, guild_id, "ativo")
            raise
        atacante = cog._obter_atacante(combate)
        defensor = cog._obter_defensor(combate)
        if not atacante or not defensor:
            cog.combates.pop(ctx.channel.id, None)
            await cog._marcar_combate(jogadores, guild_id, "ativo")
            await ctx.send(embed=_embed_erro("PvP", "Não foi possível montar os participantes do combate."))
            return
        embed = _embed_acao("⚔️ PvP", atacante, defensor, combate.get("numero_turno", 1), extra="**Duelo PvP iniciado.**", cor=discord.Color.red())
        cog.preparar_embed(ctx, embed)
        await cog._mostrar_inicio(ctx)


async def _ataque(ctx, chave, titulo):
    cog = await _cog(ctx)
    if cog is None:
        return
    async with cog._lock(ctx.channel.id):
        combate = cog._obter_combate(ctx.channel.id)
        atacante = cog._obter_atacante(combate) if combate else {"nome": ctx.author.display_name}
        defensor = cog._obter_defensor(combate) if combate else {"nome": "-"}
        golpe = luta_db.GOLPES.get(chave, {})
        embed = _embed_acao(
            titulo, atacante, defensor, combate.get("numero_turno", 1) if combate else 1,
            dano=_valor_int(golpe.get("dano_base")), mana=_valor_int(golpe.get("custo_mana")),
            efeito=_efeito_texto(golpe.get("efeito")), extra=golpe.get("descricao", "Ação de combate."),
        )
        await cog.executar_ataque_jogador(ctx, chave, embed=embed)


async def soco(ctx):
    await _ataque(ctx, "soco", "👊 Soco")


async def chute(ctx):
    await _ataque(ctx, "chute", "🦶 Chute")


async def defesa(ctx):
    async with cog._lock(ctx.channel.id):
        combate = cog._obter_combate(ctx.channel.id)
        atacante = cog._obter_atacante(combate) if combate else {"nome": ctx.author.display_name}
        defensor = cog._obter_defensor(combate) if combate else atacante
        golpe = luta_db.GOLPES.get("defesa", {})
        embed = _embed_acao("🛡️ Defesa", defensor, atacante, combate.get("numero_turno", 1) if combate else 1, mana=_valor_int(golpe.get("custo_mana")), efeito="Redução de dano", extra=golpe.get("descricao", "Reduz o dano do próximo ataque."))
        await cog.executar_defesa_jogador(ctx, "defesa", embed=embed)



async def esquiva(ctx):
    async with cog._lock(ctx.channel.id):
        combate = cog._obter_combate(ctx.channel.id)
        atacante = cog._obter_atacante(combate) if combate else {"nome": ctx.author.display_name}
        defensor = cog._obter_defensor(combate) if combate else atacante
        golpe = luta_db.GOLPES.get("esquiva", {})
        embed = _embed_acao("💨 Esquiva", defensor, atacante, combate.get("numero_turno", 1) if combate else 1, mana=_valor_int(golpe.get("custo_mana")), efeito="Tentativa de esquiva", extra=golpe.get("descricao", "Tenta desviar do próximo ataque."))
        await cog.executar_defesa_jogador(ctx, "esquiva", embed=embed)



async def fugir(ctx):
    cog = await _cog(ctx)
    if cog is None:
        return
    async with cog._lock(ctx.channel.id):
        combate = cog._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            await ctx.send(embed=_embed_erro("Fuga", "Você não está em combate."))
            return
        jogador = cog._participante(combate, str(ctx.author.id))
        if not jogador or jogador.get("tipo") != "jogador":
            await ctx.send(embed=_embed_erro("Fuga", "Você não participa deste combate."))
            return
        sucesso = random.random() < (0.15 if not combate.get("pvp") else 0.10)
        embed = painel(
            atacante=ctx.author.display_name, ataque="resultado", vida=_vida(jogador), mana=_mana(jogador), dano="-",
            efeito="Fuga", alvo="Combate", turno=combate.get("numero_turno", 1), oponente="-", vida_oponente="-",
            extra=f"**{'🏃 Fuga realizada com sucesso!' if sucesso else '❌ Não conseguiu fugir do combate.'}**",
            cor=discord.Color.green() if sucesso else discord.Color.orange(),
        )
        if not sucesso:
            await ctx.send(embed=embed)
            return
        combate["ativo"] = False
        combate["fase"] = "finalizado"
        await cog._salvar(combate)
        await cog._marcar_combate([p for p in combate.get("participantes", []) if p.get("tipo") == "jogador"], guild_id=str(combate.get("guild_id")), situacao="ativo")
        cog.combates.pop(ctx.channel.id, None)
        cog._embeds_acao.pop(ctx.channel.id, None)
        if combate.get("ui_message") is not None:
            cog._ui_views.pop(combate["ui_message"].id, None)
        await ctx.send(embed=embed)


async def matar(ctx):
    cog = await _cog(ctx)
    if cog is None:
        return
    combate = cog._obter_combate(ctx.channel.id)
    vencedor = cog._participante(combate, combate.get("vencedor_id")) if combate else None
    embed = painel(atacante=ctx.author.display_name, ataque="resultado", vida=_vida(vencedor), mana=_mana(vencedor), dano="-", efeito="Finalização", alvo="-", turno="fim", oponente="Combate encerrado", vida_oponente="-", extra=f"**☠️ {vencedor.get('nome')} escolheu finalizar o PvP com morte.**" if vencedor else "**☠️ Finalização por morte.**", cor=discord.Color.dark_red())
    async with cog._lock(ctx.channel.id):
        cog.preparar_embed(ctx, embed)
        await cog._finalizar_pvp(ctx, "morte")


async def desmaiar(ctx):
    cog = await _cog(ctx)
    if cog is None:
        return
    combate = cog._obter_combate(ctx.channel.id)
    vencedor = cog._participante(combate, combate.get("vencedor_id")) if combate else None
    embed = painel(atacante=ctx.author.display_name, ataque="resultado", vida=_vida(vencedor), mana=_mana(vencedor), dano="-", efeito="Finalização", alvo="-", turno="fim", oponente="Combate encerrado", vida_oponente="-", extra=f"**💤 {vencedor.get('nome')} escolheu finalizar o PvP por desmaio.**" if vencedor else "**💤 Finalização por desmaio.**", cor=discord.Color.orange())
    async with cog._lock(ctx.channel.id):
        cog.preparar_embed(ctx, embed)
        await cog._finalizar_pvp(ctx, "desmaio")


def _comando(callback, nome, **kwargs):
    return commands.Command(callback, name=nome, **kwargs)


async def setup(bot):
    cog = bot.get_cog("Luta")
    if cog is None:
        cog = Luta(bot)
        await bot.add_cog(cog)
    for nome in (
        "luta", "fight", "combate", "soco", "chute", "defesa", "defender", "def", "shield", "block", "bloquear", "bloqueio",
        "esquiva", "esquivar", "desviar", "dodge", "desvio", "fugir", "fuga", "escape", "escapar", "run", "matar", "desmaiar",
    ):
        bot.remove_command(nome)
    grupo = commands.Group(luta, name="luta", aliases=["fight", "combate"], invoke_without_command=True, help="Sistema de combate.")
    grupo.add_command(_comando(monstros, "monstros", help="Lista os monstros disponíveis."))
    grupo.add_command(_comando(pve, "pve", help="Inicia um combate PvE."))
    grupo.add_command(_comando(pvp, "pvp", help="Inicia um combate PvP."))
    bot.add_command(grupo)
    comandos = (
        (soco, "soco", {}), (chute, "chute", {}),
        (defesa, "defesa", {"aliases": ["defender", "def", "shield", "block", "bloquear", "bloqueio"]}),
        (esquiva, "esquiva", {"aliases": ["esquivar", "desviar", "dodge", "desvio"]}),
        (fugir, "fugir", {"aliases": ["fuga", "escape", "escapar", "run"]}),
        (matar, "matar", {}), (desmaiar, "desmaiar", {}),
    )
    for callback, nome, opcoes in comandos:
        bot.add_command(_comando(callback, nome, **opcoes))
    comando_luta = bot.get_command("luta")
    print("[LUTA][REGISTRO]", f"luta={bool(comando_luta)}", f"monstros={bool(comando_luta and comando_luta.get_command('monstros'))}", f"pve={bool(comando_luta and comando_luta.get_command('pve'))}", "arquitetura=embed-no-comando")
