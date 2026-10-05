# Roadmap

Fases macro. O detalhe do dia a dia fica no `STATUS.md`.

**F0 — Setup.** Ambiente, GitHub, Claude Code, documentação. ✅ (falta só executar o setup local)

**F1 — Base Presidente 1º turno por município.** ✅ Coletor da API JSON, parser EA20, Parquet normalizado, testes de invariantes, join com IBGE. Inclui exterior. 3 divergências reais documentadas em `docs/DADOS.md` (não bloqueiam F2).

**F2 — Mapa v1.** `web/` com MapLibre: Brasil → UF → município; cor por candidato (mistura OKLab e modo vencedor+margem alternáveis); painel lateral com resultados da região clicada. Exterior como camada de pontos.

**F3 — Análises.** Notebooks + página de análises: votos por região (N/NE/CO/SE/S/exterior), abstenção/brancos/nulos por recorte, distribuição de margens, concentração (ex.: quantos municípios fazem X% dos votos de cada candidato), correlação com eleitorado (perfil por seção do Dados Abertos).

**F4 — Zona/seção.** Quando sair o CSV de seção 2026 (ou via BU, plano B). Mapa por local de votação (pontos) e por zona (polígonos aproximados).

**F5 — 2º turno (25/10, se houver).** Mesmo pipeline com eleição 6258; comparativo de transferência de votos T1→T2 por município.

**F6 — Outros cargos.** Governador, Senador, Deputados (eleição 6259/6260). Só se F1–F4 estiverem sólidas.

**Publicação.** GitHub Pages servindo `web/` + `data/processed/` leve.
