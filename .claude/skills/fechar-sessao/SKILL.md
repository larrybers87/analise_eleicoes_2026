---
name: fechar-sessao
description: Use ao terminar qualquer tarefa ou quando o usuário disser "fecha a sessão", "atualiza a doc" ou "/fechar-sessao". Atualiza STATUS.md, registra decisões e descobertas de dados, e prepara o commit.
---

# Fechar sessão

Objetivo: a próxima sessão (sua ou do usuário) começa sabendo exatamente onde parou, lendo só `CLAUDE.md` + `docs/STATUS.md`.

1. **`docs/STATUS.md`**
   - Atualize a data na linha "Última atualização" com um resumo de 5–10 palavras.
   - Mova itens concluídos para "Feito" (uma linha cada, com o arquivo/comando relevante). Se "Feito" passar de ~15 linhas, condense os mais antigos numa linha por fase.
   - Reescreva "Próximo" com no máximo 5 itens, em ordem, acionáveis.
   - Registre bloqueios e dúvidas em aberto.
2. **`docs/DECISOES.md`** — se foi tomada decisão não-trivial (biblioteca, formato, abordagem, trade-off), adicione entrada `D-NNN` no fim.
3. **`docs/DADOS.md`** — se descobriu algo sobre os dados (campo, encoding, URL, armadilha, inconsistência), registre na seção certa.
4. **`docs/ROADMAP.md`** — só mude se uma fase foi concluída ou o escopo mudou.
5. **`CLAUDE.md`** — só mude se mudou stack, estrutura, comandos ou regra de trabalho.
6. Rode `ruff check .` e `pytest -q` se houve mudança de código; reporte falhas no STATUS.
7. Proponha a mensagem de commit (português, imperativo) e faça o commit se o usuário já autorizou commits na sessão.

Não duplique informação entre arquivos. Escreva curto.
