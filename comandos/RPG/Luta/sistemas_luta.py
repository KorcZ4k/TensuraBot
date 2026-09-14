"""Motor de combate com interface de mensagem única e navegação por Avançar."""
from __future__ import annotations
import asyncio
import random
import discord
from database.python import luta as luta_db
from ..luta import Luta as _LutaLegada
from .Infos_Luta import obter_monstro
from .Mensagens_luta import imagem_golpe

class _UIContext:
    """Proxy que transforma ctx.send() do motor em edição da mensagem do combate."""
    def __init__(self, original, message, combate=None):
        self._original = original
        self._message = message
        self._combate = combate
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
        if content is not None:
            embed = kwargs.get("embed")
            if embed is None:
                embed = discord.Embed(description=str(content), color=discord.Color.blurple())
            else:
                embed.description = f"{embed.description or ''}\n\n{content}".strip()
            kwargs["embed"] = embed
        kwargs.pop("file", None)
        kwargs.pop("files", None)
        self._combate["ui_stage"] = "result"
        self._combate["ui_waiting_advance"] = True
        await self._message.edit(**kwargs)
        return self._message

class _AvancarView(discord.ui.View):
    def __init__(self, cog, timeout=7200):
        super().__init__(timeout=timeout)
        self.cog = cog
        botao = discord.ui.Button(label="Avançar", emoji="▶️", style=discord.ButtonStyle.primary, custom_id="luta:avancar")
        botao.callback = self._callback
        self.add_item(botao)
    async def _callback(self, interaction: discord.Interaction):
        await self.cog.avancar(interaction)

class Luta(_LutaLegada):
    """Motor único. O PvE usa uma única mensagem, editada tela a tela."""
    def __init__(self, bot):
        super().__init__(bot)
        self._embeds_acao = {}
        self._ui_views = {}

    def _encontrar_monstro(self, nome):
        monstro_id, _ = obter_monstro(nome)
        return monstro_id

    def _vida(self, participante):
        vida = max(0, int(float((participante or {}).get("vida", 0) or 0)))
        maxima = max(1, int(float((participante or {}).get("vida_maxima", vida) or 1)))
        return f"{vida}/{maxima}"

    def _acao_embed(self, *, atacante, defensor, nome, emoji, turno, dano, mana, descricao, efeito="Nenhum"):
        embed = discord.Embed(title=f"{emoji} {nome}", description=descricao, color=discord.Color.blurple())
        embed.add_field(name="👤 Atacante", value=atacante.get("nome", "User"), inline=True)
        embed.add_field(name="🎯 Alvo", value=defensor.get("nome", "-"), inline=True)
        embed.add_field(name="⚔️ Dano base", value=str(dano), inline=True)
        embed.add_field(name="🔷 Mana", value=str(mana), inline=True)
        embed.add_field(name="✦ Efeito", value=str(efeito or "Nenhum"), inline=True)
        embed.add_field(name="🔄 Turno", value=str(turno), inline=True)
        embed.add_field(name="❤️ Vida", value=self._vida(atacante), inline=True)
        embed.add_field(name="👹 Vida do alvo", value=self._vida(defensor), inline=True)
        embed.set_footer(text="Tensura Moon - Korczak Technologies!")
        return embed

    async def _ui_editar(self, combate, embed, *, view=True):
        mensagem = combate.get("ui_message")
        if mensagem is None:
            return
        if view:
            view_obj = self._ui_views.get(mensagem.id)
            if view_obj is None:
                view_obj = _AvancarView(self)
                self._ui_views[mensagem.id] = view_obj
            await mensagem.edit(embed=embed, view=view_obj)
        else:
            await mensagem.edit(embed=embed, view=None)

    def _ui_context(self, ctx, combate):
        mensagem = combate.get("ui_message")
        return _UIContext(ctx, mensagem, combate) if mensagem is not None else ctx

    def _embed_velocidade(self, combate):
        linhas = [f"{i + 1}. **{p.get('nome', 'Desconhecido')}** — {int(float(p.get('Velocidade', p.get('velocidade', 0)) or 0))} Vel." for i, p in enumerate(combate.get("participantes", []))]
        atacante = self._obter_atacante(combate)
        embed = discord.Embed(title="⚡ Ordem de velocidade", description="\n".join(linhas) or "Nenhum participante.", color=discord.Color.blurple())
        embed.add_field(name="🔄 Próximo", value=f"**{atacante.get('nome', '-') if atacante else '-'}**", inline=False)
        embed.set_footer(text="Tensura Moon - Korczak Technologies!")
        return embed

    def _embed_aguarde_jogador(self, combate):
        atacante = self._obter_atacante(combate)
        defensor = self._obter_defensor(combate)
        embed = self._acao_embed(atacante=atacante or {}, defensor=defensor or {}, nome="Sua vez", emoji="👤", turno=combate.get("numero_turno", 1), dano=0, mana=atacante.get("mana", 0) if atacante else 0, descricao=f"Use `!soco` ou `!chute` para atacar **{defensor.get('nome', '-') if defensor else '-'}**.")
        return embed

    def _embed_turno_monstro(self, combate):
        atacante = self._obter_atacante(combate)
        defensor = self._obter_defensor(combate)
        return self._acao_embed(atacante=atacante or {}, defensor=defensor or {}, nome="Vez do monstro", emoji="👹", turno=combate.get("numero_turno", 1), dano=0, mana=0, descricao=f"**{atacante.get('nome', 'Monstro') if atacante else 'Monstro'}** está pronto para atacar.")

    def _embed_defesa(self, combate):
        ataque = combate.get("ataque_pendente") or {}
        defensor = self._obter_defensor(combate)
        atacante = self._participante(combate, ataque.get("atacante_id"))
        return self._acao_embed(atacante=atacante or {}, defensor=defensor or {}, nome="Defenda-se", emoji="🛡️", turno=combate.get("numero_turno", 1), dano=ataque.get("dano_base", 0), mana=0, descricao=f"**{defensor.get('nome', 'Jogador') if defensor else 'Jogador'}**, use `!defesa` ou `!esquiva`.")

    async def _mostrar_ataque_ui(self, combate):
        ataque = combate.get("ataque_pendente") or {}
        atacante = self._participante(combate, ataque.get("atacante_id"))
        defensor = self._participante(combate, ataque.get("defensor_id"))
        if not ataque or not atacante or not defensor:
            return
        efeito = ataque.get("efeito") or {}
        if isinstance(efeito, dict):
            efeito = efeito.get("nome", efeito.get("tipo", "Nenhum")) or "Nenhum"
        embed = self._acao_embed(atacante=atacante, defensor=defensor, nome=ataque.get("nome", "Ataque"), emoji="👹" if atacante.get("tipo") == "monstro" else "⚔️", turno=combate.get("numero_turno", 1), dano=ataque.get("dano_base", 0), mana=ataque.get("mana_base", 0), descricao=f"**{atacante.get('nome')}** atacou **{defensor.get('nome')}**.", efeito=efeito)
        url = imagem_golpe(ataque.get("tipo") or ataque.get("nome"))
        if url:
            embed.set_image(url=url)
        if defensor.get("tipo") == "jogador":
            embed.add_field(name="🛡️ Defesa", value="Use `!defesa` ou `!esquiva`.", inline=False)
        await self._ui_editar(combate, embed)

    async def mostrar_ataque(self, ctx, embed, arquivo=None):
        combate = self._obter_combate(ctx.channel.id)
        if combate and combate.get("ui_message"):
            await self._mostrar_ataque_ui(combate)
            combate["ui_stage"] = "attack"
            return
        if embed is None:
            return
        ataque = (combate or {}).get("ataque_pendente") or {}
        url = imagem_golpe(ataque.get("tipo") or ataque.get("nome"))
        if url:
            embed.set_image(url=url)
        kwargs = {"embed": embed}
        if arquivo is not None:
            kwargs["file"] = arquivo
        await ctx.send(**kwargs)
        if not combate or not combate.get("ativo"):
            return
        defensor = self._participante(combate, ataque.get("defensor_id"))
        if defensor and defensor.get("tipo") == "monstro":
            await asyncio.sleep(0.25)
            await self._defesa_monstro(ctx)

    async def executar_ataque_jogador(self, ctx, tipo_ataque, embed):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            await ctx.send("❌ Não há combate ativo."); return
        if combate.get("aguardando_finalizacao"):
            await ctx.send("❌ O combate aguarda a finalização PvP."); return
        if combate.get("fase") != "ataque":
            await ctx.send("❌ O ataque anterior ainda não foi defendido."); return
        atacante = self._obter_atacante(combate); defensor = self._obter_defensor(combate)
        if not atacante or not defensor: return
        if atacante.get("tipo") != "jogador" or str(atacante.get("id")) != str(ctx.author.id):
            await ctx.send(f"❌ É a vez de **{atacante.get('nome', 'outro jogador')}**."); return
        golpe = luta_db.GOLPES.get(tipo_ataque, {})
        self._criar_ataque(combate, tipo_ataque, atacante, defensor, nome=golpe.get("nome", tipo_ataque.title()), dano_base=float(golpe.get("dano_base", 0) or 0), com_arma=bool(golpe.get("com_arma")), efeito=golpe.get("efeito", {}))
        if combate.get("ui_message"):
            await self._mostrar_ataque_ui(combate)
            combate["ui_stage"] = "attack"
        else:
            await self.mostrar_ataque(ctx, embed)

    async def executar_defesa_jogador(self, ctx, acao, embed):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo") or combate.get("fase") != "defesa":
            await ctx.send("❌ Não há ataque pendente para defender."); return
        defensor = self._obter_defensor(combate)
        if not defensor or defensor.get("tipo") != "jogador" or str(defensor.get("id")) != str(ctx.author.id):
            nome = defensor.get("nome", "outro jogador") if defensor else "outro jogador"
            await ctx.send(f"❌ É **{nome}** quem deve defender este ataque."); return
        defensor["defesa_ativa"] = acao == "defesa"
        defensor["esquiva_ativa"] = acao == "esquiva"
        if combate.get("ui_message"):
            await self._resolver_ataque(self._ui_context(ctx, combate))
        else:
            await ctx.send(embed=embed)
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
        if isinstance(embed, tuple):
            embed = embed[0]
        if embed is None:
            embed = self._acao_embed(atacante=atacante, defensor=defensor, nome=ataque.get("nome", "Ataque"), emoji="👹" if atacante.get("tipo") == "monstro" else "⚔️", turno=combate.get("numero_turno", 1), dano=ataque.get("dano_base", 0), mana=ataque.get("mana_base", 0), descricao="Oponente realizou uma ação de combate.")
        await self.mostrar_ataque(ctx, embed)

    async def _mostrar_inicio(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if not combate or not combate.get("ativo"):
            return
        preparado = self._embeds_acao.pop(ctx.channel.id, None)
        arquivo = None
        if isinstance(preparado, tuple):
            embed, arquivo = preparado
        else:
            embed = preparado
        if embed is None:
            atacante = self._obter_atacante(combate); defensor = self._obter_defensor(combate)
            embed = discord.Embed(title="⚔️ Combate PvP" if combate.get("pvp") else "⚔️ Combate PvE", description=f"🔔 Turno {combate.get('numero_turno', 1)}\n⚡ {atacante.get('nome')} começa contra {defensor.get('nome')}.", color=discord.Color.red())
        if combate.get("ui_message"):
            await self._ui_editar(combate, embed)
            return
        kwargs = {"embed": embed}
        if arquivo is not None:
            kwargs["file"] = arquivo
        mensagem = await ctx.send(**kwargs)
        combate["ui_message"] = mensagem
        combate["ui_stage"] = "attributes"
        self._ui_views[mensagem.id] = _AvancarView(self)
        await mensagem.edit(view=self._ui_views[mensagem.id])

    async def avancar(self, interaction: discord.Interaction):
        combate = self._obter_combate(interaction.channel.id)
        if not combate or not combate.get("ativo") or combate.get("ui_message") is None:
            await interaction.response.send_message("❌ Este combate não está mais ativo.", ephemeral=True); return
        if interaction.message.id != combate["ui_message"].id:
            await interaction.response.send_message("❌ Esta tela não pertence ao combate atual.", ephemeral=True); return
        await interaction.response.defer()
        async with self._lock(interaction.channel.id):
            stage = combate.get("ui_stage", "attributes")
            if stage == "attributes":
                combate["ui_stage"] = "velocity"
                await self._ui_editar(combate, self._embed_velocidade(combate))
            elif stage == "velocity":
                atacante = self._obter_atacante(combate); defensor = self._obter_defensor(combate)
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
                if combate.get("ativo"):
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

    async def _criar_ataque_monstro_ui(self, combate):
        atacante = self._obter_atacante(combate); defensor = self._obter_defensor(combate)
        if not atacante or not defensor:
            return
        ids = atacante.get("golpes", [])
        disponiveis = [luta_db.GOLPES[i] for i in ids if i in luta_db.GOLPES]
        golpe = random.choice(disponiveis) if disponiveis else {"nome": "Ataque do Monstro", "dano_base": atacante.get("dano_base", 10), "efeito": {}}
        self._criar_ataque(combate, "ataque_monstro", atacante, defensor, nome=f"{golpe.get('emoji', '👹')} {golpe.get('nome', 'Ataque do Monstro')}", dano_base=float(golpe.get("dano_base", 0) or 0), efeito=golpe.get("efeito", {}), com_arma=bool(golpe.get("com_arma")))
        combate["ui_stage"] = "attack"
        await self._mostrar_ataque_ui(combate)

    async def _proximo_turno(self, ctx):
        combate = self._obter_combate(ctx.channel.id)
        if combate and combate.get("ui_message"):
            if combate.get("ui_waiting_advance"):
                return
            resultado = self._condicao_vitoria(combate)
            if resultado:
                await self._finalizar(ctx, motivo="vida"); return
            atual = int(combate.get("turno", 0)); proximo = self._proximo_indice(combate, atual)
            if proximo is None:
                await self._finalizar(ctx, motivo="vida"); return
            combate["turno"] = proximo
            combate["numero_turno"] = int(combate.get("numero_turno", 1)) + 1
            combate["fase"] = "ataque"
            combate["ataque_pendente"] = None
            atacante = self._obter_atacante(combate)
            if not atacante:
                return
            bloqueado = await self._aplicar_efeitos_inicio(ctx, atacante)
            if not _vivo(atacante):
                await self._salvar(combate); await self._finalizar(ctx, motivo="efeitos"); return
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

    async def resultado_ataque(self, ctx): return await self._resolver_ataque(ctx)
    async def resultado_defesa(self, ctx, acao): return await self._defesa_jogador(ctx, acao)
    async def resultado_magia(self, ctx, dados_magia): return await self.usar_magia_no_combate(ctx, dados_magia)
    async def resultado_ataque_monstro(self, ctx): return await self._ataque_monstro(ctx)
    async def resultado_pvp(self, ctx, motivo): return await self._finalizar_pvp(ctx, motivo)
    async def resultado_final(self, ctx, motivo="vida", vencedor=None, perdedor=None): return await self._finalizar(ctx, motivo=motivo, vencedor=vencedor, perdedor=perdedor)

SistemaLuta = Luta
__all__ = ["Luta", "SistemaLuta"]
