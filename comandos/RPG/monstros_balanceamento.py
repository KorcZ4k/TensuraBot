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
    forca = atributos["Força"]
    defesa = atributos["Defesa"]
    magia = atributos["Magia"]
    vitalidade = atributos["Vitalidade"]
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
    return [p for p in combate.get("participantes", [])
            if _vivo(p) and p is not atacante and p.get("equipe") != equipe]


def _matar_invocados(combate, boss_id):
    for participante in combate.get("participantes", []):
        if participante.get("invocado") and participante.get("equipe") == "inimigos" and boss_id == "cavaleiro-esqueletico":
            participante["vida"] = 0


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
        elif mid == "orc-rei":
            dados["nome"] = "🩸 Investida Predatória"
        elif mid == "fenix":
            efeito = dict(dados.get("efeito") or {})
            if not efeito or str(efeito.get("nome", "")).casefold() != "queimadura":
                dados["efeito"] = {"nome": "queimadura", "valor": 10, "turnos": 3}
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
            multiplicador = 4 if estado.get("furia_draconica") else 3
            dano_normal = float(atacante.get("Força", 0) or 0) + float(atacante.get("Velocidade", 0) or 0) + float(atacante.get("dano_base", 0) or 0)
            dano_base = max(0, int(dano_normal * multiplicador - (dano_normal - float(atacante.get("dano_base", 0) or 0))))
            estado["sopro_elemental"] = True
            estado["sopro_multiplicador"] = multiplicador
            self._criar_ataque(
                combate, "ataque_monstro", atacante, defensor,
                nome="🔥 Sopro Elemental", dano_base=dano_base,
                efeito={"nome": "queimadura", "valor": 10, "turnos": 3},
                com_arma=False, area=True, area_targets=_alvos(combate, atacante),
                multiplicador_area=multiplicador,
            )
            await self._anunciar_ataque(ctx)
            return

        if mid == "cavaleiro-esqueletico" and not estado.get("invocou_exercito"):
            estado["invocou_exercito"] = True
            for i in range(3):
                servo = luta_db.criar_monstro("esqueleto", 1)
                if not servo:
                    continue
                servo["id"] = f"esqueleto-invocado-{i + 1}"
                servo["monstro_id"] = "esqueleto"
                servo["nome"] = f"Esqueleto Invocado {i + 1}"
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
            if _eh(participante, "cavaleiro-esqueletico"):
                _matar_invocados(self._obter_combate(ctx.channel.id) or {}, "cavaleiro-esqueletico")
            return bloqueado
        mid = str(participante.get("boss_id", participante.get("id", "")))
        if mid == "fenix":
            cura = max(1, int(float(participante.get("vida_maxima", 0)) * 0.04))
            antes = float(participante.get("vida", 0))
            participante["vida"] = min(float(participante.get("vida_maxima", antes)), antes + cura)
            if participante["vida"] > antes:
                await ctx.send(f"🔥 **{participante.get('nome')}** recuperou **{int(participante['vida'] - antes)} HP** pela Chama Eterna.")
        efeitos = participante.get("efeitos", [])
        defesa = max(0.0, float(participante.get("defesa", 0) or 0))
        dano_profundo = 0
        novos = []
        for efeito in efeitos:
            if str(efeito.get("nome", "")).casefold() == "sangramento_profundo":
                bruto = max(0, int(float(efeito.get("valor", 10) or 10)))
                dano_profundo += max(1, int(bruto - defesa * 0.50))
            turnos = int(float(efeito.get("turnos", 1) or 1)) - 1
            if turnos > 0:
                efeito["turnos"] = turnos
                novos.append(efeito)
        if dano_profundo:
            participante["efeitos"] = novos
            participante["vida"] = max(0, float(participante.get("vida", 0)) - dano_profundo)
            await ctx.send(f"🩸 **{participante.get('nome')}** sofreu **{int(dano_profundo)}** de Sangramento Profundo.")
            if not _vivo(participante) and _eh(participante, "cavaleiro-esqueletico"):
                _matar_invocados(self._obter_combate(ctx.channel.id) or {}, "cavaleiro-esqueletico")
        return bloqueado

    def _reset_sequencia(estado, alvo_id):
        if estado.get("alvo_id") != alvo_id:
            estado["alvo_id"] = alvo_id
            estado["acertos_consecutivos"] = 0

    def _regras_monstro(self, dano, resultado, atacante, defensor):
        estado = _estado(atacante)
        mid = str(atacante.get("boss_id", atacante.get("id", "")))
        alvo_id = str(defensor.get("id"))
        if atacante.get("tipo") != "monstro":
            return dano, resultado
        if resultado != "atingiu":
            if mid in {"goblin-rei", "lobo-alpha", "orc-rei", "cavaleiro-esqueletico"}:
                estado["acertos_consecutivos"] = 0
            return dano, resultado
        if mid == "goblin-rei":
            _reset_sequencia(estado, alvo_id)
            estado["acertos_consecutivos"] = int(estado.get("acertos_consecutivos", 0)) + 1
            if estado.pop("critico_pendente", False):
                dano = int(dano * 2)
            if estado["acertos_consecutivos"] % 3 == 0:
                estado["acumulos"] = min(3, int(estado.get("acumulos", 0)) + 1)
                if estado["acumulos"] >= 3:
                    estado["critico_pendente"] = True
            dano = int(dano * (1 + 0.15 * int(estado.get("acumulos", 0))))
        elif mid in {"lobo-alpha", "orc-rei"}:
            _reset_sequencia(estado, alvo_id)
            estado["acertos_consecutivos"] = int(estado.get("acertos_consecutivos", 0)) + 1
            if estado.pop("furia_alvo_pendente", False) and estado.get("furia_alvo_id") == alvo_id:
                dano = int(dano * 1.50)
                estado["furia_alvo_id"] = None
            if float(defensor.get("vida", 0) or 0) - dano <= float(defensor.get("vida_maxima", 1) or 1) * 0.30:
                estado["furia_alvo_pendente"] = True
                estado["furia_alvo_id"] = alvo_id
            if estado["acertos_consecutivos"] % 3 == 0:
                self._aplicar_efeito(defensor, {"nome": "sangramento_profundo", "valor": 10, "turnos": 3, "ignora_defesa": 0.50})
        elif mid == "cavaleiro-esqueletico":
            _reset_sequencia(estado, alvo_id)
            estado["acertos_consecutivos"] = int(estado.get("acertos_consecutivos", 0)) + 1
            if estado["acertos_consecutivos"] % 3 == 0:
                fraturas = int(estado.setdefault("fraturas", {}).get(alvo_id, 0)) + 1
                estado["fraturas"][alvo_id] = fraturas
                self._aplicar_efeito(defensor, {"nome": "fratura", "valor": 0, "turnos": 3})
                if fraturas >= 3:
                    self._aplicar_efeito(defensor, {"nome": "stun", "valor": 0, "turnos": 1})
                    estado["fraturas"][alvo_id] = 0
        return dano, resultado

    def _aplicar_corrosao(self, dano, defensor):
        corrosao = next((e for e in defensor.get("efeitos", []) if str(e.get("nome", "")).casefold() == "corrosao"), None)
        if not corrosao:
            return dano
        stacks = min(3, max(1, int(corrosao.get("acumulo", 1))))
        return int(dano * (1 - 0.10 * stacks))

    def fisico_boss(self, atacante, defensor, ataque):
        dano, resultado = original_fisico(self, atacante, defensor, ataque)
        if resultado == "atingiu" and atacante.get("tipo") == "jogador":
            dano = self._aplicar_corrosao(dano, defensor)
        if resultado == "atingiu" and _eh(defensor, "dragao-adulto"):
            dano = int(dano * 0.65)
        if resultado == "atingiu" and ataque.get("area"):
            for alvo in ataque.get("area_targets", []):
                if alvo is defensor or not _vivo(alvo):
                    continue
                dano_area, resultado_area = original_fisico(self, atacante, alvo, ataque)
                if resultado_area != "atingiu":
                    continue
                if atacante.get("tipo") == "jogador":
                    dano_area = self._aplicar_corrosao(dano_area, alvo)
                if _eh(alvo, "dragao-adulto"):
                    dano_area = int(dano_area * 0.65)
                if _eh(atacante, "dragao-adulto") and _estado(atacante).get("furia_draconica"):
                    dano_area = int(dano_area * 1.30)
                alvo["vida"] = max(0, float(alvo.get("vida", 0)) - dano_area)
                if ataque.get("efeito"):
                    self._aplicar_efeito(alvo, ataque["efeito"])
        if resultado == "atingiu" and _eh(atacante, "dragao-adulto") and _estado(atacante).get("furia_draconica"):
            dano = int(dano * 1.30)
        if resultado == "atingiu" and _eh(defensor, "cavaleiro-esqueletico") and float(defensor.get("vida", 0)) - dano <= 0:
            _matar_invocados(self._obter_combate_por_participantes(defensor), "cavaleiro-esqueletico")
        return self._regras_monstro(dano, resultado, atacante, defensor)

    def magia_boss(self, atacante, defensor, ataque):
        dano, resultado = original_magia(self, atacante, defensor, ataque)
        if resultado == "atingiu" and atacante.get("tipo") == "jogador":
            dano = self._aplicar_corrosao(dano, defensor)
        if resultado == "atingiu" and _eh(defensor, "dragao-adulto"):
            dano = int(dano * 0.70)
        if resultado == "atingiu" and _eh(atacante, "dragao-adulto") and _estado(atacante).get("furia_draconica"):
            dano = int(dano * 1.30)
        if resultado == "atingiu" and _eh(defensor, "cavaleiro-esqueletico") and float(defensor.get("vida", 0)) - dano <= 0:
            self._matar_invocados_por_boss(defensor, "cavaleiro-esqueletico")
        return self._regras_monstro(dano, resultado, atacante, defensor)

    def _matar_invocados_por_boss(self, defensor, boss_id):
        for combate in self.combates.values():
            if defensor in combate.get("participantes", []):
                _matar_invocados(combate, boss_id)
                return

    def _obter_combate_por_participantes(self, defensor):
        for combate in self.combates.values():
            if defensor in combate.get("participantes", []):
                return combate
        return {}

    def efeito_boss(self, defensor, efeito):
        if isinstance(efeito, dict):
            nome = str(efeito.get("nome", efeito.get("tipo", ""))).casefold()
            if _eh(defensor, "dragao-adulto") and nome in {"stun", "paralisia", "sono", "sleep", "prisao", "prisão"} and random.random() < 0.75:
                return None
            if nome == "corrosao":
                efeitos = defensor.setdefault("efeitos", [])
                atual = next((e for e in efeitos if str(e.get("nome", "")).casefold() == "corrosao"), None)
                if atual:
                    atual["acumulo"] = min(3, int(atual.get("acumulo", 1)) + int(efeito.get("acumulo", 1)))
                    atual["turnos"] = int(efeito.get("turnos", 3) or 3)
                    return atual
                novo = dict(efeito)
                novo["acumulo"] = min(3, int(novo.get("acumulo", 1) or 1))
                efeitos.append(novo)
                return novo
            if nome == "sangramento_profundo":
                efeitos = defensor.setdefault("efeitos", [])
                atual = next((e for e in efeitos if str(e.get("nome", "")).casefold() == nome), None)
                if atual:
                    atual["turnos"] = max(int(atual.get("turnos", 3)), int(efeito.get("turnos", 3)))
                    atual["valor"] = max(int(atual.get("valor", 10)), int(efeito.get("valor", 10)))
                    atual["ignora_defesa"] = 0.50
                    return atual
                novo = dict(efeito)
                novo["ignora_defesa"] = 0.50
                efeitos.append(novo)
                return novo
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
                    p["Velocidade"] = float(p.get("Velocidade", 0)) * 1.20
                    p["velocidade"] = p["Velocidade"]
                    atual = combate.get("participantes", [])[int(combate.get("turno", 0)) % max(1, len(combate.get("participantes", [])))] if combate.get("participantes") else None
                    combate["participantes"] = sorted(combate["participantes"], key=lambda x: float(x.get("Velocidade", x.get("velocidade", 0)) or 0), reverse=True)
                    if atual in combate["participantes"]:
                        combate["turno"] = combate["participantes"].index(atual)
                    await ctx.send("🐉 **Fúria Dracônica:** +30% Dano, +20% Velocidade e o Sopro agora causa **4× Dano**!")
        await original_proximo_turno(self, ctx)

    async def recompensar_sem_tp(self, combate):
        resultado = self._condicao_vitoria(combate)
        if resultado != "jogadores" or luta_db.db is None:
            return 0, 0
        xp = sum(int(float(p.get("xp_recompensa", 0) or 0)) for p in combate.get("participantes", []) if p.get("tipo") == "monstro" and not p.get("invocado"))
        hunos = sum(int(float(p.get("hunos_recompensa", 0) or 0)) for p in combate.get("participantes", []) if p.get("tipo") == "monstro" and not p.get("invocado"))
        vivos = [p for p in combate.get("participantes", []) if p.get("tipo") == "jogador" and _vivo(p)]
        if not vivos:
            return xp, hunos
        for i, p in enumerate(vivos):
            ganho_xp = xp // len(vivos) + (1 if i < xp % len(vivos) else 0)
            ganho_hunos = hunos // len(vivos) + (1 if i < hunos % len(vivos) else 0)
            filtro = {"ID": str(p.get("id")), "guild_id": str(combate.get("guild_id"))}
            await luta_db.run_db(luta_db.db["Jogadores"].update_one, filtro, {"$inc": {"XP": ganho_xp}})
            await luta_db.run_db(luta_db.db["Hunos"].update_one, filtro, {"$inc": {"carteira": ganho_hunos}}, upsert=True)
        return xp, hunos

    Luta._regras_monstro = _regras_monstro
    Luta._criar_ataque = criar_ataque_boss
    Luta._ataque_monstro = ataque_monstro_boss
    Luta._resolver_ataque = resolver_boss
    Luta._aplicar_efeitos_inicio = inicio_boss
    Luta._dano_fisico = fisico_boss
    Luta._dano_magia = magia_boss
    Luta._aplicar_efeito = efeito_boss
    Luta._proximo_turno = proximo_turno_boss
    Luta._recompensar = recompensar_sem_tp


_patch_luta()


async def setup(bot):
    print("[MONSTROS] Balanceamento e habilidades especiais dos bosses carregados.")
