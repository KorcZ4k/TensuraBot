# Performance — Etapas 16–20

## Etapa 16 — Cadastro fora do event loop

Criada `cadastro_async()` em `database/python/users.py`. A construção das operações continua síncrona e barata, enquanto os seis `bulk_write` do Mongo passam por `run_db()`.

A API síncrona `cadastro()` foi preservada para compatibilidade.

## Etapa 17 — Escritas independentes em paralelo

Os seis conjuntos de cadastro (`Jogadores`, `Mora`, `Hunos`, `Inventários`, `Magias` e `Habilidades`) são enviados em paralelo com `asyncio.gather`.

Isso reduz o tempo de parede do cadastro sem alterar os documentos ou filtros usados.

## Etapa 18 — Cadastro inicial de guilds em paralelo

O `on_ready` agora cadastra as guilds em paralelo, em vez de esperar uma guild terminar antes de iniciar a próxima.

Também foi extraído `_cadastrar_guild()` para manter a rotina simples.

## Etapa 19 — Reconexão sem recadastro global

`on_ready` pode ser disparado novamente após reconexões. O recadastro completo agora acontece apenas uma vez por processo.

Novos membros continuam sendo tratados por `on_member_join`, e falha durante o cadastro inicial não marca a inicialização como concluída, permitindo nova tentativa em um próximo `on_ready`.

## Etapa 20 — Instrumentação mais barata

O contador de métricas de `run_db()` deixou de usar um `asyncio.Lock` em cada operação.

Como a atualização do `Counter` ocorre sem `await` entre leitura/escrita, ela não é intercalada por outra coroutine no event loop. Os snapshots continuam sendo obtidos sem bloquear o event loop.

A instrumentação continua opcional: `MONGO_PERF_LOG=0` mantém o caminho normal sem medição detalhada.
