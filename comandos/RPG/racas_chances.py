"""Sistema de chances raciais inspirado na escala de poder de Tensura.

As chances são pesos relativos para random.choices(), não precisam somar 100.
Raças comuns recebem peso alto; raças de alto nível e híbridos recebem pesos
progressivamente menores. Híbridos usam a combinação das raridades das raças
componentes e uma penalidade adicional pela raridade da combinação.
"""

from __future__ import annotations

import math
import random


# Pesos-base: aproximadamente alinhados à frequência/força mostradas em Tensura.
# Humanos, goblins e slimes são muito mais comuns; Ogros, demônios, anjos e
# dragões são progressivamente mais raros. True Dragons são excepcionais.
PESOS_BASE = {
    "Humano": 32.0,
    "Goblin": 18.0,
    "Slime": 16.0,
    "Kobold": 7.0,
    "Anão": 4.0,
    "Elfo": 4.0,
    "Meio-Elfo": 4.0,
    "Halfling": 3.0,
    "Homem-Fera": 3.0,
    "Orc": 3.0,
    "Homem-Lagarto": 2.5,
    "Sereiano": 2.0,
    "Ogro": 1.5,
    "Ghoul": 1.5,
    "Harpia": 1.2,
    "Homem-Cão": 1.0,
    "Homem-Gato": 1.0,
    "Homem-Lobo": 0.8,
    "Homem-Coelho": 0.8,
    "Wight": 0.7,
    "Homem-Pássaro": 0.7,
    "Homem-Peixe": 0.6,
    "Homem-Tigre": 0.35,
    "Homem-Cobra": 0.35,
    "Homem-Urso": 0.30,
    "Homúnculo": 0.25,
    "Espírito": 0.15,
    "Tengu": 0.15,
    "Gigante": 0.12,
    "Insetar": 0.10,
    "Elemental": 0.10,
    "Demônio": 0.08,
    "Vampiro": 0.05,
    "Anjo": 0.02,
    "Dragão": 0.005,
    "Dragão Verdadeiro": 0.00001,
}


def _peso_hibrido(nome: str) -> float | None:
    """Calcula o peso de híbridos a partir das raças componentes."""
    if nome.startswith("Meio-"):
        partes = nome.split("-", 2)
        if len(partes) != 3:
            return None
        primeiro = f"{partes[0]}-{partes[1]}"
        segundo = partes[2]
    elif nome.startswith("Híbrido "):
        corpo = nome[len("Híbrido "):]
        if "-" not in corpo:
            return None
        primeiro, segundo = corpo.split("-", 1)
    else:
        return None

    w1 = PESOS_BASE.get(primeiro)
    w2 = PESOS_BASE.get(segundo)
    if w1 is None or w2 is None:
        return None

    # Combinar duas raças já reduz bastante a frequência. Quanto mais rara
    # qualquer uma das partes, menor fica a chance final.
    peso = math.sqrt(w1 * w2) * (0.025 if nome.startswith("Meio-") else 0.02)

    # Dragão + Demônio é uma combinação extraordinária: fica abaixo das
    # raças lendárias normais e próxima do nível de excepcionalidade de um
    # True Dragon.
    if {primeiro, segundo} == {"Dragão", "Demônio"}:
        return 0.000001

    # Combinações envolvendo Dragão Verdadeiro são quase impossíveis.
    if "Dragão Verdadeiro" in {primeiro, segundo}:
        return peso * 0.001

    return max(peso, 0.0000001)


def peso_raca(nome: str) -> float:
    """Retorna o peso lore-friendly da raça."""
    nome = str(nome).strip()
    if nome in PESOS_BASE:
        return PESOS_BASE[nome]
    hibrido = _peso_hibrido(nome)
    if hibrido is not None:
        return hibrido
    return 0.0000001


def aplicar_chances(racas: list[dict]) -> list[dict]:
    """Atualiza em memória o campo `chance` de cada raça."""
    for raca in racas:
        if isinstance(raca, dict):
            raca["chance"] = peso_raca(raca.get("nome", ""))
    return racas


def sortear_raca(racas: list[dict]) -> str:
    """Sorteia uma raça usando os pesos Tensura."""
    racas = aplicar_chances(racas)
    nomes = [r["nome"] for r in racas if peso_raca(r.get("nome", "")) > 0]
    pesos = [peso_raca(nome) for nome in nomes]
    if not nomes:
        raise RuntimeError("Nenhuma raça possui chance de sorteio.")
    return random.choices(nomes, weights=pesos, k=1)[0]


__all__ = ["PESOS_BASE", "aplicar_chances", "peso_raca", "sortear_raca"]
