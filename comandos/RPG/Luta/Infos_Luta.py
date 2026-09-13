"""Informações e regras de referência do sistema de luta.

Este módulo não registra comandos nem envia mensagens. Ele concentra as
consultas que descrevem o que monstros e golpes podem fazer, deixando o
motor livre para resolver o combate.
"""

from __future__ import annotations

import unicodedata

from database.python import luta as luta_db


def normalizar(texto: object) -> str:
    """Normaliza nomes para buscas de monstros, golpes e efeitos."""
    return unicodedata.normalize("NFKD", str(texto or "")).casefold().strip()


def listar_monstros() -> list[tuple[str, dict]]:
    """Retorna todos os monstros disponíveis para o sistema de combate."""
    return list(luta_db.MONSTROS.items())


def obter_monstro(nome: str):
    """Localiza um monstro pelo ID ou nome exibido."""
    alvo = normalizar(nome)
    for monstro_id, dados in luta_db.MONSTROS.items():
        if normalizar(monstro_id) == alvo or normalizar(dados.get("nome")) == alvo:
            return monstro_id, dados
    return None, None


def obter_golpe(nome: str) -> dict:
    """Retorna os dados de um golpe cadastrado."""
    return luta_db.GOLPES.get(nome, {})


def golpes_do_monstro(monstro: dict) -> list[dict]:
    """Expande os IDs de golpes de um monstro para seus dados completos."""
    return [
        luta_db.GOLPES[golpe_id]
        for golpe_id in monstro.get("golpes", [])
        if golpe_id in luta_db.GOLPES
    ]


def resumo_monstro(monstro_id: str, dados: dict) -> str:
    """Resumo curto usado pela interface de listagem de monstros."""
    return (
        f"ID: `{monstro_id}`\n"
        f"❤️ Vida: {dados.get('vida_base', 0)}\n"
        f"⚔️ Dano: {dados.get('dano_base', 0)}\n"
        f"✨ XP: {dados.get('xp_recompensa', 0)}\n"
        f"💰 Hunos: {dados.get('hunos_recompensa', 0)}"
    )
