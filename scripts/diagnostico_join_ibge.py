"""Diagnóstico (não corrige nada): cruza `presidente_t1_municipio_totais.parquet`
com a malha de municípios do IBGE via `geobr`, por `cd_mun_ibge`.

Reporta:
  - municípios do TSE sem par no IBGE (esperado: os do exterior, sem `cdi`);
  - municípios do TSE do Brasil (não exterior) sem par no IBGE (problema real,
    se houver);
  - municípios do IBGE sem par no TSE.

Uso:
    python scripts/diagnostico_join_ibge.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import geobr
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eleicao import config  # noqa: E402


def main() -> int:
    mun_totais = pd.read_parquet(config.DATA_PROCESSED / "presidente_t1_municipio_totais.parquet")

    gdf_ibge = geobr.read_municipality(year=2024, show_progress=False)
    gdf_ibge = gdf_ibge.assign(cd_mun_ibge=gdf_ibge["code_muni"].astype("Int64").astype(str))

    tse_brasil = mun_totais[~mun_totais["eh_exterior"]].copy()
    tse_exterior = mun_totais[mun_totais["eh_exterior"]].copy()

    print(f"municípios TSE total: {len(mun_totais)}")
    print(f"  Brasil (eh_exterior=False): {len(tse_brasil)}")
    print(f"  Exterior (eh_exterior=True): {len(tse_exterior)}")
    print(f"municípios IBGE (geobr, year=2024): {len(gdf_ibge)}")

    tse_sem_cdi = tse_brasil[tse_brasil["cd_mun_ibge"].isna() | (tse_brasil["cd_mun_ibge"] == "")]
    print(
        f"\nmunicípios do TSE marcados como Brasil mas SEM cd_mun_ibge preenchido: "
        f"{len(tse_sem_cdi)}"
    )
    if len(tse_sem_cdi):
        print(tse_sem_cdi[["uf", "cd_mun_tse", "nm_mun"]].to_string(index=False))

    ids_tse_brasil = set(tse_brasil["cd_mun_ibge"].dropna()) - {""}
    ids_ibge = set(gdf_ibge["cd_mun_ibge"])

    tse_sem_par_ibge = ids_tse_brasil - ids_ibge
    ibge_sem_par_tse = ids_ibge - ids_tse_brasil

    print(
        f"\nmunicípios do TSE (Brasil, com cd_mun_ibge) SEM par na malha IBGE: "
        f"{len(tse_sem_par_ibge)}"
    )
    if tse_sem_par_ibge:
        divergentes = tse_brasil[tse_brasil["cd_mun_ibge"].isin(tse_sem_par_ibge)]
        print(divergentes[["uf", "cd_mun_tse", "cd_mun_ibge", "nm_mun"]].to_string(index=False))

    print(f"\nmunicípios do IBGE SEM par no TSE: {len(ibge_sem_par_tse)}")
    if ibge_sem_par_tse:
        divergentes_ibge = gdf_ibge[gdf_ibge["cd_mun_ibge"].isin(ibge_sem_par_tse)]
        print(divergentes_ibge[["cd_mun_ibge", "name_muni", "abbrev_state"]].to_string(index=False))

    print(f"\nmunicípios do exterior (TSE, sem cd_mun_ibge por natureza): {len(tse_exterior)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
