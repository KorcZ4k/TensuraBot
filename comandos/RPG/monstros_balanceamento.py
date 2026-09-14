"""Balanceamento e habilidades especiais dos monstros/bosses."""

import random

from database.python import luta as luta_db

ATRIBUTOS = (
    "Força", "Defesa", "Vitalidade", "Velocidade",
    "Destreza", "Magia", "Sorte", "Inteligencia",
)
BOSS_IDS = {
    "slime-rei", "goblin-rei", "lobo-alpha", "orc-rei",
    "cavaleiro-esqueletico", "dragao-adulto", "arquidemonio",
}


def criar_monstro_balanceado(tipo: str, nivel: int = 1):
    dados = luta_db.MONSTROS.get(str(tipo))
    if not dados:
        return None
    nivel_minimo = int(dados.get("nivel_minimo", 1) or 1)
    nivel_maximo = int(dados.get("nivel_maximo", 99) or 99)
    nivel = max(nivel_minimo, min(int(nivel), nivel_maximo))
    fator = 1 + max(0, nivel - nivel_minimo) * 0.75
    base = dados.get("atributos_base", {}) or {}
    atributos = {nome: int(float(base.get(nome, 0) or 0) * fator) for nome in ATRIBUTOS}
    vitalidade = atributos["Vitalidade"]
    magia = atributos["Magia"]
    forca = atributos["Força"]
    defesa = atributos["Defesa"]
    return {
        "id": str(tipo), "monstro_id": str(tipo), "nome": dados.get("nome", tipo),
        "emoji": dados.get("emoji", "👹"), "tipo": "monstro", "nivel": nivel,
        "nivel_minimo": nivel_minimo, "nivel_maximo": nivel_maximo,
        "vida": vitalidade * 10, "vida_maxima": vitalidade * 10,
        "mana": magia, "mana_maxima": magia, **atributos,
        "defesa": forca + defesa, "velocidade": atributos["Velocidade"],
        "dano_base": int(float(dados.get("dano_base", forca) or forca) * fator),
        "xp_recompensa": int(float(dados.get("xp_recompensa", 0) or 0) * fator),
        "hunos_recompensa": int(float(dados.get("hunos_recompensa", 10) or 10) * fator),
        "golpes": list(dados.get("golpes", [])),
        "boss": str(tipo) in BOSS_IDS, "boss_id": str(tipo), "boss_estado": {},
        "defesa_ativa": False, "esquiva_ativa": False,
        "defesa_magica_ativa": False, "defesa_magica_valor": 0,
    }


luta_db.criar_monstro = criar_monstro_balanceado


def _estado(p):
    return p.setdefault("boss_estado", {})


def _eh(p, *ids):
    return str(p.get("boss_id", p.get("id", ""))) in ids


def _vivo(p):
    return float(p.get("vida", 0) or 0) > 0


def _alvos(combate, atacante):
    equipe = atacante.get("equipe")
    return [p for p in combate.get("participantes", []) if _vivo(p) and p is not atacante and p.get("equipe") != equipe]


def _patch_luta():
    from .Luta.sistemas_luta import Luta

    original_ataque = Luta._ataque_monstro
    original_resolver = Luta._resolver_ataque
    original_inicio = Luta._aplicar_efeitos_inicio
    original_fisico = Luta._dano_fisico
    original_magia = Luta._dano_magia
    original_efeito = Luta._aplicar_efeito
    original_proximo_turno = Luta._proximo_turno
    original_criar_ataque = Luta._criar_ataque
    
    def criar_ataque_boss(self, combate, tipo, atacante, defensor, **dados):
        mid = str(atacante.get("boss_id", atacante.get("id", "")))
        if mid == "slime-rei":
            dados["nome"] = "🧪 Lodo Corrosivo"
            dados["efeito"] = {"nome": "corrosao", "valor": 10, "turnos": 3}
        elif mid == "lobo-alpha":
            dados["nome"] = "🦷 Mordida Predatória"
        return original_criar_ataque(self, combate, tipo, atacante, defensor, **dados)

    async def ataque_monstro_boss(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo") or combate.get("fase") != "ataque":
            return
        atacante = self._obter_atacante(combate)
        defensor = self._obter_defensor(combate)
        if not atacante or atacante.get("tipo") != "monstro" or not defensor:
            return
        mid = str(atacante.get("boss_id", atacante.get("id", "")))
        estado = _estado(atacante)
        turno = int(combate.get("numero_turno", 1))

        if mid == "dragao-adulto" and turno % 4 == 0:
            total_normal = _raw_normal_damage(atacante) + float(atacante.get("dano_base", 0) or 0)
            multiplicador = 4 if estado.get("furia_draconica") else 3
            estado["sopro_elemental"] = True
            estado["sopro_multiplicador"] = multiplicador
            dano_base = max(0, multiplicador * total_normal - _raw_normal_damage(atacante))
            self._criar_ataque(
                combate, "ataque_monstro", atacante, defensor,
                nome="🔥 Sopro Elemental", dano_base=dano_base,
                efeito={"nome": "queimadura", "valor": 10, "turnos": 3},
                com_arma=False, area=True, area_targets=_alvos(combate, atacante),
                multiplicador_area=multiplicador)
            await self._anunciar_ataque(ctx)
            return

        if mid == "cavaleiro-esqueletico" and not estado.get("invocou_exercito") and float(atacante.get("vida", 0)) <= float(atacante.get("vida_maxima", 1)) * 0.50:
            estado["invocou_exercito"] = True
            for i in range(3):
                servo = luta_db.criar_monstro("esqueleto", 1)
                if servo:
                    servo["id"] = f"esqueleto-invocado-{i+1}"
                    servo["monstro_id"] = "esqueleto"
                    servo["nome"] = f"Esqueleto Invocado {i+1}"
                    servo["equipe"] = atacante.get("equipe", "inimigos")
                    servo["invocado"] = True
                    servo["expira_turno"] = int(combate.get("numero_turno", 1)) + 6
                    combate.setdefault("participantes", []).append(servo)
            await ctx.send("💀 **Exército dos Mortos:** o Cavaleiro Esquelético invocou **3 Esqueletos**!")
        await original_ataque(self, ctx)

    async def resolver_boss(self, ctx):
        await original_resolver(self, ctx)

    async def inicio_boss(self, ctx, participante):
        bloqueado = await original_inicio(self, ctx, participante)
        if not _vivo(participante):
            return bloqueado
        mid = str(participante.get("boss_id", participante.get("id", "")))
        if mid in BOSS_IDS or mid == "fenix":
            cura = max(1, int(float(participante.get("vida_maxima", 0)) * 0.04))
            antes = float(participante.get("vida", 0))
            participante["vida"] = min(float(participante.get("vida_maxima", antes)), antes + cura)
            if participante["vida"] > antes:
                await ctx.send(f"🔥 **{participante.get('nome')}** recuperou **{int(participante['vida'] - antes)} HP** pela Chama Eterna.")
        return bloqueado

    def _regras_monstro(self, dano, resultado, atacante, defensor):
        if resultado != "atingiu" or atacante.get("tipo") != "monstro":
            return dano, resultado
        estado = _estado(atacante)
        alvo_id = str(defensor.get("id"))
        mid = str(atacante.get("boss_id", atacante.get("id", "")))

        if mid == "slime-rei":
            efeitos = defensor.setdefault("efeitos", [])
            corrosao = next((e for e in efeitos if str(e.get("nome", "")).casefold() == "corrosao"), None)
            if corrosao:
                corrosao["acumulo"] = min(3, int(corrosao.get("acumulo", 1)) + 1)
                corrosao["turnos"] = 3
            else:
                efeitos.append({"nome": "corrosao", "turnos": 3, "valor": 10, "acumulo": 1})

        if mid == "goblin-rei":
            if estado.get("alvo_id") == alvo_id:
                estado["acertos_consecutivos"] = int(estado.get("acertos_consecutivos", 0)) + 1
            else:
                estado["alvo_id"] = alvo_id; estado["acertos_consecutivos"] = 1
            if estado["acertos_consecutivos"] % 3 == 0:
                estado["acumulos"] = min(3, int(estado.get("acumulos", 0)) + 1)
                if estado["acumulos"] >= 3:
                    estado["critico_pendente"] = True
            dano = int(dano * (1 + 0.15 * int(estado.get("acumulos", 0))))
            if estado.pop("critico_pendente", False):
                dano *= 2

        elif mid in {"lobo-alpha", "orc-rei"}:
            if estado.get("alvo_id") == alvo_id:
                estado["acertos_consecutivos"] = int(estado.get("acertos_consecutivos", 0)) + 1
            else:
                estado["alvo_id"] = alvo_id; estado["acertos_consecutivos"] = 1
            if estado.pop("furia_alvo_pendente", False):
                dano = int(dano * 1.50)
            if float(defensor.get("vida", 0) or 0) - dano <= float(defensor.get("vida_maxima", 1) or 1) * 0.30:
                estado["furia_alvo_pendente"] = True
            if estado["acertos_consecutivos"] % 3 == 0:
                self._aplicar_efeito(defensor, {"nome": "sangramento_profundo", "valor": 10, "turnos": 3, "ignora_defesa": 0.50})

        elif mid == "cavaleiro-esqueletico":
            estado["acertos_consecutivos"] = int(estado.get("acertos_consecutivos", 0)) + 1
            if estado["acertos_consecutivos"] % 3 == 0:
                fraturas = int(estado.setdefault("fraturas", {}).get(alvo_id, 0)) + 1
                estado["fraturas"][alvo_id] = fraturas
                self._aplicar_efeito(defensor, {"nome": "fratura", "valor": 0, "turnos": 3})
                if fraturas >= 3:
                    self._aplicar_efeito(defensor, {"nome": "stun", "valor": 0, "turnos": 1})
                    estado["fraturas"][alvo_id] = 0
        return dano, resultado

    def fisico_boss(self, atacante, defensor, ataque):
        dano, resultado = original_fisico(self, atacante, defensor, ataque)
        if resultado == "atingiu" and atacante.get("tipo") == "jogador":
            corrosao = next((e for e in defensor.get("efeitos", []) if str(e.get("nome", "")).casefold() == "corrosao"), None)
            if corrosao:
                dano = int(dano * (1 - 0.10 * min(3, int(corrosao.get("acumulo", 1)))))
        if resultado == "atingiu" and _eh(defensor, "dragao-adulto"):
            dano = int(dano * 0.65)
        if resultado == "atingiu" and ataque.get("area"):
            for alvo in ataque.get("area_targets", []):
                if alvo is not defensor and _vivo(alvo):
                    dano_area = max(1, int(float(atacante.get("Força", 0)) + float(atacante.get("Velocidade", 0)) + float(ataque.get("dano_base", 0) or 0)))
                    alvo["vida"] = max(0, float(alvo.get("vida", 0)) - dano_area)
        if resultado == "atingiu" and _eh(atacante, "dragao-adulto") and _estado(atacante).get("furia_draconica"):
            dano = int(dano * 1.30)
        return self._regras_monstro(dano, resultado, atacante, defensor)

    def magia_boss(self, atacante, defensor, ataque):
        dano, resultado = original_magia(self, atacante, defensor, ataque)
        if resultado == "atingiu" and atacante.get("tipo") == "jogador":
            corrosao = next((e for e in defensor.get("efeitos", []) if str(e.get("nome", "")).casefold() == "corrosao"), None)
            if corrosao:
                dano = int(dano * (1 - 0.10 * min(3, int(corrosao.get("acumulo", 1)))))
        if resultado == "atingiu" and _eh(defensor, "dragao-adulto"):
            dano = int(dano * 0.70)
        if resultado == "atingiu" and _eh(atacante, "dragao-adulto") and _estado(atacante).get("furia_draconica"):
            dano = int(dano * 1.30)
        return self._regras_monstro(dano, resultado, atacante, defensor)

    def efeito_boss(self, defensor, efeito):
        if isinstance(efeito, dict):
            nome = str(efeito.get("nome", efeito.get("tipo", ""))).casefold()
            if _eh(defensor, "dragao-adulto") and nome in {"stun", "paralisia", "sono", "sleep", "prisao", "prisão"} and random.random() < 0.75:
                return None
        return original_efeito(self, defensor, efeito)

    async def proximo_turno_boss(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if combate:
            turno_atual = int(combate.get("numero_turno", 1))
            combate["participantes"] = [p for p in combate.get("participantes", []) if not (p.get("invocado") and turno_atual >= int(p.get("expira_turno", 10**9)))]
            for p in combate.get("participantes", []):
                if p.get("tipo") != "monstro":
                    continue
                mid = str(p.get("boss_id", p.get("id", "")))
                estado = _estado(p)
                if mid == "dragao-adulto" and not estado.get("furia_draconica") and float(p.get("vida", 0) or 0) <= float(p.get("vida_maxima", 1) or 1) * 0.25:
                    estado["furia_draconica"] = True
                    p["dano_base"] = float(p.get("dano_base", 0)) * 1.30
                    p["Velocidade"] = float(p.get("Velocidade", 0)) * 1.20
                    p["velocidade"] = p["Velocidade"]
                    await ctx.send("🐉 **Fúria Dracônica:** +30% Dano, +20% Velocidade e o Sopro agora causa **4× Dano**!")
        await original_proximo_turno(self, ctx)

    Luta._criar_ataque = criar_ataque_boss
    Luta._ataque_monstro = ataque_monstro_boss
    Luta._resolver_ataque = resolver_boss
    Luta._aplicar_efeitos_inicio = inicio_boss
    Luta._dano_fisico = fisico_boss
    Luta._dano_magia = magia_boss
    Luta._aplicar_efeito = efeito_boss
    Luta._proximo_turno = proximo_turno_boss


_patch_luta()


async def setup(bot):
    print("[MONSTROS] Balanceamento e habilidades especiais dos bosses carregados.")
