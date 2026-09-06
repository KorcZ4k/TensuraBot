import asyncio
import random

import discord
from discord.ext import commands

from database.python.mongodb import db
from database.python.luta import (
    MONSTROS,
    pode_lutar,
    criar_participante_jogador,
    criar_monstro,
    calcular_dano,
    obter_vencedores,
)


class Luta(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.combates = {}

    # O restante do motor de combate será restaurado do histórico do commit anterior.
