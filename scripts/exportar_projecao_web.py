"""Gera `web/data/projecao_backtest.json` (aba "2º turno: projeção" do site).

Nesta fase a aba mostra SÓ o método e o backtest 2018→2022; a projeção 2026 só é
publicada junto com o resultado real do 2º turno (STATUS.md). Por isso este script lê uma
lista FECHADA de arquivos, por nome explícito, e aborta se algum caminho tiver "2026"
(proteção contra ler `data/processed/projecao_t2_2026_*`, a seção 7 do método ou
`projecao_t2_2026_linhas_compostas.csv`). Lógica em `eleicao.backtest_web`.

Uso:
    python scripts/exportar_projecao_web.py
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eleicao import backtest_web, config  # noqa: E402

INTERIM = config.RAIZ / "data" / "interim" / "projecao_t2"
PROC = config.DATA_PROCESSED
SAIDA = config.RAIZ / "web" / "data" / "projecao_backtest.json"

GERADO_POR = {
    INTERIM: "scripts/backtest_2018_2022.py",
    PROC: "scripts/processar_presidente_2018.py e scripts/processar_presidente_2022.py",
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

PROIBIDO = ("2026", "projecao_t2_2026", "METODO_secao7")


def checar_caminho(caminho: Path) -> Path:
    """Aborta se o caminho apontar para algo de 2026; senão, exige que o arquivo exista."""
    nome = caminho.as_posix()
    for termo in PROIBIDO:
        if termo in nome.replace(config.RAIZ.as_posix(), ""):
            raise SystemExit(f"ABORTADO: caminho proibido nesta fase ({termo!r}): {caminho}")
    if not caminho.exists():
        origem = next((s for d, s in GERADO_POR.items() if caminho.is_relative_to(d)), "?")
        raise SystemExit(f"arquivo ausente: {caminho}\n  gere com: python {origem}")
    return caminho


def ler_csv(caminho: Path) -> pd.DataFrame:
    return pd.read_csv(checar_caminho(caminho), dtype={"uf": str})


def ler_parquet(caminho: Path) -> pd.DataFrame:
    return pd.read_parquet(checar_caminho(caminho))


def main() -> int:
    for c in [*CSV_BACKTEST.values(), *TOTAIS.values(), CAND_2022_T2]:
        checar_caminho(c)  # falha cedo, antes de ler qualquer coisa
    dados = backtest_web.montar(
        resumo=ler_csv(CSV_BACKTEST["resumo"]),
        erros_uf=ler_csv(CSV_BACKTEST["erros_uf"]),
        ablacao=ler_csv(CSV_BACKTEST["ablacao"]),
        totais={
            ano: {turno: ler_parquet(TOTAIS[(ano, turno)]) for turno in (1, 2)}
            for ano in (2018, 2022)
        },
        cand_2022_t2=ler_parquet(CAND_2022_T2),
    )
    dados["fontes"] = [
        p.relative_to(config.RAIZ).as_posix()
        for p in [*CSV_BACKTEST.values(), *TOTAIS.values(), CAND_2022_T2]
    ]
    texto = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    SAIDA.write_bytes(texto)
    print(
        f"  {SAIDA.name}: {len(texto) / 1024:.1f} KB bruto, "
        f"{len(gzip.compress(texto, 9)) / 1024:.1f} KB gzip; "
        f"{len(dados['textos'])} números de texto; escala ±{dados['escala']['limite_pp']} p.p."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
