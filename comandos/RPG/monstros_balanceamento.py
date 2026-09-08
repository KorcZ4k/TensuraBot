"""Balanceamento centralizado dos atributos dos monstros."""

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


def criar_monstro_balanceado(tipo: str, nivel: int = 1):
    dados = luta_db.MONSTROS.get(tipo)
    if not dados:
        return None

    nivel_minimo = int(dados.get("nivel_minimo", 1) or 1)
    nivel_maximo = int(dados.get("nivel_maximo", 99) or 99)
    nivel = max(nivel_minimo, min(int(nivel), nivel_maximo))

    # O status informado no JSON é o status real do monstro no nível mínimo.
    # A progressão só começa quando o nível ultrapassa o nível mínimo.
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

    return {
        "id": str(tipo),
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
        "Força": forca,
        "Defesa": defesa,
        "Vitalidade": vitalidade,
        "Velocidade": atributos["Velocidade"],
        "Destreza": atributos["Destreza"],
        "Magia": magia,
        "Sorte": atributos["Sorte"],
        "Inteligencia": atributos["Inteligencia"],
        "defesa": (forca + defesa) * 2,
        "velocidade": atributos["Velocidade"],
        "dano_base": int(float(dados.get("dano_base", forca) or forca) * fator),
        "xp_recompensa": int(float(dados.get("xp_recompensa", 20) or 20) * fator),
        "hunos_recompensa": int(float(dados.get("hunos_recompensa", 10) or 10) * fator),
        "tp_recompensa": int(dados.get("tp_recompensa", 100) or 100),
        "golpes": list(dados.get("golpes", [])),
        "defesa_ativa": False,
        "esquiva_ativa": False,
    }


# O comando !luta pve usa a função importada por luta_sync.
base_luta.criar_monstro = criar_monstro_balanceado
luta_db.criar_monstro = criar_monstro_balanceado


async def setup(bot):
    print("[MONSTROS] Balanceamento de atributos carregado.")
