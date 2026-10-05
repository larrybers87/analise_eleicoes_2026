"""Constantes da eleição 2026 e construtores de URL da API de divulgação do TSE.

Fonte: https://resultados.tse.jus.br/oficial/comum/config/ele-c.json (ver docs/DADOS.md).
"""

from pathlib import Path

BASE_URL = "https://resultados.tse.jus.br"
AMBIENTE = "oficial"
CICLO = "ele2026"
PLEITO_T1 = 3220

ELEICAO_FEDERAL_T1 = 6257  # Presidente, 1º turno
ELEICAO_FEDERAL_T2 = 6258  # Presidente, 2º turno
ELEICAO_ESTADUAL_T1 = 6259
ELEICAO_ESTADUAL_T2 = 6260

CARGO_PRESIDENTE = 1
CARGO_GOVERNADOR = 3
CARGO_SENADOR = 5
CARGO_DEP_FEDERAL = 6
CARGO_DEP_ESTADUAL = 7
CARGO_DEP_DISTRITAL = 8

UFS = [
    "ac", "al", "am", "ap", "ba", "ce", "df", "es", "go", "ma", "mg", "ms", "mt", "pa",
    "pb", "pe", "pi", "pr", "rj", "rn", "ro", "rr", "rs", "sc", "se", "sp", "to",
]
UF_EXTERIOR = "zz"

RAIZ = Path(__file__).resolve().parents[2]
DATA_RAW = RAIZ / "data" / "raw"
DATA_INTERIM = RAIZ / "data" / "interim"
DATA_PROCESSED = RAIZ / "data" / "processed"


def _prefixo(eleicao: int) -> str:
    return f"/{AMBIENTE}/{CICLO}/{eleicao}"


def caminho_config_municipios(eleicao: int) -> str:
    return f"{_prefixo(eleicao)}/config/mun-e{eleicao:06d}-cm.json"


def caminho_resultado(eleicao: int, cargo: int, uf: str, cd_mun: str | None = None) -> str:
    """Resultado unificado (EA20). `uf='br'` para Brasil; `cd_mun` com 5 dígitos para município."""
    uf = uf.lower()
    abrangencia = uf if cd_mun is None else f"{uf}{int(cd_mun):05d}"
    return f"{_prefixo(eleicao)}/dados/{uf}/{abrangencia}-c{cargo:04d}-e{eleicao:06d}-u.json"


def caminho_acompanhamento(eleicao: int, uf: str = "br") -> str:
    uf = uf.lower()
    return f"{_prefixo(eleicao)}/dados/{uf}/{uf}-e{eleicao:06d}-ab.json"


def url(caminho: str) -> str:
    return f"{BASE_URL}{caminho}"


def caminho_local(caminho: str) -> Path:
    """Espelho local de um caminho remoto em data/raw/ (sem o prefixo do ambiente)."""
    return DATA_RAW / caminho.removeprefix(f"/{AMBIENTE}/")
