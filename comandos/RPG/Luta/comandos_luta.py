"""Comandos públicos de luta.

Regra desta camada: cada comando monta o próprio ``discord.Embed``. O motor
recebe esse Embed e apenas executa a ação/turno. Não existe monkeypatch global
de ``Context.send`` neste módulo.
"""

from __future__ import annotations

import random
from typing import Optional

import discord
from discord.ext import commands

from database.python.mongodb import run_db
from database.python import luta as luta_db
from ..luta import _criar_participante
from .sistemas_luta import Luta


def _embed_erro(titulo: str, descricao: str) -> discord.Embed:
    return discord.Embed(title=f"❌ {titulo}", description=descricao, color=discord.Color.red())


def _embed_status(*, titulo: str, atacante: dict, defensor: dict, turno: int, descricao: str, dano: int = 0, mana: int = 0, efeito: str = "Nenhum") -> discord.Embed:
    embed = discord.Embed(title=titulo, description=descricao, color=discord.Color.blurple())
    embed.add_field(name="👤 Atacante", value=atacante.get("nome", "User"), inline=True)
    embed.add_field(name="🎯 Alvo", value=defensor.get("nome", "-"), inline=True)
    embed.add_field(name="⚔️ Dano", value=str(dano), inline=True)
    embed.add_field(name="🔷 Mana", value=str(mana), inline=True)
    embed.add_field(name="✦ Efeito", value=efeito or "Nenhum", inline=True)
    embed.add_field(name="🔄 Turno", value=str(turno), inline=True)
    return embed


async def _cog(ctx) -> Optional[Luta]:
    cog = ctx.bot.get_cog("Luta")
    if cog is None:
        await ctx.send(embed=_embed_erro("Combate", "O sistema de combate não foi carregado."))
    return cog


async def luta(ctx):
    await ctx.send(embed=discord.Embed(
        title="🌙 MOON TENSURA — COMBATE",
        description=(
            "`!luta monstros` — lista os monstros\n"
            "`!luta pve <monstro>` — inicia PvE\n"
            "`!luta pvp @jogador` — inicia PvP\n\n"
            "`!soco` · `!chute` · `!defesa` · `!esquiva` · `!fugir`"
        ),
        color=discord.Color.blurple(),
    ))


async def monstros(ctx):
    if not luta_db.MONSTROS:
        await ctx.send(embed=_embed_erro("Monstros", "Nenhum monstro foi carregado."))
        return
    itens = list(luta_db.MONSTROS.items())
    for inicio in range(0, len(itens), 25):
        embed = discord.Embed(title="👹 Monstros Disponíveis", color=discord.Color.dark_red())
        for monstro_id, dados in itens[inicio:inicio + 25]:
            embed.add_field(
                name=f"{dados.get('emoji', '👹')} {dados.get('nome', monstro_id)}",
                value=(
                    f"ID: `{monstro_id}`\n"
                    f"❤️ Vida: {dados.get('vida_base', 0)}\n"
                    f"⚔️ Dano: {dados.get('dano_base', 0)}\n"
                    f"✨ XP: {dados.get('xp_recompensa', 0)}\n"
                    f"💰 Hunos: {dados.get('hunos_recompensa', 0)}"
                ),
                inline=True,
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

        guild_id = str(ctx.guild.id)
        user_id = str(ctx.author.id)
        verificacao = await run_db(luta_db.pode_lutar, user_id, guild_id)
        if not verificacao.get("pode"):
            await ctx.send(embed=_embed_erro("PvE", verificacao.get("mensagem", "Você não pode lutar.")))
            return

        jogador = await _criar_participante(user_id, guild_id)
        if not jogador:
            await ctx.send(embed=_embed_erro("PvE", "Você precisa ter um personagem registrado para lutar."))
            return
        jogador["nome"] = jogador.get("nome") or ctx.author.display_name

        reserva = await run_db(luta_db.iniciar_cooldown_monstro, user_id, guild_id, str(monstro_id))
        if not reserva.get("sucesso"):
            segundos = int(reserva.get("segundos_restantes", 0) or 0)
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
            inicio = discord.Embed(
                title="🌙 MOON TENSURA — PvE",
                description=f"⚔️ **{atacante.get('nome')}** iniciou um combate contra **{defensor.get('nome')}**.",
                color=discord.Color.red(),
            )
            inicio.add_field(name="👤 Jogador", value=atacante.get("nome", "User"), inline=True)
            inicio.add_field(name="👹 Oponente", value=defensor.get("nome", "-"), inline=True)
            inicio.add_field(name="❤️ Vida", value=f"{int(jogador.get('vida', 0))}/{int(jogador.get('vida_maxima', jogador.get('vida', 0)) or 1)}", inline=True)
            inicio.add_field(name="🔷 Mana", value=str(int(jogador.get("mana", 0) or 0)), inline=True)
            inicio.add_field(name="🔄 Turno", value=str(combate.get("numero_turno", 1)), inline=True)
            inicio.set_footer(text="Tensura Moon - Korczak Technologies!")
            cog.preparar_embed(ctx, inicio)
            await cog._mostrar_inicio(ctx)
        except Exception:
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
    if membro is None:
        await ctx.send(embed=_embed_erro("PvP", "Mencione um membro válido. Exemplo: `!luta pvp @jogador`"))
        return
    if membro.bot or membro.id == ctx.author.id:
        await ctx.send(embed=_embed_erro("PvP", "Alvo inválido para PvP."))
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
                await ctx.send(embed=_embed_erro("PvP", f"{usuario.display_name}: {verificacao.get('mensagem', 'não pode lutar.')}"))
                return
            jogador = await _criar_participante(usuario.id, guild_id)
            if not jogador:
                await ctx.send(embed=_embed_erro("PvP", f"{usuario.display_name} não possui personagem registrado."))
                return
            jogador["nome"] = jogador.get("nome") or usuario.display_name
            jogadores.append(jogador)

        combate = cog._novo_combate(jogadores, guild_id, pvp=True)
        cog.combates[ctx.channel.id] = combate
        await cog._marcar_combate(jogadores, guild_id, "ativo_combate")
        atacante = cog._obter_atacante(combate)
        defensor = cog._obter_defensor(combate)
        inicio = discord.Embed(
            title="🌙 MOON TENSURA — PvP",
            description=f"⚔️ **{atacante.get('nome')}** inicia o duelo contra **{defensor.get('nome')}**.",
            color=discord.Color.red(),
        )
        inicio.add_field(name="👤 Atacante", value=atacante.get("nome", "-"), inline=True)
        inicio.add_field(name="🎯 Alvo", value=defensor.get("nome", "-"), inline=True)
        inicio.add_field(name="🔄 Turno", value=str(combate.get("numero_turno", 1)), inline=True)
        cog.preparar_embed(ctx, inicio)
        await cog._mostrar_inicio(ctx)


async def soco(ctx):
    cog = await _cog(ctx)
    if cog is None:
        return
    combate = cog._obter_combate(ctx.channel.id)
    atacante = cog._obter_atacante(combate) if combate else {"nome": ctx.author.display_name, "vida": 0, "mana": 0}
    defensor = cog._obter_defensor(combate) if combate else {"nome": "-"}
    golpe = luta_db.GOLPES["soco"]
    soco = _embed_status(
        titulo="👊 Soco",
        atacante=atacante,
        defensor=defensor or {"nome": "-"},
        turno=combate.get("numero_turno", 1) if combate else 1,
        descricao=golpe.get("descricao", "Um soco básico."),
        dano=int(golpe.get("dano_base", 0)),
        mana=int(golpe.get("custo_mana", 0)),
        efeito=golpe.get("efeito", "Nenhum"),
    )
    async with cog._lock(ctx.channel.id):
        await cog.executar_ataque_jogador(ctx, "soco", embed=soco)


async def chute(ctx):
    cog = await _cog(ctx)
    if cog is None:
        return
    combate = cog._obter_combate(ctx.channel.id)
    atacante = cog._obter_atacante(combate) if combate else {"nome": ctx.author.display_name, "vida": 0, "mana": 0}
    defensor = cog._obter_defensor(combate) if combate else {"nome": "-"}
    golpe = luta_db.GOLPES["chute"]
    chute = _embed_status(
        titulo="🦶 Chute",
        atacante=atacante,
        defensor=defensor or {"nome": "-"},
        turno=combate.get("numero_turno", 1) if combate else 1,
        descricao=golpe.get("descricao", "Um chute poderoso."),
        dano=int(golpe.get("dano_base", 0)),
        mana=int(golpe.get("custo_mana", 0)),
        efeito=golpe.get("efeito", "Nenhum"),
    )
    async with cog._lock(ctx.channel.id):
        await cog.executar_ataque_jogador(ctx, "chute", embed=chute)


async def defesa(ctx):
    cog = await _cog(ctx)
    if cog is None:
        return
    combate = cog._obter_combate(ctx.channel.id)
    atacante = cog._obter_atacante(combate) if combate else {"nome": ctx.author.display_name, "vida": 0, "mana": 0}
    defensor = cog._obter_defensor(combate) if combate else {"nome": ctx.author.display_name}
    golpe = luta_db.GOLPES["defesa"]
    defesa = _embed_status(
        titulo="🛡️ Defesa",
        atacante=defensor or atacante,
        defensor=atacante,
        turno=combate.get("numero_turno", 1) if combate else 1,
        descricao=golpe.get("descricao", "Reduz o dano do próximo ataque."),
        dano=0,
        mana=int(golpe.get("custo_mana", 0)),
        efeito="Redução de dano",
    )
    async with cog._lock(ctx.channel.id):
        await cog.executar_defesa_jogador(ctx, "defesa", embed=defesa)


async def esquiva(ctx):
    cog = await _cog(ctx)
    if cog is None:
        return
    combate = cog._obter_combate(ctx.channel.id)
    atacante = cog._obter_atacante(combate) if combate else {"nome": ctx.author.display_name, "vida": 0, "mana": 0}
    defensor = cog._obter_defensor(combate) if combate else {"nome": ctx.author.display_name}
    golpe = luta_db.GOLPES["esquiva"]
    esquiva = _embed_status(
        titulo="💨 Esquiva",
        atacante=defensor or atacante,
        defensor=atacante,
        turno=combate.get("numero_turno", 1) if combate else 1,
        descricao=golpe.get("descricao", "Tenta desviar do próximo ataque."),
        dano=0,
        mana=int(golpe.get("custo_mana", 0)),
        efeito="Tentativa de esquiva",
    )
    async with cog._lock(ctx.channel.id):
        await cog.executar_defesa_jogador(ctx, "esquiva", embed=esquiva)


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
        fuga = discord.Embed(title="🏃 Fuga", description="Tentando escapar do combate...", color=discord.Color.orange())
        if random.random() >= (0.15 if not combate.get("pvp") else 0.10):
            fuga.description = f"❌ **{jogador.get('nome')}** não conseguiu fugir."
            await ctx.send(embed=fuga)
            return
        combate["ativo"] = False
        await cog._salvar(combate)
        cog.combates.pop(ctx.channel.id, None)
        fuga.description = f"🏃 **{jogador.get('nome')}** conseguiu fugir!"
        await ctx.send(embed=fuga)


async def matar(ctx):
    cog = await _cog(ctx)
    if cog is None:
        return
    combate = cog._obter_combate(ctx.channel.id)
    vencedor = cog._participante(combate, combate.get("vencedor_id")) if combate else None
    matar = discord.Embed(
        title="☠️ Matar",
        description=f"**{vencedor.get('nome')}** escolheu finalizar o PvP com morte." if vencedor else "Finalização por morte.",
        color=discord.Color.dark_red(),
    )
    async with cog._lock(ctx.channel.id):
        await cog._finalizar_pvp(ctx, "morte")


async def desmaiar(ctx):
    cog = await _cog(ctx)
    if cog is None:
        return
    combate = cog._obter_combate(ctx.channel.id)
    vencedor = cog._participante(combate, combate.get("vencedor_id")) if combate else None
    desmaiar = discord.Embed(
        title="💤 Desmaiar",
        description=f"**{vencedor.get('nome')}** escolheu finalizar o PvP por desmaio." if vencedor else "Finalização por desmaio.",
        color=discord.Color.orange(),
    )
    # O embed é preparado antes da finalização para que o sistema o publique.
    if cog is not None:
        cog.preparar_embed(ctx, desmaiar)
    async with cog._lock(ctx.channel.id):
        await cog._finalizar_pvp(ctx, "desmaio")


def _comando(callback, nome, **kwargs):
    return commands.Command(callback, name=nome, **kwargs)


async def setup(bot):
    """Registra somente os comandos desta camada e um único motor Luta."""
    cog = bot.get_cog("Luta")
    if cog is None:
        cog = Luta(bot)
        await bot.add_cog(cog)

    for nome in (
        "luta", "fight", "combate", "soco", "chute", "defesa", "defender",
        "def", "shield", "block", "bloquear", "bloqueio", "esquiva", "esquivar",
        "desviar", "dodge", "desvio", "fugir", "fuga", "escape", "escapar", "run",
        "matar", "desmaiar",
    ):
        bot.remove_command(nome)

    grupo = commands.Group(
        luta,
        name="luta",
        aliases=["fight", "combate"],
        invoke_without_command=True,
        help="Sistema de combate.",
    )
    grupo.add_command(_comando(monstros, "monstros", help="Lista os monstros disponíveis."))
    grupo.add_command(_comando(pve, "pve", help="Inicia um combate PvE."))
    grupo.add_command(_comando(pvp, "pvp", help="Inicia um combate PvP."))
    bot.add_command(grupo)

    comandos = (
        (soco, "soco", {}),
        (chute, "chute", {}),
        (defesa, "defesa", {"aliases": ["defender", "def", "shield", "block", "bloquear", "bloqueio"]}),
        (esquiva, "esquiva", {"aliases": ["esquivar", "desviar", "dodge", "desvio"]}),
        (fugir, "fugir", {"aliases": ["fuga", "escape", "escapar", "run"]}),
        (matar, "matar", {}),
        (desmaiar, "desmaiar", {}),
    )
    for callback, nome, opcoes in comandos:
        bot.add_command(_comando(callback, nome, **opcoes))

    comando_luta = bot.get_command("luta")
    print(
        "[LUTA][REGISTRO]",
        f"luta={bool(comando_luta)}",
        f"monstros={bool(comando_luta and comando_luta.get_command('monstros'))}",
        f"pve={bool(comando_luta and comando_luta.get_command('pve'))}",
        "arquitetura=embed-no-comando",
    )
