"""Orquestração: lê os JSONs EA20 já em `data/raw/` e gera os Parquet de saída.

Não baixa nada (use `scripts/coletar_presidente.py` antes). Lê o config de
municípios para montar a lista de abrangências a processar e para preencher
`cd_mun_ibge`/`nm_mun` (ausentes no próprio EA20) e `eh_exterior`.

Gera em `data/processed/`:
  - `presidente_t1_municipio.parquet` / `presidente_t1_municipio_totais.parquet`
    (todos os municípios, Brasil + exterior)
  - `presidente_t1_uf.parquet` / `presidente_t1_uf_totais.parquet` (27 UFs + zz,
    arquivo oficial de cada UF — não é soma dos municípios)
  - `presidente_t1_br.parquet` / `presidente_t1_br_totais.parquet` (arquivo
    oficial do Brasil)

Uso:
    python scripts/processar_presidente.py --eleicao 6257
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eleicao import config  # noqa: E402
from eleicao.parse_ea20 import parse_ea20  # noqa: E402


def _carregar_config_municipios(eleicao: int) -> dict:
    caminho_cfg = config.caminho_local(config.caminho_config_municipios(eleicao))
    if not caminho_cfg.exists():
        raise FileNotFoundError(
            f"config de municípios não encontrado em {caminho_cfg}. "
            "Rode scripts/coletar_presidente.py antes."
        )
    return json.loads(caminho_cfg.read_text(encoding="utf-8"))


def _ler_json(caminho_local: Path) -> bytes:
    if not caminho_local.exists():
        raise FileNotFoundError(f"arquivo esperado não foi baixado: {caminho_local}")
    return caminho_local.read_bytes()


def processar_municipios(
    eleicao: int, config_municipios: dict
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Processa todos os municípios (Brasil + exterior) do config.

    Retorna `(df_candidatos, df_totais)` empilhados, com a coluna booleana
    `eh_exterior` adicionada em `df_totais`.
    """
    lista_candidatos: list[pd.DataFrame] = []
    lista_totais: list[pd.DataFrame] = []
    faltando: list[str] = []

    total_municipios = sum(len(a["mu"]) for a in config_municipios["abr"])
    with tqdm(total=total_municipios, desc="parseando municípios", unit="mun") as pbar:
        for abrangencia in config_municipios["abr"]:
            uf = abrangencia["cd"]
            eh_exterior = uf == config.UF_EXTERIOR
            for municipio in abrangencia["mu"]:
                cd_mun = municipio["cd"]
                cd_mun_ibge = municipio["cdi"] or None
                nm_mun = municipio["nm"]
                caminho = config.caminho_local(
                    config.caminho_resultado(eleicao, config.CARGO_PRESIDENTE, uf, cd_mun)
                )
                if not caminho.exists():
                    faltando.append(f"{uf}{cd_mun}")
                    pbar.update(1)
                    continue

                conteudo = _ler_json(caminho)
                dfc, dft = parse_ea20(conteudo, uf=uf, cd_mun_ibge=cd_mun_ibge, nm_mun=nm_mun)
                dft["eh_exterior"] = eh_exterior
                lista_candidatos.append(dfc)
                lista_totais.append(dft)
                pbar.update(1)

    if faltando:
        print(
            f"AVISO: {len(faltando)} município(s) do config sem arquivo baixado/parseado: "
            f"{faltando[:20]}{'...' if len(faltando) > 20 else ''}",
            file=sys.stderr,
        )

    df_candidatos = pd.concat(lista_candidatos, ignore_index=True)
    df_totais = pd.concat(lista_totais, ignore_index=True)
    return df_candidatos, df_totais


def processar_ufs(eleicao: int, config_municipios: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Processa os arquivos oficiais de cada UF (27 + zz) — não é soma dos municípios."""
    lista_candidatos: list[pd.DataFrame] = []
    lista_totais: list[pd.DataFrame] = []

    for abrangencia in config_municipios["abr"]:
        uf = abrangencia["cd"]
        caminho = config.caminho_local(
            config.caminho_resultado(eleicao, config.CARGO_PRESIDENTE, uf)
        )
        if not caminho.exists():
            print(f"AVISO: arquivo de UF ausente (não processado): {caminho}", file=sys.stderr)
            continue
        conteudo = _ler_json(caminho)
        dfc, dft = parse_ea20(conteudo, uf=uf)
        lista_candidatos.append(dfc)
        lista_totais.append(dft)

    df_candidatos = pd.concat(lista_candidatos, ignore_index=True)
    df_totais = pd.concat(lista_totais, ignore_index=True)
    return df_candidatos, df_totais


def processar_br(eleicao: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    caminho = config.caminho_local(config.caminho_resultado(eleicao, config.CARGO_PRESIDENTE, "br"))
    conteudo = _ler_json(caminho)
    return parse_ea20(conteudo, uf="br")


def main(eleicao: int) -> int:
    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    config_municipios = _carregar_config_municipios(eleicao)

    print("processando municípios...")
    mun_candidatos, mun_totais = processar_municipios(eleicao, config_municipios)
    mun_candidatos.to_parquet(
        config.DATA_PROCESSED / "presidente_t1_municipio.parquet", index=False
    )
    mun_totais.to_parquet(
        config.DATA_PROCESSED / "presidente_t1_municipio_totais.parquet", index=False
    )
    print(f"  {len(mun_totais)} municípios, {len(mun_candidatos)} linhas de candidato")

    print("processando UFs (arquivos oficiais, não soma dos municípios)...")
    uf_candidatos, uf_totais = processar_ufs(eleicao, config_municipios)
    uf_candidatos.to_parquet(config.DATA_PROCESSED / "presidente_t1_uf.parquet", index=False)
    uf_totais.to_parquet(config.DATA_PROCESSED / "presidente_t1_uf_totais.parquet", index=False)
    print(f"  {len(uf_totais)} UFs (incl. zz), {len(uf_candidatos)} linhas de candidato")

    print("processando BR (arquivo oficial)...")
    br_candidatos, br_totais = processar_br(eleicao)
    br_candidatos.to_parquet(config.DATA_PROCESSED / "presidente_t1_br.parquet", index=False)
    br_totais.to_parquet(config.DATA_PROCESSED / "presidente_t1_br_totais.parquet", index=False)
    print(f"  {len(br_candidatos)} linhas de candidato (BR)")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--eleicao", type=int, default=config.ELEICAO_FEDERAL_T1, help="código da eleição (TSE)"
    )
    args = parser.parse_args()
    sys.exit(main(args.eleicao))
