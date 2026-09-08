"""Balanceamento centralizado dos atributos e recompensas dos monstros."""

import discord
from discord.ext import commands

from database.python import luta as luta_db
from . import luta_sync as base_luta


ATRIBUTOS = (
    "Força",
    "Defesa",
    "Vitalidade",
    "Velocidade",
    "Destreza",
    "Magia",
    "Sorte",
    "Inteligencia",
)


def _tp_monstro(dados, nivel, nivel_minimo):
    base = int(dados.get("tp_recompensa", 0) or 0)
    if str(dados.get("nome", "")).casefold() == "slime":
        tabela = {1: 20, 2: 25, 3: 35, 4: 50}
        if nivel in tabela:
            return tabela[nivel]
        return int(round(50 * (1.25 ** (nivel - 4))))
    return int(round(base * (1 + 0.10 * max(0, nivel - nivel_minimo))))


def criar_monstro_balanceado(tipo: str, nivel: int = 1):
    dados = luta_db.MONSTROS.get(tipo)
    if not dados:
        return None

    nivel_minimo = int(dados.get("nivel_minimo", 1) or 1)
    nivel_maximo = int(dados.get("nivel_maximo", 99) or 99)
    nivel = max(nivel_minimo, min(int(nivel), nivel_maximo))

    fator = 1 + max(0, nivel - nivel_minimo) * 0.75
    base = dados.get("atributos_base", {})
    atributos = {
        nome: int(float(base.get(nome, 0) or 0) * fator)
        for nome in ATRIBUTOS
    }

    vitalidade = atributos["Vitalidade"]
    magia = atributos["Magia"]
    forca = atributos["Força"]
    defesa = atributos["Defesa"]
    tp_recompensa = _tp_monstro(dados, nivel, nivel_minimo)

    return {
        "id": str(tipo),
        "monstro_id": str(tipo),
        "nome": dados.get("nome", tipo),
        "emoji": dados.get("emoji", "👹"),
        "tipo": "monstro",
        "nivel": nivel,
        "nivel_minimo": nivel_minimo,
        "nivel_maximo": nivel_maximo,
        "vida": vitalidade * 10,
        "vida_maxima": vitalidade * 10,
        "mana": magia,
        "mana_maxima": magia,
        "Força": atributos["Força"],
        "Defesa": atributos["Defesa"],
        "Vitalidade": vitalidade,
        "Velocidade": atributos["Velocidade"],
        "Destreza": atributos["Destreza"],
        "Magia": magia,
        "Sorte": atributos["Sorte"],
        "Inteligencia": atributos["Inteligencia"],
        "defesa": (forca + defesa) * 2,
        "velocidade": atributos["Velocidade"],
        "dano_base": int(float(dados.get("dano_base", forca) or forca) * fator),
        "xp_recompensa": tp_recompensa,
        "hunos_recompensa": int(float(dados.get("hunos_recompensa", 10) or 10) * fator),
        "tp_recompensa": tp_recompensa,
        "golpes": list(dados.get("golpes", [])),
        "defesa_ativa": False,
        "esquiva_ativa": False,
    }


base_luta.criar_monstro = criar_monstro_balanceado
luta_db.criar_monstro = criar_monstro_balanceado


def _encontrar_monstro(nome):
    nome = str(nome or "").strip().casefold()
    for monstro_id, dados in luta_db.MONSTROS.items():
        if str(monstro_id).strip().casefold() == nome:
            return monstro_id
        if str(dados.get("nome", "")).strip().casefold() == nome:
            return monstro_id
    return None


async def _pve_corrigido(self, ctx, *partes_monstro):
    if not ctx.guild:
        return

    if self._combate_ativo(ctx.channel.id):
        await ctx.send("❌ Já existe um combate ativo neste canal.")
        return

    monstro_tipo = " ".join(str(parte) for parte in partes_monstro).strip()
    if not monstro_tipo:
        embed = discord.Embed(
            title="⚔️ Luta PvE",
            description="Informe o monstro que deseja enfrentar.\n\nExemplo: `!luta pve slime`",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)
        return

    monstro_id = _encontrar_monstro(monstro_tipo)
    if not monstro_id:
        await ctx.send(f"❌ Monstro `{monstro_tipo}` não encontrado. Use `!luta monstros` para ver os disponíveis.")
        return

    guild_id = str(ctx.guild.id)
    user_id = str(ctx.author.id)
    verificacao = luta_db.pode_lutar(user_id, guild_id)
    if not verificacao.get("pode", False):
        await ctx.send(verificacao.get("mensagem", "❌ Você não pode lutar."))
        return

    jogador = luta_db.criar_participante_jogador(user_id, guild_id)
    if not jogador:
        await ctx.send("❌ Você não possui um personagem registrado.")
        return

    jogador["nome"] = jogador.get("nome") or ctx.author.display_name
    monstro = criar_monstro_balanceado(monstro_id, 1)
    if not monstro:
        await ctx.send("❌ Não foi possível criar esse monstro.")
        return

    participantes = [jogador, monstro]
    participantes.sort(key=lambda p: p.get("velocidade", 0), reverse=True)
    self.combates[ctx.channel.id] = {
        "participantes": participantes,
        "turno": 0,
        "numero_turno": 1,
        "fase": "ataque",
        "ativo": True,
        "pvp": False,
        "guild_id": guild_id,
        "ataque_pendente": None,
        "historico": [],
        "aguardando_finalizacao": False,
        "vencedor_id": None,
        "perdedor_id": None,
    }
    self._atualizar_situacao(jogador["id"], guild_id, "ativo_combate")
    await self._mostrar_inicio(ctx)


def _instalar_pve_corrigido(bot):
    grupo = bot.get_command("luta")
    cog = bot.get_cog("Luta")
    if grupo is None or cog is None:
        print("[MONSTROS][ERRO] Não foi possível instalar o comando PvE: cog Luta não carregado.")
        return False

    grupo.remove_command("pve")

    async def pve_callback(ctx, *partes_monstro):
        await _pve_corrigido(cog, ctx, *partes_monstro)

    comando = commands.Command(
        pve_callback,
        name="pve",
        help="Inicia um combate PvE contra um monstro.",
    )
    grupo.add_command(comando)
    return True


async def setup(bot):
    _instalar_pve_corrigido(bot)
    print("[MONSTROS] Balanceamento de atributos, TP e PvE carregado.")
