"""Conteúdo da página `web/projecao.html` (aba "2º turno: projeção"): só o BACKTEST 2018→2022.

Monta `web/data/projecao_backtest.json` a partir de tabelas já calculadas por
`scripts/backtest_2018_2022.py` (CSV em `data/interim/projecao_t2/`) e dos totais
municipais de 2018 e 2022 (achado de mobilização entre turnos). Funções puras: a leitura
dos arquivos fica em `scripts/exportar_projecao_web.py`.

NADA da projeção 2026 entra aqui (regra da fase F5a: a projeção só é publicada junto com
o resultado real do 2º turno). O módulo não conhece nenhum caminho de arquivo.

Como em `eleicao.analise.site`, todo número exibido vira uma chave de `textos` (já
formatada em pt-BR); o HTML não tem número digitado.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from eleicao.analise.regioes import UF_EXTERIOR
from eleicao.analise.site import formatar
from eleicao.cores import (
    COR_ERRO_NEGATIVO,
    COR_ERRO_POSITIVO,
    cor_divergente_simetrica,
    escala_divergente_assimetrica,
)

MODELO_REFERENCIA = "regter_nac"

CASAS_JSON = 4
"""Casas decimais dos valores brutos no JSON (os textos exibidos usam 1 ou 2)."""

MODELOS_TABELA: list[tuple[str, str, str]] = [
    (
        "regter_nac",
        "Referência",
        "Matriz nacional; terceiros pela composição do seu eleitorado no 2º turno anterior",
    ),
    ("base_nac", "Blocos", "Matriz nacional; cada candidato do 1º turno é uma linha da matriz"),
    (
        "regter_uf",
        "Referência por UF",
        "Como a referência, mas com uma matriz estimada para cada UF",
    ),
    (
        "baseline_a",
        "Baseline (a)",
        "1º turno renormalizado entre os dois finalistas, sem transferência",
    ),
    (
        "baseline_b",
        "Baseline (b)",
        "Votos de terceiros e brancos/nulos divididos na proporção dos finalistas",
    ),
]
"""(id no CSV, rótulo curto, descrição) das linhas da tabela, na ordem de exibição."""

MODELOS_MAPA = ["regter_nac", "base_nac", "baseline_a", "baseline_b"]
"""Modelos do seletor do mapa. A escala é a MESMA para todos (comparáveis entre si)."""

PASSO_LIMITE_ESCALA = 0.5
"""O limite da escala simétrica é o maior |erro| por UF dos modelos do mapa, arredondado
para cima em múltiplos deste passo (p.p.)."""

COLUNAS_RESUMO = {
    "modelo",
    "erro_br_pp",
    "uf_media_abs",
    "mae_municipal_pp",
    "acerto_vencedor_uf",
    "erro_abst_br_pp",
}

ABLACAO = {
    "puro": "B2018 puro",
    "comp_ciro": "2018 + composicao so em ciro",
    "comp_3": "2018 + composicao nos 3",
    "linha_bn": "2018 com linha bn = oraculo 2022",
    "linha_abst": "2018 com linha abst = oraculo 2022",
}
"""Variantes da ablação (coluna `variante` do CSV) usadas no texto da página."""


# ============================== mobilização ==================================


def participacao_br(totais: pd.DataFrame) -> dict[str, float]:
    """Abstenção e brancos+nulos em % dos aptos, Brasil SEM o exterior (soma de votos).

    Brancos+nulos = comparecimento − válidos (inclui nulos técnicos, como na F5a)."""
    t = totais[totais["uf"] != UF_EXTERIOR]
    aptos = float(t["eleitorado"].sum())
    return {
        "abst_pct_aptos": 100 * float(t["abstencao"].sum()) / aptos,
        "bn_pct_aptos": 100 * float(t["comparecimento"].sum() - t["validos"].sum()) / aptos,
    }


def mobilizacao(totais: dict[int, dict[int, pd.DataFrame]]) -> dict[str, dict[str, float]]:
    """{ano: {abst_t1, abst_t2, delta_abst_pp, bn_t1, bn_t2}} para cada ano de `totais`."""
    saida = {}
    for ano, por_turno in sorted(totais.items()):
        t1, t2 = participacao_br(por_turno[1]), participacao_br(por_turno[2])
        saida[str(ano)] = {
            "abst_t1": round(t1["abst_pct_aptos"], CASAS_JSON),
            "abst_t2": round(t2["abst_pct_aptos"], CASAS_JSON),
            "delta_abst_pp": round(t2["abst_pct_aptos"] - t1["abst_pct_aptos"], CASAS_JSON),
            "bn_t1": round(t1["bn_pct_aptos"], CASAS_JSON),
            "bn_t2": round(t2["bn_pct_aptos"], CASAS_JSON),
        }
    return saida


def pct_pl_validos_br(cand_t2: pd.DataFrame, nr_pl: int = 22) -> float:
    """% do PL entre os válidos do 2º turno, Brasil sem exterior (soma de votos)."""
    c = cand_t2[cand_t2["uf"] != UF_EXTERIOR]
    return 100 * float(c.loc[c["nr_candidato"] == nr_pl, "votos"].sum()) / float(c["votos"].sum())


# ================================ escala =====================================


def limite_escala(erros_uf: pd.DataFrame, modelos: list[str]) -> float:
    maior = float(erros_uf[modelos].abs().to_numpy().max())
    return math.ceil(maior / PASSO_LIMITE_ESCALA) * PASSO_LIMITE_ESCALA


# ================================ montagem ===================================


def _validar(resumo: pd.DataFrame, erros_uf: pd.DataFrame, ablacao: pd.DataFrame) -> None:
    faltam = COLUNAS_RESUMO - set(resumo.columns)
    if faltam:
        raise ValueError(f"backtest_resumo.csv sem as colunas {sorted(faltam)}")
    ids = [m for m, _, _ in MODELOS_TABELA]
    for m in ids:
        if m not in set(resumo["modelo"]):
            raise ValueError(f"backtest_resumo.csv sem o modelo {m}")
        if m not in erros_uf.columns:
            raise ValueError(f"backtest_erros_uf.csv sem a coluna {m}")
    if len(erros_uf) != 27 or erros_uf["uf"].nunique() != 27 or UF_EXTERIOR in set(erros_uf["uf"]):
        raise ValueError("backtest_erros_uf.csv precisa ter as 27 UFs, sem o exterior")
    falta_ab = set(ABLACAO.values()) - set(ablacao["variante"])
    if falta_ab:
        raise ValueError(f"backtest_ablacao_linhas.csv sem as variantes {sorted(falta_ab)}")


def _pior_uf(erros_uf: pd.DataFrame, modelo: str) -> tuple[str, float]:
    i = int(np.argmax(erros_uf[modelo].abs().to_numpy()))
    return str(erros_uf["uf"].iloc[i]), float(erros_uf[modelo].iloc[i])


def montar(
    resumo: pd.DataFrame,
    erros_uf: pd.DataFrame,
    ablacao: pd.DataFrame,
    totais: dict[int, dict[int, pd.DataFrame]],
    cand_2022_t2: pd.DataFrame,
) -> dict[str, Any]:
    """Conteúdo de `web/data/projecao_backtest.json`."""
    _validar(resumo, erros_uf, ablacao)
    res = resumo.set_index("modelo")
    erros = erros_uf.sort_values("uf").reset_index(drop=True)
    ab = ablacao.set_index("variante")
    valores: dict[str, float] = {}
    fmt: dict[str, tuple[int, str]] = {}

    def put(chave: str, valor: float, casas: int, tipo: str) -> None:
        valores[chave] = round(float(valor), CASAS_JSON)
        fmt[chave] = (casas, tipo)

    # ---- tabela
    tabela = []
    for mid, rotulo, descricao in MODELOS_TABELA:
        r = res.loc[mid]
        uf_pior, erro_pior = _pior_uf(erros, mid)
        acertos = round(float(r["acerto_vencedor_uf"]) * 27)
        tabela.append(
            {
                "id": mid,
                "rotulo": rotulo,
                "descricao": descricao,
                "referencia": mid == MODELO_REFERENCIA,
                "erro_br_pp": round(float(r["erro_br_pp"]), CASAS_JSON),
                "uf_media_abs_pp": round(float(r["uf_media_abs"]), CASAS_JSON),
                "pior_uf": uf_pior,
                "pior_uf_erro_pp": round(erro_pior, CASAS_JSON),
                "mae_municipal_pp": round(float(r["mae_municipal_pp"]), CASAS_JSON),
                "vencedor_uf_certos": acertos,
                "vencedor_uf_total": 27,
                "erro_abst_br_pp": round(float(r["erro_abst_br_pp"]), CASAS_JSON),
                "textos": {
                    "erro_br_pp": formatar(r["erro_br_pp"], 2, "pp"),
                    "uf_media_abs_pp": formatar(r["uf_media_abs"], 2, "dec"),
                    "pior_uf": f"{uf_pior.upper()} ({formatar(erro_pior, 2, 'pp')})",
                    "mae_municipal_pp": formatar(r["mae_municipal_pp"], 2, "dec"),
                    "vencedor_uf": f"{acertos}/27",
                    "erro_abst_br_pp": formatar(r["erro_abst_br_pp"], 2, "pp"),
                },
            }
        )

    # ---- mapa
    limite = limite_escala(erros, MODELOS_MAPA)
    mapa = {
        mid: {
            uf: {
                "erro_pp": round(float(v), CASAS_JSON),
                "cor": cor_divergente_simetrica(
                    float(v), limite, COR_ERRO_NEGATIVO, COR_ERRO_POSITIVO
                ),
                "texto": formatar(v, 2, "pp"),
            }
            for uf, v in zip(erros["uf"], erros[mid], strict=True)
        }
        for mid in MODELOS_MAPA
    }
    escala = escala_divergente_assimetrica(-limite, limite, COR_ERRO_NEGATIVO, COR_ERRO_POSITIVO)

    # ---- números do texto
    ref = res.loc[MODELO_REFERENCIA]
    blocos = res.loc["base_nac"]
    put("ref.erro_br", ref["erro_br_pp"], 2, "pp")
    put("ref.uf_media_abs", ref["uf_media_abs"], 2, "dec")
    put("ref.erro_abst", ref["erro_abst_br_pp"], 2, "pp")
    put("blocos.erro_br", blocos["erro_br_pp"], 1, "pp")
    put("blocos.erro_abst", blocos["erro_abst_br_pp"], 2, "pp")
    put("real_2022.pct_pl", pct_pl_validos_br(cand_2022_t2), 2, "pct")
    put("escala.limite", limite, 1, "dec")
    put("ablacao.puro", ab.loc[ABLACAO["puro"], "erro_br_pp"], 2, "pp")
    put("ablacao.comp_ciro", ab.loc[ABLACAO["comp_ciro"], "erro_br_pp"], 2, "pp")
    put("ablacao.comp_3", ab.loc[ABLACAO["comp_3"], "erro_br_pp"], 2, "pp")
    put("ablacao.linha_bn", ab.loc[ABLACAO["linha_bn"], "erro_br_pp"], 2, "pp")
    put("ablacao.linha_abst", ab.loc[ABLACAO["linha_abst"], "erro_br_pp"], 2, "pp")
    put("ablacao.puro_abst", ab.loc[ABLACAO["puro"], "erro_abst_pp"], 2, "pp")
    put("ablacao.linha_abst_abst", ab.loc[ABLACAO["linha_abst"], "erro_abst_pp"], 2, "pp")
    mob = mobilizacao(totais)
    for ano in ("2018", "2022"):
        m = mob[ano]
        put(f"mob.{ano}.delta_abst", m["delta_abst_pp"], 2, "pp")
        put(f"mob.{ano}.bn_t1", m["bn_t1"], 1, "pct")
        put(f"mob.{ano}.bn_t2", m["bn_t2"], 1, "pct")
        put(f"mob.{ano}.abst_t1", m["abst_t1"], 1, "pct")
        put(f"mob.{ano}.abst_t2", m["abst_t2"], 1, "pct")

    return {
        "descricao": (
            "Backtest 2018→2022 da projeção do 2º turno por inferência ecológica (F5a). "
            "Erro = previsto − real do % do PL entre os válidos no 2º turno de 2022, em p.p. "
            "Não contém nenhum número da projeção 2026."
        ),
        "modelo_referencia": MODELO_REFERENCIA,
        "tabela": tabela,
        "modelos_mapa": [
            {"id": mid, "rotulo": next(r for m, r, _ in MODELOS_TABELA if m == mid)}
            for mid in MODELOS_MAPA
        ],
        "mapa": mapa,
        "escala": {
            "limite_pp": limite,
            "stops": [[round(v, 4), c] for v, c in escala],
            "rotulo_negativo": "subestimou o PL",
            "rotulo_positivo": "superestimou o PL",
        },
        "mobilizacao": mob,
        "valores": valores,
        "textos": {k: formatar(v, *fmt[k]) for k, v in valores.items()},
    }
