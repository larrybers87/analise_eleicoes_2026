---
name: tse-dados
description: Use antes de escrever ou alterar qualquer código que baixe, leia ou interprete dados do TSE (API JSON de resultados, arquivos de urna, CSVs do Dados Abertos). Contém URLs, códigos de eleição e regras anti-bloqueio.
---

# Dados do TSE — regras de uso

Referência completa em `docs/DADOS.md`. Leia a seção relevante antes de codar.

## Constantes 2026
- Base: `https://resultados.tse.jus.br/oficial`, ciclo `ele2026`, pleito `3220`.
- Presidente: eleição `6257` (1º turno), `6258` (2º turno), cargo `1` → `c0001`.
- Estadual: `6259` / `6260`. Cargos: Gov `3`, Sen `5`, DepFed `6`, DepEst `7`, DepDist `8`.
- Eleição no nome do arquivo com 6 dígitos (`e006257`); cargo com 4 (`c0001`); município TSE com 5 (`75353`).

## Regras anti-bloqueio (obrigatórias)
1. Máximo ~10 req/s (limite oficial 100/s, bloqueio de 10 min renovável).
2. Nunca gerar URL de município fora do arquivo de config `mun-e006257-cm.json`. 404 em sequência bloqueia o IP.
3. Cache em `data/raw/<ciclo>/<eleicao>/...` espelhando o caminho remoto. Se o arquivo existe, não baixe de novo (exceto `--force`).
4. Retry com backoff exponencial (tenacity) só para 5xx/timeout; 404 não é retentado — é logado e a coleta para se passar de 5.
5. Ao receber 403/429: parar tudo e aguardar 10 min.

## Validação depois de parsear
- Soma de votos dos municípios == total da UF == total BR (por candidato e brancos/nulos/abstenção).
- `comparecimento + abstencao == eleitorado`.
- `validos + brancos + nulos == comparecimento` (brancos não são válidos — Lei 9.504/97; votos "anulados sub judice" precisam de tratamento à parte, ver spec EA20).
- Divergências vão para `docs/DADOS.md` → "Armadilhas".
