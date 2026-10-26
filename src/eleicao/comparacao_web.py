"""Bloco "Previsto × real" da aba "2º turno: projeção" (`comparacao_t2` do JSON).

Compara a projeção publicada (D-037, intocada) com o 2º turno de 2026 apurado. Funções puras:
os caminhos e a leitura ficam em `scripts/exportar_projecao_web.py`.

O que é fato e o que é estimativa fica explícito nos textos:
- placar, cenários e mapa por UF comparam números oficiais com números projetados;
- a decomposição por origem usa a matriz ecológica estimada do T1 para o T2 e leva o IC
  de bootstrap por UF inteira (o mais conservador); linhas com IC que inclui zero ficam
  marcadas como "não distinguível de zero";
- o ganho mínimo do PT fora da base de Lula é aritmética por município, sem modelo.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from eleicao.analise.regioes import UF_EXTERIOR
from eleicao.analise.site import formatar
from eleicao.cores import (
    COR_ERRO_NEGATIVO,
    COR_ERRO_POSITIVO,
    cor_divergente_simetrica,
    escala_divergente_assimetrica,
)
from eleicao.projecao_web import CENARIO_BASE, CENARIOS_PRINCIPAIS, RECORTE_TOTAL

NR_PL, NR_PT = 22, 13
PASSO_ESCALA = 0.5
ROTULOS_ORIGEM = {
    "flavio": "Eleitores de Flávio (1º turno)",
    "lula": "Eleitores de Lula (1º turno)",
    "cury": "Eleitores de Cury",
    "renan": "Eleitores de Renan",
    "caiado": "Eleitores de Caiado",
    "outros_2026": "Eleitores dos demais candidatos",
    "bn_2026": "Brancos e nulos do 1º turno",
    "abst_2026": "Abstenção do 1º turno",
}


def _lista(itens: list[str]) -> str:
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]


def _votos(cand: pd.DataFrame, nr: int) -> int:
    return int(cand.loc[cand["nr_candidato"].astype(int) == nr, "votos"].sum())


def real_por_recorte(cand: pd.DataFrame, tot: pd.DataFrame) -> dict[str, float]:
    """Votos e percentuais sobre os válidos de um recorte (uma linha de `tot`)."""
    pl, pt = _votos(cand, NR_PL), _votos(cand, NR_PT)
    t = tot.iloc[0]
    return {
        "pl": pl,
        "pt": pt,
        "pct_pl": 100 * pl / (pl + pt),
        "pct_pt": 100 * pt / (pl + pt),
        "abst_pct": 100 * float(t["abstencao"]) / float(t["eleitorado"]),
    }


def _real_ufs(cand_uf: pd.DataFrame) -> pd.DataFrame:
    v = cand_uf.assign(nr=cand_uf["nr_candidato"].astype(int)).pivot_table(
        index="uf", columns="nr", values="votos", aggfunc="sum"
    )
    return pd.DataFrame({"pct_pl": 100 * v[NR_PL] / (v[NR_PL] + v[NR_PT])})


def montar(
    br_proj: pd.DataFrame,
    uf_proj: pd.DataFrame,
    cand_br: pd.DataFrame,
    tot_br: pd.DataFrame,
    cand_uf: pd.DataFrame,
    decomposicao: pd.DataFrame,
    ganhos: dict[str, float],
) -> dict[str, Any]:
    """Conteúdo de `comparacao_t2`. Todos os textos saem formatados daqui."""
    real = real_por_recorte(cand_br, tot_br)
    tot = br_proj[br_proj["recorte"] == RECORTE_TOTAL].set_index("cenario")

    # ---- placar
    base = tot.loc[CENARIO_BASE]
    faixa = float(base["faixa_pl_pp"])
    erro = float(base["pct_pl_validos"]) - real["pct_pl"]
    placar = {
        "prev_pct_pl": round(float(base["pct_pl_validos"]), 4),
        "real_pct_pl": round(real["pct_pl"], 4),
        "erro_pp": round(erro, 4),
        "faixa_pp": faixa,
        "dentro_da_faixa": abs(erro) <= faixa,
        "vencedor_certo": (float(base["pct_pl_validos"]) > 50) == (real["pct_pl"] > 50),
    }

    # ---- cenários (nenhum foi escolhido depois do resultado: a base é a declarada)
    cenarios = []
    for cid, rotulo in CENARIOS_PRINCIPAIS:
        e = float(tot.loc[cid, "pct_pl_validos"]) - real["pct_pl"]
        cenarios.append(
            {
                "id": cid,
                "rotulo": rotulo,
                "erro_pp": round(e, 4),
                "dentro_da_faixa": abs(e) <= faixa,
                "prev_texto": formatar(float(tot.loc[cid, "pct_pl_validos"]), 1, "pct"),
                "erro_texto": formatar(e, 1, "pp"),
            }
        )

    # ---- UFs (cenário base)
    ru = _real_ufs(cand_uf)
    ub = uf_proj[(uf_proj["cenario"] == CENARIO_BASE)].set_index("uf")
    ufs27 = [u for u in ub.index if u != UF_EXTERIOR]
    erros = pd.Series({u: float(ub.loc[u, "pct_pl_validos"] - ru.loc[u, "pct_pl"]) for u in ufs27})
    limite = math.ceil(erros.abs().max() / PASSO_ESCALA) * PASSO_ESCALA
    faixa_uf = float(ub.loc[ufs27[0], "faixa_pp"])
    ufs = {
        u: {
            "prev_pct_pl": round(float(ub.loc[u, "pct_pl_validos"]), 4),
            "real_pct_pl": round(float(ru.loc[u, "pct_pl"]), 4),
            "erro_pp": round(float(e), 4),
            "cor": cor_divergente_simetrica(float(e), limite, COR_ERRO_NEGATIVO, COR_ERRO_POSITIVO),
            "texto": f"{u.upper()}: previsto PL {formatar(ub.loc[u, 'pct_pl_validos'], 1, 'pct')}, "
            f"real {formatar(ru.loc[u, 'pct_pl'], 1, 'pct')} "
            f"(erro {formatar(e, 1, 'pp')})",
        }
        for u, e in erros.items()
    }
    lado_certo = sum(
        (ub.loc[u, "pct_pl_validos"] > 50) == (ru.loc[u, "pct_pl"] > 50) for u in ufs27
    )
    na_faixa = int((erros.abs() <= faixa_uf).sum())
    todos_positivos = bool((erros > 0).all())
    escala = escala_divergente_assimetrica(-limite, limite, COR_ERRO_NEGATIVO, COR_ERRO_POSITIVO)

    # ---- decomposição por origem (votos a mais de PL sobre PT na projeção, milhões)
    dec = []
    for r in decomposicao.itertuples():
        lo, hi, v = r.ic_uf_lo / 1e6, r.ic_uf_hi / 1e6, r.excesso_pl_menos_pt / 1e6
        dec.append(
            {
                "id": r.origem,
                "rotulo": ROTULOS_ORIGEM[r.origem],
                "milhoes": round(v, 4),
                "lo": round(lo, 4),
                "hi": round(hi, 4),
                "distingue_de_zero": lo > 0 or hi < 0,
                "texto": formatar(v, 1, "dec"),
                "texto_ic": f"{formatar(lo, 1, 'dec')} a {formatar(hi, 1, 'dec')}",
            }
        )
    soma = float(decomposicao["excesso_pl_menos_pt"].sum()) / 1e6

    melhor = min(cenarios, key=lambda c: abs(c["erro_pp"]))
    todos_pl = all(float(tot.loc[c["id"], "pct_pl_validos"]) > 50 for c in cenarios)
    resumo = ("Os quatro cenários principais projetaram o PL à frente. " if todos_pl else "") + (
        f"O mais próximo do resultado foi “{melhor['rotulo']}” ({melhor['erro_texto']}). "
        "Isso só é conhecido agora: não o torna a melhor previsão antes da votação. "
        + (
            "O cenário declarado antes do resultado foi o base, que não foi alterado."
            if melhor["id"] != CENARIO_BASE
            else "Ele também era o cenário base, declarado antes do resultado."
        )
    )

    # ponto 1: leitura qualitativa à frente dos números, calculada da decomposição
    nomes = {
        "flavio": "eleitores de Flávio",
        "lula": "eleitores de Lula",
        "cury": "eleitores de Cury",
        "renan": "eleitores de Renan",
        "caiado": "eleitores de Caiado",
        "outros_2026": "eleitores dos demais candidatos",
        "bn_2026": "brancos e nulos do 1º turno",
        "abst_2026": "abstenção do 1º turno",
    }
    fortes = sorted(
        (d for d in dec if d["distingue_de_zero"] and d["milhoes"] > 0), key=lambda d: -d["milhoes"]
    )
    incertos = [d for d in dec if not d["distingue_de_zero"]]
    leitura = (
        "Leitura qualitativa: o erro se concentra em "
        + _lista([nomes[d["id"]] for d in fortes])
        + "; para "
        + _lista([nomes[d["id"]] for d in incertos])
        + ", a estimativa não permite apontar a origem do erro."
    )

    pt_fora = ganhos["ganho_minimo_votos"] / 1e6
    textos = {
        "placar_prev": f"Previsto (cenário base): PL {formatar(base['pct_pl_validos'], 1, 'pct')} "
        f"dos válidos",
        "placar_real": f"Real: PL {formatar(real['pct_pl'], 1, 'pct')}, PT "
        f"{formatar(real['pct_pt'], 1, 'pct')}",
        "erro": f"Erro {formatar(erro, 1, 'pp')} (previsto menos real), "
        f"fora da faixa de ±{formatar(faixa, 0, 'dec')} p.p."
        if not placar["dentro_da_faixa"]
        else f"Erro {formatar(erro, 1, 'pp')}, dentro da faixa de "
        f"±{formatar(faixa, 0, 'dec')} p.p.",
        "vencedor": (
            "O método não distinguia vencedor (PL dentro da faixa em torno de 50%); "
            "o resultado real ficou do lado do PT."
            if base["veredito"] == "indistinguivel" and real["pct_pl"] < 50
            else "O vencedor projetado coincidiu com o real."
            if placar["vencedor_certo"]
            else "O vencedor projetado não coincidiu com o real."
        ),
        "ufs_lado": f"{lado_certo} de 27 UFs no lado certo (acima ou abaixo de 50%)",
        "ufs_faixa": f"{na_faixa} de 27 UFs dentro da faixa de "
        f"±{formatar(faixa_uf, 1, 'dec')} p.p.",
        "ufs_sinal": "O erro teve o mesmo sinal em todas as UFs: a projeção superestimou o PL "
        "em todo o país."
        if todos_positivos
        else "O erro mudou de sinal entre UFs.",
        "abst": f"Abstenção real: {formatar(real['abst_pct'], 2, 'pct')} dos aptos "
        f"(projetada no cenário base: {formatar(float(base['pct_abst_aptos']), 2, 'pct')}).",
        "cenarios_resumo": resumo,
        "leitura_decomposicao": leitura,
        "soma_dec": formatar(soma, 1, "dec"),
        "pt_fora_lula": formatar(pt_fora, 1, "dec"),
        "pt_t2": formatar(ganhos["pt_t2"] / 1e6, 1, "dec"),
        "lula_t1": formatar(ganhos["lula_t1"] / 1e6, 1, "dec"),
        "limite_escala": formatar(limite, 1, "dec"),
    }
    return {
        "placar": placar,
        "cenarios": cenarios,
        "ufs": ufs,
        "contagem_ufs": {
            "lado_certo": int(lado_certo),
            "na_faixa": na_faixa,
            "erro_todos_positivos": todos_positivos,
        },
        "escala": {
            "limite_pp": limite,
            "stops": [[round(v, 4), c] for v, c in escala],
            "rotulo_negativo": "subestimou o PL",
            "rotulo_positivo": "superestimou o PL",
        },
        "decomposicao": dec,
        "ganho_minimo_pt": {k: round(v, 2) for k, v in ganhos.items()},
        "textos": textos,
    }
