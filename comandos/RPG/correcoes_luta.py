"""Camada de comandos do sistema de luta.

O motor de combate continua no Cog ``Luta``, mas NENHUM comando publico e
registrado como metodo de Cog. O discord.py injeta ``self`` em callbacks de
Cog e isso foi a origem dos erros intermitentes de ``ctx`` ausente.

Aqui o Cog funciona apenas como servico/estado. Todos os comandos sao
callbacks de modulo e recebem exatamente ``ctx`` do discord.py.
"""

import random
from typing import Optional

import discord
from discord.ext import commands

from database.python import luta as luta_db
from database.python.mongodb import run_db
from comandos.RPG import luta as luta_mod


async def _cog(ctx):
    cog = ctx.bot.get_cog("Luta")
    if cog is None:
        await ctx.send("❌ O sistema de combate não foi carregado.")
    return cog


async def _luta(ctx):
    cog = await _cog(ctx)
    if cog is None:
        return
    await ctx.send(embed=discord.Embed(
        title="⚔️ Sistema de Combate",
        description=(
            "`!luta monstros` — lista os monstros\n"
            "`!luta pve <monstro>` — inicia PvE\n"
            "`!luta pvp @jogador` — inicia PvP\n\n"
            "`!soco` · `!chute` · `!defesa` · `!esquiva` · `!fugir`"
        ),
        color=discord.Color.red(),
    ))


async def _monstros(ctx):
    if not luta_db.MONSTROS:
        await ctx.send("❌ Nenhum monstro foi carregado.")
        return

    itens = list(luta_db.MONSTROS.items())
    for inicio in range(0, len(itens), 25):
        embed = discord.Embed(title="🐉 Monstros Disponíveis", color=discord.Color.dark_red())
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


async def _pve(ctx, *, monstro_tipo: str = ""):
    if ctx.guild is None:
        await ctx.send("❌ Este comando só funciona em servidor.")
        return
    monstro_tipo = str(monstro_tipo or "").strip()
    if not monstro_tipo:
        await ctx.send("❌ Informe o monstro. Exemplo: `!luta pve slime`")
        return

    cog = await _cog(ctx)
    if cog is None:
        return

    async with cog._lock(ctx.channel.id):
        if cog._combate_ativo(ctx.channel.id):
            await ctx.send("❌ Já existe um combate ativo neste canal.")
            return

        monstro_id = cog._encontrar_monstro(monstro_tipo)
        if not monstro_id:
            await ctx.send(f"❌ Monstro `{monstro_tipo}` não encontrado. Use `!luta monstros`.")
            return

        guild_id = str(ctx.guild.id)
        user_id = str(ctx.author.id)
        verificacao = await run_db(luta_db.pode_lutar, user_id, guild_id)
        if not verificacao.get("pode"):
            await ctx.send(verificacao.get("mensagem", "❌ Você não pode lutar."))
            return

        jogador = await luta_mod._criar_participante(user_id, guild_id)
        if not jogador:
            await ctx.send("❌ Você precisa ter um personagem registrado para lutar.")
            return
        jogador["nome"] = jogador.get("nome") or ctx.author.display_name

        reserva = await run_db(luta_db.iniciar_cooldown_monstro, user_id, guild_id, str(monstro_id))
        if not reserva.get("sucesso"):
            segundos = int(reserva.get("segundos_restantes", 0) or 0)
            horas, resto = divmod(segundos, 3600)
            minutos = resto // 60
            restante = f"{horas}h {minutos}min" if horas else f"{max(1, minutos)}min"
            nome = luta_db.MONSTROS.get(str(monstro_id), {}).get("nome", str(monstro_id))
            await ctx.send(f"⏳ Você já lutou contra **{nome}**. Tente novamente em **{restante}**.")
            return

        fim_cooldown = reserva.get("fim")
        try:
            monstro = await run_db(luta_db.criar_monstro, str(monstro_id), 1)
            if not monstro:
                raise RuntimeError("criar_monstro retornou vazio")
            combate = cog._novo_combate([jogador, monstro], guild_id)
            cog.combates[ctx.channel.id] = combate
            await cog._marcar_combate([jogador], guild_id, "ativo_combate")
            await cog._mostrar_inicio(ctx)
        except Exception:
            if fim_cooldown is not None:
                try:
                    await run_db(luta_db.cancelar_cooldown_monstro, user_id, guild_id, str(monstro_id), fim_cooldown)
                except Exception as erro:
                    print(f"[LUTA][PVE][COOLDOWN][ERRO] {type(erro).__name__}: {erro}")
            cog.combates.pop(ctx.channel.id, None)
            raise


async def _pvp(ctx, membro: Optional[discord.Member] = None):
    if ctx.guild is None:
        await ctx.send("❌ Este comando só funciona em servidor.")
        return
    if membro is None:
        membro = next((m for m in ctx.message.mentions if not m.bot and m.id != ctx.author.id), None)
    if membro is None:
        await ctx.send("❌ Mencione um membro válido. Exemplo: `!luta pvp @jogador`")
        return
    if membro.bot or membro.id == ctx.author.id:
        await ctx.send("❌ Alvo inválido para PvP.")
        return

    cog = await _cog(ctx)
    if cog is None:
        return
    async with cog._lock(ctx.channel.id):
        if cog._combate_ativo(ctx.channel.id):
            await ctx.send("❌ Já existe um combate ativo neste canal.")
            return
        guild_id = str(ctx.guild.id)
        jogadores = []
        for usuario in (ctx.author, membro):
            verificacao = await run_db(luta_db.pode_lutar, str(usuario.id), guild_id)
            if not verificacao.get("pode"):
                await ctx.send(f"❌ {usuario.display_name}: {verificacao.get('mensagem', 'não pode lutar.')}")
                return
            jogador = await luta_mod._criar_participante(usuario.id, guild_id)
            if not jogador:
                await ctx.send(f"❌ {usuario.display_name} não possui personagem registrado.")
                return
            jogador["nome"] = jogador.get("nome") or usuario.display_name
            jogadores.append(jogador)
        cog.combates[ctx.channel.id] = cog._novo_combate(jogadores, guild_id, pvp=True)
        await cog._marcar_combate(jogadores, guild_id, "ativo_combate")
        await cog._mostrar_inicio(ctx)


async def _soco(ctx):
    cog = await _cog(ctx)
    if cog:
        async with cog._lock(ctx.channel.id):
            await cog._ataque_jogador(ctx, "soco")


async def _chute(ctx):
    cog = await _cog(ctx)
    if cog:
        async with cog._lock(ctx.channel.id):
            await cog._ataque_jogador(ctx, "chute")


async def _defesa(ctx):
    cog = await _cog(ctx)
    if cog:
        async with cog._lock(ctx.channel.id):
            await cog._defesa_jogador(ctx, "defesa")


async def _esquiva(ctx):
    cog = await _cog(ctx)
    if cog:
        async with cog._lock(ctx.channel.id):
            await cog._defesa_jogador(ctx, "esquiva")


async def _fugir(ctx):
    cog = await _cog(ctx)
    if cog is None:
        return
    async with cog._lock(ctx.channel.id):
        combate = cog._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            await ctx.send("❌ Você não está em combate.")
            return
        jogador = cog._participante(combate, str(ctx.author.id))
        if not jogador or jogador.get("tipo") != "jogador":
            await ctx.send("❌ Você não participa deste combate.")
            return
        if random.random() >= (0.15 if not combate.get("pvp") else 0.10):
            await ctx.send("❌ Você não conseguiu fugir.")
            return
        combate["ativo"] = False
        await cog._salvar(combate)
        cog.combates.pop(ctx.channel.id, None)
        await ctx.send(f"🏃 **{jogador.get('nome')}** conseguiu fugir!")


async def _matar(ctx):
    cog = await _cog(ctx)
    if cog:
        async with cog._lock(ctx.channel.id):
            await cog._finalizar_pvp(ctx, "morte")


async def _desmaiar(ctx):
    cog = await _cog(ctx)
    if cog:
        async with cog._lock(ctx.channel.id):
            await cog._finalizar_pvp(ctx, "desmaio")


def _novo_comando(callback, nome, **kwargs):
    return commands.Command(callback, name=nome, **kwargs)


async def setup(bot):
    # O Cog foi carregado pela extensao canônica imediatamente antes deste
    # modulo. Ele fica registrado como serviço, mas seus comandos antigos são
    # removidos do bot para impedir qualquer binding de self/ctx.
    if bot.get_cog("Luta") is None:
        raise RuntimeError("Cog Luta não foi carregado antes de correcoes_luta.")

    for nome in (
        "luta", "fight", "combate", "soco", "chute", "defesa", "defender",
        "def", "shield", "block", "bloquear", "bloqueio", "esquiva", "esquivar",
        "desviar", "dodge", "desvio", "fugir", "fuga", "escape", "escapar", "run",
        "matar", "desmaiar",
    ):
        bot.remove_command(nome)

    grupo = commands.Group(
        _luta,
        name="luta",
        aliases=["fight", "combate"],
        invoke_without_command=True,
        help="Sistema de combate.",
    )
    grupo.add_command(_novo_comando(_monstros, "monstros", help="Lista os monstros disponíveis."))
    grupo.add_command(_novo_comando(_pve, "pve", help="Inicia um combate PvE."))
    grupo.add_command(_novo_comando(_pvp, "pvp", help="Inicia um combate PvP."))
    bot.add_command(grupo)

    comandos = [
        (_soco, "soco", {}),
        (_chute, "chute", {}),
        (_defesa, "defesa", {"aliases": ["defender", "def", "shield", "block", "bloquear", "bloqueio"]}),
        (_esquiva, "esquiva", {"aliases": ["esquivar", "desviar", "dodge", "desvio"]}),
        (_fugir, "fugir", {"aliases": ["fuga", "escape", "escapar", "run"]}),
        (_matar, "matar", {}),
        (_desmaiar, "desmaiar", {}),
    ]
    for callback, nome, opcoes in comandos:
        bot.add_command(_novo_comando(callback, nome, **opcoes))

    print("[LUTA][REGISTRO] interface standalone carregada: !luta, !luta monstros, !luta pve, !luta pvp e ações de combate.")
