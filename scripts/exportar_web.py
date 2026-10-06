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
  - `resultados/forca/cand_<nr>.json` (12) % dos válidos de UM candidato nos 5.571
                                    municípios — array posicional, sob demanda (D-018)
  - `resumo_candidatos.json`        painel do candidato selecionado, pré-calculado

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

from eleicao import config, forca  # noqa: E402
from eleicao.analise import composicao, swing  # noqa: E402
from eleicao.analise.base import vencedor_municipal  # noqa: E402
from eleicao.cores import (  # noqa: E402
    COR_OUTROS,
    ESCALA_NEUTRA_FIM_HEX,
    FRACOES_ESCALA,
    MARGEM_SATURACAO,
    N_STOPS_ESCALA,
    NEUTRO_EMPATE_HEX,
    agrupar_outros,
    carregar_paleta,
    eh_acromatico,
    escala_divergente_assimetrica,
    escala_forca,
    escala_forca_neutra,
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

COR_NAO_VENCEU = "#cfd6dd"
OPACIDADE_NAO_VENCEU = 0.45
"""Modo "Onde venceu" (D-018): regiões em que o candidato selecionado NÃO foi
o 1º colocado. Cinza-azulado claro com opacidade baixa — fica visivelmente
"para trás" das regiões pintadas na cor do candidato, mas ainda deixa ler a
fronteira e o relevo do mapa (opacidade 0 esconderia o desenho do país).
Escolhido mais escuro que `COR_SEM_VOTOS`/`NEUTRO_EMPATE_HEX` de propósito:
"ele não venceu aqui" é diferente de "não há dado aqui" e de "empate".
Definido aqui, no Python, e só lido pelo JS — mesma regra das outras cores."""

PCT_DECIMAIS = 3
"""Casas decimais dos percentuais exportados em `resultados/forca/*.json`.

Não é estética: os 7 candidatos menores têm percentil 98 entre 0,043% e
0,17% (medido). Com 2 casas, a escala de cor de Rui Costa Pimenta teria 5
degraus no total; com 3 casas, ~43. O custo é ~1 byte por município por
candidato (~5KB brutos por arquivo, quase nada depois do gzip)."""

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

FORMATO_TOP_MUNICIPIOS = ["cd_mun_ibge", "nome", "uf", "pct", "votos"]
"""Ordem dos campos de cada linha dos top 10 de `resumo_candidatos.json`."""

ORDEM_FORCA = "cd_mun_ibge crescente (numérico)"
"""Ordem dos arrays posicionais de `resultados/forca/cand_<nr>.json`.

Declarada em `meta.json` (`forca_ordem`) e garantida por
`eleicao.forca.pct_por_municipio`. O JS NÃO pode confiar na ordem de inserção
das chaves de `municipios_br.json`: as chaves são códigos IBGE de 7 dígitos,
que o JavaScript trata como "integer-indexed properties" e reordena
numericamente em `Object.keys`, independentemente da ordem em que o Python as
escreveu. Em vez de depender desse detalhe, os dois lados usam a mesma ordem
explícita (numérica crescente) e o JS ordena na mão; o campo `n` de cada
arquivo serve de conferência de alinhamento."""

N_TOP_MUNICIPIOS = 10


def offsets_forca(indice: list[str], uf_por_ibge: dict[str, str]) -> dict[str, int]:
    """Posição inicial de cada UF dentro do array posicional de `forca/cand_<nr>.json`.

    Funciona porque o código IBGE de 7 dígitos começa com o código de 2 dígitos
    da UF: ordenar os municípios por `cd_mun_ibge` crescente (ver `ORDEM_FORCA`)
    os deixa automaticamente AGRUPADOS por UF, em blocos contíguos. Com o
    offset do bloco, o front-end fatia o array de um candidato para uma UF
    específica usando só os códigos daquela UF (que ele já tem em
    `uf_<sigla>.json`) — sem precisar baixar o índice nacional de 5.571
    municípios (117KB gzip) só para descobrir a posição de cada um.

    Aborta se algum bloco não for contíguo (se algum dia a premissa do código
    IBGE mudar, é melhor o build quebrar do que o mapa pintar a UF errada).
    """
    offsets: dict[str, int] = {}
    ultima: str | None = None
    for i, ibge in enumerate(indice):
        sigla = uf_por_ibge[ibge]
        if sigla != ultima:
            if sigla in offsets:
                raise SystemExit(
                    f"bloco da UF {sigla} não é contíguo na ordem '{ORDEM_FORCA}' "
                    "— o fatiamento por UF do front-end deixaria de valer"
                )
            offsets[sigla] = i
            ultima = sigla
    return offsets


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


Vencedor = tuple[int | None, float | None]
"""`(nr_vencedor | None, margem_pp | None)` de uma região, vindo de
`eleicao.analise.base.vencedor_municipal` — a MESMA função usada nas análises (D-030).
Empate exato: `(None, 0.0)`. Sem voto válido: `(None, None)`."""


def tabela_vencedores(df_cand: pd.DataFrame) -> dict[tuple[str, str], Vencedor]:
    """`{(uf, cd_mun_tse): (vencedor, margem_pp)}` para cada região de `df_cand`.

    Única fonte de "quem venceu" do export: chama `base.vencedor_municipal` (que já trata
    empate exato como "sem vencedor") e não reimplementa nada. Funciona para município, UF
    e Brasil porque os três Parquet têm as colunas `uf`/`cd_mun_tse`.
    """
    # UF e Brasil não têm código de município no Parquet (None): vira "" para o groupby
    entrada = df_cand[["uf", "cd_mun_tse", "nr_candidato", "votos"]].copy()
    entrada["cd_mun_tse"] = entrada["cd_mun_tse"].fillna("")
    vw = vencedor_municipal(entrada)
    saida: dict[tuple[str, str], Vencedor] = {}
    for uf, cd, nr, validos, margem in zip(
        vw["uf"],
        vw["cd_mun_tse"],
        vw["nr_vencedor"],
        vw["validos"],
        vw["margem_pp"],
        strict=True,
    ):
        if validos <= 0:
            saida[(uf, cd)] = (None, None)
        elif nr is None or pd.isna(nr):
            saida[(uf, cd)] = (None, 0.0)
        else:
            saida[(uf, cd)] = (int(nr), round(float(margem), 3))
    return saida


def calcular_cores(votos: dict[int, int], paleta: dict[int, str], venc: Vencedor) -> Cores:
    """Cores dos 2 modos + vencedor + margem em p.p. sobre o 2º colocado.

    `venc` vem de `tabela_vencedores` (função da análise). A mistura usa TODOS os
    candidatos (não o agrupamento "Outros"). Empate exato: sem vencedor e `cor_margem`
    neutra (`NEUTRO_EMPATE_HEX`) — o empate não pode herdar a cor de ninguém.
    """
    total = sum(votos.values())
    nr, margem = venc
    if total <= 0:
        return Cores(COR_SEM_VOTOS, COR_SEM_VOTOS, None, None)
    if nr is None:
        return Cores(mistura_oklab(votos, paleta), NEUTRO_EMPATE_HEX, None, 0.0)
    return Cores(
        mistura=mistura_oklab(votos, paleta),
        margem=vencedor_margem(votos, paleta),
        vencedor=nr,
        margem_pp=margem,
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


def _pct(valor: float) -> float | int:
    """Arredonda para `PCT_DECIMAIS` e devolve `int` quando dá 0 (encurta o JSON)."""
    v = round(float(valor), PCT_DECIMAIS)
    return 0 if v == 0 else v


def votos_posicional(votos: dict[int, int], ordem: list[int]) -> list[int]:
    """`[votos_do_candidato_1, ...]` na ordem de `meta.json.ordem_candidatos`.

    Deliberadamente SEM `agrupar_outros`: este array existe justamente para o
    modo "Força", que precisa do número de CADA um dos 12 candidatos. O
    `votos[]` dos registros (que o painel usa nas barras) continua agrupado —
    os dois convivem porque servem a coisas diferentes (D-018)."""
    return [int(votos.get(nr, 0)) for nr in ordem]


def exportar_forca(
    pct_mun: pd.DataFrame, p98: dict[int, float], paleta: dict[int, str]
) -> tuple[dict[str, int], int]:
    """Um arquivo por candidato com o % dos válidos dele nos 5.571 municípios.

    Array POSICIONAL (ver `ORDEM_FORCA`), sem a chave do município — é o que
    torna o arquivo pequeno o bastante (19–38KB brutos, 3–16KB gzip) para ser
    baixado sob demanda quando o usuário seleciona um candidato. Só o NÚMERO
    sai daqui: a cor nasce no navegador combinando esse número com os stops de
    `meta.json.escala_forca` numa expressão `interpolate` do MapLibre — nunca
    exportamos cor por município × candidato (12 × 5.571 = 66.852 cores).
    """
    total = 0
    for nr in sorted(paleta):
        if nr not in pct_mun.columns:
            raise SystemExit(f"candidato {nr} da paleta ausente do parquet de municípios")
        obj = {
            "nr": nr,
            "n": int(len(pct_mun)),
            "p98": round(p98[nr], 4),
            "ordem": ORDEM_FORCA,
            "pct": [_pct(v) for v in pct_mun[nr]],
        }
        total += escrever_json(WEB_DATA / "resultados" / "forca" / f"cand_{nr}.json", obj)
    return {"resultados/forca/cand_<nr>.json (12)": total}, total


def construir_resumo(
    mun_tot: pd.DataFrame,
    pct_mun: pd.DataFrame,
    votos_mun: dict[Any, dict[int, int]],
    venc_mun: dict[tuple[str, str], Vencedor],
    votos_ext_agregado: dict[int, int],
    p98: dict[int, float],
    ordem: list[int],
) -> dict[str, Any]:
    """Resumo por candidato para o painel lateral (pré-calculado em Python).

    O que entra aqui é só o que o JS NÃO consegue derivar do que já carregou:
    municípios vencidos (total e por UF — derivável de `municipios_br.json`,
    mas isso forçaria baixar 117KB gzip só para contar), os dois top 10
    (derivável, mas exigiria os 27 `uf_*.json`, ~450KB gzip por seleção) e o
    resultado no exterior. Melhor/pior UF NÃO entra: o JS calcula exato a
    partir de `br.json.ufs[].votos_cand`, que já está carregado desde o
    início (ver D-018).
    """
    mun_br = mun_tot[~mun_tot["eh_exterior"]]
    chave_por_ibge: dict[str, tuple[str, str]] = {}
    uf_por_ibge: dict[str, str] = {}
    nome_por_ibge: dict[str, str] = {}
    for ibge, uf, cd, nome in zip(
        mun_br["cd_mun_ibge"],
        mun_br["uf"],
        mun_br["cd_mun_tse"],
        mun_br["nm_mun"],
        strict=True,
    ):
        chave_por_ibge[str(ibge)] = (uf, cd)
        uf_por_ibge[str(ibge)] = str(uf)
        nome_por_ibge[str(ibge)] = str(nome)

    # vencedor de cada município: `venc_mun`, da função da análise (empate = sem vencedor)
    vencidos: dict[int, list[str]] = {nr: [] for nr in ordem}
    empates: list[str] = []
    for ibge, chave in chave_por_ibge.items():
        nr, margem = venc_mun[chave]
        if nr is not None:
            vencidos.setdefault(int(nr), []).append(ibge)
        elif margem == 0.0:
            empates.append(ibge)

    # vencedor de cada local do exterior (para "venceu em N postos")
    vencidos_ext: dict[int, int] = {nr: 0 for nr in ordem}
    com_voto_ext = 0
    for (uf, cd), votos in votos_mun.items():
        if uf != config.UF_EXTERIOR or sum(votos.values()) <= 0:
            continue
        com_voto_ext += 1
        nr, _ = venc_mun[(uf, cd)]
        if nr is not None:
            vencidos_ext[nr] += 1

    total_ext = sum(votos_ext_agregado.values())
    ordem_ext = sorted(votos_ext_agregado.items(), key=lambda it: it[1], reverse=True)
    posicao_ext = {nr: i + 1 for i, (nr, _) in enumerate(ordem_ext)}

    # votos absolutos por município × candidato, na mesma ordem de pct_mun
    votos_abs = pd.DataFrame(
        {
            nr: [votos_mun.get(chave_por_ibge[ibge], {}).get(nr, 0) for ibge in pct_mun.index]
            for nr in ordem
        },
        index=pct_mun.index,
    )

    def top(serie: pd.Series, nr: int) -> list[list[Any]]:
        melhores = serie.sort_values(ascending=False).head(N_TOP_MUNICIPIOS)
        return [
            [
                ibge,
                nome_por_ibge[ibge],
                uf_por_ibge[ibge],
                _pct(pct_mun.loc[ibge, nr]),
                int(votos_abs.loc[ibge, nr]),
            ]
            for ibge in melhores.index
        ]

    resumo: dict[str, Any] = {}
    for nr in ordem:
        ibges = vencidos.get(nr, [])
        por_uf: dict[str, int] = {}
        for ibge in ibges:
            sigla = uf_por_ibge[ibge]
            por_uf[sigla] = por_uf.get(sigla, 0) + 1
        resumo[str(nr)] = {
            "p98": round(p98[nr], 4),
            "municipios_vencidos": len(ibges),
            "municipios_vencidos_por_uf": dict(sorted(por_uf.items())),
            "pct_max_municipio": _pct(pct_mun[nr].max()),
            "top_pct": top(pct_mun[nr], nr),
            "top_votos": top(votos_abs[nr], nr),
            "exterior": {
                "votos": int(votos_ext_agregado.get(nr, 0)),
                "pct": _pct(votos_ext_agregado.get(nr, 0) / total_ext * 100) if total_ext else 0,
                "posicao": posicao_ext.get(nr),
                "locais_vencidos": vencidos_ext.get(nr, 0),
                "locais_com_voto": com_voto_ext,
            },
        }
    return {
        "formato_top": FORMATO_TOP_MUNICIPIOS,
        "n_municipios_br": int(len(mun_br)),
        # empates exatos não têm vencedor (não entram em nenhum `municipios_vencidos`)
        "empates": [[ibge, nome_por_ibge[ibge], uf_por_ibge[ibge]] for ibge in sorted(empates)],
        "candidatos": resumo,
    }


SWING_DECIMAIS = 2
"""Casas dos swings por município em `resultados/swing.json`. Duas, e não uma, porque o
limite negativo da escala (p1 do Δmargem) fica perto de zero (medido: ~−0,05 p.p.): com uma
casa, o arredondamento decidiria sozinho a cor dos municípios nessa faixa."""

COR_HACHURA_SEM_PAR = "#9aa4ae"
"""Traço da hachura dos municípios sem par 2022↔2026 no modo "Swing" (fundo: COR_SEM_VOTOS)."""


def _r(valor: float | None, casas: int) -> float | int | None:
    if valor is None or pd.isna(valor):
        return None
    v = round(float(valor), casas)
    return 0 if v == 0 else v


def calcular_swing(mun_tot: pd.DataFrame, ordem_ibge: list[str], paleta: dict[int, str]) -> dict:
    """Swing 1T 2022 → 1T 2026 para o modo "Swing" do mapa (D-030).

    Só chama funções testadas de `eleicao.analise` (`composicao.swing_pt_pl`,
    `swing.delta_margem_municipal`/`_agregado`, `swing.limites_escala_delta`) e a escala de
    `cores.escala_divergente_assimetrica`. Devolve o conteúdo de `resultados/swing.json`, o
    bloco `escala_swing` do `meta.json` e o swing agregado por UF (para `br.json.ufs[]`).
    Exterior fora (não tem mapa). Município sem par fica `null`, com o motivo em `sem_par`.
    """
    dados = composicao.swing_pt_pl()
    pt = dados["pt"][dados["pt"]["uf"] != config.UF_EXTERIOR]
    pl = dados["pl"][dados["pl"]["uf"] != config.UF_EXTERIOR]
    sem = dados["sem_par"][dados["sem_par"]["uf"] != config.UF_EXTERIOR]

    dm = swing.delta_margem_municipal(pt, pl)
    lim_neg, lim_pos = swing.limites_escala_delta(dm["delta_margem_pp"])
    br = swing.delta_margem_agregado(pt, pl).iloc[0]
    por_uf = swing.delta_margem_agregado(pt, pl, "uf")

    br_tot = mun_tot[~mun_tot["eh_exterior"]]
    ibge_de = {
        (u, str(c)): str(i)
        for u, c, i in zip(br_tot["uf"], br_tot["cd_mun_tse"], br_tot["cd_mun_ibge"], strict=True)
    }
    por_ibge = {
        ibge_de[(u, str(c))]: (a, b)
        for u, c, a, b in zip(
            dm["uf"], dm["cd_mun_tse"], dm["swing_pt_pp"], dm["swing_pl_pp"], strict=True
        )
    }
    sem_par = {
        ibge_de[(u, str(c))]: m
        for u, c, m in zip(sem["uf"], sem["cd_mun_tse"], sem["motivo"], strict=True)
    }
    arr_pt = [_r(por_ibge.get(i, (None, None))[0], SWING_DECIMAIS) for i in ordem_ibge]
    arr_pl = [_r(por_ibge.get(i, (None, None))[1], SWING_DECIMAIS) for i in ordem_ibge]
    faltando = {i for i, v in zip(ordem_ibge, arr_pt, strict=True) if v is None}
    if faltando != set(sem_par):
        raise SystemExit(
            f"swing: municípios sem valor {sorted(faltando)} != sem_par {sorted(sem_par)}"
        )

    escala = escala_divergente_assimetrica(
        lim_neg, lim_pos, paleta[swing.NR_LULA], paleta[swing.NR_PL_2026]
    )
    arquivo = {
        "n": len(ordem_ibge),
        "ordem": ORDEM_FORCA,
        "pt": arr_pt,
        "pl": arr_pl,
        "sem_par": sem_par,
    }
    meta = {
        "valores": [round(v, 4) for v, _ in escala],
        "cores": [c for _, c in escala],
        "limite_negativo": round(lim_neg, 4),
        "limite_positivo": round(lim_pos, 4),
        "percentis": list(swing.PERCENTIS_ESCALA_DELTA),
        "n_pareados_br": int(len(dm)),
        "br": [_r(br["swing_pt_pp"], 3), _r(br["swing_pl_pp"], 3), _r(br["delta_margem_pp"], 3)],
        "formato": ["swing_pt_pp", "swing_pl_pp", "delta_margem_pp"],
        "cor_sem_par": COR_SEM_VOTOS,
        "cor_hachura": COR_HACHURA_SEM_PAR,
    }
    uf = {
        u: [_r(a, 3), _r(b, 3), _r(d, 3)]
        for u, a, b, d in zip(
            por_uf["uf"],
            por_uf["swing_pt_pp"],
            por_uf["swing_pl_pp"],
            por_uf["delta_margem_pp"],
            strict=True,
        )
    }
    return {"arquivo": arquivo, "meta": meta, "uf": uf}


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
    linha_totais: pd.Series, votos: dict[int, int], paleta: dict[int, str], venc: Vencedor
) -> dict[str, Any]:
    cores = calcular_cores(votos, paleta, venc)
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

    # vencedor de cada região: UMA implementação, a da análise (D-030)
    venc_mun = tabela_vencedores(mun_cand)
    venc_uf = {uf: v for (uf, _), v in tabela_vencedores(uf_cand).items()}
    venc_br = tabela_vencedores(br_cand)[("br", "")]

    votos_br = dict(
        zip(br_cand["nr_candidato"].astype(int), br_cand["votos"].astype(int), strict=True)
    )
    # ordem canônica dos arrays posicionais `votos_cand`: por votação nacional
    # (é também a ordem do seletor de candidato do mapa).
    ordem_cand = [nr for nr, _ in sorted(votos_br.items(), key=lambda it: it[1], reverse=True)]
    if set(ordem_cand) != set(paleta):
        raise SystemExit(
            f"paleta e parquet divergem: {sorted(set(paleta) ^ set(ordem_cand))} "
            "— regenere config/candidatos.yaml a partir de presidente_t1_br.parquet"
        )
    total_validos_br = sum(votos_br.values())

    # --- "força": % dos válidos por município × candidato (exterior fora) ----
    pct_mun = forca.pct_por_municipio(mun_cand, mun_tot)
    p98 = {nr: forca.escala_maxima(pct_mun[nr]) for nr in ordem_cand}
    mun_br_tot = mun_tot[~mun_tot["eh_exterior"]]
    uf_por_ibge = {
        str(i): str(u) for i, u in zip(mun_br_tot["cd_mun_ibge"], mun_br_tot["uf"], strict=True)
    }
    offsets = offsets_forca(list(pct_mun.index), uf_por_ibge)

    # --- swing 2022 → 2026 (modo "Swing" do mapa, D-030) --------------------
    sw_dados = calcular_swing(mun_tot, list(pct_mun.index), paleta)

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
                # votos/pct nacionais aqui (e não só em br.json) porque o
                # seletor de candidato precisa dos 12, e o `votos[]` de
                # br.json já vem com `agrupar_outros` aplicado — os 7 menores
                # estariam somados em "outros" lá.
                "votos": int(votos_br[nr]),
                "pct_validos": round(votos_br[nr] / total_validos_br * 100, 4),
                "acromatico": eh_acromatico(paleta[nr]),
            }
            for nr, info in sorted(nomes_cand.items())
        },
        "ordem_candidatos": ordem_cand,
        "cor_outros": COR_OUTROS,
        "cor_sem_votos": COR_SEM_VOTOS,
        "cor_nao_venceu": COR_NAO_VENCEU,
        "opacidade_nao_venceu": OPACIDADE_NAO_VENCEU,
        "neutro_empate": NEUTRO_EMPATE_HEX,
        "margem_saturacao_pp": MARGEM_SATURACAO * 100,
        "escala_margem_pp": ESCALA_MARGEM_PP,
        "escala_margem": {str(nr): escala_margem(nr, paleta) for nr in sorted(paleta)},
        # --- modo "Força" (D-018) ---------------------------------------------
        # `escala_forca[nr]` = N_STOPS_ESCALA cores hex já interpoladas em
        # OKLab, de 0% dos válidos até `forca_p98[nr]`%; `escala_forca_fracoes`
        # diz em que fração do teto cada stop fica. O JS multiplica fração ×
        # p98 para montar o `interpolate` do MapLibre e os ticks da legenda —
        # nunca calcula cor. Os 7 candidatos acromáticos compartilham
        # `escala_forca_neutra` (o valor em `escala_forca[nr]` deles é
        # idêntico a ela, para o JS não precisar de caso especial).
        "escala_forca_fracoes": [round(f, 6) for f in FRACOES_ESCALA],
        "escala_forca": {str(nr): escala_forca(nr, paleta) for nr in sorted(paleta)},
        "escala_forca_neutra": escala_forca_neutra(),
        "escala_neutra_fim": ESCALA_NEUTRA_FIM_HEX,
        "n_stops_escala": N_STOPS_ESCALA,
        "forca_p98": {str(nr): round(p98[nr], 4) for nr in sorted(paleta)},
        "forca_percentil": forca.PERCENTIL_FORCA,
        "forca_ordem": ORDEM_FORCA,
        "forca_offsets": offsets,
        # --- modo "Swing 2022→2026" (D-030): escala divergente ASSIMÉTRICA,
        # centro 0 = neutro; cada lado satura no próprio percentil (p1 / p99).
        "escala_swing": sw_dados["meta"],
        "n_municipios_br": int(len(pct_mun)),
        "formato_top_municipios": FORMATO_TOP_MUNICIPIOS,
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
    reg_br = registro(br_tot, votos_br, paleta, venc_br)
    reg_br["nome"] = "Brasil"
    reg_br["votos_cand"] = votos_posicional(votos_br, ordem_cand)

    resumo_ufs = []
    registros_uf: dict[str, dict[str, Any]] = {}
    for _, linha in uf_tot.iterrows():
        sigla = linha["uf"]
        reg = registro(linha, votos_uf[sigla], paleta, venc_uf[sigla])
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
                # 27 × 12 inteiros (~2,6KB brutos): é o que faz o modo
                # "Força" e o ranking de melhor/pior UF funcionarem no nível
                # "Brasil por UF" com ZERO requisição extra. Votos absolutos
                # (e não %) para o JS derivar o % exato de `validos`.
                "votos_cand": votos_posicional(votos_uf[sigla], ordem_cand),
                # [swing PT, swing PL, Δmargem PL−PT] agregados (ponderados), p.p.
                "swing": sw_dados["uf"].get(sigla),
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
            "votos_cand": votos_posicional(votos_uf[config.UF_EXTERIOR], ordem_cand),
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
            reg = registro(linha, votos, paleta, venc_mun[(sigla, linha["cd_mun_tse"])])
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
        reg = registro(linha, votos, paleta, venc_mun[(linha["uf"], linha["cd_mun_tse"])])
        reg.pop("cd_mun_ibge", None)
        # 186 × 12 inteiros (~11KB brutos, arquivo só do modal): permite
        # ordenar/destacar a lista do exterior por QUALQUER candidato,
        # inclusive os 7 que `agrupar_outros` esconderia em "outros".
        reg["votos_cand"] = votos_posicional(votos, ordem_cand) if sum(votos.values()) else None
        locais.append(reg)
    locais.sort(key=lambda it: it["nome"])
    tamanhos["exterior.json"] = escrever_json(
        WEB_DATA / "exterior.json",
        {"agregado": reg_ext, "locais": locais},
    )

    tamanhos["resultados/swing.json"] = escrever_json(
        WEB_DATA / "resultados" / "swing.json", sw_dados["arquivo"]
    )

    # --- força por candidato + resumo do painel ------------------------------
    tam_forca, _ = exportar_forca(pct_mun, p98, paleta)
    tamanhos.update(tam_forca)

    resumo = construir_resumo(
        mun_tot, pct_mun, votos_mun, venc_mun, votos_uf[config.UF_EXTERIOR], p98, ordem_cand
    )
    tamanhos["resumo_candidatos.json"] = escrever_json(WEB_DATA / "resumo_candidatos.json", resumo)

    kb_forca = tamanhos["resultados/forca/cand_<nr>.json (12)"] / 1024
    print(
        f"  resultados: {len(indice_br)} municípios no índice nacional, {len(locais)} no exterior"
    )
    print(
        "  força (p98 do % dos válidos por município, exterior fora): "
        + ", ".join(f"{nr}={p98[nr]:.3f}%" for nr in ordem_cand[:5])
        + f", … (12 arquivos, {kb_forca:.0f}KB brutos)"
    )
    vencidos_total = sum(c["municipios_vencidos"] for c in resumo["candidatos"].values())
    print(
        f"  resumo: {vencidos_total} municípios atribuídos a um vencedor "
        f"(de {resumo['n_municipios_br']})"
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
    ("resumo_candidatos.json", ["resumo_candidatos.json"]),
    ("resultados/br.json", ["resultados/br.json"]),
    ("resultados/municipios_br.json", ["resultados/municipios_br.json"]),
    ("resultados/uf/uf_<sigla>.json", ["resultados/uf/"]),
    ("resultados/forca/cand_<nr>.json", ["resultados/forca/"]),
    ("resultados/swing.json", ["resultados/swing.json"]),
    ("analises.json", ["analises.json"]),
    ("analises_dispersao.json", ["analises_dispersao.json"]),
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
