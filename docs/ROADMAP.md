# Roadmap

Fases macro. O detalhe do dia a dia fica no `STATUS.md`.

**F0 — Setup.** Ambiente, GitHub, Claude Code, documentação. ✅ (falta só executar o setup local)

**F1 — Base Presidente 1º turno por município.** ✅ Coletor da API JSON, parser EA20, Parquet normalizado, testes de invariantes, join com IBGE. Inclui exterior. 3 divergências reais documentadas em `docs/DADOS.md` (não bloqueiam F2).

**F2 — Mapa v1.** ✅ `web/` com MapLibre: Brasil por UF ↔ Brasil por município (toggle) → drill-down por UF → município; cor por candidato (mistura OKLab e modo vencedor+margem alternáveis); painel lateral com resultados da região clicada; busca por nome; responsivo (bottom-sheet no celular). Exterior: card de totais na visão Brasil + tabela ordenável dos 186 locais (sem mapa na v1 — ver F2.1). Dados gerados por `scripts/exportar_web.py`, conferidos por `scripts/verificar_export_web.py`. Divergências do plano em `docs/DECISOES.md` D-016.

**F2.2 — Seleção de candidato.** ✅ Seletor (cor + nome + % nacional) e dois modos novos para o candidato escolhido: **"Onde venceu"** (só onde ele foi 1º, na cor dele pela margem; cinza claro com opacidade baixa no resto) e **"Força"** (todo o mapa pelo % de válidos dele, de 0 ao percentil 98 entre os 5.571 municípios). Funciona em Brasil por UF, Brasil por município e no drill-down por UF; no exterior, ordena e destaca a tabela. Legenda própria por modo (com os % reais nos ticks), painel lateral com municípios/UFs vencidos, top 10 por % e por votos, melhor/pior UF e resultado no exterior, e estado na URL (`?camada=&uf=&mun=&modo=&candidato=`). Dados novos: `resultados/forca/cand_<nr>.json` (12) + `resumo_candidatos.json` + `votos_cand` em `br.json`/`exterior.json` — **+367KB brutos / +114KB gzip** no `web/data/`, carga inicial praticamente igual (70,3 → 72,2KB gzip). Decisões em `docs/DECISOES.md` D-018.

**F2.1 — Geocodificação do exterior.** As 186 "cidades" do exterior no config do TSE só têm nome, sem coordenadas/país. Construir uma tabela offline (cidade → país/coordenadas aproximadas) para plotar como pontos no mapa-múndi (talvez agregados por país). Lista estática de postos consulares, não muda com frequência — não bloqueia F2.

**F3 — Análises.** Base de enriquecimento ✅ (05/10/2026): Presidente 2022 (1º/2º turno, município), perfil do eleitorado 2026 por município (sexo/faixa etária incl. 16-17 e 70+/grau de instrução), população Censo 2022 + PIB per capita municipal (IBGE) — 6 Parquet novos em `data/processed/`, schemas em `docs/DADOS.md`. Falta: notebooks + página de análises propriamente ditos — votos por região (N/NE/CO/SE/S/exterior), abstenção/brancos/nulos por recorte, distribuição de margens, concentração (ex.: quantos municípios fazem X% dos votos de cada candidato), comparativo 2022→2026, correlação com perfil do eleitorado/IBGE.

**F4 — Zona/seção.** Quando sair o CSV de seção 2026 (ou via BU, plano B). Mapa por local de votação (pontos) e por zona (polígonos aproximados).

**F5 — 2º turno (25/10, se houver).** Mesmo pipeline com eleição 6258; comparativo de transferência de votos T1→T2 por município.

**F6 — Outros cargos.** Governador, Senador, Deputados (eleição 6259/6260). Só se F1–F4 estiverem sólidas.

**Publicação.** ✅ GitHub Pages via Actions (`.github/workflows/pages.yml`), publicando `web/` (dados em `web/data/`, gerados de `data/processed/`). https://larrybers87.github.io/analise_eleicoes_2026/
