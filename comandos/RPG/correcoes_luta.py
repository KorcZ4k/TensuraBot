"""Compatibilidade do sistema de luta.

O PvE e registrado aqui como um callback independente do Cog. Assim o
Discord passa apenas ``ctx`` para este comando e nao existe qualquer
rebind de callback de Cog que possa produzir ``ctx`` ausente.
"""

from discord.ext import commands

from database.python import luta as luta_db
from database.python.mongodb import run_db
from comandos.RPG import luta as luta_mod


async def _pve(ctx, *, monstro_tipo: str = ""):
    """Inicia um combate PvE completo sem depender de binding de Cog."""
    if ctx.guild is None:
        await ctx.send("❌ Este comando só funciona em servidor.")
        return

    monstro_tipo = str(monstro_tipo or "").strip()
    if not monstro_tipo:
        await ctx.send("❌ Informe o monstro. Exemplo: `!luta pve slime`")
        return

    combate_cog = ctx.bot.get_cog("Luta")
    if combate_cog is None:
        await ctx.send("❌ O sistema de combate não foi carregado.")
        return

    async with combate_cog._lock(ctx.channel.id):
        if combate_cog._combate_ativo(ctx.channel.id):
            await ctx.send("❌ Já existe um combate ativo neste canal.")
            return

        monstro_id = combate_cog._encontrar_monstro(monstro_tipo)
        if not monstro_id:
            await ctx.send(f"❌ Monstro `{monstro_tipo}` não encontrado. Use `!luta monstros` para ver os disponíveis.")
            return

        guild_id = str(ctx.guild.id)
        user_id = str(ctx.author.id)

        verificacao = await run_db(luta_db.pode_lutar, user_id, guild_id)
        if not verificacao.get("pode"):
            await ctx.send(verificacao.get("mensagem", "❌ Você não pode lutar."))
            return

        jogador = await run_db(luta_mod._criar_participante, user_id, guild_id)
        if not jogador:
            await ctx.send("❌ Você precisa ter um personagem registrado para lutar.")
            return
        jogador["nome"] = jogador.get("nome") or ctx.author.display_name

        reserva = await run_db(
            luta_db.iniciar_cooldown_monstro,
            user_id,
            guild_id,
            str(monstro_id),
        )
        if not reserva.get("sucesso"):
            segundos = int(reserva.get("segundos_restantes", 0) or 0)
            horas, resto = divmod(segundos, 3600)
            minutos = resto // 60
            restante = f"{horas}h {minutos}min" if horas else f"{max(1, minutos)}min"
            dados = luta_db.MONSTROS.get(str(monstro_id), {})
            nome = dados.get("nome", str(monstro_id))
            await ctx.send(f"⏳ Você já lutou contra **{nome}**. Tente novamente em **{restante}**.")
            return

        fim_cooldown = reserva.get("fim")
        try:
            monstro = await run_db(luta_db.criar_monstro, str(monstro_id), 1)
            if not monstro:
                raise RuntimeError("criar_monstro retornou vazio")

            combate = combate_cog._novo_combate([jogador, monstro], guild_id)
            combate_cog.combates[ctx.channel.id] = combate
            await combate_cog._marcar_combate([jogador], guild_id, "ativo_combate")
            await combate_cog._mostrar_inicio(ctx)
        except Exception:
            if fim_cooldown is not None:
                try:
                    await run_db(
                        luta_db.cancelar_cooldown_monstro,
                        user_id,
                        guild_id,
                        str(monstro_id),
                        fim_cooldown,
                    )
                except Exception as erro_cooldown:
                    print(f"[LUTA][PVE][ERRO] Falha ao liberar cooldown: {type(erro_cooldown).__name__}: {erro_cooldown}")
            combate_cog.combates.pop(ctx.channel.id, None)
            raise


async def setup(bot):
    grupo = bot.get_command("luta")
    if grupo is None:
        raise RuntimeError("Comando !luta não foi registrado.")

    # Remove somente o antigo subcomando PvE. Os demais subcomandos continuam
    # exatamente no Cog canônico, inclusive !luta monstros.
    grupo.remove_command("pve")

    novo_pve = commands.Command(_pve, name="pve", help="Inicia um combate PvE contra um monstro.")
    grupo.add_command(novo_pve)
