"""Parsers do IBGE: Censo 2022 (população) e PIB dos Municípios (per capita).

Funções puras — recebem bytes/texto já em ``data/raw/`` e devolvem
DataFrames. Fontes e armadilhas documentadas em `docs/DADOS.md` → "4. IBGE".
"""

from __future__ import annotations

import json

import pandas as pd

# Posições (1-indexadas, conforme o PDF de layout do IBGE) dos campos usados
# do arquivo fixo "PIB dos Municípios - base de dados 2010-2023.txt". O slice
# de cada campo vai da sua posição até a posição do PRÓXIMO campo do layout
# (não da "largura" declarada, que para os campos monetários é só
# "dígitos.decimais", ex. "18.3" — ver docs/DADOS.md). Confirmado por
# inspeção direta: linha de 1258 bytes (1256 de conteúdo + CRLF), última
# posição do layout (1163) + largura declarada (94) == 1256.
_PIB_COLSPECS: list[tuple[str, int, int]] = [
    ("ano", 0, 5),  # posição 1, até a posição 6 (Código Grande Região)
    ("sigla_uf", 23, 26),  # posição 24, até a posição 27 (Nome da UF)
    ("cd_mun_ibge", 46, 54),  # posição 47, até a posição 55 (Nome do Município)
    ("nm_mun_ibge", 54, 95),  # posição 55, até a posição 96 (Região Metropolitana)
    ("pib_mil_reais", 934, 953),  # posição 935, até a posição 954 (PIB per capita)
    ("pib_per_capita_reais", 953, 972),  # posição 954, até a posição 973 (Atividade...)
]


def parse_pib_municipios(texto: str, *, ano: str) -> pd.DataFrame:
    """Parseia o TXT de largura fixa "PIB dos Municípios" (IBGE, ref. 2010) para 1 ano.

    `texto` é o conteúdo decodificado (latin-1) do arquivo inteiro (2010-2023,
    todos os municípios, 1 linha por município×ano). Filtra para `ano`
    (string, ex. ``"2023"``) — ver docs/DADOS.md sobre por que só PIB total e
    per capita estão disponíveis para 2022/2023 (demais variáveis omitidas
    pelo IBGE nesses dois anos, nota 2 do layout).
    """
    linhas = texto.splitlines()
    registros = []
    for linha in linhas:
        if len(linha) < 972:
            continue
        valores = {nome: linha[ini:fim].strip() for nome, ini, fim in _PIB_COLSPECS}
        if valores["ano"] != ano:
            continue
        registros.append(valores)

    df = pd.DataFrame(registros)
    df["cd_mun_ibge"] = df["cd_mun_ibge"].astype("int64")
    df["pib_mil_reais"] = df["pib_mil_reais"].astype(float)
    df["pib_per_capita_reais"] = df["pib_per_capita_reais"].astype(float)
    df["sigla_uf"] = df["sigla_uf"].str.lower()
    return df[
        ["cd_mun_ibge", "nm_mun_ibge", "sigla_uf", "pib_mil_reais", "pib_per_capita_reais"]
    ].reset_index(drop=True)


def parse_populacao_censo_2022(conteudo_json: bytes) -> pd.DataFrame:
    """Parseia a resposta da API SIDRA (agregado 4709, variável 93, período 2022).

    Formato: lista com 1 item (a variável), ``resultados[0].series[]`` — 1
    série por município, com ``serie.2022`` = população residente (Censo
    2022, 1ª apuração). Ver docs/DADOS.md → "4. IBGE".
    """
    dados = json.loads(conteudo_json)
    series = dados[0]["resultados"][0]["series"]
    registros = [
        {
            "cd_mun_ibge": int(item["localidade"]["id"]),
            "nm_mun_ibge": item["localidade"]["nome"],
            "populacao_censo_2022": int(item["serie"]["2022"]),
        }
        for item in series
    ]
    return pd.DataFrame(registros)
