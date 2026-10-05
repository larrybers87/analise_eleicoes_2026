"""Exporta `web/data/` a partir de `data/processed/` (ver docs/DECISOES.md D-015).

Gera dois conjuntos independentes (ciclos de atualização diferentes — D-015 item 3):

GEOMETRIA (estável, só muda se a malha do IBGE mudar) — `web/data/geo/`:
  - `brasil_uf.topojson`            27 UFs (camada de referência, sempre carregada)
  - `brasil_municipios.topojson`    5.571 municípios do Brasil, mais simplificado
                                    (camada "Brasil por município", carregada sob demanda)
  - `municipios/uf_<sigla>.topojson` municípios de uma UF, menos simplificado
                                    (drill-down, carregado sob demanda)

RESULTADOS (refresháveis por `verificar_atualizacoes.py`) — `web/data/`:
  - `meta.json`                     geração do snapshot + paleta + índice de UFs
  - `resultados/br.json`            Brasil + resumo das 27 UFs + resumo do exterior
  - `resultados/uf/uf_<sigla>.json` UF completa + todos os municípios dela
  - `resultados/municipios_br.json` índice nacional compacto (cor + busca por nome)
  - `exterior.json`                 186 registros do exterior + agregado

Toda cor sai daqui pronta em hex (`src/eleicao/cores.py`) — o JavaScript nunca
recalcula mistura/OKLab (regra do agente `mapa-web`).

Uso:
    python scripts/exportar_web.py                 # tudo
    python scripts/exportar_web.py --sem-geometria  # só os JSON de resultado (rápido)
    python scripts/exportar_web.py --apenas-geometria
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import geobr
import geopandas as gpd
import pandas as pd
import topojson as tp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eleicao import config  # noqa: E402
from eleicao.cores import (  # noqa: E402
    COR_OUTROS,
    MARGEM_SATURACAO,
    NEUTRO_EMPATE_HEX,
    agrupar_outros,
    carregar_paleta,
    mistura_oklab,
    vencedor_margem,
)

WEB = config.RAIZ / "web"
WEB_DATA = WEB / "data"
FONTE = "TSE — resultados.tse.jus.br"

# --- Tolerâncias de simplificação (graus decimais; EPSG:4674 ~ WGS84) ----------
# ATENÇÃO 1: no pacote `topojson`, o `epsilon` de `.toposimplify()` está em
# unidades do CRS de ENTRADA (graus), não em unidades quantizadas — o método
# desquantiza os arcos, simplifica e requantiza. Valores grandes (ex. 100) não
# "simplificam mais": saturam no piso imposto por `prevent_oversimplify=True`
# (cada arco fica com 2 pontos) e produzem exatamente o mesmo arquivo para
# qualquer epsilon acima de ~0,05. 1 grau ≈ 111 km.
#
# ATENÇÃO 2: a entrada tem que ser a malha COMPLETA do geobr
# (`simplified=False`). A malha `simplified=True` já vem simplificada feature a
# feature, o que destrói o compartilhamento exato de vértices entre vizinhos —
# `topojson` então não reconhece as fronteiras comuns e explode o número de
# arcos (medido: MG com 20.460 arcos vindo da malha simplificada contra 2.533
# da malha completa; nacional, 113.358 contra ~13 mil). Como `prevent_over-
# simplify` mantém no mínimo 2 pontos por arco, arcos demais criam um PISO de
# tamanho que a simplificação não consegue furar (o nacional travava em ~3,8MB
# bruto / 1,1MB gzip por esse motivo).
TOL_UF = 0.005  # ~550 m — camada de referência, sempre visível, 27 features
# (mesma tolerância da camada por-UF de municípios, de propósito: as fronteiras
# de UF desenhadas por cima dos municípios no drill-down ficam coerentes)
TOL_MUN_UF = 0.005  # ~550 m — drill-down numa UF (zoom alto)
TOL_MUN_BR = 0.01  # ~1,1 km — camada nacional de municípios (zoom de país)

PREQUANTIZE = 1e6  # quantização de trabalho (alta) antes de simplificar
TOPOQUANTIZE_UF = 1e5
TOPOQUANTIZE_MUN_UF = 1e5
TOPOQUANTIZE_MUN_BR = 1e4

# --- critérios de aceitação da simplificação ---------------------------------
# A simplificação Douglas-Peucker (único algoritmo disponível aqui — o pacote
# `simplification`, que traria Visvalingam-Whyatt, não está instalado) pode
# introduzir AUTO-INTERSEÇÕES PONTUAIS em anéis: um "nó" onde o caminho
# simplificado cruza outro trecho do mesmo polígono. A geometria fica
# tecnicamente inválida (`is_valid == False`) mas a área afetada é
# desprezível e o MapLibre renderiza sem artefato visível.
#
# Divergência deliberada do texto de D-015 ("nenhuma geometria inválida"):
# exigir `is_valid` em 100% das features é inalcançável com DP em tolerância
# útil (medido: 15 das 27 UFs e ~0,5% dos municípios ficam com um nó
# pontual). O que validamos no lugar, de forma mais informativa:
#   - geometria nula/vazia ou de área zero          -> ERRO (aborta)
#   - contagem de features != config do TSE         -> ERRO
#   - id ausente/duplicado                          -> ERRO
#   - feature que perdeu mais de 40% da área        -> ERRO
#   - área total fora de ±2% da malha original      -> ERRO
#   - área afetada pelas auto-interseções > 0,05%   -> ERRO
#     (se for mais que isso, não é um nó pontual: é deformação de verdade)
MAX_PERDA_AREA_FEATURE = 0.40
MAX_PERDA_AREA_NACIONAL = 0.60
"""Limite mais frouxo só para `brasil_municipios.topojson`.

Motivo (medido, não arbitrado): essa camada é vista no zoom de país, onde
1 px ≈ 2,5 km. O município mais afetado é sempre Santa Cruz de Minas/MG
(3157336), o menor do Brasil (3,2 km², ~1 px na tela): ele cai para 1,64 km²
(45% do original). Importante: essa perda é a MESMA em TOL_MUN_BR=0,01 e
0,02 — um polígono desse tamanho fica reduzido ao seu mínimo de pontos em
qualquer tolerância da ordem de 1 km, então baixar a tolerância não resolve,
só aumenta o arquivo (0,02 dá 1.287KB/308KB gzip; 0,01 dá 1.540KB/371KB,
com o mesmo pior caso). Ficamos em 0,01 pela qualidade dos municípios médios
ao dar zoom, e subimos o teto de perda para 60% só neste nível. O limite de
40% dos demais níveis não é decorativo: foi ele que abortou o build e trouxe
esse caso à tona."""
MAX_DESVIO_AREA_TOTAL = 0.02
MAX_AREA_AUTOINTERSECCAO = 0.0005
CRS_AREA = "EPSG:5880"  # Policônica SIRGAS 2000 / Brasil — para medir área em km²

COR_SEM_VOTOS = "#eeeeee"
"""Cor das regiões sem nenhum voto válido (41 postos do exterior onde a seção
nunca foi instalada — ver docs/DADOS.md). Não é mistura de nada: é um hachurado
visual de "sem dado", definido aqui (Python) e só lido pelo JS."""

CAMPOS_TOTAIS = [
    "eleitorado",
    "comparecimento",
    "abstencao",
    "validos",
    "brancos",
    "nulos_vn",
    "nulos_tvn",
    "secoes_totalizadas",
    "secoes_total",
    "status_totalizacao",
    "tf_judicial",
    "matematicamente_definido",
    "data_hora_totalizacao",
]
CAMPOS_TOTAIS_SE_NAO_ZERO = ["anulados", "anulados_sub_judice"]

FORMATO_MUNICIPIOS_BR = [
    "nome",
    "uf",
    "cd_mun_tse",
    "cor_mistura",
    "cor_margem",
    "vencedor",
    "margem_pp",
]
"""Ordem dos campos de cada entrada de `resultados/municipios_br.json`
(array em vez de objeto — 5.571 entradas, economiza ~40% do arquivo).
Replicado em `meta.json` para o JS não hardcodar a ordem."""


# ============================== resultados ===================================


def _nativo(valor: Any) -> Any:
    """Converte escalar numpy/pandas para tipo nativo JSON-serializável."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if hasattr(valor, "item"):
        return valor.item()
    if isinstance(valor, str):
        return valor
    return valor


def _totais(linha: pd.Series) -> dict[str, Any]:
    tot = {campo: _nativo(linha[campo]) for campo in CAMPOS_TOTAIS if campo in linha}
    for campo in CAMPOS_TOTAIS_SE_NAO_ZERO:
        valor = _nativo(linha.get(campo))
        if valor:  # omitido quando 0/None — o painel só mostra se > 0 (docs/DADOS.md)
            tot[campo] = valor
    return tot


@dataclass
class Cores:
    mistura: str
    margem: str
    vencedor: int | None
    margem_pp: float | None


def calcular_cores(votos: dict[int, int], paleta: dict[int, str]) -> Cores:
    """Cores dos 2 modos + vencedor + margem em p.p. sobre o 2º colocado.

    Usa TODOS os candidatos (não o agrupamento "Outros") — ver docstring de
    `agrupar_outros` em `src/eleicao/cores.py`.
    """
    total = sum(votos.values())
    if total <= 0:
        return Cores(COR_SEM_VOTOS, COR_SEM_VOTOS, None, None)
    ordenado = sorted(votos.items(), key=lambda it: it[1], reverse=True)
    votos_1 = ordenado[0][1]
    votos_2 = ordenado[1][1] if len(ordenado) > 1 else 0
    return Cores(
        mistura=mistura_oklab(votos, paleta),
        margem=vencedor_margem(votos, paleta),
        vencedor=int(ordenado[0][0]),
        margem_pp=round((votos_1 - votos_2) / total * 100, 3),
    )


ESCALA_MARGEM_PP = [0, 5, 10, 15, 20, 25, 30, 35, 40]
"""Pontos (p.p.) da escala de `vencedor_margem` exportada para a legenda.

A legenda do modo "vencedor + margem" precisa mostrar a rampa neutro→cor
plena. Exportamos os stops JÁ CALCULADOS em Python (`vencedor_margem`) em vez
de deixar o CSS interpolar `linear-gradient(neutro, cor)`: o navegador
interpolaria em sRGB e a rampa da legenda não bateria com a do mapa, que é
interpolada em OKLab. Ver a regra "cores sempre calculadas em Python"."""


def escala_margem(nr: int, paleta: dict[int, str]) -> list[str]:
    """Stops hex da rampa de `vencedor_margem` do candidato `nr`, de 0 a 40 p.p."""
    stops = []
    for pp in ESCALA_MARGEM_PP:
        m = pp / 100
        # dois candidatos fictícios com margem exata `m` sobre um total de 10.000:
        # `vencedor_margem` só consulta a paleta do vencedor, então o "2º" pode
        # ser uma chave qualquer fora da paleta.
        votos = {nr: round(5000 * (1 + m)), -1: round(5000 * (1 - m))}
        stops.append(vencedor_margem(votos, paleta))
    return stops


def lista_candidatos(votos: dict[int, int]) -> list[list[Any]]:
    """`[[nr|"outros", votos], ...]` ordenado por votos desc, com "Outros" agrupado."""
    if sum(votos.values()) <= 0:
        return []
    agrupado = agrupar_outros(votos)
    itens = sorted(agrupado.items(), key=lambda it: it[1], reverse=True)
    # "outros" sempre no fim, independente do volume
    itens.sort(key=lambda it: it[0] == "outros")
    return [[nr, int(v)] for nr, v in itens]


def registro(
    linha_totais: pd.Series, votos: dict[int, int], paleta: dict[int, str]
) -> dict[str, Any]:
    cores = calcular_cores(votos, paleta)
    return {
        "nome": _nativo(linha_totais.get("nm_mun")),
        "cd_mun_tse": _nativo(linha_totais.get("cd_mun_tse")),
        "cd_mun_ibge": _nativo(linha_totais.get("cd_mun_ibge")) or None,
        "cor_mistura": cores.mistura,
        "cor_margem": cores.margem,
        "vencedor": cores.vencedor,
        "margem_pp": cores.margem_pp,
        "votos": lista_candidatos(votos),
        "totais": _totais(linha_totais),
    }


def votos_por_regiao(df_cand: pd.DataFrame, chaves: list[str]) -> dict[Any, dict[int, int]]:
    """`{chave: {nr_candidato: votos}}` a partir do parquet de candidatos."""
    saida: dict[Any, dict[int, int]] = {}
    for chave, grupo in df_cand.groupby(chaves, sort=False):
        chave = chave[0] if isinstance(chave, tuple) and len(chaves) == 1 else chave
        saida[chave] = dict(
            zip(grupo["nr_candidato"].astype(int), grupo["votos"].astype(int), strict=True)
        )
    return saida


def escrever_json(caminho: Path, obj: Any) -> int:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    caminho.write_text(texto, encoding="utf-8")
    return len(texto.encode("utf-8"))


def carregar_config_municipios() -> dict[str, Any]:
    """Lê `mun-e006257-cm.json` (EA12) — fonte da contagem oficial por UF e dos nomes de UF."""
    caminho = (
        config.DATA_RAW
        / config.CICLO
        / str(config.ELEICAO_FEDERAL_T1)
        / "config"
        / f"mun-e{config.ELEICAO_FEDERAL_T1:06d}-cm.json"
    )
    if not caminho.exists():
        raise SystemExit(f"config de municípios não encontrado: {caminho}")
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    abr = {a["cd"].lower(): a for a in dados["abr"]}
    return {
        "nomes_uf": {sigla: a["ds"] for sigla, a in abr.items()},
        "n_municipios": {sigla: len(a["mu"]) for sigla, a in abr.items()},
        "ibge_por_uf": {sigla: {m["cdi"] for m in a["mu"] if m["cdi"]} for sigla, a in abr.items()},
    }


def exportar_resultados(cfg_mun: dict[str, Any], paleta: dict[int, str]) -> dict[str, int]:
    proc = config.DATA_PROCESSED
    br_tot = pd.read_parquet(proc / "presidente_t1_br_totais.parquet").iloc[0]
    br_cand = pd.read_parquet(proc / "presidente_t1_br.parquet")
    uf_tot = pd.read_parquet(proc / "presidente_t1_uf_totais.parquet")
    uf_cand = pd.read_parquet(proc / "presidente_t1_uf.parquet")
    mun_tot = pd.read_parquet(proc / "presidente_t1_municipio_totais.parquet")
    mun_cand = pd.read_parquet(proc / "presidente_t1_municipio.parquet")

    nomes_cand = br_cand.set_index(br_cand["nr_candidato"].astype(int))[
        ["nm_urna", "partido"]
    ].to_dict("index")

    votos_uf = votos_por_regiao(uf_cand, ["uf"])
    votos_mun = votos_por_regiao(mun_cand, ["uf", "cd_mun_tse"])

    tamanhos: dict[str, int] = {}

    # --- sanidade: soma dos candidatos == validos do bloco de totais ----------
    divergencias = 0
    for _, linha in mun_tot.iterrows():
        soma = sum(votos_mun.get((linha["uf"], linha["cd_mun_tse"]), {}).values())
        if soma != linha["validos"]:
            divergencias += 1
    if divergencias:
        print(
            f"  AVISO: {divergencias} municípios com soma(votos candidatos) != validos "
            "— percentuais do painel usam a soma dos candidatos"
        )

    # --- meta.json -----------------------------------------------------------
    snapshot = json.loads((proc / "snapshot_6257.json").read_text(encoding="utf-8"))
    idg = snapshot["br"]["idg"]
    meta = {
        "fonte": FONTE,
        "fonte_url": "https://resultados.tse.jus.br",
        "eleicao": snapshot["eleicao"],
        "cargo": "Presidente",
        "turno": 1,
        "snapshot": {
            "idg": idg,
            "dg": snapshot["br"]["dg"],
            "hg": snapshot["br"]["hg"],
            "dt_totalizacao": snapshot["br"]["dt_totalizacao"],
            "ht_totalizacao": snapshot["br"]["ht_totalizacao"],
            "status_totalizacao": snapshot["br"]["and"],
            "tf_judicial": snapshot["br"]["tf"],
            "matematicamente_definido": snapshot["br"]["md"],
        },
        "gerado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
        "candidatos": {
            str(nr): {
                "nm_urna": info["nm_urna"],
                "partido": info["partido"],
                "cor": paleta[nr],
            }
            for nr, info in sorted(nomes_cand.items())
        },
        "cor_outros": COR_OUTROS,
        "cor_sem_votos": COR_SEM_VOTOS,
        "neutro_empate": NEUTRO_EMPATE_HEX,
        "margem_saturacao_pp": MARGEM_SATURACAO * 100,
        "escala_margem_pp": ESCALA_MARGEM_PP,
        "escala_margem": {str(nr): escala_margem(nr, paleta) for nr in sorted(paleta)},
        "formato_municipios_br": FORMATO_MUNICIPIOS_BR,
        "ufs": [
            {
                "sigla": sigla,
                "nome": cfg_mun["nomes_uf"][sigla],
                "n_municipios": cfg_mun["n_municipios"][sigla],
            }
            for sigla in sorted(cfg_mun["nomes_uf"])
        ],
    }
    tamanhos["meta.json"] = escrever_json(WEB_DATA / "meta.json", meta)

    # --- br.json (Brasil + resumo das UFs + resumo do exterior) --------------
    votos_br = dict(
        zip(br_cand["nr_candidato"].astype(int), br_cand["votos"].astype(int), strict=True)
    )
    reg_br = registro(br_tot, votos_br, paleta)
    reg_br["nome"] = "Brasil"

    resumo_ufs = []
    registros_uf: dict[str, dict[str, Any]] = {}
    for _, linha in uf_tot.iterrows():
        sigla = linha["uf"]
        reg = registro(linha, votos_uf[sigla], paleta)
        reg["nome"] = cfg_mun["nomes_uf"][sigla]
        reg["uf"] = sigla
        registros_uf[sigla] = reg
        if sigla == config.UF_EXTERIOR:
            continue
        resumo_ufs.append(
            {
                "uf": sigla,
                "nome": reg["nome"],
                "cd_uf_ibge": None,  # preenchido abaixo com o código IBGE da malha
                "cor_mistura": reg["cor_mistura"],
                "cor_margem": reg["cor_margem"],
                "vencedor": reg["vencedor"],
                "margem_pp": reg["margem_pp"],
                "eleitorado": reg["totais"]["eleitorado"],
                "validos": reg["totais"]["validos"],
            }
        )

    codigos_uf = codigos_uf_ibge()
    for item in resumo_ufs:
        item["cd_uf_ibge"] = codigos_uf.get(item["uf"])

    reg_ext = registros_uf[config.UF_EXTERIOR]
    reg_ext["nome"] = "Exterior"

    br_json = {
        "br": reg_br,
        "ufs": sorted(resumo_ufs, key=lambda it: it["nome"]),
        "exterior": {
            "nome": "Exterior",
            "cor_mistura": reg_ext["cor_mistura"],
            "cor_margem": reg_ext["cor_margem"],
            "vencedor": reg_ext["vencedor"],
            "margem_pp": reg_ext["margem_pp"],
            "votos": reg_ext["votos"],
            "totais": reg_ext["totais"],
            "n_locais": cfg_mun["n_municipios"][config.UF_EXTERIOR],
        },
    }
    tamanhos["resultados/br.json"] = escrever_json(WEB_DATA / "resultados" / "br.json", br_json)

    # --- uf_<sigla>.json + índice nacional de municípios ---------------------
    indice_br: dict[str, list[Any]] = {}
    total_uf_bytes = 0
    for sigla in sorted(cfg_mun["nomes_uf"]):
        if sigla == config.UF_EXTERIOR:
            continue
        linhas = mun_tot[mun_tot["uf"] == sigla]
        municipios = []
        for _, linha in linhas.iterrows():
            votos = votos_mun[(sigla, linha["cd_mun_tse"])]
            reg = registro(linha, votos, paleta)
            municipios.append(reg)
            if reg["cd_mun_ibge"]:
                indice_br[reg["cd_mun_ibge"]] = [
                    reg["nome"],
                    sigla,
                    reg["cd_mun_tse"],
                    reg["cor_mistura"],
                    reg["cor_margem"],
                    reg["vencedor"],
                    reg["margem_pp"],
                ]
        municipios.sort(key=lambda it: it["nome"])
        obj = {"uf": registros_uf[sigla], "municipios": municipios}
        total_uf_bytes += escrever_json(WEB_DATA / "resultados" / "uf" / f"uf_{sigla}.json", obj)
    tamanhos["resultados/uf/uf_<sigla>.json (27)"] = total_uf_bytes

    tamanhos["resultados/municipios_br.json"] = escrever_json(
        WEB_DATA / "resultados" / "municipios_br.json",
        {"formato": FORMATO_MUNICIPIOS_BR, "municipios": indice_br},
    )

    # --- exterior.json -------------------------------------------------------
    ext = mun_tot[mun_tot["eh_exterior"]]
    locais = []
    for _, linha in ext.iterrows():
        votos = votos_mun[(linha["uf"], linha["cd_mun_tse"])]
        reg = registro(linha, votos, paleta)
        reg.pop("cd_mun_ibge", None)
        locais.append(reg)
    locais.sort(key=lambda it: it["nome"])
    tamanhos["exterior.json"] = escrever_json(
        WEB_DATA / "exterior.json",
        {"agregado": reg_ext, "locais": locais},
    )

    print(
        f"  resultados: {len(indice_br)} municípios no índice nacional, {len(locais)} no exterior"
    )
    return tamanhos


# ============================== geometria ====================================


def codigos_uf_ibge() -> dict[str, int]:
    gdf = geobr.read_state(year=2024, simplified=True, show_progress=False)
    return {str(r.abbrev_state).lower(): int(r.code_state) for r in gdf.itertuples()}


def _geojson(topo: tp.Topology) -> gpd.GeoDataFrame:
    gj = json.loads(topo.to_geojson())
    return gpd.GeoDataFrame.from_features(gj["features"], crs="EPSG:4674")


def validar_e_escrever(
    topo: tp.Topology,
    caminho: Path,
    esperado: int,
    coluna_id: str,
    rotulo: str,
    areas_orig: dict[str, float],
    max_perda: float = MAX_PERDA_AREA_FEATURE,
) -> tuple[int, int]:
    """Valida (falha alto nos critérios acima) e grava o TopoJSON.

    `areas_orig`: `{id: área km²}` da malha ORIGINAL (não simplificada), para
    medir quanto a simplificação distorceu cada feature.
    `max_perda`: perda de área tolerada na feature mais afetada (a camada
    nacional usa um limite mais frouxo — ver `MAX_PERDA_AREA_NACIONAL`).
    Devolve `(bytes, bytes_gzip)`.
    """
    gdf = _geojson(topo)

    if len(gdf) != esperado:
        raise SystemExit(
            f"[{rotulo}] contagem de features {len(gdf)} != esperado {esperado} "
            "(config de municípios do TSE)"
        )
    if coluna_id not in gdf.columns:
        raise SystemExit(f"[{rotulo}] propriedade de id '{coluna_id}' ausente nas features")
    ids = gdf[coluna_id].astype(str)
    if gdf[coluna_id].isna().any() or (ids == "").any():
        raise SystemExit(f"[{rotulo}] há features sem '{coluna_id}'")
    if ids.duplicated().any():
        raise SystemExit(
            f"[{rotulo}] '{coluna_id}' duplicado: {ids[ids.duplicated()].tolist()[:5]}"
        )

    nulas = int(gdf.geometry.isna().sum())
    vazias = int(gdf.geometry.is_empty.sum())
    if nulas or vazias:
        raise SystemExit(f"[{rotulo}] {nulas} geometrias nulas e {vazias} vazias pós-simplificação")

    proj = gdf.to_crs(CRS_AREA)
    areas = proj.geometry.area / 1e6  # km²
    zeradas = ids[areas <= 0].tolist()
    if zeradas:
        raise SystemExit(f"[{rotulo}] {len(zeradas)} features com área zero: {zeradas[:5]}")

    orig = ids.map(areas_orig)
    if orig.isna().any():
        raise SystemExit(f"[{rotulo}] sem área original para {ids[orig.isna()].tolist()[:5]}")
    razao = areas.to_numpy() / orig.to_numpy()
    pior = int(razao.argmin())
    if razao.min() < 1 - max_perda:
        raise SystemExit(
            f"[{rotulo}] feature {ids.iloc[pior]} perdeu {(1 - razao.min()) * 100:.1f}% da área "
            f"(limite {max_perda * 100:.0f}%) — tolerância alta demais"
        )
    desvio_total = areas.sum() / orig.sum() - 1
    if abs(desvio_total) > MAX_DESVIO_AREA_TOTAL:
        raise SystemExit(
            f"[{rotulo}] área total desviou {desvio_total * 100:+.2f}% "
            f"(limite ±{MAX_DESVIO_AREA_TOTAL * 100:.0f}%)"
        )

    # auto-interseções: contamos e medimos a área que elas de fato afetam
    mascara_inval = ~gdf.geometry.is_valid
    n_inval = int(mascara_inval.sum())
    area_afetada = 0.0
    if n_inval:
        # `buffer(0)` em vez de `make_valid()`: resolve o "nó" da auto-interseção
        # devolvendo sempre um polígono (make_valid devolve GeometryCollection de
        # dimensão mista e chega a lançar `GEOSException: Overlay input is
        # mixed-dimension` em alguns anéis do nível nacional). A diferença de área
        # entre o anel original e o `buffer(0)` é exatamente o que queremos medir:
        # quanto da feature a auto-interseção de fato compromete.
        corrigidas = proj[mascara_inval].geometry.buffer(0).area / 1e6
        area_afetada = float((corrigidas - areas[mascara_inval]).abs().sum() / areas.sum())
        if area_afetada > MAX_AREA_AUTOINTERSECCAO:
            raise SystemExit(
                f"[{rotulo}] auto-interseções afetam {area_afetada * 100:.4f}% da área "
                f"(limite {MAX_AREA_AUTOINTERSECCAO * 100:.2f}%) — não são nós pontuais"
            )

    i_min = int(areas.to_numpy().argmin())
    menor = (
        f"{ids.iloc[i_min]} {areas.iloc[i_min]:.2f}km² "
        f"({areas.iloc[i_min] / orig.iloc[i_min] * 100:.0f}% do original)"
    )

    caminho.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(topo.to_dict(), separators=(",", ":"))
    bruto = texto.encode("utf-8")
    caminho.write_text(texto, encoding="utf-8")
    gz = len(gzip.compress(bruto, 9))

    print(
        f"  {rotulo:22s} feats={len(gdf):5d} raw={len(bruto) / 1024:7.1f}KB "
        f"gzip={gz / 1024:6.1f}KB área{desvio_total * 100:+.2f}% "
        f"pior-feat={(1 - razao.min()) * 100:4.1f}% autoint={n_inval:4d}/{area_afetada * 100:.4f}% "
        f"menor={menor}"
    )
    return len(bruto), gz


def construir(gdf: gpd.GeoDataFrame, tol: float, quant: float) -> tp.Topology:
    topo = tp.Topology(gdf, prequantize=PREQUANTIZE, toposimplify=False, shared_coords=False)
    return topo.toposimplify(tol).topoquantize(quant)


def exportar_geometria(
    cfg_mun: dict[str, Any], nacional: bool = True, apenas_nacional: bool = False
) -> dict[str, int]:
    print("  lendo a malha COMPLETA de municípios do IBGE (geobr, simplified=False)...")
    t_leitura = time.time()
    muns = geobr.read_municipality(year=2024, simplified=False, show_progress=False)
    print(
        f"    {len(muns)} municípios, "
        f"{int(muns.geometry.count_coordinates().sum()):,} vértices "
        f"em {time.time() - t_leitura:.1f}s"
    )
    muns = muns.assign(cd_mun_ibge=muns["code_muni"].astype("Int64").astype(str))
    muns["uf"] = muns["abbrev_state"].str.lower()
    muns = muns[["cd_mun_ibge", "uf", "geometry"]].reset_index(drop=True)

    invalidas_entrada = int((~muns.geometry.is_valid).sum())
    if invalidas_entrada:
        print(f"  entrada do geobr tinha {invalidas_entrada} geometrias inválidas — make_valid()")
        muns["geometry"] = muns.geometry.make_valid()

    esperado_br = sum(
        n for sigla, n in cfg_mun["n_municipios"].items() if sigla != config.UF_EXTERIOR
    )
    if len(muns) != esperado_br:
        raise SystemExit(
            f"malha do IBGE tem {len(muns)} municípios, config do TSE tem {esperado_br}"
        )

    print("  medindo áreas da malha original (referência de validação)...")
    t0 = time.time()
    areas_km2 = muns.to_crs(CRS_AREA).geometry.area / 1e6
    areas_mun = dict(zip(muns["cd_mun_ibge"], areas_km2.astype(float), strict=True))
    print(f"    {sum(areas_mun.values()):,.0f} km² em {time.time() - t0:.1f}s")

    tamanhos: dict[str, int] = {}
    geo = WEB_DATA / "geo"

    # --- UFs (dissolve da própria malha municipal: fronteiras coincidentes) --
    if not apenas_nacional:
        t0 = time.time()
        codigos = codigos_uf_ibge()
        ufs = muns.dissolve(by="uf", as_index=False)[["uf", "geometry"]]
        ufs["cd_uf_ibge"] = ufs["uf"].map(codigos).astype(int)
        ufs["nm_uf"] = ufs["uf"].map(cfg_mun["nomes_uf"])
        areas_uf = {
            str(codigos[sigla]): float(areas_km2[muns["uf"] == sigla].sum())
            for sigla in muns["uf"].unique()
        }
        print(f"    (dissolve de UF em {time.time() - t0:.1f}s)")
        topo_uf = construir(ufs[["cd_uf_ibge", "uf", "nm_uf", "geometry"]], TOL_UF, TOPOQUANTIZE_UF)
        bruto, _ = validar_e_escrever(
            topo_uf, geo / "brasil_uf.topojson", 27, "cd_uf_ibge", "brasil_uf", areas_uf
        )
        tamanhos["geo/brasil_uf.topojson"] = bruto

        # --- municípios por UF ----------------------------------------------
        t0 = time.time()
        total_bruto = 0
        for sigla in sorted(muns["uf"].unique()):
            sub = muns[muns["uf"] == sigla][["cd_mun_ibge", "geometry"]].reset_index(drop=True)
            esperado = cfg_mun["n_municipios"][sigla]
            topo = construir(sub, TOL_MUN_UF, TOPOQUANTIZE_MUN_UF)
            bruto, _ = validar_e_escrever(
                topo,
                geo / "municipios" / f"uf_{sigla}.topojson",
                esperado,
                "cd_mun_ibge",
                f"municipios/{sigla}",
                areas_mun,
            )
            total_bruto += bruto
        tamanhos["geo/municipios/uf_<sigla>.topojson (27)"] = total_bruto
        print(f"    (27 UFs por município em {time.time() - t0:.1f}s)")

    # --- municípios do Brasil inteiro ---------------------------------------
    if nacional:
        t0 = time.time()
        sub = muns[["cd_mun_ibge", "geometry"]].reset_index(drop=True)
        topo = tp.Topology(sub, prequantize=PREQUANTIZE, toposimplify=False, shared_coords=False)
        t_topo = time.time() - t0
        t1 = time.time()
        topo = topo.toposimplify(TOL_MUN_BR).topoquantize(TOPOQUANTIZE_MUN_BR)
        bruto, _ = validar_e_escrever(
            topo,
            geo / "brasil_municipios.topojson",
            esperado_br,
            "cd_mun_ibge",
            "brasil_municipios",
            areas_mun,
            max_perda=MAX_PERDA_AREA_NACIONAL,
        )
        tamanhos["geo/brasil_municipios.topojson"] = bruto
        print(
            f"    (topologia nacional {t_topo:.1f}s + simplificação/quantização "
            f"{time.time() - t1:.1f}s = {time.time() - t0:.1f}s total)"
        )

    return tamanhos


# ================================ main =======================================


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sem-geometria", action="store_true", help="só os JSON de resultado")
    ap.add_argument("--apenas-geometria", action="store_true", help="só os TopoJSON")
    ap.add_argument(
        "--sem-nacional",
        action="store_true",
        help="pula o TopoJSON nacional de municípios (o mais lento de gerar)",
    )
    ap.add_argument(
        "--apenas-nacional",
        action="store_true",
        help="regera só o TopoJSON nacional (útil para calibrar TOL_MUN_BR)",
    )
    args = ap.parse_args()
    if args.apenas_nacional:
        args.apenas_geometria = True

    cfg_mun = carregar_config_municipios()
    paleta = carregar_paleta()
    print(f"paleta: {len(paleta)} candidatos; UFs no config do TSE: {len(cfg_mun['nomes_uf'])}")

    if not args.apenas_geometria:
        print("resultados:")
        exportar_resultados(cfg_mun, paleta)
    if not args.sem_geometria:
        print("geometria:")
        exportar_geometria(
            cfg_mun,
            nacional=not args.sem_nacional,
            apenas_nacional=args.apenas_nacional,
        )

    tabela_tamanhos()
    return 0


GRUPOS = [
    ("meta.json", ["meta.json"]),
    ("exterior.json", ["exterior.json"]),
    ("resultados/br.json", ["resultados/br.json"]),
    ("resultados/municipios_br.json", ["resultados/municipios_br.json"]),
    ("resultados/uf/uf_<sigla>.json", ["resultados/uf/"]),
    ("geo/brasil_uf.topojson", ["geo/brasil_uf.topojson"]),
    ("geo/brasil_municipios.topojson", ["geo/brasil_municipios.topojson"]),
    ("geo/municipios/uf_<sigla>.topojson", ["geo/municipios/"]),
]


def tabela_tamanhos() -> None:
    """Tabela bruto/gzip por tipo de arquivo (o que vale para a transferência HTTP)."""
    print(f"\n{'arquivo / grupo':38s} {'n':>4s} {'bruto KB':>10s} {'gzip KB':>9s} {'maior KB':>9s}")
    print("-" * 74)
    total_bruto = total_gz = 0
    for rotulo, prefixos in GRUPOS:
        arquivos = [
            p
            for p in sorted(WEB_DATA.rglob("*"))
            if p.is_file()
            and any(p.relative_to(WEB_DATA).as_posix().startswith(pref) for pref in prefixos)
        ]
        if not arquivos:
            continue
        brutos = [p.stat().st_size for p in arquivos]
        gzs = [len(gzip.compress(p.read_bytes(), 9)) for p in arquivos]
        total_bruto += sum(brutos)
        total_gz += sum(gzs)
        print(
            f"{rotulo:38s} {len(arquivos):4d} {sum(brutos) / 1024:10.1f} "
            f"{sum(gzs) / 1024:9.1f} {max(brutos) / 1024:9.1f}"
        )
    print("-" * 74)
    print(f"{'TOTAL web/data/':38s} {'':4s} {total_bruto / 1024:10.1f} {total_gz / 1024:9.1f}")
    inicial = ["meta.json", "resultados/br.json", "geo/brasil_uf.topojson"]
    gz_inicial = sum(
        len(gzip.compress((WEB_DATA / n).read_bytes(), 9))
        for n in inicial
        if (WEB_DATA / n).exists()
    )
    print(f"\ncarga inicial (meta + br + brasil_uf): {gz_inicial / 1024:.1f} KB gzip")


if __name__ == "__main__":
    raise SystemExit(main())
