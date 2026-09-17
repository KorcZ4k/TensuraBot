"""Contrato de recompensa: XP, Hunos e TP são concedidos juntos."""
from database.python import luta as luta_db
from .sistemas_luta import Luta


async def _recompensar_async(self, combate):
    resultado = self._condicao_vitoria(combate)
    if resultado != "jogadores" or luta_db.db is None:
        return 0, 0
    monstros = [p for p in combate.get("participantes", [])
                if p.get("tipo") == "monstro" and not p.get("invocado")]
    xp = sum(int(float(p.get("xp_recompensa", 0) or 0)) for p in monstros)
    hunos = sum(int(float(p.get("hunos_recompensa", 0) or 0)) for p in monstros)
    tp = sum(int(float(p.get("tp_recompensa", p.get("xp_recompensa", 0)) or 0)) for p in monstros)
    vivos = [p for p in combate.get("participantes", [])
             if p.get("tipo") == "jogador" and float(p.get("vida", 0) or 0) > 0]
    if not vivos:
        return xp, hunos
    for i, jogador in enumerate(vivos):
        ganho_xp = xp // len(vivos) + (1 if i < xp % len(vivos) else 0)
        ganho_hunos = hunos // len(vivos) + (1 if i < hunos % len(vivos) else 0)
        ganho_tp = tp // len(vivos) + (1 if i < tp % len(vivos) else 0)
        filtro = {"ID": str(jogador.get("id")), "guild_id": str(combate.get("guild_id"))}
        await luta_db.run_db(luta_db.db["Jogadores"].update_one, filtro,
                             {"$inc": {"XP": ganho_xp, "TP": ganho_tp}})
        await luta_db.run_db(luta_db.db["Hunos"].update_one, filtro,
                             {"$inc": {"carteira": ganho_hunos}}, upsert=True)
    return xp, hunos


Luta._recompensar = _recompensar_async
