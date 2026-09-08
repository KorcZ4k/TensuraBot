"""Balanceamento centralizado dos atributos e recompensas dos monstros."""

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
        # Após o nível 4, mantém crescimento de 25% por nível.
        return int(round(50 * (1.25 ** (nivel - 4))))
    # Para os demais monstros, o valor informado no JSON é a recompensa no
    # nível mínimo. Cada nível acima dele aumenta a recompensa em 10%.
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
        # O motor de progressão usa xp_recompensa para converter a vitória em
        # TP. Aqui os dois valores ficam iguais para respeitar a recompensa
        # específica do monstro e do nível.
        "xp_recompensa": tp_recompensa,
        "hunos_recompensa": int(float(dados.get("hunos_recompensa", 10) or 10) * fator),
        "tp_recompensa": tp_recompensa,
        "golpes": list(dados.get("golpes", [])),
        "defesa_ativa": False,
        "esquiva_ativa": False,
    }


base_luta.criar_monstro = criar_monstro_balanceado
luta_db.criar_monstro = criar_monstro_balanceado


async def setup(bot):
    print("[MONSTROS] Balanceamento de atributos e TP carregado.")
