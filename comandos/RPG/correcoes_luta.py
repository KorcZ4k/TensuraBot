"""Compatibilidade legada do sistema de luta.

O comando canonico de combate vive em ``comandos.RPG.luta``. Este modulo
precisa continuar carregavel porque faz parte da lista de extensoes, mas nao
pode substituir callbacks de comandos ja registrados no Cog: isso remove a
ligacao que o discord.py faz entre o callback e a instancia do Cog e provoca
erros como ``ctx`` ausente.
"""


async def setup(bot):
    # Intencionalmente sem monkeypatch de callbacks.
    # Os comandos de !luta devem usar diretamente os callbacks definidos no Cog.
    return
