"""Comandos públicos de luta.

Cada comando cria o próprio Embed. O motor somente executa a regra e publica
esse Embed; não existe monkeypatch global de Context.send aqui.
"""

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
from .Mensagens_luta import imagem_monstro
from .sistemas_luta import Luta

FOOTER = "Tensura Moon - Korczak Technologies!"


def _embed_erro(titulo: str, descricao: str) -> discord.Embed:
    return discord.Embed(title=f"❌ {titulo}", description=descricao, color=discord.Color.red())


def _vida(p: dict) -> str:
    vida = int(float((p or {}).get("vida", 0) or 0))
    maxima = int(float((p or {}).get("vida_maxima", vida) or vida or 1))
    return f"{max(0, vida)}/{max(1, maxima)}"


def _mana(p: dict) -> str:
    return str(int(float((p or {}).get("mana", 0) or 0)))


def _embed_status(*, titulo: str, atacante: dict, defensor: dict, turno: int, descricao: str, dano: int = 0, mana: int = 0, efeito: str = "Nenhum") -> discord.Embed:
    texto = (
        "╭────────────────────────────────────────────╮\n"
        "│              🌙  MOON TENSURA              │\n"
        "├────────────────────────────────────────────┤\n"
        f"│ ⋮ → 👤 | {atacante.get('nome', 'User')} atacou usando {titulo}\n"
        f"│ ⋮ → ❤️ | Vida de {atacante.get('nome', 'User')}: {_vida(atacante)}\n"
        f"│ ⋮ → 🔷 | Mana de: {_mana(atacante)}\n"
        "├────────────────────────────────────────────┤\n"
        f"│ │ → ⚔️ | Dano: {dano}\n"
        f"│ │ → ✦  | Efeito: {efeito or 'Nenhum'}\n"
        f"│ │ → 🎯 | Alvo: {defensor.get('nome', '-')}\n"
        f"│ │ → 🔄 | Turno: {turno}\n"
        "├ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┄ ┤\n"
        f"│ │ → 👹 | Oponente: {defensor.get('nome', '-')}\n"
        f"│ │ → ❤️ | Vida: {_vida(defensor)}\n"
        "╰────────────────────────────────────────────╯"
    )
    embed = discord.Embed(title="🌙 MOON TENSURA", description=texto, color=discord.Color.blurple())
    embed.add_field(name="📋 Especificação", value=descricao or "Sem descrição.", inline=False)
    embed.set_footer(text=FOOTER)
    return embed


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
        return discord.File(io.BytesIO(dados), filename="monstro.webp")
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
        return None


async def _cog(ctx) -> Optional[Luta]:
    cog = ctx.bot.get_cog("Luta")
    if cog is None:
        await ctx.send(embed=_embed_erro("Combate", "O sistema de combate não foi carregado."))
    return cog


async def luta(ctx):
    await ctx.send(embed=discord.Embed(title="🌙 MOON TENSURA — COMBATE", description="`!luta monstros` — lista os monstros\n`!luta pve <monstro>` — inicia PvE\n`!luta pvp @jogador` — inicia PvP\n\n`!soco` · `!chute` · `!defesa` · `!esquiva` · `!fugir`", color=discord.Color.blurple()))


async def monstros(ctx):
    if not luta_db.MONSTROS:
        await ctx.send(embed=_embed_erro("Monstros", "Nenhum monstro foi carregado."))
        return
    itens = list(luta_db.MONSTROS.items())
    for inicio in range(0, len(itens), 25):
        embed = discord.Embed(title="👹 Monstros Disponíveis", color=discord.Color.dark_red())
        for monstro_id, dados in itens[inicio:inicio + 25]:
            embed.add_field(name=f"{dados.get('emoji', '👹')} {dados.get('nome', monstro_id)}", value=f"ID: `{monstro_id}`\n❤️ Vida: {dados.get('vida_base', 0)}\n⚔️ Dano: {dados.get('dano_base', 0)}\n✨ XP: {dados.get('xp_recompensa', 0)}\n💰 Hunos: {dados.get('hunos_recompensa', 0)}", inline=True)
        await ctx.send(embed=embed)


async def pve(ctx, *, monstro_tipo: str = ""):
    if ctx.guild is None:
        await ctx.send(embed=_embed_erro("PvE", "Este comando só funciona em servidor.")); return
    monstro_tipo = str(monstro_tipo or "").strip()
    if not monstro_tipo:
        await ctx.send(embed=_embed_erro("PvE", "Informe o monstro. Exemplo: `!luta pve slime`")); return
    cog = await _cog(ctx)
    if cog is None: return
    async with cog._lock(ctx.channel.id):
        if cog._combate_ativo(ctx.channel.id):
            await ctx.send(embed=_embed_erro("PvE", "Já existe um combate ativo neste canal.")); return
        monstro_id = cog._encontrar_monstro(monstro_tipo)
        if not monstro_id:
            await ctx.send(embed=_embed_erro("PvE", f"Monstro `{monstro_tipo}` não encontrado. Use `!luta monstros`.")); return
        guild_id = str(ctx.guild.id); user_id = str(ctx.author.id)
        verificacao = await run_db(luta_db.pode_lutar, user_id, guild_id)
        if not verificacao.get("pode"):
            await ctx.send(embed=_embed_erro("PvE", verificacao.get("mensagem", "Você não pode lutar."))); return
        jogador = await _criar_participante(user_id, guild_id)
        if not jogador:
            await ctx.send(embed=_embed_erro("PvE", "Você precisa ter um personagem registrado para lutar.")); return
        jogador["nome"] = jogador.get("nome") or ctx.author.display_name
        reserva = await run_db(luta_db.iniciar_cooldown_monstro, user_id, guild_id, str(monstro_id))
        if not reserva.get("sucesso"):
            segundos = int(reserva.get("segundos_restantes", 0) or 0); horas, resto = divmod(segundos, 3600); minutos = resto // 60
            restante = f"{horas}h {minutos}min" if horas else f"{max(1, minutos)}min"
            nome = luta_db.MONSTROS.get(str(monstro_id), {}).get("nome", str(monstro_id))
            await ctx.send(embed=_embed_erro("PvE", f"Você já lutou contra **{nome}**. Tente novamente em **{restante}**.")); return
        fim_cooldown = reserva.get("fim")
        try:
            monstro = await run_db(luta_db.criar_monstro, str(monstro_id), 1)
            if not monstro: raise RuntimeError("criar_monstro retornou vazio")
            combate = cog._novo_combate([jogador, monstro], guild_id)
            cog.combates[ctx.channel.id] = combate
            await cog._marcar_combate([jogador], guild_id, "ativo_combate")
            atacante = cog._obter_atacante(combate); defensor = cog._obter_defensor(combate)
            dados = luta_db.MONSTROS.get(str(monstro_id), {})
            atributos = dados.get("atributos_base", {})
            atributos_texto = "\n".join(f"**{k}:** {v}" for k, v in atributos.items()) or "Sem atributos cadastrados."
            golpes = ", ".join(str(g) for g in dados.get("golpes", [])) or "Nenhum"
            descricao = (
                "╭────────────────────────────────────────────╮\n"
                "│              🌙  MOON TENSURA              │\n"
                "├────────────────────────────────────────────┤\n"
                f"│ ⋮ → 👤 | Jogador: {atacante.get('nome', ctx.author.display_name)}\n"
                f"│ ⋮ → 👹 | Monstro: {defensor.get('nome', monstro_id)}\n"
                f"│ ⋮ → ❤️ | Vida: {_vida(defensor)}\n"
                f"│ ⋮ → ⚔️ | Dano base: {dados.get('dano_base', 0)}\n"
                f"│ ⋮ → 🎚️ | Nível: {defensor.get('nivel', 1)}\n"
                "├────────────────────────────────────────────┤\n"
                "│ │ → 📊 | ATRIBUTOS DO MONSTRO                │\n"
                f"│ │ → 💪 | Força: {atributos.get('Força', 0)}\n"
                f"│ │ → 🛡️ | Defesa: {atributos.get('Defesa', 0)}\n"
                f"│ │ → ❤️ | Vitalidade: {atributos.get('Vitalidade', 0)}\n"
                f"│ │ → ⚡ | Velocidade: {atributos.get('Velocidade', 0)}\n"
                f"│ │ → 🎯 | Destreza: {atributos.get('Destreza', 0)}\n"
                f"│ │ → ✨ | Magia: {atributos.get('Magia', 0)}\n"
                f"│ │ → 🍀 | Sorte: {atributos.get('Sorte', 0)}\n"
                f"│ │ → 🧠 | Inteligencia: {atributos.get('Inteligencia', 0)}\n"
                "├────────────────────────────────────────────┤\n"
                f"│ │ → 👊 | Golpes: {golpes}\n"
                f"│ │ → ✨ | XP: {dados.get('xp_recompensa', 0)}\n"
                f"│ │ → 💰 | Hunos: {dados.get('hunos_recompensa', 0)}\n"
                f"│ │ → 🔷 | TP: {dados.get('tp_recompensa', 0)}\n"
                f"│ │ → 🔄 | Turno: {combate.get('numero_turno', 1)}\n"
                "╰────────────────────────────────────────────╯"
            )
            panel = discord.Embed(title=f"🌙 MOON TENSURA — {dados.get('emoji', '👹')} {defensor.get('nome', monstro_id)}", description=descricao, color=discord.Color.red())
            panel.add_field(name="📊 Atributos completos", value=atributos_texto, inline=False)
            panel.set_footer(text=FOOTER)
            url = imagem_monstro(monstro)
            arquivo = await _baixar_imagem_monstro(url)
            if arquivo is not None:
                filename = arquivo.filename
                panel.set_image(url=f"attachment://{filename}")
            cog.preparar_embed(ctx, panel, arquivo=arquivo)
            await cog._mostrar_inicio(ctx)
        except Exception:
            if fim_cooldown is not None:
                try: await run_db(luta_db.cancelar_cooldown_monstro, user_id, guild_id, str(monstro_id), fim_cooldown)
                except Exception as erro: print(f"[LUTA][PVE][COOLDOWN][ERRO] {type(erro).__name__}: {erro}")
            cog.combates.pop(ctx.channel.id, None); cog._embeds_acao.pop(ctx.channel.id, None)
            raise


async def pvp(ctx, membro: Optional[discord.Member] = None):
    if ctx.guild is None:
        await ctx.send(embed=_embed_erro("PvP", "Este comando só funciona em servidor.")); return
    if membro is None: membro = next((m for m in ctx.message.mentions if not m.bot and m.id != ctx.author.id), None)
    if membro is None or membro.bot or membro.id == ctx.author.id:
        await ctx.send(embed=_embed_erro("PvP", "Mencione um membro válido. Exemplo: `!luta pvp @jogador`")); return
    cog = await _cog(ctx)
    if cog is None: return
    async with cog._lock(ctx.channel.id):
        if cog._combate_ativo(ctx.channel.id):
            await ctx.send(embed=_embed_erro("PvP", "Já existe um combate ativo neste canal.")); return
        guild_id = str(ctx.guild.id); jogadores = []
        for usuario in (ctx.author, membro):
            verificacao = await run_db(luta_db.pode_lutar, str(usuario.id), guild_id)
            if not verificacao.get("pode"):
                await ctx.send(embed=_embed_erro("PvP", f"{usuario.display_name}: {verificacao.get('mensagem', 'não pode lutar.')}")); return
            jogador = await _criar_participante(usuario.id, guild_id)
            if not jogador:
                await ctx.send(embed=_embed_erro("PvP", f"{usuario.display_name} não possui personagem registrado.")); return
            jogador["nome"] = jogador.get("nome") or usuario.display_name; jogadores.append(jogador)
        combate = cog._novo_combate(jogadores, guild_id, pvp=True); cog.combates[ctx.channel.id] = combate
        await cog._marcar_combate(jogadores, guild_id, "ativo_combate")
        inicio = _embed_status(titulo="⚔️ PvP", atacante=cog._obter_atacante(combate), defensor=cog._obter_defensor(combate), turno=combate.get("numero_turno", 1), descricao="Duelo PvP iniciado.")
        cog.preparar_embed(ctx, inicio); await cog._mostrar_inicio(ctx)


async def soco(ctx):
    cog = await _cog(ctx)
    if cog is None: return
    combate = cog._obter_combate(ctx.channel.id); atacante = cog._obter_atacante(combate) if combate else {"nome": ctx.author.display_name}; defensor = cog._obter_defensor(combate) if combate else {"nome": "-"}; golpe = luta_db.GOLPES["soco"]
    embed = _embed_status(titulo="👊 Soco", atacante=atacante, defensor=defensor, turno=combate.get("numero_turno", 1) if combate else 1, descricao=golpe.get("descricao", "Um soco básico."), dano=int(golpe.get("dano_base", 0)), mana=int(golpe.get("custo_mana", 0)), efeito=golpe.get("efeito", "Nenhum"))
    async with cog._lock(ctx.channel.id): await cog.executar_ataque_jogador(ctx, "soco", embed=embed)


async def chute(ctx):
    cog = await _cog(ctx)
    if cog is None: return
    combate = cog._obter_combate(ctx.channel.id); atacante = cog._obter_atacante(combate) if combate else {"nome": ctx.author.display_name}; defensor = cog._obter_defensor(combate) if combate else {"nome": "-"}; golpe = luta_db.GOLPES["chute"]
    embed = _embed_status(titulo="🦶 Chute", atacante=atacante, defensor=defensor, turno=combate.get("numero_turno", 1) if combate else 1, descricao=golpe.get("descricao", "Um chute poderoso."), dano=int(golpe.get("dano_base", 0)), mana=int(golpe.get("custo_mana", 0)), efeito=golpe.get("efeito", "Nenhum"))
    async with cog._lock(ctx.channel.id): await cog.executar_ataque_jogador(ctx, "chute", embed=embed)


async def defesa(ctx):
    cog = await _cog(ctx)
    if cog is None: return
    combate = cog._obter_combate(ctx.channel.id); atacante = cog._obter_atacante(combate) if combate else {"nome": ctx.author.display_name}; defensor = cog._obter_defensor(combate) if combate else atacante; golpe = luta_db.GOLPES["defesa"]
    embed = _embed_status(titulo="🛡️ Defesa", atacante=defensor, defensor=atacante, turno=combate.get("numero_turno", 1) if combate else 1, descricao=golpe.get("descricao", "Reduz o dano do próximo ataque."), mana=int(golpe.get("custo_mana", 0)), efeito="Redução de dano")
    async with cog._lock(ctx.channel.id): await cog.executar_defesa_jogador(ctx, "defesa", embed=embed)


async def esquiva(ctx):
    cog = await _cog(ctx)
    if cog is None: return
    combate = cog._obter_combate(ctx.channel.id); atacante = cog._obter_atacante(combate) if combate else {"nome": ctx.author.display_name}; defensor = cog._obter_defensor(combate) if combate else atacante; golpe = luta_db.GOLPES["esquiva"]
    embed = _embed_status(titulo="💨 Esquiva", atacante=defensor, defensor=atacante, turno=combate.get("numero_turno", 1) if combate else 1, descricao=golpe.get("descricao", "Tenta desviar do próximo ataque."), mana=int(golpe.get("custo_mana", 0)), efeito="Tentativa de esquiva")
    async with cog._lock(ctx.channel.id): await cog.executar_defesa_jogador(ctx, "esquiva", embed=embed)


async def fugir(ctx):
    cog = await _cog(ctx)
    if cog is None: return
    async with cog._lock(ctx.channel.id):
        combate = cog._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"): await ctx.send(embed=_embed_erro("Fuga", "Você não está em combate.")); return
        jogador = cog._participante(combate, str(ctx.author.id))
        if not jogador or jogador.get("tipo") != "jogador": await ctx.send(embed=_embed_erro("Fuga", "Você não participa deste combate.")); return
        fuga = discord.Embed(title="🌙 MOON TENSURA", description=f"🏃 **{jogador.get('nome')}** tenta fugir do combate.", color=discord.Color.orange())
        if random.random() >= (0.15 if not combate.get("pvp") else 0.10): fuga.description = f"❌ **{jogador.get('nome')}** não conseguiu fugir."; await ctx.send(embed=fuga); return
        combate["ativo"] = False; await cog._salvar(combate); cog.combates.pop(ctx.channel.id, None); fuga.description = f"🏃 **{jogador.get('nome')}** conseguiu fugir!"; await ctx.send(embed=fuga)


async def matar(ctx):
    cog = await _cog(ctx)
    if cog is None: return
    combate = cog._obter_combate(ctx.channel.id); vencedor = cog._participante(combate, combate.get("vencedor_id")) if combate else None
    embed = discord.Embed(title="🌙 MOON TENSURA", description=f"☠️ **{vencedor.get('nome')}** escolheu finalizar o PvP com morte." if vencedor else "☠️ Finalização por morte.", color=discord.Color.dark_red())
    cog.preparar_embed(ctx, embed)
    async with cog._lock(ctx.channel.id): await cog._finalizar_pvp(ctx, "morte")


async def desmaiar(ctx):
    cog = await _cog(ctx)
    if cog is None: return
    combate = cog._obter_combate(ctx.channel.id); vencedor = cog._participante(combate, combate.get("vencedor_id")) if combate else None
    embed = discord.Embed(title="🌙 MOON TENSURA", description=f"💤 **{vencedor.get('nome')}** escolheu finalizar o PvP por desmaio." if vencedor else "💤 Finalização por desmaio.", color=discord.Color.orange())
    cog.preparar_embed(ctx, embed)
    async with cog._lock(ctx.channel.id): await cog._finalizar_pvp(ctx, "desmaio")


def _comando(callback, nome, **kwargs):
    return commands.Command(callback, name=nome, **kwargs)


async def setup(bot):
    cog = bot.get_cog("Luta")
    if cog is None:
        cog = Luta(bot)
        await bot.add_cog(cog)
    for nome in ("luta", "fight", "combate", "soco", "chute", "defesa", "defender", "def", "shield", "block", "bloquear", "bloqueio", "esquiva", "esquivar", "desviar", "dodge", "desvio", "fugir", "fuga", "escape", "escapar", "run", "matar", "desmaiar"):
        bot.remove_command(nome)
    grupo = commands.Group(luta, name="luta", aliases=["fight", "combate"], invoke_without_command=True, help="Sistema de combate.")
    grupo.add_command(_comando(monstros, "monstros", help="Lista os monstros disponíveis."))
    grupo.add_command(_comando(pve, "pve", help="Inicia um combate PvE."))
    grupo.add_command(_comando(pvp, "pvp", help="Inicia um combate PvP."))
    bot.add_command(grupo)
    comandos = ((soco, "soco", {}), (chute, "chute", {}), (defesa, "defesa", {"aliases": ["defender", "def", "shield", "block", "bloquear", "bloqueio"]}), (esquiva, "esquiva", {"aliases": ["esquivar", "desviar", "dodge", "desvio"]}), (fugir, "fugir", {"aliases": ["fuga", "escape", "escapar", "run"]}), (matar, "matar", {}), (desmaiar, "desmaiar", {}))
    for callback, nome, opcoes in comandos:
        bot.add_command(_comando(callback, nome, **opcoes))
    comando_luta = bot.get_command("luta")
    print("[LUTA][REGISTRO]", f"luta={bool(comando_luta)}", f"monstros={bool(comando_luta and comando_luta.get_command('monstros'))}", f"pve={bool(comando_luta and comando_luta.get_command('pve'))}", "arquitetura=embed-no-comando")
