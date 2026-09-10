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
        "defesa": forca + defesa,
        "velocidade": atributos["Velocidade"],
        "dano_base": int(float(dados.get("dano_base", forca) or forca) * fator),
        "xp_recompensa": tp_recompensa,
        "hunos_recompensa": int(float(dados.get("hunos_recompensa", 10) or 10) * fator),
        "tp_recompensa": tp_recompensa,
        "golpes": list(dados.get("golpes", [])),
        "defesa_ativa": False,
        "esquiva_ativa": False,
        "defesa_magica_ativa": False,
        "defesa_magica_valor": 0,
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


def _preencher_atributos_jogador(jogador, dados):
    """Garante que o participante de combate tenha todos os atributos da ficha."""
    jogador["Força"] = float(dados.get("Força", 0) or 0)
    jogador["Defesa"] = float(dados.get("Defesa", 0) or 0)
    jogador["Vitalidade"] = float(dados.get("Vitalidade", 0) or 0)
    jogador["Velocidade"] = float(dados.get("Velocidade", 0) or 0)
    jogador["Destreza"] = float(dados.get("Destreza", 0) or 0)
    jogador["Magia"] = float(dados.get("Magia", 0) or 0)
    jogador["Sorte"] = float(dados.get("Sorte", 0) or 0)
    jogador["Inteligencia"] = float(
        dados.get("Inteligencia", dados.get("inteligencia", dados.get("Inteligência", 0))) or 0
    )
    jogador["defesa"] = jogador["Força"] + jogador["Defesa"]
    jogador["velocidade"] = jogador["Velocidade"]
    jogador["defesa_magica_ativa"] = False
    jogador["defesa_magica_valor"] = 0
    return jogador


    comando = grupo.get_command("pve")
    if comando is None:
        print("[MONSTROS][ERRO] Comando PvE não encontrado no grupo luta.")
        return False

    async def pve_callback(self, ctx, *partes_monstro):
        await _pve_corrigido(self, ctx, *partes_monstro)

    comando.callback = pve_callback
    return True


async def setup(bot):
    print("[MONSTROS] Balanceamento de atributos, TP e PvE carregado.")
