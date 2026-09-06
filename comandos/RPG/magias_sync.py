import discord
from discord.ext import commands

from database.python.mongodb import db
from database.python.magias import DatabaseMagias

class Magias(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

    def normalizar(self, texto):
        """
    Normaliza textos para comparação.
    """

        if texto is None:
            return ""

        return str(texto).strip().lower()

    def normalizar_lista(self, lista):
        """
    Normaliza uma lista que pode conter strings ou dicionários.
    """

        resultado = []

        if not lista:
            return resultado

        for item in lista:

            if isinstance(item, dict):

                valor = (
                item.get("id")
                or item.get("ID")
                or item.get("nome")
                or item.get("Nome")
                or ""
            )

            else:
                valor = item

            valor_normalizado = self.normalizar(valor)

            if valor_normalizado:
                resultado.append(valor_normalizado)

        return resultado

    def carregar_catalogo(self, dados, chave):
        """
    Obtém uma lista de um catálogo JSON.
    """

        if not dados:
            return []

        if isinstance(dados, list):
            return dados

        if isinstance(dados, dict):

            resultado = dados.get(chave, [])

            if isinstance(resultado, list):
                return resultado

        return []

    def buscar_item(self, lista, identificador):
        """
    Busca um item pelo ID ou nome.
    """

        identificador = self.normalizar(identificador)

        for item in lista:

            if isinstance(item, dict):

                item_id = self.normalizar(
                item.get("id")
                or item.get("ID")
                or ""
            )

                item_nome = self.normalizar(
                item.get("nome")
                or item.get("Nome")
                or ""
            )

                if identificador == item_id:
                    return item

                if identificador == item_nome:
                    return item

            else:

                if self.normalizar(item) == identificador:
                    return item

        return None

    def formatar_lista(self, lista, limite=1024):
        """
    Formata uma lista para uso em Embed.
    """

        if not lista:
            return "Nenhum."

        texto = ""

        for item in lista:

            if isinstance(item, dict):

                nome = (
                item.get("nome")
                or item.get("Nome")
                or item.get("id")
                or item.get("ID")
                or "Desconhecido"
            )

                item_id = (
                item.get("id")
                or item.get("ID")
                or ""
            )

                if item_id:

                    linha = (
                    f"• **{nome}** "
                    f"(`{item_id}`)\n"
                )

                else:

                    linha = (
                    f"• **{nome}**\n"
                )

            else:

                linha = (
                f"• `{item}`\n"
            )

            if len(texto) + len(linha) > limite:

                texto += "..."
                break

            texto += linha

        return texto or "Nenhum."

    def converter_numero(self, valor, padrao=0):
        """
    Converte valores para float sem gerar erro.
    """

        try:
            return float(valor)

        except (
        TypeError,
        ValueError
    ):
            return float(padrao)

    def obter_efeito_final(
    self,
    efeito_forma,
    efeito_elemento
):
        """
    Combina os efeitos da forma e do elemento.

    Atualmente o sistema de combate aceita um efeito por ataque.
    A prioridade é dada ao efeito da forma. Caso ela não possua
    efeito válido, utiliza o efeito elemental.
    """

        if (
        isinstance(efeito_forma, dict)
        and efeito_forma
    ):

            nome = self.normalizar(
            efeito_forma.get("nome")
        )

            if nome:
                return dict(efeito_forma)

        if (
        isinstance(efeito_elemento, dict)
        and efeito_elemento
    ):

            nome = self.normalizar(
            efeito_elemento.get("nome")
        )

            if nome:
                return dict(efeito_elemento)

        return {}

# ============================================================
# COMANDO BASE
# ============================================================

    @commands.group(
    name="magias",
    aliases=["magia"],
    invoke_without_command=True
)
    async def magias(self, ctx):

        embed = discord.Embed(
        title="🔮 Sistema de Magias",
        description=(
            "`!magias list` — Ver suas formas e elementos\n"
            "`!magias formas` — Ver todas as formas disponíveis\n"
            "`!magias elementos` — Ver todos os elementos disponíveis\n"
            "`!magias count` — Ver quantidade de formas\n\n"
            "`!usarmagia <forma> <elemento>` — Usar magia\n\n"
            "Durante um combate, a magia será enviada "
            "automaticamente para o sistema de luta."
        ),
        color=discord.Color.purple()
    )

        await ctx.send(embed=embed)

# ============================================================
# !MAGIAS LIST
# ============================================================

    @magias.command(
    name="list",
    aliases=["lista", "listar"]
)
    async def listar_magias(self, ctx):

        if ctx.guild is None:

            await ctx.send(
            "❌ Este comando só pode ser usado em um servidor."
        )

            return

        if db is None:

            await ctx.send(
            "❌ Banco de dados não conectado."
        )

            return

        db_magias = DatabaseMagias(db)

        doc = db_magias.get_magia_doc(
        str(ctx.author.id),
        str(ctx.guild.id)
    )

        if not doc:

            await ctx.send(
            "❌ Você não possui um documento de magias registrado."
        )

            return

        formas = doc.get(
        "magias",
        []
    )

        elementos = doc.get(
        "tipos",
        []
    )

        embed = discord.Embed(
        title=f"🔮 Magias de {ctx.author.display_name}",
        color=discord.Color.purple()
    )

        embed.set_thumbnail(
        url=ctx.author.display_avatar.url
    )

        if formas:

            embed.add_field(
            name=f"🔷 Formas ({len(formas)})",
            value=self.formatar_lista(formas),
            inline=False
        )

        else:

            embed.add_field(
                name="🔷 Formas (0)",
            value="Você não possui nenhuma forma.",
            inline=False
        )

        if elementos:

            embed.add_field(
            name=f"🌈 Elementos ({len(elementos)})",
            value=self.formatar_lista(elementos),
            inline=False
        )

        else:

            embed.add_field(
            name="🌈 Elementos (0)",
            value="Você não possui nenhum elemento.",
            inline=False
        )

        embed.set_footer(
        text="Use: !usarmagia <forma> <elemento>"
    )

        await ctx.send(embed=embed)

# ============================================================
# !MAGIAS COUNT
# ============================================================

    @magias.command(
    name="count",
    aliases=["contar", "quantidade"]
)
    async def contar_magias(self, ctx):

        if ctx.guild is None:

            await ctx.send(
            "❌ Este comando só pode ser usado em um servidor."
        )

            return

        if db is None:

            await ctx.send(
            "❌ Banco de dados não conectado."
        )

            return

        db_magias = DatabaseMagias(db)

        doc = db_magias.get_magia_doc(
        str(ctx.author.id),
        str(ctx.guild.id)
    )

        if not doc:

            await ctx.send(
            "❌ Você não possui magias registradas."
        )

            return

        formas = doc.get(
        "magias",
        []
    )

        elementos = doc.get(
        "tipos",
        []
    )

        await ctx.send(
        f"🔷 {ctx.author.mention}, você possui "
        f"**{len(formas)} forma(s)** e "
        f"**{len(elementos)} elemento(s)**."
    )

# ============================================================
# !MAGIAS FORMAS
# ============================================================

    @magias.command(
    name="formas",
    aliases=["forma"]
)
    async def listar_formas(self, ctx):

        if db is None:

            await ctx.send(
            "❌ Banco de dados não conectado."
        )

            return

        db_magias = DatabaseMagias(db)

        dados = db_magias._carregar_json(
        db_magias.arquivo_formas
    )

        formas = self.carregar_catalogo(
        dados,
        "formas"
    )

        if not formas:

            await ctx.send(
            "❌ Nenhuma forma foi encontrada."
        )

            return

        paginas = []
        pagina_atual = ""

        for forma in formas:

            if not isinstance(forma, dict):

                linha = f"• `{forma}`\n"

            else:

                forma_id = forma.get(
                "id",
                "desconhecida"
            )

                nome = forma.get(
                "nome",
                forma_id
            )

                descricao = forma.get(
                "descricao",
                "Sem descrição."
            )

                mana = forma.get(
                "mana_base",
                0
            )

                dano = forma.get(
                "dano_base",
                0
            )

                cura = forma.get(
                "cura_base",
                0
            )

                linha = (
                f"**{nome}** (`{forma_id}`)\n"
                f"└ {descricao}\n"
                f"└ 💠 Mana: `{mana}` | "
                f"⚔️ Dano: `{dano}`"
            )

                if cura:
                    linha += (
                    f" | 💚 Cura: `{cura}`"
                )

                linha += "\n\n"

            if (
            len(pagina_atual)
            + len(linha)
            > 1024
        ):

                if pagina_atual:
                    paginas.append(
                    pagina_atual
                )

                pagina_atual = ""

            pagina_atual += linha

        if pagina_atual:
            paginas.append(pagina_atual)

        for indice, pagina in enumerate(
        paginas,
        start=1
    ):

            embed = discord.Embed(
            title="🔷 Formas de Magia",
            color=discord.Color.purple()
        )

            embed.add_field(
            name=(
                f"📜 Formas — Página "
                f"{indice}/{len(paginas)}"
            ),
            value=pagina,
            inline=False
        )

            embed.set_footer(
            text=f"Total: {len(formas)} forma(s)"
        )

            await ctx.send(embed=embed)

# ============================================================
# !MAGIAS ELEMENTOS
# ============================================================

    @magias.command(
    name="elementos",
    aliases=["elemento"]
)
    async def listar_elementos(self, ctx):

        if db is None:

            await ctx.send(
            "❌ Banco de dados não conectado."
        )

            return

        db_magias = DatabaseMagias(db)

        dados = db_magias._carregar_json(
        db_magias.arquivo_elementos
    )

        elementos = self.carregar_catalogo(
        dados,
        "elementos"
    )

        if not elementos:

            await ctx.send(
            "❌ Nenhum elemento foi encontrado."
        )

            return

        paginas = []
        pagina_atual = ""

        for elemento in elementos:

            if not isinstance(elemento, dict):

                linha = f"• `{elemento}`\n"

            else:

                elemento_id = elemento.get(
                "id",
                "desconhecido"
            )

                nome = elemento.get(
                "nome",
                elemento_id
            )

                descricao = elemento.get(
                "descricao",
                ""
            )

                linha = (
                f"**{nome}** (`{elemento_id}`)"
            )

                if descricao:
                    linha += (
                    f"\n└ {descricao}"
                )

                linha += "\n\n"

            if (
            len(pagina_atual)
            + len(linha)
            > 1024
        ):

                if pagina_atual:
                    paginas.append(
                    pagina_atual
                )

                pagina_atual = ""

            pagina_atual += linha

        if pagina_atual:
            paginas.append(pagina_atual)

        for indice, pagina in enumerate(
        paginas,
        start=1
    ):

            embed = discord.Embed(
            title="🌈 Elementos Mágicos",
            color=discord.Color.purple()
        )

            embed.add_field(
            name=(
                f"📜 Elementos — Página "
                f"{indice}/{len(paginas)}"
            ),
            value=pagina,
            inline=False
        )

            embed.set_footer(
            text=f"Total: {len(elementos)} elemento(s)"
        )

            await ctx.send(embed=embed)

# ============================================================
# !USARMAGIA
# ============================================================

    @commands.command(
    name="usarmagia",
    aliases=[
        "usar_magia",
        "cast"
    ]
)
    async def usar_magia(
    self,
    ctx,
    forma_id: str,
    elemento_id: str
):

        if ctx.guild is None:

            await ctx.send(
            "❌ Este comando só pode ser usado em um servidor."
        )

            return

        if db is None:

            await ctx.send(
            "❌ Banco de dados não conectado."
        )

            return

        user_id = str(ctx.author.id)
        guild_id = str(ctx.guild.id)

        forma_id = self.normalizar(
            forma_id
    )

        elemento_id = self.normalizar(
            elemento_id
    )

        db_magias = DatabaseMagias(db)

    # ========================================================
    # DOCUMENTO DO JOGADOR
    # ========================================================

        doc = db_magias.get_magia_doc(
        user_id,
        guild_id
    )

        if not doc:

            await ctx.send(
            "❌ Você não possui um documento de magias registrado."
        )

            return

        formas_jogador = doc.get(
        "magias",
        []
    )

        elementos_jogador = doc.get(
        "tipos",
        []
    )

    # ========================================================
    # VERIFICAR FORMA
    # ========================================================

        formas_normalizadas = (
        self.normalizar_lista(
            formas_jogador
        )
    )

        if forma_id not in formas_normalizadas:

            await ctx.send(
            f"❌ Você não possui a forma "
            f"`{forma_id}`.\n\n"
            "Use `!magias list` para ver "
            "suas formas."
        )

            return

    # ========================================================
    # VERIFICAR ELEMENTO
    # ========================================================

        elementos_normalizados = (
        self.normalizar_lista(
            elementos_jogador
        )
    )

        if elemento_id not in elementos_normalizados:

            await ctx.send(
            f"❌ Você não possui o elemento "
            f"`{elemento_id}`.\n\n"
            "Use `!magias list` para ver "
            "seus elementos."
        )

            return

    # ========================================================
    # CARREGAR CATÁLOGO DE FORMAS
    # ========================================================

        dados_formas = db_magias._carregar_json(
        db_magias.arquivo_formas
    )

        formas_catalogo = self.carregar_catalogo(
        dados_formas,
        "formas"
    )

        forma = self.buscar_item(
        formas_catalogo,
        forma_id
    )

        if not forma:

            await ctx.send(
            f"❌ A forma `{forma_id}` existe "
            "no seu registro, mas não foi encontrada "
            "no catálogo de formas."
        )

            return

        if not isinstance(forma, dict):

            forma = {
            "id": forma_id,
            "nome": str(forma)
        }

    # ========================================================
    # CARREGAR CATÁLOGO DE ELEMENTOS
    # ========================================================

        dados_elementos = (
        db_magias._carregar_json(
            db_magias.arquivo_elementos
        )
    )

        elementos_catalogo = (
        self.carregar_catalogo(
            dados_elementos,
            "elementos"
        )
    )

        elemento = self.buscar_item(
        elementos_catalogo,
        elemento_id
    )

        if not elemento:

            await ctx.send(
            f"❌ O elemento `{elemento_id}` existe "
            "no seu registro, mas não foi encontrado "
            "no catálogo de elementos."
        )

            return

        if not isinstance(elemento, dict):

            elemento = {
            "id": elemento_id,
            "nome": str(elemento)
        }

    # ========================================================
    # DADOS DA FORMA
    # ========================================================

        forma_nome = forma.get(
        "nome",
        forma_id.title()
    )

        mana_base = self.converter_numero(
        forma.get(
            "mana_base",
            0
        )
    )

        dano_base = self.converter_numero(
        forma.get(
            "dano_base",
            0
        )
    )

        cura_base = self.converter_numero(
        forma.get(
            "cura_base",
            0
        )
    )

        defesa_base = self.converter_numero(
        forma.get(
            "defesa_base",
            0
        )
    )

        alcance = forma.get(
        "alcance",
        "Não definido"
    )

        alvo = forma.get(
        "alvo",
        "Não definido"
    )

        tipos_forma = forma.get(
        "tipos",
        []
    )

        efeito_forma = forma.get(
        "efeito",
        {}
    )

    # ========================================================
    # DADOS DO ELEMENTO
    # ========================================================

        elemento_nome = elemento.get(
        "nome",
        elemento_id.title()
    )

        bonus_dano = self.converter_numero(
        elemento.get(
            "bonus_dano",
            elemento.get(
                "dano_bonus",
                0
            )
        )
    )

        bonus_mana = self.converter_numero(
        elemento.get(
            "bonus_mana",
            elemento.get(
                "mana_bonus",
                0
            )
        )
    )

        multiplicador_dano = self.converter_numero(
        elemento.get(
            "multiplicador_dano",
            1
        ),
        1
    )

        if multiplicador_dano <= 0:
            multiplicador_dano = 1

        efeito_elemento = elemento.get(
        "efeito",
        {}
    )

    # ========================================================
    # CÁLCULO FINAL
    # ========================================================

        dano_final = (
        dano_base
        + bonus_dano
    ) * multiplicador_dano

        mana_final = (
        mana_base
        + bonus_mana
    )

        if mana_final < 0:
            mana_final = 0

    # Cura é enviada como dano negativo para o sistema
    # atual de combate.
        if cura_base > 0 and dano_final <= 0:

            dano_para_combate = (
            -abs(cura_base)
        )

        else:

            dano_para_combate = (
            dano_final
        )

    # ========================================================
    # EFEITO FINAL
    # ========================================================

        efeito_final = (
           self.obter_efeito_final(
            efeito_forma,
            efeito_elemento
        )
    )

    # ========================================================
    # NOME DA MAGIA
    # ========================================================

        nome_magia = (
        f"{forma_nome} de {elemento_nome}"
    )

    # ========================================================
    # DADOS ENVIADOS PARA O SISTEMA DE LUTA
    # ========================================================

        dados_magia = {
        "nome": nome_magia,
        "forma": forma_id,
        "elemento": elemento_nome,
        "mana_base": mana_final,
        "dano_base": dano_para_combate,
        "cura_base": cura_base,
        "defesa_base": defesa_base,
        "alcance": alcance,
        "alvo": alvo,
        "tipos": tipos_forma,
        "efeito": efeito_final,
    }

    # ========================================================
    # VERIFICAR COMBATE
    # ========================================================

        luta_cog = self.bot.get_cog(
        "Luta"
    )

        if luta_cog:

            try:

                combate_ativo = (
                luta_cog._combate_ativo(
                    ctx.channel.id
                )
            )

            except Exception:

                combate_ativo = False

            if combate_ativo:

                resultado = (
                    await luta_cog.usar_magia_no_combate(
                    ctx,
                    dados_magia
                )
            )

                if resultado:
                    return

    # ========================================================
    # MAGIA FORA DE COMBATE
    # ========================================================

        embed = discord.Embed(
        title="✨ Magia Preparada",
        description=(
            f"{ctx.author.mention} utilizou "
            f"**{nome_magia}**!"
        ),
        color=discord.Color.purple()
    )

        embed.add_field(
        name="🔷 Forma",
        value=forma_nome,
        inline=True
    )

        embed.add_field(
        name="🌈 Elemento",
        value=elemento_nome,
        inline=True
    )

        embed.add_field(
        name="💠 Custo de Mana",
        value=str(int(mana_final)),
        inline=True
    )

        if dano_final > 0:

            embed.add_field(
            name="⚔️ Poder",
            value=str(int(dano_final)),
            inline=True
        )

        if cura_base > 0:

            embed.add_field(
            name="💚 Cura",
            value=str(int(cura_base)),
            inline=True
        )

        if defesa_base > 0:

            embed.add_field(
            name="🛡️ Defesa",
            value=str(int(defesa_base)),
            inline=True
        )

        embed.add_field(
        name="🎯 Alvo",
        value=str(alvo),
        inline=True
    )

        embed.add_field(
        name="📏 Alcance",
        value=str(alcance),
        inline=True
    )

        if tipos_forma:

            texto_tipos = ", ".join(
            str(tipo)
            for tipo in tipos_forma
        )

            if len(texto_tipos) > 1024:
                texto_tipos = texto_tipos[:1021] + "..."

            embed.add_field(
            name="🏷️ Tipos",
            value=texto_tipos,
            inline=False
        )

        if efeito_final:

            efeito_nome = (
                efeito_final.get(
                "nome",
                "Efeito"
            )
        )

            efeito_descricao = (
            efeito_final.get(
                "descricao",
                ""
            )
        )

            efeito_turnos = (
            efeito_final.get(
                "turnos",
                0
            )
        )

            efeito_valor = (
            efeito_final.get(
                "valor",
                0
            )
        )

            texto_efeito = (
            f"**{efeito_nome}**"
        )

            if efeito_descricao:

                texto_efeito += (
                f"\n{efeito_descricao}"
            )

            if efeito_turnos:

                texto_efeito += (
                f"\n⏱️ Duração: "
                f"`{efeito_turnos}` turno(s)"
            )

            if efeito_valor:

                texto_efeito += (
                f"\n📊 Valor: "
                f"`{efeito_valor}`"
            )

            embed.add_field(
            name="✨ Efeito",
            value=texto_efeito,
            inline=False
        )

        embed.set_footer(
        text=(
            "Fora de combate, a magia apenas "
            "é exibida. Em combate, ela consome "
            "mana e é resolvida pelo sistema de luta."
        )
    )

        await ctx.send(embed=embed)

# ============================================================

# SETUP

# ============================================================

async def setup(bot):
    await bot.add_cog(
Magias(bot)
)
