"""Processa Resultados 2022 (Presidente) do Portal de Dados Abertos do TSE.

Lê os ZIPs já baixados em `data/raw/dadosabertos/` (não baixa nada — baixar
manualmente ou com um script futuro, ver docs/DADOS.md) e gera, para o 1º e
o 2º turno:

  - `data/processed/presidente_2022_t<turno>_municipio.parquet` (candidatos,
    schema comparável a `presidente_t1_municipio.parquet` de 2026)
  - `data/processed/presidente_2022_t<turno>_municipio_totais.parquet`
    (eleitorado/comparecimento/abstenção/brancos/nulos)

Também confere o join com o config de municípios de 2026
(`mun-e006257-cm.json`) pelo código TSE (`cd_mun_tse`), reportando
municípios sem par de cada lado, e imprime a soma nacional por candidato
(1º turno) para conferência manual contra os números de referência.

Uso:
    python scripts/processar_presidente_2022.py
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eleicao import config  # noqa: E402
from eleicao.parse_dadosabertos_2022 import parse_candidatos_2022, parse_totais_2022  # noqa: E402

RAIZ_DADOSABERTOS = (
    config.DATA_RAW / "dadosabertos" / "cdn.tse.jus.br" / "estatistica" / "sead" / "odsele"
)
ZIP_CANDIDATOS = (
    RAIZ_DADOSABERTOS / "votacao_candidato_munzona" / "votacao_candidato_munzona_2022.zip"
)
MEMBRO_CANDIDATOS = "votacao_candidato_munzona_2022_BR.csv"
ZIP_TOTAIS = RAIZ_DADOSABERTOS / "detalhe_votacao_munzona" / "detalhe_votacao_munzona_2022.zip"
MEMBRO_TOTAIS = "detalhe_votacao_munzona_2022_BR.csv"


def _ler_csv_do_zip(caminho_zip: Path, membro: str) -> pd.DataFrame:
    with zipfile.ZipFile(caminho_zip) as z, z.open(membro) as f:
        return pd.read_csv(f, sep=";", encoding="latin-1", quotechar='"', dtype=str)


def _carregar_config_municipios_2026() -> dict[str, str]:
    """`{uf+cd_mun_tse(5 dígitos): cd_mun_ibge}` a partir do config de 2026 (EA12)."""
    caminho = config.caminho_local(config.caminho_config_municipios(config.ELEICAO_FEDERAL_T1))
    cfg = json.loads(Path(caminho).read_text(encoding="utf-8"))
    mapa = {}
    for abrangencia in cfg["abr"]:
        uf = abrangencia["cd"]
        for municipio in abrangencia["mu"]:
            mapa[f"{uf}{municipio['cd']}"] = municipio["cdi"] or None
    return mapa


def _reportar_join(municipios_2022: set[str], municipios_2026: set[str]) -> None:
    so_2022 = sorted(municipios_2022 - municipios_2026)
    so_2026 = sorted(municipios_2026 - municipios_2022)
    print(f"  municípios em 2022 sem par em 2026 (config e006257): {len(so_2022)}")
    if so_2022:
        print(f"    {so_2022[:20]}{'...' if len(so_2022) > 20 else ''}")
    print(f"  municípios em 2026 (config e006257) sem par em 2022: {len(so_2026)}")
    if so_2026:
        print(f"    {so_2026[:20]}{'...' if len(so_2026) > 20 else ''}")


def processar_turno(
    turno: int,
    df_candidatos_bruto: pd.DataFrame,
    df_totais_bruto: pd.DataFrame,
    mapa_cd_mun_ibge: dict[str, str | None],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    candidatos = parse_candidatos_2022(df_candidatos_bruto, turno=turno)
    totais = parse_totais_2022(df_totais_bruto, turno=turno)

    totais["cd_mun_ibge"] = (totais["uf"] + totais["cd_mun_tse"]).map(mapa_cd_mun_ibge)

    candidatos = candidatos.merge(
        totais[["uf", "cd_mun_tse", "validos"]], on=["uf", "cd_mun_tse"], how="left"
    )
    candidatos["pct_validos"] = (
        100.0 * candidatos["votos"] / candidatos["validos"].replace(0, pd.NA)
    ).fillna(0.0)
    candidatos = candidatos[
        ["uf", "cd_mun_tse", "nr_candidato", "nm_urna", "partido", "votos", "pct_validos"]
    ]
    return candidatos, totais


def main() -> int:
    if not ZIP_CANDIDATOS.exists() or not ZIP_TOTAIS.exists():
        print(
            "ERRO: ZIPs de Dados Abertos 2022 não encontrados em "
            f"{RAIZ_DADOSABERTOS} — baixar antes (ver docs/DADOS.md).",
            file=sys.stderr,
        )
        return 1

    print("lendo CSVs (membro BR, abrangência federal) dos ZIPs...")
    df_candidatos_bruto = _ler_csv_do_zip(ZIP_CANDIDATOS, MEMBRO_CANDIDATOS)
    df_totais_bruto = _ler_csv_do_zip(ZIP_TOTAIS, MEMBRO_TOTAIS)
    print(f"  candidatos: {len(df_candidatos_bruto)} linhas (zona×candidato, todos os turnos)")
    print(f"  totais: {len(df_totais_bruto)} linhas (zona, todos os turnos)")

    mapa_cd_mun_ibge = _carregar_config_municipios_2026()
    municipios_2026 = set(mapa_cd_mun_ibge)

    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)

    for turno in (1, 2):
        print("\n--- 1º turno ---" if turno == 1 else "\n--- 2º turno ---")
        candidatos, totais = processar_turno(
            turno, df_candidatos_bruto, df_totais_bruto, mapa_cd_mun_ibge
        )
        municipios_2022 = set(totais["uf"] + totais["cd_mun_tse"])
        print(f"  {len(totais)} municípios, {len(candidatos)} linhas de candidato")
        _reportar_join(municipios_2022, municipios_2026)

        soma_candidatos = (
            candidatos.groupby("nr_candidato")["votos"].sum().sort_values(ascending=False)
        )
        print("  soma nacional por candidato (top 5):")
        for nr, votos in soma_candidatos.head(5).items():
            nome = candidatos.loc[candidatos["nr_candidato"] == nr, "nm_urna"].iloc[0]
            print(f"    {nr} {nome}: {votos}")

        candidatos.to_parquet(
            config.DATA_PROCESSED / f"presidente_2022_t{turno}_municipio.parquet", index=False
        )
        totais.to_parquet(
            config.DATA_PROCESSED / f"presidente_2022_t{turno}_municipio_totais.parquet",
            index=False,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
