"""Processa população (Censo 2022) e PIB per capita municipal (IBGE).

Lê os arquivos já baixados em `data/raw/ibge/` (ver docs/DADOS.md → "4.
IBGE") e gera `data/processed/ibge_municipio.parquet`, indexado por
`cd_mun_ibge` (código de 7 dígitos, mesmo campo usado desde F1 para o join
TSE↔IBGE via `cdi`).

Uso:
    python scripts/processar_ibge.py
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eleicao import config  # noqa: E402
from eleicao.parse_ibge import parse_pib_municipios, parse_populacao_censo_2022  # noqa: E402

CAMINHO_POPULACAO = (
    config.DATA_RAW
    / "ibge"
    / "servicodados.ibge.gov.br"
    / "api"
    / "v3"
    / "agregados"
    / "4709"
    / "periodos"
    / "2022"
    / "variaveis"
    / "93.json"
)
CAMINHO_PIB_ZIP = (
    config.DATA_RAW
    / "ibge"
    / "ftp.ibge.gov.br"
    / "Pib_Municipios"
    / "2022_2023"
    / "base"
    / "base_de_dados_2010_2023_txt.zip"
)
MEMBRO_PIB_TXT = "PIB dos Municípios - base de dados 2010-2023.txt"
ANO_PIB_MAIS_RECENTE = "2023"


def main() -> int:
    if not CAMINHO_POPULACAO.exists():
        print(f"ERRO: população não encontrada em {CAMINHO_POPULACAO}", file=sys.stderr)
        return 1
    if not CAMINHO_PIB_ZIP.exists():
        print(f"ERRO: PIB municipal não encontrado em {CAMINHO_PIB_ZIP}", file=sys.stderr)
        return 1

    print("parseando população (Censo 2022, SIDRA agregado 4709, variável 93)...")
    populacao = parse_populacao_censo_2022(CAMINHO_POPULACAO.read_bytes())
    print(f"  {len(populacao)} municípios")

    print(f"parseando PIB per capita municipal (ano {ANO_PIB_MAIS_RECENTE})...")
    with zipfile.ZipFile(CAMINHO_PIB_ZIP) as z, z.open(MEMBRO_PIB_TXT) as f:
        texto = f.read().decode("latin-1")
    pib = parse_pib_municipios(texto, ano=ANO_PIB_MAIS_RECENTE)
    print(f"  {len(pib)} municípios")

    combinado = populacao.merge(
        pib[["cd_mun_ibge", "pib_mil_reais", "pib_per_capita_reais"]],
        on="cd_mun_ibge",
        how="outer",
        indicator=True,
    )
    so_populacao = combinado[combinado["_merge"] == "left_only"]
    so_pib = combinado[combinado["_merge"] == "right_only"]
    print(f"  municípios só em população (sem PIB {ANO_PIB_MAIS_RECENTE}): {len(so_populacao)}")
    if len(so_populacao):
        print(f"    {so_populacao['cd_mun_ibge'].tolist()[:20]}")
    print(f"  municípios só em PIB (sem população Censo 2022): {len(so_pib)}")
    if len(so_pib):
        print(f"    {so_pib['cd_mun_ibge'].tolist()[:20]}")

    combinado = combinado.drop(columns="_merge").sort_values("cd_mun_ibge").reset_index(drop=True)

    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    destino = config.DATA_PROCESSED / "ibge_municipio.parquet"
    combinado.to_parquet(destino, index=False)
    print(f"\nescrito: {destino} ({len(combinado)} linhas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
