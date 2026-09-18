"""Implementação final das invariantes do combate.

Esta classe é a que os comandos registram no Cog. Ela herda o motor já
balanceado e centraliza alvo, ataque pendente, defesa, UI e avanço.
"""
from __future__ import annotations

import asyncio
import copy
import discord
from database.python import luta as luta_db
from .. import monstros_balanceamento as boss_rules

from .sistemas_luta import Luta as _BaseLuta, _UIContext, _vivo


class Luta(_BaseLuta):
    async def _mostrar_aguarde_player(self, combate):
        combate["ui_stage"] = "player_action"
        await self._ui_editar(combate, self._embed_aguarde_jogador(combate))
    
    def _por_id(self, combate, participante_id):
        if participante_id is None:
            return None
        return next((p for p in combate.get("participantes", [])
                     if str(p.get("id")) == str(participante_id)), None)

    def _normalizar_estado(self, combate):
        """Normaliza invariantes sem trocar identidade de turno silenciosamente."""
        participantes = combate.setdefault("participantes", [])
        combate.setdefault("historico", [])
        combate.setdefault("ataque_pendente", None)
        combate.setdefault("turno", 0)
        combate.setdefault("numero_turno", 1)
        combate.setdefault("fase", "ataque")
        combate.setdefault("ativo", True)
        combate.setdefault("ui_stage", "attributes")
        combate.setdefault("ui_waiting_advance", False)
        combate.setdefault("_turno_participante_id", None)
        if participantes:
            ids = {str(p.get("id")) for p in participantes}
            turno_id = combate.get("_turno_participante_id")
            if turno_id is not None and str(turno_id) in ids:
                combate["turno"] = next(i for i,p in enumerate(participantes) if str(p.get("id")) == str(turno_id))
            else:
                combate["turno"] = max(0, min(int(combate.get("turno", 0)), len(participantes)-1))
                combate["_turno_participante_id"] = participantes[combate["turno"]].get("id")
        combate["numero_turno"] = max(1, int(combate.get("numero_turno", 1)))
        ataque = combate.get("ataque_pendente")
        if ataque:
            atacante = self._por_id(combate, ataque.get("atacante_id"))
            defensor = self._por_id(combate, ataque.get("defensor_id"))
            if not atacante or not defensor:
                combate["ataque_pendente"] = None
                combate["fase"] = "ataque"
                combate["ui_stage"] = "turn"
                combate["ui_waiting_advance"] = False
            else:
                combate["fase"] = "defesa"

    def _obter_atacante(self, combate):
        self._normalizar_estado(combate)
        ataque = combate.get("ataque_pendente")
        if ataque:
            return self._por_id(combate, ataque.get("atacante_id"))
        participantes = combate.get("participantes", [])
        if not participantes:
            return None
        atual = int(combate.get("turno", 0)) % len(participantes)
        if _vivo(participantes[atual]):
            combate["_turno_participante_id"] = participantes[atual].get("id")
            return participantes[atual]
        for passo in range(1, len(participantes) + 1):
            indice = (atual + passo) % len(participantes)
            if _vivo(participantes[indice]):
                combate["turno"] = indice
                combate["_turno_participante_id"] = participantes[indice].get("id")
                return participantes[indice]
        return None

    def _obter_defensor(self, combate):
        self._normalizar_estado(combate)
        ataque = combate.get("ataque_pendente")
        if ataque:
            return self._por_id(combate, ataque.get("defensor_id"))
        atacante = self._obter_atacante(combate)
        if not atacante:
            return None
        equipe = atacante.get("equipe")
        return next((p for p in combate.get("participantes", [])
                     if p is not atacante and _vivo(p) and p.get("equipe") != equipe), None)

    def _criar_ataque(self, combate, tipo, atacante, defensor, **dados):
        """Cria exatamente um ataque e congela atacante/alvo até a resolução."""
        self._normalizar_estado(combate)
        existente = combate.get("ataque_pendente")
        if existente:
            if (str(existente.get("atacante_id")) != str((atacante or {}).get("id")) or
                    str(existente.get("defensor_id")) != str((defensor or {}).get("id"))):
                raise RuntimeError("tentativa de substituir ataque pendente por outro alvo")
            combate["fase"] = "defesa"
            return existente
        if not atacante or not defensor:
            raise RuntimeError("ataque criado sem atacante ou defensor")
        if not _vivo(atacante):
            raise RuntimeError("ataque criado por participante derrotado")
        if not _vivo(defensor):
            raise RuntimeError("ataque criado contra participante derrotado")
        if tipo not in {"fisico", "magia", "soco", "chute", "ataque_monstro"}:
            raise ValueError(f"tipo de ataque inválido: {tipo}")
        dados.setdefault("efeito", {})
        dados.setdefault("mana_base", 0)
        dados.setdefault("com_arma", False)
        try:
            dados["dano_base"] = float(dados.get("dano_base", 0) or 0)
            dados["mana_base"] = float(dados.get("mana_base", 0) or 0)
        except (TypeError, ValueError) as erro:
            raise ValueError("dano_base/mana_base inválidos") from erro
        efeito = dados.get("efeito")
        if isinstance(efeito, str):
            efeito = {"nome": efeito}
            dados["efeito"] = efeito
        if efeito is not None and not isinstance(efeito, dict):
            raise ValueError("efeito de ataque inválido")
        ataque = {"tipo": tipo, "nome": dados.pop("nome", "⚔️ Ataque"),
                  "atacante_id": atacante.get("id"), "defensor_id": defensor.get("id"), **dados}
        combate["ataque_pendente"] = ataque
        combate["fase"] = "defesa"
        combate["ui_waiting_advance"] = False
        combate["ui_stage"] = "attack"
        return ataque

    async def _mostrar_ataque_ui(self, combate):
        ataque = combate.get("ataque_pendente")
        if not ataque:
            raise RuntimeError("UI solicitada sem ataque pendente")
        atacante = self._por_id(combate, ataque.get("atacante_id"))
        defensor = self._por_id(combate, ataque.get("defensor_id"))
        if not atacante or not defensor:
            raise RuntimeError("ataque pendente sem atacante ou defensor")
        efeito = ataque.get("efeito") or "Nenhum"
        if isinstance(efeito, dict):
            efeito = efeito.get("nome", efeito.get("tipo", "Nenhum"))
        embed = self._acao_embed(atacante=atacante, defensor=defensor,
            nome=ataque.get("nome", "Ataque"),
            emoji="👹" if atacante.get("tipo") == "monstro" else "⚔️",
            turno=combate.get("numero_turno", 1), dano=ataque.get("dano_base", 0),
            mana=ataque.get("mana_base", 0),
            descricao=f"**{atacante.get('nome')}** atacou **{defensor.get('nome')}**.", efeito=efeito)
        await self._ui_editar(combate, embed)
        combate["ui_stage"] = "attack"
        combate["ui_waiting_advance"] = False

    async def _anunciar_ataque(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return
        ataque = combate.get("ataque_pendente")
        if not ataque:
            raise RuntimeError("tentativa de anunciar ataque inexistente")
        if not self._por_id(combate, ataque.get("atacante_id")) or not self._por_id(combate, ataque.get("defensor_id")):
            raise RuntimeError("ataque pendente sem participantes para anúncio")
        if combate.get("ui_message"):
            await self._mostrar_ataque_ui(combate)
            return
        embed = self._embeds_acao.pop(ctx.channel.id, None)
        if isinstance(embed, tuple):
            embed = embed[0]
        if embed is None:
            atacante = self._por_id(combate, ataque["atacante_id"])
            defensor = self._por_id(combate, ataque["defensor_id"])
            embed = discord.Embed(description=f"**{atacante.get('nome')}** atacou **{defensor.get('nome')}**!", color=discord.Color.orange())
        await ctx.send(embed=embed)

    async def _ataque_monstro(self, ctx):
        """Único caminho de criação do ataque de monstro; nunca duplica pending."""
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return None
        if combate.get("ataque_pendente"):
            combate["fase"] = "defesa"
            combate["ui_stage"] = "attack"
            return combate["ataque_pendente"]
        atacante = self._obter_atacante(combate)
        defensor = self._obter_defensor(combate)
        if not atacante or not defensor or atacante.get("tipo") != "monstro":
            raise RuntimeError("turno do monstro sem atacante/defensor válido")
        import random
        especial = boss_rules.ataque_especial(combate, atacante, defensor)
        if especial is not None:
            dados, tipo = especial, "fisico"
        else:
            golpes = [luta_db.GOLPES[i] for i in (atacante.get("golpes") or []) if i in luta_db.GOLPES]
            if not golpes:
                raise RuntimeError("monstro sem golpe válido: configure pelo menos um golpe válido")
            golpe = boss_rules.ajustar_ataque(atacante, random.choice(golpes))
            dados = {"nome": golpe.get("nome", "Ataque"), "dano_base": float(golpe.get("dano_base", atacante.get("dano_base", 0)) or 0),
                     "mana_base": float(golpe.get("custo_mana", 0) or 0), "com_arma": bool(golpe.get("com_arma", False)),
                     "efeito": golpe.get("efeito", {}) or {}}
            tipo_original = str(golpe.get("tipo", "monstro")).casefold()
            tipo = "magia" if tipo_original in {"magia", "magico", "mágico"} else "ataque_monstro"
        ataque = self._criar_ataque(combate, tipo, atacante, defensor, **dados)
        if combate.get("ui_message"):
            await self._mostrar_ataque_ui(combate)
        else:
            await self._anunciar_ataque(ctx)
        return ataque

    async def _criar_ataque_monstro_ui(self, combate):
        mensagem = combate.get("ui_message")
        if mensagem is None:
            raise RuntimeError("combate sem mensagem para ataque de monstro")
        ctx = _UIContext(mensagem, mensagem, combate, self)
        await self._ataque_monstro(ctx)
        if combate.get("ativo") and not combate.get("ataque_pendente"):
            raise RuntimeError("turno do monstro terminou sem gerar ataque")
        if combate.get("ataque_pendente") and combate.get("ui_stage") != "attack":
            combate["fase"] = "defesa"
            await self._mostrar_ataque_ui(combate)

    async def _resolver_ataque(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return
        ataque = combate.get("ataque_pendente")
        if not ataque or ataque.get("_resolvendo"):
            return
        participante_snapshots = [(p, copy.deepcopy(p)) for p in combate.get("participantes", [])]
        estado_anterior = {
            "ataque_pendente": copy.deepcopy(ataque),
            "fase": combate.get("fase", "defesa"),
            "ui_stage": combate.get("ui_stage", "attack"),
            "ui_waiting_advance": combate.get("ui_waiting_advance", False),
            "aguardando_finalizacao": combate.get("aguardando_finalizacao", False),
            "vencedor_id": combate.get("vencedor_id"),
            "perdedor_id": combate.get("perdedor_id"),
            "historico": list(combate.get("historico", [])),
        }
        atacante = self._por_id(combate, ataque.get("atacante_id"))
        defensor = self._por_id(combate, ataque.get("defensor_id"))
        ataque["_resolvendo"] = True
        try:
            if not atacante or not defensor:
                combate["historico"].append("Ataque pendente descartado: participante ausente.")
                combate["ataque_pendente"] = None
                combate["fase"] = "ataque"
                combate["ui_stage"] = "turn"
                self._limpar_defesas(combate)
                await self._salvar(combate)
                await self._proximo_turno(ctx)
                return
            if not _vivo(atacante) or not _vivo(defensor):
                combate["historico"].append("Ataque pendente descartado: participante derrotado.")
                combate["ataque_pendente"] = None
                combate["fase"] = "ataque"
                combate["ui_stage"] = "turn"
                self._limpar_defesas(combate)
                await self._salvar(combate)
                await self._proximo_turno(ctx)
                return
            duelo_pendente = False
            if ataque.get("tipo") == "magia" and float(ataque.get("cura_base", 0) or 0) > 0:
                cura = int(float(atacante.get("Magia", atacante.get("magia", 0)) or 0) + float(atacante.get("Inteligencia", atacante.get("Inteligência", 0)) or 0) + float(ataque.get("cura_base", 0) or 0))
                atacante["vida"] = min(int(float(atacante.get("vida_maxima", atacante.get("vida", 0)) or 0)), int(float(atacante.get("vida", 0) or 0)) + cura)
                mensagem = f"✨ **{atacante.get('nome')}** recuperou **{cura} de vida**."
            else:
                if ataque.get("tipo") == "magia":
                    dano, resultado = self._dano_magia(atacante, defensor, ataque)
                    tipo_texto = "mágico"
                else:
                    dano, resultado = self._dano_fisico(atacante, defensor, ataque)
                    tipo_texto = ""
                if resultado == "esquivou":
                    mensagem = f"💨 **{defensor.get('nome')}** esquivou do ataque!"
                else:
                    vida_antes = int(float(defensor.get("vida", 0) or 0))
                    if combate.get("assentamento_duelo") and dano >= vida_antes:
                        dano = max(0, vida_antes - 1)
                        duelo_pendente = True
                    defensor["vida"] = max(0, vida_antes - dano)
                    mensagem = (f"✨ **{atacante.get('nome')}** causou **{dano} de dano mágico** em **{defensor.get('nome')}**."
                                if tipo_texto else f"⚔️ **{atacante.get('nome')}** causou **{dano} de dano** em **{defensor.get('nome')}**.")
                    efeito = self._aplicar_efeito(defensor, ataque.get("efeito"))
                    if efeito:
                        mensagem += f"\n⚠️ Efeito: **{efeito.title()}**."
                    if combate.get("assentamento_duelo") and defensor.get("vida", 0) <= 0:
                        defensor["vida"] = 1
                        duelo_pendente = True
            if ataque.get("area"):
                alvos_area = []
                vistos = {str(defensor.get("id"))}
                for alvo in ataque.get("area_targets", []) or []:
                    alvo_id = str((alvo or {}).get("id"))
                    if alvo_id in vistos:
                        continue
                    alvo_real = self._por_id(combate, alvo_id)
                    if alvo_real and _vivo(alvo_real):
                        vistos.add(alvo_id)
                        alvos_area.append(alvo_real)
                for alvo in alvos_area:
                    dano_area, resultado_area = (
                        self._dano_magia(atacante, alvo, ataque)
                        if ataque.get("tipo") == "magia"
                        else self._dano_fisico(atacante, alvo, ataque)
                    )
                    if resultado_area == "esquivou":
                        mensagem += f"\n💨 **{alvo.get('nome')}** esquivou da área do ataque."
                        continue
                    vida_area = int(float(alvo.get("vida", 0) or 0))
                    alvo["vida"] = max(0, vida_area - max(0, int(dano_area)))
                    efeito_area = self._aplicar_efeito(alvo, ataque.get("efeito"))
                    mensagem += f"\n🔥 **{alvo.get('nome')}** sofreu **{max(0, int(dano_area))} de dano**."
                    if efeito_area:
                        mensagem += f" Efeito: **{str(efeito_area).title()}**."
            combate["historico"].append(mensagem)
            self._limpar_defesas(combate)
            combate["ataque_pendente"] = None
            combate["fase"] = "ataque"
            combate["ui_stage"] = "result"
            combate["ui_waiting_advance"] = True
            embed = discord.Embed(title="💥 Resultado", description=mensagem, color=discord.Color.red())
            embed.add_field(name="📋 Status", value=self._texto_status(combate["participantes"]), inline=False)
            await self._ui_editar(combate, embed)
            if combate.get("assentamento_duelo") and duelo_pendente:
                await self._finalizar_duelo_assentamento(ctx, atacante, defensor)
                return
            if combate.get("pvp") and not _vivo(defensor):
                combate["aguardando_finalizacao"] = True
                combate["vencedor_id"] = str(atacante.get("id"))
                combate["perdedor_id"] = str(defensor.get("id"))
                combate["fase"] = "finalizacao"
                await self._salvar(combate)
                return
            resultado = self._condicao_vitoria(combate)
            if resultado:
                combate["ui_waiting_advance"] = False
                await self._finalizar(self._ui_context(ctx, combate), motivo="vida", vencedor=atacante, perdedor=defensor)
                return
            await self._salvar(combate)
        except Exception:
            for participante, snapshot in participante_snapshots:
                participante.clear()
                participante.update(snapshot)
            combate["ataque_pendente"] = estado_anterior["ataque_pendente"]
            combate["fase"] = estado_anterior["fase"]
            combate["ui_stage"] = estado_anterior["ui_stage"]
            combate["ui_waiting_advance"] = estado_anterior["ui_waiting_advance"]
            combate["aguardando_finalizacao"] = estado_anterior["aguardando_finalizacao"]
            if estado_anterior["vencedor_id"] is None:
                combate.pop("vencedor_id", None)
            else:
                combate["vencedor_id"] = estado_anterior["vencedor_id"]
            if estado_anterior["perdedor_id"] is None:
                combate.pop("perdedor_id", None)
            else:
                combate["perdedor_id"] = estado_anterior["perdedor_id"]
            combate["historico"] = estado_anterior["historico"]
            if combate.get("ataque_pendente"):
                combate["ataque_pendente"].pop("_resolvendo", None)
            raise
        finally:
            if combate.get("ataque_pendente") is ataque:
                ataque.pop("_resolvendo", None)

    async def executar_defesa_jogador(self, ctx, acao, embed=None):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            await ctx.send("❌ Não há combate ativo.")
            return
        ataque = combate.get("ataque_pendente")
        if combate.get("fase") != "defesa" or not ataque:
            await self._ui_context(ctx, combate).send("❌ Não há ataque pendente para defender.", _luta_error=True)
            return
        defensor = self._obter_defensor(combate)
        if not defensor or str(defensor.get("id")) != str(ctx.author.id):
            nome = defensor.get("nome", "outro jogador") if defensor else "outro jogador"
            await self._ui_context(ctx, combate).send(f"❌ É **{nome}** quem deve defender este ataque.", _luta_error=True)
            return
        self._limpar_defesas(combate)
        defensor["defesa_ativa"] = acao == "defesa"
        defensor["esquiva_ativa"] = acao == "esquiva"
        combate["ui_stage"] = "resolving"
        combate["ui_waiting_advance"] = False
        try:
            await self._resolver_ataque(self._ui_context(ctx, combate))
        except Exception as erro:
            for participante in combate.get("participantes", []):
                participante["defesa_ativa"] = False
                participante["esquiva_ativa"] = False
            if combate.get("ataque_pendente") is ataque and combate.get("ativo"):
                combate["fase"] = "defesa"
                combate["ui_stage"] = "defense_action"
                await self._ui_context(ctx, combate).send(f"❌ Erro ao resolver a defesa: `{type(erro).__name__}: {erro}`.", _luta_error=True)
            return

    async def _limpar_recursos_combate(self, channel_id, combate):
        self._embeds_acao.pop(channel_id, None)
        mensagem = combate.get("ui_message")
        if mensagem is not None:
            view = self._ui_views.pop(mensagem.id, None)
            if view is not None:
                view.stop()
            getattr(self, "_ui_avancar_locks", {}).pop(mensagem.id, None)

    def _dano_fisico(self, atacante, defensor, ataque):
        if defensor.get("esquiva_ativa"):
            defensor["esquiva_ativa"] = False
            velocidade = float(defensor.get("Velocidade", defensor.get("velocidade", 0)) or 0)
            destreza = float(defensor.get("Destreza", defensor.get("destreza", 0)) or 0)
            if __import__("random").random() < min(0.75, 0.10 + (velocidade + destreza) / 500):
                return 0, "esquivou"
        dano = float(atacante.get("Força", atacante.get("forca", 0)) or 0) + float(atacante.get("Velocidade", atacante.get("velocidade", 0)) or 0)
        dano += float(ataque.get("dano_base", 0) or 0)
        if ataque.get("com_arma"):
            dano += float(atacante.get("dano_arma", 0) or 0)
        if defensor.get("defesa_magica_ativa"):
            dano -= float(defensor.get("defesa_magica_valor", 0) or 0)
            defensor["defesa_magica_ativa"] = False
            defensor["defesa_magica_valor"] = 0
        elif defensor.get("defesa_ativa"):
            defesa_total = float(defensor.get("Força", defensor.get("forca", 0)) or 0) + float(defensor.get("Defesa", defensor.get("defesa", 0)) or 0)
            dano *= 1.0 - min(1.0, max(0.0, defesa_total) / 300.0)
        defensor["defesa_ativa"] = False
        dano = max(0, int(dano))
        combate = self._obter_combate_por_participantes(defensor)
        dano = boss_rules.corrosao(dano, defensor)
        return boss_rules.regras_dano(dano, "atingiu", atacante, defensor, ataque, combate)

    def _dano_magia(self, atacante, defensor, ataque):
        if defensor.get("esquiva_ativa"):
            defensor["esquiva_ativa"] = False
            velocidade = float(defensor.get("Velocidade", defensor.get("velocidade", 0)) or 0)
            if __import__("random").random() < min(0.75, 0.10 + velocidade / 500):
                return 0, "esquivou"
        dano = float(atacante.get("Magia", atacante.get("magia", 0)) or 0) + float(atacante.get("Inteligencia", atacante.get("Inteligência", 0)) or 0)
        dano += float(ataque.get("dano_base", 0) or 0)
        if defensor.get("defesa_magica_ativa"):
            dano -= float(defensor.get("defesa_magica_valor", 0) or 0)
            defensor["defesa_magica_ativa"] = False
            defensor["defesa_magica_valor"] = 0
        elif defensor.get("defesa_ativa"):
            dano -= float(defensor.get("Defesa", defensor.get("defesa", 0)) or 0) * 0.5
        defensor["defesa_ativa"] = False
        dano = max(0, int(dano))
        combate = self._obter_combate_por_participantes(defensor)
        dano = boss_rules.corrosao(dano, defensor)
        return boss_rules.regras_dano(dano, "atingiu", atacante, defensor, ataque, combate)

    def _aplicar_efeito(self, defensor, efeito):
        if not isinstance(efeito, dict):
            return None
        especial = boss_rules.efeito_especial(defensor, efeito)
        if especial is not None:
            return especial
        nome = str(efeito.get("nome", efeito.get("tipo", ""))).strip().lower()
        if not nome:
            return None
        turnos = max(1, int(float(efeito.get("turnos", efeito.get("duracao", 1)) or 1)))
        valor = int(float(efeito.get("valor", 5) or 5))
        entrada = {"nome": nome, "turnos": turnos, "valor": valor}
        defensor.setdefault("efeitos", []).append(entrada)
        return nome

    async def _aplicar_efeitos_inicio(self, ctx, participante):
        combate = self._obter_combate(ctx.channel.id)
        boss_rules.inicio_especial(combate or {}, participante)
        dano_total = 0
        bloqueado = False
        novos = []
        for efeito in list(participante.get("efeitos", []) or []):
            if not isinstance(efeito, dict):
                continue
            nome = str(efeito.get("nome", efeito.get("tipo", ""))).strip().lower()
            valor = max(0, int(float(efeito.get("valor", 5) or 5)))
            if nome in {"veneno", "queimadura", "sangramento"}:
                dano_total += valor
            elif nome == "sangramento_profundo":
                defesa = float(participante.get("Defesa", participante.get("defesa", 0)) or 0) + float(participante.get("Força", participante.get("forca", 0)) or 0)
                dano_total += max(1, int(valor - defesa * 0.5))
            if nome in {"paralisia", "stun", "prisao", "prisão"}:
                bloqueado = True
            turnos = int(float(efeito.get("turnos", 1) or 1)) - 1
            if turnos > 0:
                copia = dict(efeito); copia["turnos"] = turnos; novos.append(copia)
        participante["efeitos"] = novos
        if dano_total:
            participante["vida"] = max(0, int(float(participante.get("vida", 0) or 0)) - dano_total)
            await ctx.send(f"⚠️ **{participante.get('nome')}** sofreu **{dano_total}** de efeitos.")
        return bloqueado

    def _obter_combate_por_participantes(self, participante):
        """Busca por identidade do objeto, evitando colisões de IDs entre combates."""
        if participante is None:
            return {}
        for combate in self.combates.values():
            if any(p is participante for p in combate.get("participantes", [])):
                return combate
        return {}
    
    def _limpar_defesas(self, combate):
        for participante in combate.get("participantes", []):
            participante["defesa_ativa"] = False
            participante["esquiva_ativa"] = False
            participante["defesa_magica_ativa"] = False
            participante["defesa_magica_valor"] = 0

    async def _recompensar(self, combate):
        """Único cálculo de recompensa; protegido contra aplicação duplicada."""
        if combate.get("recompensa_aplicada"):
            return (int(combate.get("recompensa_xp", 0)), int(combate.get("recompensa_hunos", 0)), int(combate.get("recompensa_tp", 0)))
        if self._condicao_vitoria(combate) != "jogadores" or luta_db.db is None:
            return 0, 0, 0
        monstros = [p for p in combate.get("participantes", [])
                    if p.get("tipo") == "monstro" and not p.get("invocado") and _vivo(p) is False]
        xp_total = sum(int(float(p.get("xp_recompensa", 0) or 0)) for p in monstros)
        tp_total = sum(int(float(p.get("tp_recompensa", p.get("xp_recompensa", 0)) or 0)) for p in monstros)
        hunos_total = sum(int(float(p.get("hunos_recompensa", 0) or 0)) for p in monstros)
        vivos = [p for p in combate.get("participantes", [])
                 if p.get("tipo") == "jogador" and _vivo(p)]
        if not vivos:
            return xp_total, hunos_total, tp_total
        guild_id = str(combate.get("guild_id"))
        for i, jogador in enumerate(vivos):
            xp = xp_total // len(vivos) + (i < xp_total % len(vivos))
            tp = tp_total // len(vivos) + (i < tp_total % len(vivos))
            hunos = hunos_total // len(vivos) + (i < hunos_total % len(vivos))
            filtro = {"ID": str(jogador.get("id")), "guild_id": guild_id}
            await luta_db.run_db(luta_db.db["Jogadores"].update_one, filtro, {"$inc": {"XP": int(xp), "TP": int(tp)}})
            await luta_db.run_db(luta_db.db["Hunos"].update_one, filtro, {"$inc": {"carteira": int(hunos)}}, upsert=True)
        combate["recompensa_aplicada"] = True
        combate["recompensa_xp"] = xp_total
        combate["recompensa_hunos"] = hunos_total
        combate["recompensa_tp"] = tp_total
        return xp_total, hunos_total, tp_total

    async def _finalizar(self, ctx, motivo="vida", vencedor=None, perdedor=None):
        combate = self._obter_combate(ctx.channel.id)
        if not combate:
            return
        estado_anterior = {
            "ativo": combate.get("ativo", True), "fase": combate.get("fase", "ataque"),
            "ui_stage": combate.get("ui_stage", "turn"), "ui_waiting_advance": combate.get("ui_waiting_advance", False),
            "ataque_pendente": combate.get("ataque_pendente"),
        }
        resultado = self._condicao_vitoria(combate)
        if resultado is None and motivo in {"vida", "efeitos"}:
            combate["ativo"] = True
            combate["fase"] = "ataque"
            combate["ataque_pendente"] = None
            combate["ui_waiting_advance"] = False
            await self._proximo_turno(ctx)
            return
        combate["ativo"] = False
        combate["fase"] = "finalizado"
        try:
            await self._salvar(combate)
            xp = hunos = tp = 0
            if not combate.get("pvp") and resultado == "jogadores":
                xp, hunos, tp = await self._recompensar(combate)
            descricao = (
                f"💀 **{vencedor.get('nome')}** finalizou **{perdedor.get('nome')}** ({motivo})."
                if combate.get("pvp") and vencedor and perdedor else
                "🏆 Os jogadores venceram o combate!" if resultado == "jogadores" else
                "💀 Os jogadores foram derrotados." if resultado == "inimigos" else
                "⚖️ O combate terminou em empate."
            )
            embed = discord.Embed(title="⚔️ Combate Finalizado", description=descricao, color=discord.Color.green() if resultado == "jogadores" else discord.Color.red())
            embed.add_field(name="🎁 Recompensas", value=f"✨ XP: **{xp}**\n🔷 TP: **{tp}**\n💰 Hunos: **{hunos}**", inline=False)
            embed.add_field(name="📋 Status", value=self._texto_status(combate["participantes"]), inline=False)
            await ctx.send(embed=embed)
            await self._limpar_recursos_combate(ctx.channel.id, combate)
            self.combates.pop(ctx.channel.id, None)
        except Exception:
            combate.update(estado_anterior)
            if combate.get("ativo"):
                combate["fase"] = "defesa" if combate.get("ataque_pendente") else estado_anterior["fase"]
                combate["ui_stage"] = "attack" if combate.get("ataque_pendente") else estado_anterior["ui_stage"]
            try:
                await self._salvar(combate)
            except Exception as save_erro:
                print(f"[LUTA][ROLLBACK][ERRO] {type(save_erro).__name__}: {save_erro}")
            raise

    async def _abandonar_combate(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return False
        snapshot = {"ativo": combate.get("ativo", True), "fase": combate.get("fase", "ataque"),
                    "ataque_pendente": copy.deepcopy(combate.get("ataque_pendente")),
                    "ui_stage": combate.get("ui_stage", "turn")}
        try:
            combate["ativo"] = False
            combate["fase"] = "finalizado"
            combate["ataque_pendente"] = None
            self._limpar_defesas(combate)
            await self._salvar(combate)
            jogadores = [p for p in combate.get("participantes", []) if p.get("tipo") == "jogador"]
            await self._marcar_combate(jogadores, str(combate.get("guild_id")), "ativo")
            await self._limpar_recursos_combate(ctx.channel.id, combate)
            self.combates.pop(ctx.channel.id, None)
            return True
        except Exception:
            combate.update(snapshot)
            raise

    async def _finalizar_pvp(self, ctx, motivo):
        """Finaliza PvP somente quando existe uma vitória pendente válida."""
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            await ctx.send("❌ Não há combate PvP ativo.")
            return
        if not combate.get("pvp") or not combate.get("aguardando_finalizacao"):
            await ctx.send("❌ Este combate não está aguardando finalização PvP.")
            return
        vencedor = self._por_id(combate, combate.get("vencedor_id"))
        perdedor = self._por_id(combate, combate.get("perdedor_id"))
        if not vencedor or not perdedor:
            raise RuntimeError("finalização PvP sem vencedor ou perdedor válido")
        if str(vencedor.get("id")) != str(getattr(ctx.author, "id", "")):
            await ctx.send("❌ Apenas o vencedor do turno decisivo pode finalizar este PvP.")
            return
        if motivo not in {"morte", "desmaio"}:
            raise ValueError("motivo de finalização PvP inválido")
        if motivo == "morte":
            perdedor["vida"] = 0
        else:
            perdedor["vida"] = max(1, int(float(perdedor.get("vida", 0) or 0)))
        combate["aguardando_finalizacao"] = False
        combate["fase"] = "finalizacao"
        await self._finalizar(ctx, motivo=motivo, vencedor=vencedor, perdedor=perdedor)

    async def avancar(self, interaction: discord.Interaction):
        channel_id = interaction.channel.id
        lock = self._lock(channel_id)
        if lock.locked():
            msg = "⏳ Aguarde a ação de combate anterior terminar."
            if not interaction.response.is_done(): await interaction.response.send_message(msg, ephemeral=True)
            else: await interaction.followup.send(msg, ephemeral=True)
            return
        async with lock:
            return await self._avancar_locked(interaction)

    async def _avancar_locked(self, interaction: discord.Interaction):
        combate = self._obter_combate(interaction.channel.id)
        if not combate or not combate.get("ativo"):
            return await super().avancar(interaction)
        mensagem = combate.get("ui_message")
        if mensagem is None or interaction.message is None or interaction.message.id != mensagem.id:
            msg = "❌ Esta tela não pertence ao combate atual."
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
            return
        if combate.get("ui_owner_id") is not None and str(combate["ui_owner_id"]) != str(interaction.user.id):
            msg = "❌ Apenas o jogador deste combate pode avançar a tela."
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
            return
        if not interaction.response.is_done():
            await interaction.response.defer()
        self._normalizar_estado(combate)
        try:
            stage = combate.get("ui_stage", "attributes")
            if combate.get("ataque_pendente"):
                await self._mostrar_ataque_ui(combate)
                return
            if stage == "attributes":
                combate["ui_stage"] = "velocity"
                await self._ui_editar(combate, self._embed_velocidade(combate))
            elif stage == "velocity":
                if (self._obter_atacante(combate) or {}).get("tipo") == "monstro":
                    await self._criar_ataque_monstro_ui(combate)
                else:
                    combate["ui_stage"] = "player_action"
                    await self._ui_editar(combate, self._embed_aguarde_jogador(combate))
            elif stage == "attack":
                defensor = self._obter_defensor(combate)
                if defensor and defensor.get("tipo") == "monstro":
                    self._limpar_defesas(combate)
                    await self._resolver_ataque(self._ui_context(interaction, combate))
                else:
                    combate["ui_stage"] = "defense_action"
                    await self._ui_editar(combate, self._embed_defesa(combate))
            elif stage == "result":
                combate["ui_waiting_advance"] = False
                await self._proximo_turno(interaction)
            elif stage == "turn":
                atacante = self._obter_atacante(combate)
                if atacante and atacante.get("tipo") == "monstro":
                    await self._criar_ataque_monstro_ui(combate)
                else:
                    combate["ui_stage"] = "player_action"
                    await self._ui_editar(combate, self._embed_aguarde_jogador(combate))
            elif stage == "player_action":
                await self._ui_editar(combate, self._embed_aguarde_jogador(combate))
            elif stage == "defense_action":
                await self._ui_editar(combate, self._embed_defesa(combate))
            elif stage == "resolving":
                await interaction.followup.send("❌ A defesa está sendo processada. Aguarde o resultado.", ephemeral=True)
        except Exception as erro:
            combate["ui_waiting_advance"] = False
            if combate.get("ataque_pendente"):
                combate["fase"] = "defesa"
                combate["ui_stage"] = "attack"
            else:
                combate["fase"] = "ataque"
                combate["ui_stage"] = "turn"
            print(f"[LUTA][AVANCAR][ERRO] {type(erro).__name__}: {erro}")
            msg = f"❌ Não foi possível avançar: `{type(erro).__name__}`. O estado foi preservado."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
    async def _proximo_turno(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return
        if combate.get("ui_message"):
            if combate.get("ui_waiting_advance"):
                return
            resultado = self._condicao_vitoria(combate)
            if resultado:
                await self._finalizar(self._ui_context(ctx, combate), motivo="vida")
                return
            boss_rules.preparar_proximo_turno(combate)
            atual_id = combate.get("_turno_participante_id")
            expirados = {str(x) for x in combate.pop("_participantes_expirados", set())}
            if expirados:
                combate["participantes"] = [p for p in combate.get("participantes", []) if str(p.get("id")) not in expirados]
            if not combate.get("participantes"):
                await self._finalizar(self._ui_context(ctx, combate), motivo="vida")
                return
            if atual_id is not None:
                atual_index = next((i for i,p in enumerate(combate["participantes"]) if str(p.get("id")) == str(atual_id)), -1)
            else:
                atual_index = int(combate.get("turno", 0)) % len(combate["participantes"])
            proximo = self._proximo_indice(combate, atual_index if atual_index >= 0 else -1)
            if proximo is None:
                await self._finalizar(self._ui_context(ctx, combate), motivo="vida")
                return
            combate["turno"] = proximo
            combate["_turno_participante_id"] = combate["participantes"][proximo].get("id")
            combate["numero_turno"] = int(combate.get("numero_turno", 1)) + 1
            combate["fase"] = "ataque"
            combate["ataque_pendente"] = None
            combate["ui_stage"] = "turn"
            combate["ui_waiting_advance"] = False
            self._limpar_defesas(combate)
            atacante = self._obter_atacante(combate)
            if not atacante:
                await self._finalizar(self._ui_context(ctx, combate), motivo="vida")
                return
            ui_ctx = self._ui_context(ctx, combate)
            bloqueado = await self._aplicar_efeitos_inicio(ui_ctx, atacante)
            if not _vivo(atacante):
                await self._salvar(combate)
                await self._finalizar(ui_ctx, motivo="efeitos")
                return
            if bloqueado:
                combate["ui_stage"] = "result"
                combate["ui_waiting_advance"] = True
                await self._ui_editar(combate, self._acao_embed(atacante=atacante, defensor=atacante,
                    nome="Stun", emoji="💫", turno=combate.get("numero_turno",1), dano=0,
                    mana=atacante.get("mana",0), descricao=f"**{atacante.get('nome')}** perdeu este turno."))
                return
            await self._ui_editar(combate, self._embed_turno_monstro(combate) if atacante.get("tipo")=="monstro" else self._embed_aguarde_jogador(combate))
            return
        return await super()._proximo_turno(ctx)

