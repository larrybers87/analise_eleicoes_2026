"""Gera `web/data/projecao_backtest.json` (aba "2º turno: projeção" do site).

A aba tem o método, o backtest 2018→2022 e, com a flag `--publicar-projecao-2026`, o bloco
"A projeção de 2026" (D-037). A leitura é por LISTA FECHADA de arquivos, por nome exato:

- sempre: os CSV do backtest (`data/interim/projecao_t2/`), os totais municipais de 2018 e
  2022, os votos do T2 2022 e os totais do T1 2026 (`presidente_t1_municipio_totais.parquet`,
  resultado oficial do 1º turno, só com a flag);
- só com a flag: `data/processed/projecao_t2_2026_br.parquet` e `_uf.parquet`.

Qualquer outro caminho com "2026" no nome aborta, com ou sem a flag (ex.: `_municipio`,
`linhas_compostas`, a seção 7 do método). Sem a flag, o JSON sai com `"projecao_2026": null`
e a página mostra o texto de "será publicada depois".

A data da projeção é a do commit que ADICIONOU `projecao_t2_2026_br.parquet` ao repositório
(`git log --diff-filter=A`), verificável publicamente; sem git, o script falha (não usa mtime).

Uso:
    python scripts/exportar_projecao_web.py --publicar-projecao-2026
    python scripts/exportar_projecao_web.py          # sem o bloco 2026
"""

from __future__ import annotations

import argparse
import gzip
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eleicao import backtest_web, config  # noqa: E402

INTERIM = config.RAIZ / "data" / "interim" / "projecao_t2"
PROC = config.DATA_PROCESSED
SAIDA = config.RAIZ / "web" / "data" / "projecao_backtest.json"

GERADO_POR = {
    INTERIM: "scripts/backtest_2018_2022.py",
    PROC: "os scripts/processar_presidente*.py e scripts/projetar_t2_2026.py",
}

CSV_BACKTEST = {
    "resumo": INTERIM / "backtest_resumo.csv",
    "erros_uf": INTERIM / "backtest_erros_uf.csv",
    "ablacao": INTERIM / "backtest_ablacao_linhas.csv",
}
TOTAIS = {
    (ano, turno): PROC / f"presidente_{ano}_t{turno}_municipio_totais.parquet"
    for ano in (2018, 2022)
    for turno in (1, 2)
}
CAND_2022_T2 = PROC / "presidente_2022_t2_municipio.parquet"
TOTAIS_T1_2026 = PROC / "presidente_t1_municipio_totais.parquet"
PROJECAO_BR = PROC / "projecao_t2_2026_br.parquet"
PROJECAO_UF = PROC / "projecao_t2_2026_uf.parquet"

PERMITIDOS_COM_FLAG = frozenset({PROJECAO_BR, PROJECAO_UF})
"""Os ÚNICOS arquivos com "2026" no nome que podem ser lidos, e só com a flag."""

PROIBIDO = ("2026", "METODO_secao7")


def checar_caminho(caminho: Path, publicar: bool = False) -> Path:
    """Aborta se o caminho tiver "2026" e não estiver na lista fechada (ou faltar a flag)."""
    rel = caminho.as_posix().replace(config.RAIZ.as_posix(), "")
    na_lista = publicar and caminho in PERMITIDOS_COM_FLAG
    if any(t in rel for t in PROIBIDO) and not na_lista:
        raise SystemExit(
            f"ABORTADO: caminho fora da lista fechada"
            f"{'' if publicar else ' (sem --publicar-projecao-2026)'}: {caminho}"
        )
    if not caminho.exists():
        origem = next((s for d, s in GERADO_POR.items() if caminho.is_relative_to(d)), "?")
        raise SystemExit(f"arquivo ausente: {caminho}\n  gerado por: {origem}")
    return caminho


def commit_da_projecao() -> dict[str, str]:
    """Hash e data (ISO, fuso do commit) do commit que adicionou o parquet BR da projeção."""
    rel = PROJECAO_BR.relative_to(config.RAIZ).as_posix()
    cmd = ["git", "log", "--diff-filter=A", "--format=%H %cI", "--", rel]
    try:
        saida = subprocess.run(
            cmd, cwd=config.RAIZ, capture_output=True, text=True, check=True
        ).stdout.split()
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        raise SystemExit(f"git indisponível para datar a projeção ({' '.join(cmd)}): {e}") from e
    if len(saida) < 2:
        raise SystemExit(f"nenhum commit adicionou {rel}: versione o parquet antes de publicar")
    # o mais antigo, se houver mais de um "A" (ex.: removido e readicionado)
    return {"hash": saida[-2], "data_iso": saida[-1]}


def gerar(publicar: bool) -> tuple[dict[str, Any], list[Path]]:
    """Monta o JSON. Devolve (dados, caminhos lidos), na ordem de leitura."""
    lidos: list[Path] = []

    def ler(caminho: Path) -> pd.DataFrame:
        checar_caminho(caminho, publicar)
        lidos.append(caminho)
        if caminho.suffix == ".csv":
            return pd.read_csv(caminho, dtype={"uf": str})
        return pd.read_parquet(caminho)

    lista = [*CSV_BACKTEST.values(), *TOTAIS.values(), CAND_2022_T2]
    if publicar:
        lista += [TOTAIS_T1_2026, PROJECAO_BR, PROJECAO_UF]
    for c in lista:
        checar_caminho(c, publicar)  # falha cedo, antes de ler qualquer coisa

    dados = backtest_web.montar(
        resumo=ler(CSV_BACKTEST["resumo"]),
        erros_uf=ler(CSV_BACKTEST["erros_uf"]),
        ablacao=ler(CSV_BACKTEST["ablacao"]),
        totais={
            ano: {turno: ler(TOTAIS[(ano, turno)]) for turno in (1, 2)} for ano in (2018, 2022)
        },
        cand_2022_t2=ler(CAND_2022_T2),
    )
    dados["projecao_2026"] = None
    dados["comparacao_t2"] = None  # previsto × real: preenchido após a totalização do T2
    if publicar:
        from eleicao import projecao_web  # importa cvxpy (via projecao_t2): só com a flag

        dados["projecao_2026"] = projecao_web.montar_projecao(
            br=ler(PROJECAO_BR),
            uf=ler(PROJECAO_UF),
            totais_t1_2026=ler(TOTAIS_T1_2026),
            bn_t1_por_ano={a: dados["mobilizacao"][a]["bn_t1"] for a in ("2018", "2022")},
            commit=commit_da_projecao(),
        )
    dados["fontes"] = [p.relative_to(config.RAIZ).as_posix() for p in lidos]
    return dados, lidos


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--publicar-projecao-2026",
        action="store_true",
        help="inclui o bloco da projeção 2026 (lê só projecao_t2_2026_br/_uf.parquet)",
    )
    args = ap.parse_args(argv)
    dados, lidos = gerar(args.publicar_projecao_2026)
    texto = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    SAIDA.write_bytes(texto)
    print(f"  lidos: {len(lidos)} arquivos")
    for p in lidos:
        print(f"    {p.relative_to(config.RAIZ).as_posix()}")
    print(
        f"  {SAIDA.name}: {len(texto) / 1024:.1f} KB bruto, "
        f"{len(gzip.compress(texto, 9)) / 1024:.1f} KB gzip; "
        f"projeção 2026: {'publicada' if dados['projecao_2026'] else 'null'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
