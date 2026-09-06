# Auditoria de latência MongoDB — Etapa 1

Data: 2026-09-06  
Branch: `perf/mongo-nonblocking`  
Base: `7eb2d14a60a264ff5569a256c84ece19fbd66c51`

## Objetivo

Mapear os acessos ao MongoDB que podem bloquear o event loop do `discord.py`, identificar os hot paths e registrar a ordem segura de correção sem alterar a regra de negócio.

## Auditoria isolada por camada

### 1. Cliente MongoDB

`database/python/mongodb.py`

- Usa `pymongo.MongoClient`, que é síncrono.
- O cliente é compartilhado, o que é positivo para reaproveitamento do pool.
- `serverSelectionTimeoutMS=10000`, `connectTimeoutMS=10000` e `socketTimeoutMS=20000` significam que uma chamada síncrona feita dentro do event loop pode bloquear por segundos em caso de indisponibilidade/rede ruim.
- `retryReads=True` e `retryWrites=True` são úteis para resiliência, mas não tornam as chamadas assíncronas.

**Conclusão:** a camada precisa fornecer uma fronteira explícita para executar operações PyMongo fora do event loop.

### 2. Listeners administrativos — prioridade máxima

#### `comandos/ADMINISTRACAO/automod.py`

- `on_message` consulta `CONFIG.find_one()` para praticamente toda mensagem não isenta.
- O mesmo módulo faz `update_one()` nas configurações.
- `log()` também volta a consultar a configuração.

**Risco:** é um hot path global. Uma consulta síncrona por mensagem pode atrasar comandos, eventos e outras mensagens do bot.

#### `comandos/ADMINISTRACAO/logs.py`

- Eventos de mensagem, membro e canais passam por `_send_log()`.
- `_send_log()` chama `_config()`, que usa `CONFIG.find_one()` síncrono.
- Os comandos de configuração usam `update_one()` síncrono.

**Risco:** eventos administrativos frequentes podem bloquear o loop.

#### `comandos/ADMINISTRACAO/boas_vindas.py`

- `on_member_join` e `on_member_remove` consultam Mongo de forma síncrona.
- Os comandos de configuração também usam `update_one()` síncrono.

**Risco:** menor que AutoMod, mas ainda bloqueante.

### 3. RPG

#### `database/python/status.py` + `comandos/RPG/status.py`

- O comando é assíncrono, mas `obter_status()` acessa Mongo de forma síncrona.

#### `database/python/luta.py` + `comandos/RPG/luta.py`

- Fluxos de combate chamam consultas/updates PyMongo diretamente a partir de handlers assíncronos.
- Há múltiplos acessos sequenciais durante criação/validação/atualização dos participantes.

**Risco:** alto por combinar I/O síncrono com operações de combate que já possuem vários passos.

#### `comandos/RPG/party.py`

- O fluxo de grupo multiplica as consultas de combate por participante.
- Com quatro participantes, o padrão atual pode gerar várias consultas sequenciais.

#### `comandos/RPG/treino.py` + `database/python/treino.py`

- Uma execução de treino pode consultar cooldown mais de uma vez, atualizar e consultar novamente os valores.
- A listagem também pode consultar cooldown repetidamente.

**Risco:** médio/alto. Além do bloqueio do loop, há oportunidade clara de reduzir round-trips.

#### `comandos/RPG/magias.py` + `database/python/magias.py`

- Handlers assíncronos chamam métodos que usam PyMongo síncrono.
- Há caminhos com consultas encadeadas/duplicadas.
- Catálogos JSON estáticos também podem ser recarregados sem necessidade.

### 4. Economia

`comandos/ECONOMIA/Hunos.py` e `comandos/ECONOMIA/Mora.py` já utilizam `asyncio.to_thread()` em seus acessos Mongo relevantes.

**Conclusão:** estes módulos servem como referência do padrão correto de isolamento do PyMongo, mas não serão reescritos nesta etapa para evitar mudanças desnecessárias.

### 5. Outros módulos

O repositório possui uma camada econômica global extensa. Os acessos devem ser tratados na continuação da migração, depois que a fronteira assíncrona estiver consolidada. Não é seguro transformar todos os módulos automaticamente sem preservar a ordem de leitura/escrita e os invariantes de cada fluxo.

## Auditoria conjunta — fluxo de impacto

O problema não é apenas “uma query lenta”. O padrão sistêmico é:

```text
Discord event
    -> async handler/listener
        -> função Python normal
            -> PyMongo síncrono
                -> espera de rede/servidor
                    -> event loop bloqueado
                        -> outros eventos aguardam
```

O caso mais crítico é:

```text
mensagem Discord
    -> AutoMod.on_message
        -> CONFIG.find_one()
            -> bloqueio do event loop
```

E existe uma segunda amplificação:

```text
evento/comando
    -> várias funções
        -> várias queries síncronas sequenciais
            -> soma de latências
```

## Ranking de prioridade

| Prioridade | Área | Motivo |
|---|---|---|
| P0 | AutoMod `on_message` | Executado no caminho de mensagens e consulta Mongo síncrono |
| P0 | Fronteira central PyMongo | Sem ela, cada módulo pode introduzir novo bloqueio |
| P1 | Logs | Listener frequente + consulta de configuração |
| P1 | Boas-vindas | Listener de entrada/saída + consulta de configuração |
| P1 | Combate/party | Muitos round-trips e estado mutável |
| P2 | Treino | Consultas redundantes e cooldown |
| P2 | Status/magias | Consultas síncronas dentro de comandos assíncronos |
| P2 | Economia global | Grande superfície; migrar depois de estabilizar o padrão |

## Decisões de segurança

1. Não migrar de PyMongo para Motor/Async Mongo nesta rodada.
2. Não alterar regras de negócio, cooldowns, dano, dinheiro, XP ou estado de combate nesta etapa.
3. Criar uma única fronteira assíncrona (`asyncio.to_thread`) para o PyMongo existente.
4. Corrigir primeiro os listeners globais.
5. Cachear somente configurações de servidor e dados estáticos; não cachear saldo, HP, XP, inventário ou cooldown como fonte de verdade.
6. Invalidar/atualizar cache imediatamente após alterações administrativas.
7. Uma mudança por vez, sempre na branch `perf/mongo-nonblocking`.

## Resultado da Etapa 1

A causa estrutural da latência foi confirmada: **PyMongo síncrono é chamado a partir de caminhos assíncronos, especialmente listeners globais**. O hot path de maior risco é o AutoMod. A correção segura começa por uma fronteira assíncrona central, seguida dos listeners e, somente depois, de otimizações de cache/redução de round-trips.
