"""Processa Resultados 2018 (Presidente) do Portal de Dados Abertos do TSE.

Mesmo padrão e mesmos parsers de `processar_presidente_2022.py` (layout dos
CSVs idêntico). Lê os ZIPs de `data/raw/dadosabertos/` (já baixados) e gera
`data/processed/presidente_2018_t{1,2}_municipio.parquet` e
`..._municipio_totais.parquet`. `cd_mun_ibge` vem do config de 2026 (join por
`cd_mun_tse`); municípios de 2018 sem par em 2026 ficam com `None`.

Uso:
    python scripts/processar_presidente_2018.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import processar_presidente_2022 as base  # noqa: E402

from eleicao import config  # noqa: E402

ANO = 2018
ZIP_CANDIDATOS = (
    base.RAIZ_DADOSABERTOS / "votacao_candidato_munzona" / f"votacao_candidato_munzona_{ANO}.zip"
)
ZIP_TOTAIS = (
    base.RAIZ_DADOSABERTOS / "detalhe_votacao_munzona" / f"detalhe_votacao_munzona_{ANO}.zip"
)


def main() -> int:
    if not ZIP_CANDIDATOS.exists() or not ZIP_TOTAIS.exists():
        print(f"ERRO: ZIPs {ANO} não encontrados em {base.RAIZ_DADOSABERTOS}", file=sys.stderr)
        return 1
    cand_bruto = base._ler_csv_do_zip(ZIP_CANDIDATOS, f"votacao_candidato_munzona_{ANO}_BR.csv")
    tot_bruto = base._ler_csv_do_zip(ZIP_TOTAIS, f"detalhe_votacao_munzona_{ANO}_BR.csv")
    print(f"candidatos: {len(cand_bruto)} linhas; totais: {len(tot_bruto)} linhas")
    mapa = base._carregar_config_municipios_2026()
    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    for turno in (1, 2):
        print(f"\n--- {turno}º turno ---")
        candidatos, totais = base.processar_turno(turno, cand_bruto, tot_bruto, mapa)
        print(f"  {len(totais)} municípios, {len(candidatos)} linhas de candidato")
        base._reportar_join(set(totais["uf"] + totais["cd_mun_tse"]), set(mapa))
        candidatos.to_parquet(
            config.DATA_PROCESSED / f"presidente_{ANO}_t{turno}_municipio.parquet", index=False
        )
        totais.to_parquet(
            config.DATA_PROCESSED / f"presidente_{ANO}_t{turno}_municipio_totais.parquet",
            index=False,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
