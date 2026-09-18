"""Motor de combate com interface de mensagem única e navegação por Avançar."""
from __future__ import annotations

import asyncio
import random

import discord

from database.python import luta as luta_db
from ..luta import Luta as _LutaLegada, _vivo
from .Infos_Luta import obter_monstro
from .Mensagens_luta import imagem_golpe, painel


class _UIContext:
    """Adapta Context/Interaction para manter todo o combate em uma mensagem."""

    def __init__(self, original, message, combate=None, owner=None):
        self._original = original
        self._message = message
        self._combate = combate or {}
        self._owner = owner

    @property
    def author(self):
        return getattr(self._original, "user", getattr(self._original, "author", None))

    @property
    def channel(self):
        return self._message.channel

    @property
    def guild(self):
        return self._message.guild

    def __getattr__(self, name):
        return getattr(self._original, name)

    async def send(self, content=None, **kwargs):
        """Atualiza a tela única sem perder o estado do combate."""
        combate = self._combate
        atacante = self._get_participante(combate, combate.get("vencedor_id")) or self._atacante(combate) or {}
        defensor = self._get_participante(combate, combate.get("perdedor_id")) or self._defensor(combate) or {}
        embed = kwargs.get("embed")
        extra = content or ""
        if embed is not None and embed.description:
            extra = embed.description if not extra else f"{extra}\n{embed.description}"
        padrao = painel(
            atacante=atacante.get("nome", "User"), ataque="resultado", vida=self._vida(atacante),
            mana=atacante.get("mana", 0), dano="-", efeito="Nenhum", alvo=defensor.get("nome", "-"),
            turno=combate.get("numero_turno", 1), oponente=defensor, vida_oponente=self._vida(defensor),
            extra=extra or "Atualização do combate.", cor=discord.Color.blurple(),
        )
        view = self._owner._ui_views.get(self._message.id) if self._owner else None
        if view is None and self._owner:
            view = _AvancarView(self._owner)
            self._owner._ui_views[self._message.id] = view
        if self._owner is not None:
            await self._owner._ui_editar(combate, padrao, view=True)
        else:
            await self._message.edit(embed=padrao, attachments=[], view=view)
        return self._message

    @staticmethod
    def _vida(p):
        if not p:
            return "-"
        vida = max(0, int(float(p.get("vida", 0) or 0)))
        maxima = max(1, int(float(p.get("vida_maxima", vida) or 1)))
        return f"{vida}/{maxima}"

    @staticmethod
    def _get_participante(combate, participante_id):
        if participante_id is None:
            return None
        return next((p for p in combate.get("participantes", []) if str(p.get("id")) == str(participante_id)), None)

    @staticmethod
    def _atacante(combate):
        """Resolve o atacante pela mesma fonte de verdade do motor."""
        participantes = combate.get("participantes", [])
        if not participantes:
            return None
        ataque = combate.get("ataque_pendente") or {}
        atacante_id = ataque.get("atacante_id")
        if atacante_id is not None:
            return next((p for p in participantes if str(p.get("id")) == str(atacante_id)), None)
        indice = int(combate.get("turno", 0)) % len(participantes)
        return participantes[indice]

    @staticmethod
    def _defensor(combate):
        ataque = combate.get("ataque_pendente") or {}
        if ataque.get("defensor_id") is not None:
            return _UIContext._get_participante(combate, ataque.get("defensor_id"))
        return None


class _AvancarView(discord.ui.View):
    def __init__(self, cog, timeout=7200):
        super().__init__(timeout=timeout)
        self.cog = cog
        botao = discord.ui.Button(label="Avançar", emoji="▶️", style=discord.ButtonStyle.primary, custom_id="luta:avancar")
        botao.callback = self._callback
        self.add_item(botao)

    async def _callback(self, interaction: discord.Interaction):
        # O callback sempre responde ao Discord, mesmo se alguma etapa do motor falhar.
        try:
            await self.cog.avancar(interaction)
        except Exception as erro:
            print(f"[LUTA][UI][AVANCAR][ERRO] {type(erro).__name__}: {erro}")
            try:
                if interaction.response.is_done():
                    await interaction.followup.send("❌ Erro ao avançar o combate. O estado foi preservado.", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ Erro ao avançar o combate. O estado foi preservado.", ephemeral=True)
            except Exception as resposta_erro:
                print(f"[LUTA][UI][AVANCAR][RESPOSTA][ERRO] {type(resposta_erro).__name__}: {resposta_erro}")


class Luta(_LutaLegada):
    """PvE/PvP usa uma única mensagem; cada avanço só troca os dados da interface."""

    def __init__(self, bot):
        super().__init__(bot)
        self._embeds_acao = {}
        self._ui_views = {}

    def _encontrar_monstro(self, nome):
        monstro_id, _ = obter_monstro(nome)
        return monstro_id

    def _vida(self, participante):
        participante = participante or {}
        vida = max(0, int(float(participante.get("vida", 0) or 0)))
        maxima = max(1, int(float(participante.get("vida_maxima", vida) or 1)))
        return f"{vida}/{maxima}"

    def _acao_embed(self, *, atacante, defensor, nome, emoji, turno, dano, mana, descricao, efeito="Nenhum"):
        return painel(
            atacante=atacante.get("nome", "User"), ataque=f"{emoji} {nome}", vida=self._vida(atacante), mana=mana,
            dano=dano, efeito=efeito or "Nenhum", alvo=defensor.get("nome", "-"), turno=turno,
            oponente=defensor, vida_oponente=self._vida(defensor), extra=descricao, cor=discord.Color.blurple(),
        )

    async def _ui_editar(self, combate, embed, view=True):
        mensagem = combate.get("ui_message")
        if mensagem is None:
            return
        if not isinstance(embed, discord.Embed):
            embed = painel(extra=str(embed))
        kwargs = {"embed": embed, "attachments": []}
        if view:
            view_obj = self._ui_views.get(mensagem.id)
            if view_obj is None:
                view_obj = _AvancarView(self)
                self._ui_views[mensagem.id] = view_obj
            kwargs["view"] = view_obj
        else:
            kwargs["view"] = None
        await mensagem.edit(**kwargs)

    def _ui_context(self, ctx, combate):
        mensagem = combate.get("ui_message")
        return _UIContext(ctx, mensagem, combate, self) if mensagem is not None else ctx

    def _embed_velocidade(self, combate):
        ordem = "\n".join(f"{i + 1}. {p.get('nome', 'Desconhecido')} — {int(float(p.get('Velocidade', p.get('velocidade', 0)) or 0))} Vel." for i, p in enumerate(combate.get("participantes", []))) or "Nenhum participante."
        atacante = self._obter_atacante(combate) or {}
        return painel(atacante=atacante.get("nome", "User"), ataque="ordem de velocidade", vida=self._vida(atacante), mana=atacante.get("mana", 0), dano="-", efeito="-", alvo="Todos", turno=combate.get("numero_turno", 1), oponente="Todos", vida_oponente="-", extra=ordem, cor=discord.Color.blurple())

    def _embed_aguarde_jogador(self, combate):
        atacante = self._obter_atacante(combate) or {}
        defensor = self._obter_defensor(combate) or {}
        return self._acao_embed(atacante=atacante, defensor=defensor, nome="Sua vez", emoji="👤", turno=combate.get("numero_turno", 1), dano=0, mana=atacante.get("mana", 0), descricao=f"Use `!soco` ou `!chute` para atacar **{defensor.get('nome', '-')}**.")

    def _embed_turno_monstro(self, combate):
        atacante = self._obter_atacante(combate) or {}
        defensor = self._obter_defensor(combate) or {}
        return self._acao_embed(atacante=atacante, defensor=defensor, nome="Vez do monstro", emoji="👹", turno=combate.get("numero_turno", 1), dano=0, mana=0, descricao=f"**{atacante.get('nome', 'Monstro')}** está pronto para atacar.")

    def _embed_defesa(self, combate):
        ataque = combate.get("ataque_pendente") or {}
        defensor = self._obter_defensor(combate) or {}
        atacante = self._participante(combate, ataque.get("atacante_id")) or {}
        return self._acao_embed(atacante=atacante, defensor=defensor, nome="Defenda-se", emoji="🛡️", turno=combate.get("numero_turno", 1), dano=ataque.get("dano_base", 0), mana=0, descricao=f"**{defensor.get('nome', 'Jogador')}**, use `!defesa` ou `!esquiva`.")

    async def _mostrar_ataque_ui(self, combate):
        ataque = combate.get("ataque_pendente") or {}
        atacante = self._participante(combate, ataque.get("atacante_id"))
        defensor = self._participante(combate, ataque.get("defensor_id"))
        if not ataque or not atacante or not defensor:
            return
        efeito = ataque.get("efeito") or {}
        if isinstance(efeito, dict):
            efeito = efeito.get("nome", efeito.get("tipo", "Nenhum"))
        embed = self._acao_embed(atacante=atacante, defensor=defensor, nome=ataque.get("nome", "Ataque"), emoji="👹" if atacante.get("tipo") == "monstro" else "⚔️", turno=combate.get("numero_turno", 1), dano=ataque.get("dano_base", 0), mana=ataque.get("mana_base", 0), descricao=f"**{atacante.get('nome')}** atacou **{defensor.get('nome')}**.", efeito=efeito)
        url = imagem_golpe(ataque.get("tipo")) or imagem_golpe(ataque.get("nome"))
        if url:
            embed.set_image(url=url)
        await self._ui_editar(combate, embed)

    async def mostrar_ataque(self, ctx, embed, arquivo=None):
        combate = self._obter_combate(ctx.channel.id)
        if combate and combate.get("ui_message"):
            await self._mostrar_ataque_ui(combate)
            combate["ui_stage"] = "attack"
            return
        if embed is not None:
            kwargs = {"embed": embed}
            if arquivo is not None:
                kwargs["file"] = arquivo
            await ctx.send(**kwargs)

    async def executar_ataque_jogador(self, ctx, tipo_ataque, embed):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            if combate and combate.get("ui_message"):
                await self._ui_context(ctx, combate).send("❌ Não há combate ativo.")
            else:
                await ctx.send("❌ Não há combate ativo.")
            return
        ui = self._ui_context(ctx, combate)
        if combate.get("aguardando_finalizacao"):
            await ui.send("❌ O combate aguarda a finalização PvP.")
            return
        if combate.get("fase") != "ataque":
            await ui.send("❌ O ataque anterior ainda não foi defendido.")
            return
        atacante = self._obter_atacante(combate)
        defensor = self._obter_defensor(combate)
        if not atacante or not defensor:
            return
        if atacante.get("tipo") != "jogador" or str(atacante.get("id")) != str(ctx.author.id):
            await ui.send(f"❌ É a vez de **{atacante.get('nome', 'outro jogador')}**.")
            return
        golpe = luta_db.GOLPES.get(tipo_ataque)
        if not isinstance(golpe, dict):
            await ui.send("Golpe não está configurado.")
            return
        tipo = str(golpe.get("tipo", "fisico") or "fisico")
        if tipo not in {"fisico", "magia"}:
            tipo = "fisico"
        self._criar_ataque(combate, tipo, atacante, defensor, nome=golpe.get("nome", tipo_ataque.title()), dano_base=float(golpe.get("dano_base", 0) or 0), com_arma=bool(golpe.get("com_arma")), efeito=golpe.get("efeito", {}))
        if combate.get("ui_message"):
            await self._mostrar_ataque_ui(combate)
            combate["ui_stage"] = "attack"
        else:
            await self.mostrar_ataque(ctx, embed)

    async def executar_defesa_jogador(self, ctx, acao, embed):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo") or combate.get("fase") != "defesa":
            if combate and combate.get("ui_message"):
                await self._ui_context(ctx, combate).send("❌ Não há ataque pendente para defender.")
            else:
                await ctx.send("❌ Não há ataque pendente para defender.")
            return
        defensor = self._obter_defensor(combate)
        if not defensor or defensor.get("tipo") != "jogador" or str(defensor.get("id")) != str(ctx.author.id):
            nome = defensor.get("nome", "outro jogador") if defensor else "outro jogador"
            await self._ui_context(ctx, combate).send(f"❌ É **{nome}** quem deve defender este ataque.")
            return
        defensor["defesa_ativa"] = acao == "defesa"
        defensor["esquiva_ativa"] = acao == "esquiva"
        if combate.get("ui_message"):
            combate["ui_waiting_advance"] = False
            await self._resolver_ataque(self._ui_context(ctx, combate))
        else:
            await self._resolver_ataque(ctx)

    async def _anunciar_ataque(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return
        ataque = combate.get("ataque_pendente")
        atacante = self._participante(combate, ataque.get("atacante_id")) if ataque else None
        defensor = self._participante(combate, ataque.get("defensor_id")) if ataque else None
        if not ataque or not atacante or not defensor:
            return
        if combate.get("ui_message"):
            await self._mostrar_ataque_ui(combate)
            combate["ui_stage"] = "attack"
            return
        embed = self._embeds_acao.pop(ctx.channel.id, None)
        embed = embed[0] if isinstance(embed, tuple) else embed
        await self.mostrar_ataque(ctx, embed)

    async def _mostrar_inicio(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return
        preparado = self._embeds_acao.pop(ctx.channel.id, None)
        arquivo = preparado[1] if isinstance(preparado, tuple) else None
        embed = preparado[0] if isinstance(preparado, tuple) else preparado
        if embed is None:
            atacante = self._obter_atacante(combate) or {}
            defensor = self._obter_defensor(combate) or {}
            embed = painel(atacante=atacante.get("nome", "User"), ataque="início do combate", vida=self._vida(atacante), mana=atacante.get("mana", 0), alvo=defensor.get("nome", "-"), turno=1, oponente=defensor, vida_oponente=self._vida(defensor), extra="Combate iniciado.", cor=discord.Color.red())
        if combate.get("ui_message"):
            await self._ui_editar(combate, embed)
            return
        kwargs = {"embed": embed}
        if arquivo is not None:
            kwargs["file"] = arquivo
        mensagem = await ctx.send(**kwargs)
        combate["ui_message"] = mensagem
        combate["ui_owner_id"] = getattr(ctx.author, "id", None)
        combate["ui_stage"] = "attributes"
        combate["ui_waiting_advance"] = True
        self._ui_views[mensagem.id] = _AvancarView(self)
        await self._ui_editar(combate, embed, view=True)

    async def avancar(self, interaction: discord.Interaction):
        combate = self._obter_combate(interaction.channel.id)
        mensagem = combate.get("ui_message") if combate else None
        if not combate or not combate.get("ativo") or mensagem is None:
            if interaction.response.is_done():
                await interaction.followup.send("❌ Este combate não está mais ativo.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Este combate não está mais ativo.", ephemeral=True)
            return
        if interaction.message is None or interaction.message.id != mensagem.id:
            if interaction.response.is_done():
                await interaction.followup.send("❌ Esta tela não pertence ao combate atual.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Esta tela não pertence ao combate atual.", ephemeral=True)
            return
        if combate.get("ui_owner_id") is not None and str(combate.get("ui_owner_id")) != str(interaction.user.id):
            if interaction.response.is_done():
                await interaction.followup.send("❌ Apenas o jogador deste combate pode avançar a tela.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Apenas o jogador deste combate pode avançar a tela.", ephemeral=True)
            return
        if not interaction.response.is_done():
            await interaction.response.defer()
        stage = combate.get("ui_stage", "attributes")
        if stage == "attributes":
            combate["ui_stage"] = "velocity"
            await self._ui_editar(combate, self._embed_velocidade(combate))
        elif stage == "velocity":
            atacante = self._obter_atacante(combate)
            if atacante and atacante.get("tipo") == "monstro":
                await self._criar_ataque_monstro_ui(combate)
            else:
                combate["ui_stage"] = "player_action"
                await self._ui_editar(combate, self._embed_aguarde_jogador(combate))
        elif stage == "attack":
            defensor = self._obter_defensor(combate)
            if defensor and defensor.get("tipo") == "monstro":
                escolha = random.choice(("defesa", "esquiva", "normal"))
                defensor["defesa_ativa"] = escolha == "defesa"
                defensor["esquiva_ativa"] = escolha == "esquiva"
                combate["ui_waiting_advance"] = False
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

    async def _ataque_monstro(self, ctx):
        """Contrato legado mantido para extensões de balanceamento; o Cog efetivo sobrescreve este método."""
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return None
        ataque = combate.get("ataque_pendente")
        if ataque:
            combate["fase"] = "defesa"
            return ataque
        atacante = self._obter_atacante(combate)
        defensor = self._obter_defensor(combate)
        if not atacante or not defensor:
            raise RuntimeError("turno do monstro sem atacante/defensor válido")
        raise RuntimeError("implementação efetiva de ataque de monstro não carregada")

    async def _criar_ataque_monstro_ui(self, combate):
        atacante = self._obter_atacante(combate)
        defensor = self._obter_defensor(combate)
        if not atacante or not defensor:
            return
        ids = atacante.get("golpes", [])
        disponiveis = [luta_db.GOLPES[i] for i in ids if i in luta_db.GOLPES]
        golpe = random.choice(disponiveis) if disponiveis else {"nome": "Ataque do Monstro", "dano_base": atacante.get("dano_base", 10), "efeito": {}}
        self._criar_ataque(combate, "ataque_monstro", atacante, defensor, nome=f"{golpe.get('emoji', '👹')} {golpe.get('nome', 'Ataque do Monstro')}", dano_base=float(golpe.get("dano_base", 0) or 0), efeito=golpe.get("efeito", {}), com_arma=bool(golpe.get("com_arma")))
        combate["ui_stage"] = "attack"
        await self._mostrar_ataque_ui(combate)

    def _dano_fisico(self, atacante, defensor, ataque):
        """Defesa normal: Força + Defesa; 100 de defesa reduz 33,33% do dano."""
        if defensor.get("esquiva_ativa"):
            defensor["esquiva_ativa"] = False
            velocidade = float(defensor.get("Velocidade", defensor.get("velocidade", 0)) or 0)
            destreza = float(defensor.get("Destreza", defensor.get("destreza", 0)) or 0)
            chance = min(0.75, 0.10 + (velocidade + destreza) / 500)
            if random.random() < chance:
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
            forca = float(defensor.get("Força", defensor.get("forca", 0)) or 0)
            defesa = float(defensor.get("Defesa", defensor.get("defesa", 0)) or 0)
            defesa_total = max(0.0, forca + defesa)
            reducao = min(1.0, defesa_total / 300.0)
            dano *= 1.0 - reducao
        defensor["defesa_ativa"] = False
        return max(0, int(dano)), "atingiu"

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
            proximo = self._proximo_indice(combate, int(combate.get("turno", 0)))
            if proximo is None:
                await self._finalizar(self._ui_context(ctx, combate), motivo="vida")
                return
            combate["turno"] = proximo
            combate["numero_turno"] = int(combate.get("numero_turno", 1)) + 1
            combate["fase"] = "ataque"
            combate["ataque_pendente"] = None
            combate["ui_stage"] = "turn"
            combate["ui_waiting_advance"] = False
            for participante in combate.get("participantes", []):
                participante["defesa_ativa"] = False
                participante["esquiva_ativa"] = False
                participante["defesa_magica_ativa"] = False
                participante["defesa_magica_valor"] = 0
            atacante = self._obter_atacante(combate)
            if not atacante:
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
                await self._ui_editar(combate, painel(atacante=atacante.get("nome", "Participante"), ataque="stun", vida=self._vida(atacante), mana=atacante.get("mana", 0), dano=0, efeito="Stun", alvo="-", turno=combate.get("numero_turno", 1), oponente="-", vida_oponente="-", extra=f"**{atacante.get('nome', 'Participante')}** está atordoado e perde este turno.", cor=discord.Color.orange()))
                return
            combate["ui_stage"] = "turn"
            await self._ui_editar(combate, self._embed_turno_monstro(combate) if atacante.get("tipo") == "monstro" else self._embed_aguarde_jogador(combate))
            return
        return await super()._proximo_turno(ctx)

    async def _finalizar_pvp(self, ctx, motivo):
        combate = self._obter_combate(ctx.channel.id)
        preparado = self._embeds_acao.pop(ctx.channel.id, None)
        embed = preparado[0] if isinstance(preparado, tuple) else preparado
        if embed is not None and not (combate and combate.get("ui_message")):
            await ctx.send(embed=embed)
        return await super()._finalizar_pvp(ctx, motivo)

    def preparar_embed(self, ctx, embed, arquivo=None):
        self._embeds_acao[ctx.channel.id] = (embed, arquivo) if arquivo is not None else embed

    async def resultado_ataque(self, ctx):
        return await self._resolver_ataque(ctx)

    async def resultado_defesa(self, ctx, acao):
        return await self._defesa_jogador(ctx, acao)

    async def resultado_magia(self, ctx, dados_magia):
        return await self.usar_magia_no_combate(ctx, dados_magia)

    async def resultado_ataque_monstro(self, ctx):
        return await self._ataque_monstro(ctx)

    async def resultado_pvp(self, ctx, motivo):
        return await self._finalizar_pvp(ctx, motivo)

    async def resultado_final(self, ctx, motivo="vida", vencedor=None, perdedor=None):
        return await self._finalizar(ctx, motivo=motivo, vencedor=vencedor, perdedor=perdedor)


SistemaLuta = Luta
__all__ = ["Luta", "SistemaLuta"]
