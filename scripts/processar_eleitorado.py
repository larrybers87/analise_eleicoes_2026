"""Processa o perfil do eleitorado 2026 (Dados Abertos TSE) por município.

Lê `perfil_eleitorado_2026_BRASIL.csv` (dentro do ZIP já baixado em
`data/raw/dadosabertos/`, ~2,2GB/~9M linhas) em pedaços (`chunksize`), para
não estourar memória, e gera `data/processed/eleitorado_perfil_2026_municipio.parquet`:
1 linha por município, `total` de eleitores + percentuais por sexo, faixa
etária e grau de instrução. Ver docs/DADOS.md → "2. Eleitorado 2026".

Uso:
    python scripts/processar_eleitorado.py
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eleicao import config  # noqa: E402
from eleicao.parse_eleitorado import (  # noqa: E402
    COLUNAS_USADAS,
    agregar_chunk,
    consolidar,
    pivotar_wide,
)

CAMINHO_ZIP = (
    config.DATA_RAW
    / "dadosabertos"
    / "cdn.tse.jus.br"
    / "estatistica"
    / "sead"
    / "odsele"
    / "perfil_eleitorado"
    / "perfil_eleitorado_2026.zip"
)
MEMBRO = "perfil_eleitorado_2026_BRASIL.csv"
TAMANHO_CHUNK = 1_000_000


def main() -> int:
    if not CAMINHO_ZIP.exists():
        print(f"ERRO: ZIP não encontrado em {CAMINHO_ZIP}", file=sys.stderr)
        return 1

    with zipfile.ZipFile(CAMINHO_ZIP) as z:
        info = z.getinfo(MEMBRO)
        tamanho_total = info.file_size
        print(f"lendo {MEMBRO} ({tamanho_total / 1e9:.2f} GB descomprimido) em pedaços...")

        parciais: dict[str, list[pd.DataFrame]] = {"total": [], "sexo": [], "faixa": [], "grau": []}
        categorias_vistas: dict[str, set[str]] = {"sexo": set(), "faixa": set(), "grau": set()}

        with z.open(MEMBRO) as f, tqdm(unit="linhas", unit_scale=True) as pbar:
            leitor = pd.read_csv(
                f,
                sep=";",
                encoding="latin-1",
                quotechar='"',
                usecols=COLUNAS_USADAS,
                dtype=str,
                chunksize=TAMANHO_CHUNK,
            )
            for chunk in leitor:
                resultado = agregar_chunk(chunk)
                for nome, df in resultado.items():
                    parciais[nome].append(df)
                categorias_vistas["sexo"].update(chunk["DS_GENERO"].unique())
                categorias_vistas["faixa"].update(chunk["DS_FAIXA_ETARIA"].unique())
                categorias_vistas["grau"].update(chunk["DS_GRAU_ESCOLARIDADE"].unique())
                pbar.update(len(chunk))

    print("\ncategorias encontradas:")
    print("  sexo:", sorted(categorias_vistas["sexo"]))
    print("  faixa etária:", sorted(categorias_vistas["faixa"]))
    print("  grau de instrução:", sorted(categorias_vistas["grau"]))

    print("\nconsolidando pedaços...")
    consolidado = consolidar(parciais)
    print(f"  {len(consolidado['total'])} municípios (uf+cd_mun_tse únicos)")

    print("pivotando para formato largo (1 linha por município)...")
    largo = pivotar_wide(consolidado)

    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    destino = config.DATA_PROCESSED / "eleitorado_perfil_2026_municipio.parquet"
    largo.to_parquet(destino, index=False)
    print(f"\nescrito: {destino} ({len(largo)} linhas, {len(largo.columns)} colunas)")
    print(f"  total nacional de eleitores: {largo['total'].sum()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
