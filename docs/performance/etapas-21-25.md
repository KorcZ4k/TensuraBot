# Etapas 21–25 — Paridade e hardening

## Etapa 21 — Paridade funcional
- Auditoria dos módulos reestruturados de combate, magias e status.
- Os motores legados permanecem preservados em `*_sync.py`.
- Corrigido o carregamento da extensão de magias com `setup()` explícito.

## Etapa 22 — Combate sem corrida de escrita
- As escritas Mongo continuam fora do event loop.
- Tarefas pendentes de combate são aguardadas após cada comando do Cog.
- `cog_unload` também aguarda escritas pendentes.
- Isso evita que um comando seguinte observe o banco antes da conclusão da escrita anterior.

## Etapa 23 — Remoção de divergências
- O comando `status` voltou a usar o avatar do autor e o timestamp com fuso do comportamento original.
- Removido código/import redundante do wrapper de combate.

## Etapa 24 — Índices resilientes
- `ensure_indexes()` agora verifica os índices existentes por chave antes de criar.
- Um índice equivalente com nome diferente não provoca conflito desnecessário no startup.

## Etapa 25 — Regressão
- Testes adicionados para presença de `setup()` nos wrappers.
- Testes verificam que os motores legados continuam presentes.
- Teste verifica que o startup usa `cadastro_async()`.
- Os testes existentes de cache e concorrência continuam preservados.

## Validação
A validação estática e estrutural foi feita contra a árvore da branch. Não foi possível executar um ambiente completo Discord + MongoDB neste ambiente, portanto não é declarado teste de integração em produção.
