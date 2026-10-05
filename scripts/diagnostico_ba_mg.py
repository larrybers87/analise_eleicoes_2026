"""Diagnóstico da divergência BA/MG (ver docs/DADOS.md, "Divergências reais").

Compara `dg`/`hg`/`idg`/`and`/`tf`/`s.snt` dos 11 municípios divergentes (BA: 3,
MG: 8) com os mesmos campos do arquivo de UF correspondente — para checar se
município e UF vêm de **gerações diferentes** do backend do TSE (hipótese
registrada em docs/DADOS.md).

Não baixa nada: só lê o que já está em `data/raw/`. Rode depois de
`coletar_presidente.py` (coleta original ou com `--apenas`/`--force`).

Uso:
    python scripts/diagnostico_ba_mg.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eleicao import config  # noqa: E402

ELEICAO = config.ELEICAO_FEDERAL_T1

MUNICIPIOS_DIVERGENTES = {
    "ba": ["33693", "34673", "36013"],
    "mg": ["41556", "41696", "42005", "46078", "47198", "40622", "51977", "53171"],
}


def _campos(caminho_local: Path) -> dict:
    dado = json.loads(caminho_local.read_text(encoding="utf-8"))
    s = dado["s"]
    return {
        "dg": dado["dg"],
        "hg": dado["hg"],
        "idg": dado["idg"],
        "and": dado["and"],
        "tf": dado.get("tf"),
        "snt": s["snt"],
        "si": s["si"],
        "ts": s["ts"],
    }


def main() -> int:
    linhas: list[dict] = []

    for uf, municipios in MUNICIPIOS_DIVERGENTES.items():
        caminho_uf = config.caminho_local(
            config.caminho_resultado(ELEICAO, config.CARGO_PRESIDENTE, uf)
        )
        if not caminho_uf.exists():
            print(f"AVISO: arquivo de UF ausente: {caminho_uf}", file=sys.stderr)
            continue
        campos_uf = _campos(caminho_uf)
        linhas.append({"abrangencia": f"uf:{uf}", "uf": uf, "cd_mun": "-", **campos_uf})

        for cd_mun in municipios:
            caminho_mun = config.caminho_local(
                config.caminho_resultado(ELEICAO, config.CARGO_PRESIDENTE, uf, cd_mun)
            )
            if not caminho_mun.exists():
                print(f"AVISO: arquivo de município ausente: {caminho_mun}", file=sys.stderr)
                continue
            campos_mun = _campos(caminho_mun)
            linha = {"abrangencia": f"mun:{uf}:{cd_mun}", "uf": uf, "cd_mun": cd_mun, **campos_mun}
            linha["idg_diff_da_uf"] = campos_mun["idg"] != campos_uf["idg"]
            linha["dg_hg_diff_da_uf"] = (campos_mun["dg"], campos_mun["hg"]) != (
                campos_uf["dg"],
                campos_uf["hg"],
            )
            linhas.append(linha)

    df = pd.DataFrame(linhas)
    colunas = [
        "abrangencia",
        "dg",
        "hg",
        "idg",
        "and",
        "tf",
        "snt",
        "si",
        "ts",
        "idg_diff_da_uf",
        "dg_hg_diff_da_uf",
    ]
    colunas = [c for c in colunas if c in df.columns]
    print(df[colunas].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
