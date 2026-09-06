# Etapas 11–15 — Performance MongoDB

## Etapa 11 — Cache seguro

- Catálogos estáticos de magia já possuem cache de processo em `magias_catalog_cache.py`.
- Monstros e golpes do combate são carregados uma vez na importação de `luta.py` e permanecem somente leitura no motor.
- A configuração de treino é carregada uma vez em `treino.py`.
- Foi adicionada `database/python/json_cache.py` para novos catálogos estáticos.
- O cache devolve cópias profundas, evitando que uma chamada altere o valor compartilhado.

Não foi aplicado cache em dados de jogador, economia ou combate mutável.

## Etapa 12 — Instrumentação

`mongodb.py` agora suporta `MONGO_PERF_LOG=1` para registrar:

- número de operações;
- duração total e média;
- chamadas lentas (>= 250 ms);
- erros.

Com a variável desligada, `run_db()` mantém o caminho mínimo existente.

## Etapa 13 — Concorrência

`tests/test_performance.py` cobre:

- isolamento do cache JSON;
- invalidação/recarregamento do cache;
- execução concorrente de operações offloaded sem serialização artificial.

Os testes não fingem validar um MongoDB real: isso exige um ambiente de integração com Mongo disponível.

## Etapa 14 — Resiliência

O cliente PyMongo mantém:

- `serverSelectionTimeoutMS=10000`;
- `connectTimeoutMS=10000`;
- `socketTimeoutMS=20000`;
- `retryReads=True`;
- `retryWrites=True`;
- pool máximo de 50 conexões.

Foi adicionado `mongo_healthcheck()` para verificações futuras sem bloquear o event loop e `close_db()` para encerramento limpo. O `main.py` fecha o cliente no `finally`.

Não foi adicionado retry manual genérico em `run_db()`: repetir arbitrariamente operações de escrita poderia alterar semântica ou produzir efeitos duplicados.

## Etapa 15 — Driver assíncrono

A migração para Motor/Async Mongo foi **deliberadamente adiada**.

O projeto atualmente usa PyMongo síncrono isolado por `asyncio.to_thread()`, o que remove o bloqueio do event loop sem trocar o driver nem introduzir uma migração ampla de APIs.

Uma troca de driver só deve acontecer depois de medir o ganho real com a instrumentação e executar testes de integração/concurrency. Neste estágio, mudar o driver aumentaria o raio de risco sem evidência de necessidade.
