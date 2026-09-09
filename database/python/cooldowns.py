"""Cooldowns persistentes para ações do RPG."""
from datetime import datetime, timezone, timedelta
from database.python.mongodb import db

COLLECTION = db["Cooldowns"]


def _agora():
    return datetime.now(timezone.utc)


def restante(user_id, guild_id, chave):
    doc = COLLECTION.find_one({"ID": str(user_id), "guild_id": str(guild_id), "chave": str(chave)})
    if not doc:
        return 0
    fim = doc.get("fim")
    if not fim:
        return 0
    if isinstance(fim, str):
        fim = datetime.fromisoformat(fim)
    return max(0, int((fim - _agora()).total_seconds()))


def disponivel(user_id, guild_id, chave):
    return restante(user_id, guild_id, chave) <= 0


def iniciar(user_id, guild_id, chave, segundos):
    fim = _agora() + timedelta(seconds=int(segundos))
    COLLECTION.update_one(
        {"ID": str(user_id), "guild_id": str(guild_id), "chave": str(chave)},
        {"$set": {"fim": fim.isoformat()}},
        upsert=True,
    )
    return fim


def formatar(segundos):
    segundos = max(0, int(segundos))
    if segundos >= 3600:
        h, resto = divmod(segundos, 3600)
        m = resto // 60
        return f"{h}h {m}min" if m else f"{h}h"
    m, s = divmod(segundos, 60)
    return f"{m}min {s}s" if s else f"{m}min"
