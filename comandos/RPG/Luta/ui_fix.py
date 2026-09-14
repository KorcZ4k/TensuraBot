"""Correcoes de integracao entre comandos de combate e a UI de Avancar."""

import discord

from .sistemas_luta import Luta, _UIContext, _AvancarView
from .Mensagens_luta import painel


async def _ataque_jogador_ui(self, ctx, tipo_ataque):
    """Usa o fluxo UI em vez do metodo legado que cria mensagens separadas."""
    return await self.executar_ataque_jogador(ctx, tipo_ataque, None)


async def _defesa_jogador_ui(self, ctx, acao):
    """Resolve defesa/esquiva na mesma mensagem e libera o proximo Avancar."""
    return await self.executar_defesa_jogador(ctx, acao, None)


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
    """Mostra mensagens na tela unica sem corromper a maquina de estados.

    Mensagens de erro recebem a marca interna ``_luta_error=True`` e preservam
    exatamente a etapa em que o combate estava. Resultados reais, como o dano
    depois de !defesa, continuam mudando para ``result`` e liberando Avancar.
    """
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
        # ERRO DE ACAO: nunca cria um falso resultado avancavel.
        # Ex.: !defesa durante a vez do monstro continua em "turn".
        combate["ui_stage"] = etapa_anterior
        combate["ui_waiting_advance"] = aguardando_anterior
    else:
        # Resultado real: mostra o dano e deixa Avancar passar ao proximo turno.
        combate["ui_stage"] = "result"
        combate["ui_waiting_advance"] = True

    view = self._owner._ui_views.get(self._message.id) if self._owner else None
    if view is None and self._owner:
        view = _AvancarView(self._owner)
        self._owner._ui_views[self._message.id] = view
    await self._message.edit(embed=padrao, view=view)
    return self._message


# Os comandos publicos ja usam executar_*. Estas atribuicoes tambem cobrem
# qualquer caminho legado que ainda invoque _ataque_jogador/_defesa_jogador.
Luta._ataque_jogador = _ataque_jogador_ui
Luta._defesa_jogador = _defesa_jogador_ui
Luta._ui_editar = _ui_editar_seguro
_UIContext.send = _ui_context_send_seguro
