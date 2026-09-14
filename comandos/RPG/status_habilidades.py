import json
from pathlib import Path

from database.python.mongodb import db


BASE_DIR = Path(__file__).resolve().parents[2]
HABILIDADES_DIR = BASE_DIR / "database" / "json" / "habilidades"


def carregar_nomes_habilidades():
    nomes = {}
    for caminho in HABILIDADES_DIR.glob("*.json"):
        try:
            with open(caminho, "r", encoding="utf-8") as arquivo:
                dados = json.load(arquivo)
        except Exception:
            continue

        def percorrer(item):
            if isinstance(item, list):
                for valor in item:
                    percorrer(valor)
            elif isinstance(item, dict):
                habilidade_id = item.get("ID") or item.get("id")
                nome = item.get("Nome") or item.get("nome")
                if habilidade_id and nome:
                    nomes[str(habilidade_id)] = str(nome)
                for valor in item.values():
                    if isinstance(valor, (dict, list)):
                        percorrer(valor)

        percorrer(dados)
    return nomes


class StatusHabilidades:
    """Adiciona as habilidades ao painel visual do comando !status."""

    def __init__(self, bot):
        self.bot = bot
        self.nomes = carregar_nomes_habilidades()

    async def aplicar(self):
        comando = self.bot.get_command("status")
        if comando is None or getattr(comando, "_habilidades_status_patch", False):
            return

        callback_original = comando.callback
        nomes = self.nomes

        async def callback(*args, **kwargs):
            ctx = kwargs.get("ctx")
            if ctx is None:
                for argumento in args:
                    if hasattr(argumento, "send") and hasattr(argumento, "author"):
                        ctx = argumento
                        break

            if ctx is None:
                return await callback_original(*args, **kwargs)

            membro = kwargs.get("membro")
            if membro is None:
                indice_ctx = next((i for i, argumento in enumerate(args) if argumento is ctx), -1)
                if indice_ctx != -1 and len(args) > indice_ctx + 1:
                    candidato = args[indice_ctx + 1]
                    if candidato is not None and hasattr(candidato, "id"):
                        membro = candidato

            membro_consultado = membro or ctx.author
            enviar_original = ctx.send

            async def enviar_modificado(*send_args, **send_kwargs):
                embed = send_kwargs.get("embed")
                if embed is not None and getattr(embed, "title", None) == "🌙 MOON TENSURA • STATUS":
                    documento = db["Habilidades"].find_one({
                        "ID": str(membro_consultado.id),
                        "guild_id": str(ctx.guild.id),
                    }) or {}

                    habilidades = documento.get("habilidades", []) or []
                    if habilidades:
                        lista = [f"• **{nomes.get(str(h), str(h))}**" for h in habilidades]
                        texto = "\n".join(lista)
                    else:
                        texto = "Nenhuma habilidade obtida ainda."

                    embed.add_field(name="🧠 Habilidades", value=texto[:1024], inline=False)

                return await enviar_original(*send_args, **send_kwargs)

            ctx.send = enviar_modificado
            try:
                return await callback_original(*args, **kwargs)
            finally:
                ctx.send = enviar_original

        comando.callback = callback
        comando._habilidades_status_patch = True


async def setup(bot):
    patch = StatusHabilidades(bot)
    await patch.aplicar()
