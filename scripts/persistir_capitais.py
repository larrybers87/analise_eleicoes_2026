"""Gera data/processed/capitais.csv a partir do config bruto do TSE (uma vez, versionado).

Fonte: data/raw/ele2026/6257/config/mun-e006257-cm.json, flag `c == "s"` (ver docs/DADOS.md).
Uso:  python scripts/persistir_capitais.py
"""

from __future__ import annotations

import json

import pandas as pd

from eleicao import config

CAMINHO_CFG = config.caminho_local(config.caminho_config_municipios(config.ELEICAO_FEDERAL_T1))
SAIDA = config.DATA_PROCESSED / "capitais.csv"


def extrair_capitais(cfg: dict) -> pd.DataFrame:
    linhas = []
    for abr in cfg["abr"]:
        for mun in abr["mu"]:
            if mun.get("c") == "s":
                linhas.append({"uf": abr["cd"], "cd_mun_tse": mun["cd"], "nm_mun": mun["nm"]})
    df = pd.DataFrame(linhas).sort_values("uf").reset_index(drop=True)
    if len(df) != 27 or df["uf"].nunique() != 27:
        raise ValueError(f"esperava 27 capitais (1 por UF), obtive {len(df)}")
    return df


def main() -> None:
    cfg = json.loads(CAMINHO_CFG.read_text(encoding="utf-8"))
    df = extrair_capitais(cfg)
    df.to_csv(SAIDA, index=False, encoding="utf-8")
    print(f"{len(df)} capitais -> {SAIDA}")


if __name__ == "__main__":
    main()
