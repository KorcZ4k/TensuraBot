"""Correcoes de integracao entre comandos de combate e a UI de Avancar."""

import discord

from .sistemas_luta import Luta, _UIContext, _AvancarView
from .Mensagens_luta import painel


async def _ataque_jogador_ui(self, ctx, tipo_ataque):
    """Usa o fluxo UI em vez do metodo legado que cria mensagens separadas."""
    return await self.executar_ataque_jogador(ctx, tipo_ataque, None)


async def _defesa_jogador_ui(self, ctx, acao):
    """Resolve defesa/esquiva na mesma mensagem e libera o proximo Avancar."""
    return await _executar_defesa_ui(self, ctx, acao, None)


async def _ui_editar_seguro(self, combate, embed, view=True):
    """Edita a mensagem sem enviar attachments=[] ao Discord."""
    mensagem = combate.get("ui_message")
    if mensagem is None:
        return
    if not isinstance(embed, discord.Embed):
        embed = painel(extra=str(embed))
    kwargs = {"embed": embed}
    if view:
        view_obj = self._ui_views.get(mensagem.id)
        if view_obj is None:
            view_obj = _AvancarView(self)
            self._ui_views[mensagem.id] = view_obj
        kwargs["view"] = view_obj
    else:
        kwargs["view"] = None
    await mensagem.edit(**kwargs)


async def _ui_context_send_seguro(self, content=None, **kwargs):
    """Mostra mensagens na tela unica sem corromper a maquina de estados."""
    combate = self._combate
    atacante = self._get_participante(combate, combate.get("vencedor_id")) or self._atacante(combate) or {}
    defensor = self._get_participante(combate, combate.get("perdedor_id")) or self._defensor(combate) or {}
    embed = kwargs.get("embed")
    eh_erro = bool(kwargs.pop("_luta_error", False))
    extra = content or ""
    if embed is not None and embed.description:
        extra = embed.description if not extra else f"{extra}\n{embed.description}"
    padrao = painel(
        atacante=atacante.get("nome", "User"), ataque="resultado",
        vida=self._vida(atacante), mana=atacante.get("mana", 0),
        dano="-", efeito="Erro" if eh_erro else "Nenhum",
        alvo=defensor.get("nome", "-"), turno=combate.get("numero_turno", 1),
        oponente=defensor, vida_oponente=self._vida(defensor),
        extra=extra or "Atualizacao do combate.",
        cor=discord.Color.red() if eh_erro else discord.Color.blurple(),
    )
    etapa_anterior = combate.get("ui_stage", "attributes")
    aguardando_anterior = combate.get("ui_waiting_advance", False)
    if eh_erro:
        combate["ui_stage"] = etapa_anterior
        combate["ui_waiting_advance"] = aguardando_anterior
    else:
        combate["ui_stage"] = "result"
        combate["ui_waiting_advance"] = True
    view = self._owner._ui_views.get(self._message.id) if self._owner else None
    if view is None and self._owner:
        view = _AvancarView(self._owner)
        self._owner._ui_views[self._message.id] = view
    await self._message.edit(embed=padrao, view=view)
    return self._message


async def _executar_defesa_ui(self, ctx, acao, embed=None):
    """Fluxo deterministico da defesa, independente do callback legado."""
    combate = self._obter_combate(ctx.channel.id)
    if not combate or not combate.get("ativo"):
        if combate and combate.get("ui_message"):
            await self._ui_context(ctx, combate).send("❌ Não há combate ativo.", _luta_error=True)
        else:
            await ctx.send("❌ Não há combate ativo.")
        return

    ui = self._ui_context(ctx, combate)
    ataque = combate.get("ataque_pendente") or {}
    if combate.get("fase") != "defesa" or not ataque:
        await ui.send("❌ Não há ataque pendente para defender.", _luta_error=True)
        return
    if ataque.get("_resolvendo"):
        await ui.send("❌ Este ataque já está sendo resolvido. Aguarde o resultado.", _luta_error=True)
        return

    defensor = self._obter_defensor(combate)
    if not defensor:
        await ui.send("❌ Não foi possível identificar quem deve defender.", _luta_error=True)
        return
    if defensor.get("tipo") != "jogador" or str(defensor.get("id")) != str(ctx.author.id):
        await ui.send(f"❌ É **{defensor.get('nome', 'outro jogador')}** quem deve defender este ataque.", _luta_error=True)
        return

    # A defesa foi aceita. A partir daqui o botão Avançar não pode interferir
    # até que o ataque seja efetivamente resolvido.
    defensor["defesa_ativa"] = acao == "defesa"
    defensor["esquiva_ativa"] = acao == "esquiva"
    combate["ui_stage"] = "resolving"
    combate["ui_waiting_advance"] = False
    try:
        await self._resolver_ataque(ui)
    except Exception as erro:
        print(f"[LUTA][DEFESA][ERRO] {type(erro).__name__}: {erro}")
        if combate.get("ativo") and combate.get("ataque_pendente") is ataque:
            ataque.pop("_resolvendo", None)
            combate["ui_stage"] = "defense_action"
            combate["ui_waiting_advance"] = False
            await ui.send(f"❌ Erro ao resolver a defesa: `{type(erro).__name__}`.", _luta_error=True)


# Os comandos publicos usam executar_*. Esta atribuicao garante que o fluxo
# de defesa acima seja o unico caminho executado pela UI/comando !defesa.
Luta._ataque_jogador = _ataque_jogador_ui
Luta._defesa_jogador = _defesa_jogador_ui
Luta.executar_defesa_jogador = _executar_defesa_ui
Luta._ui_editar = _ui_editar_seguro
_UIContext.send = _ui_context_send_seguro
