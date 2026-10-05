"""Parser do resultado unificado (EA20) da API de divulgação do TSE.

Funções puras: recebem os bytes exatos do JSON (como gravados em
``data/raw/`` pelo `TseClient`) e devolvem DataFrames. Nenhum I/O aqui — quem
lê o arquivo e empilha o resultado de várias chamadas é o código de
orquestração (``scripts/processar_presidente.py``).

Mapeamento de campos: ver "Estrutura real confirmada" em `docs/DADOS.md`.
Campos conhecidos mas não solicitados explicitamente no schema alvo (ex.:
percentuais formatados, que são derivados dos contadores já capturados) são
preservados em colunas ``extra_*`` — nada é descartado silenciosamente.
"""

from __future__ import annotations

import json

import pandas as pd

_ABRANGENCIA_POR_TPABR = {"br": "br", "uf": "uf", "mu": "mun"}


def _int(valor: str | None) -> int | None:
    if valor is None or valor == "":
        return None
    return int(valor)


def _float(valor: str | None) -> float | None:
    """Converte string numérica do TSE (vírgula decimal, ex. `"57,499675335"`).

    Contrário ao que `docs/DADOS.md` registrava antes desta correção, os
    campos `p<campo>n` também usam vírgula como separador decimal (não
    ponto) — só variam em ter mais ou menos casas decimais que `p<campo>`.
    """
    if valor is None or valor == "":
        return None
    return float(valor.replace(",", "."))


def parse_ea20(
    conteudo: bytes,
    *,
    uf: str,
    cd_mun_ibge: str | None = None,
    nm_mun: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Parseia um arquivo EA20 (BR, UF ou município) em `(df_candidatos, df_totais)`.

    `uf` é sempre exigido (sigla minúscula, ex. `"br"`, `"pr"`, `"zz"`) porque,
    para abrangência de município, o próprio JSON não informa a UF — só o
    código TSE do município (`cdabr`). Para BR e UF, `uf` deve ser consistente
    com `cdabr` (usado só para doc/validação, não é recalculado a partir dele).

    `cd_mun_ibge` e `nm_mun` vêm do config de municípios (`mun-e*-cm.json`) —
    o EA20 não traz nome do município nem código IBGE.

    Ambos os DataFrames retornados têm exatamente 1 linha por município/UF/BR
    no caso de `df_totais`, e 1 linha por candidato no caso de `df_candidatos`
    (geralmente entre 10 e 13, para Presidente 2026).
    """
    dado = json.loads(conteudo)

    tpabr = dado["tpabr"]
    cdabr = dado["cdabr"]
    abrangencia = _ABRANGENCIA_POR_TPABR[tpabr]
    cd_mun_tse = cdabr if tpabr == "mu" else None

    s = dado["s"]
    e = dado["e"]
    v = dado["v"]

    status_totalizacao = dado["and"]  # "f" = final, "p" = parcial
    data_hora_totalizacao = f"{dado['dt']} {dado['ht']}"

    totais = {
        "uf": uf,
        "cd_mun_tse": cd_mun_tse,
        "cd_mun_ibge": cd_mun_ibge,
        "nm_mun": nm_mun,
        "abrangencia": abrangencia,
        "eleitorado": _int(e["te"]),
        "comparecimento": _int(e["c"]),
        "abstencao": _int(e["a"]),
        "validos": _int(v["vv"]),
        "brancos": _int(v["vb"]),
        "nulos_vn": _int(v["vn"]),
        "nulos_tvn": _int(v["tvn"]),
        "secoes_totalizadas": _int(s["si"]),
        "secoes_total": _int(s["ts"]),
        "status_totalizacao": status_totalizacao,
        "data_hora_totalizacao": data_hora_totalizacao,
        # anulados / sub judice (pedido explicitamente, ver docs/DADOS.md)
        "anulados": _int(v["van"]),
        "anulados_sub_judice": _int(v["vansj"]),
        # extras de "v": contadores adicionais não mapeados para coluna própria
        # (percentuais formatados foram deliberadamente omitidos — são
        # derivados dos contadores abaixo; ver docs/DADOS.md).
        "extra_v_vvc": _int(v.get("vvc")),
        "extra_v_vnom": _int(v.get("vnom")),
        "extra_v_vnt": _int(v.get("vnt")),
        "extra_v_vsan": _int(v.get("vsan")),
        "extra_v_vscv": _int(v.get("vscv")),
        # extras de "s"/"e": contagens de seções/eleitorado não informadas
        # ainda (relevante enquanto status_totalizacao == "p")
        "extra_s_snt": _int(s.get("snt")),
        "extra_s_sni": _int(s.get("sni")),
        "extra_s_sa": _int(s.get("sa")),
        "extra_s_sna": _int(s.get("sna")),
        "extra_e_esi": _int(e.get("esi")),
        "extra_e_esni": _int(e.get("esni")),
        "extra_e_esa": _int(e.get("esa")),
        "extra_e_esna": _int(e.get("esna")),
    }
    df_totais = pd.DataFrame([totais])

    linhas_candidatos: list[dict] = []
    for cargo in dado.get("carg", []):
        for agr in cargo.get("agr", []):
            for par in agr.get("par", []):
                for cand in par.get("cand", []):
                    vice = cand.get("vs", [{}])[0] if cand.get("vs") else {}
                    linhas_candidatos.append(
                        {
                            "uf": uf,
                            "cd_mun_tse": cd_mun_tse,
                            "nr_candidato": _int(cand["n"]),
                            "nm_urna": cand["nmu"],
                            "partido": par["sg"],
                            "votos": _int(cand["vap"]),
                            "pct_validos": _float(cand["pvapn"]),
                            # situação / destinação do voto, ver docs/DADOS.md
                            "eleito": {"s": True, "n": False}.get(cand.get("e")),
                            "situacao": cand.get("st") or None,
                            # extras não descartados
                            "extra_cand_nm_completo": cand.get("nm"),
                            "extra_cand_sqcand": cand.get("sqcand"),
                            "extra_cand_posicao_classificacao": _int(cand.get("seq")),
                            "extra_cand_dvt": cand.get("dvt"),
                            "extra_partido_nm": par.get("nm"),
                            "extra_partido_nfed": par.get("nfed") or None,
                            "extra_agremiacao_tipo": agr.get("tp"),
                            "extra_agremiacao_nome": agr.get("nm"),
                            "extra_vice_nm_urna": vice.get("nmu"),
                            "extra_vice_sqcand": vice.get("sqcand"),
                        }
                    )
    df_candidatos = pd.DataFrame(linhas_candidatos)

    return df_candidatos, df_totais
