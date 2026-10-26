"""Página "2º turno: resultado": chaves, números digitados e consistência com o T2 apurado."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser

import pandas as pd
import pytest

from eleicao import config

JSON = config.RAIZ / "web" / "data" / "segundo_turno.json"
HTML = config.RAIZ / "web" / "segundo-turno.html"
PROC = config.DATA_PROCESSED

sem_json = pytest.mark.skipif(not JSON.exists(), reason="rode scripts/exportar_segundo_turno.py")
TERMOS_PERMITIDOS = re.compile(r"docs/\w+\.md|\bg1\b")


class _Texto(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.pedacos: list[str] = []
        self._ignorar = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style", "title"):
            self._ignorar += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "title") and self._ignorar:
            self._ignorar -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignorar:
            self.pedacos.append(data)


def _texto_da_pagina() -> str:
    p = _Texto()
    p.feed(HTML.read_text(encoding="utf-8"))
    return " ".join(" ".join(p.pedacos).split())


@pytest.fixture(scope="module")
def dados() -> dict:
    return json.loads(JSON.read_text(encoding="utf-8"))


@sem_json
def test_toda_chave_data_s_tem_texto(dados: dict) -> None:
    html = re.sub(r"<!--.*?-->", "", HTML.read_text(encoding="utf-8"), flags=re.DOTALL)
    chaves = set(re.findall(r'data-s="([^"]+)"', html))
    assert chaves
    assert chaves <= set(dados["textos"]), chaves - set(dados["textos"])


def test_html_nao_tem_numero_digitado() -> None:
    texto = re.sub(r"(?<!\d)[12]º", "", _texto_da_pagina())
    texto = TERMOS_PERMITIDOS.sub("", texto)
    achados = [
        (m.group(), texto[max(0, m.start() - 25) : m.end() + 10])
        for m in re.finditer(r"\d+(?:[.,]\d+)*", texto)
        if m.group() not in {"2018", "2026"}
    ]
    assert not achados, f"números digitados: {achados}"


@sem_json
def test_placar_bate_com_o_oficial(dados: dict) -> None:
    c = pd.read_parquet(PROC / "presidente_t2_br.parquet")
    votos = c.set_index(c["nr_candidato"].astype(int))["votos"]
    margem = int(votos[13] - votos[22])
    assert dados["textos"]["margem_votos"] == f"{margem:,}".replace(",", ".")
    assert dados["textos"]["lula_votos"] == f"{int(votos[13]):,}".replace(",", ".")


@sem_json
def test_mapas_cobrem_27_ufs_e_so_pt_no_swing_positivo(dados: dict) -> None:
    assert len(dados["ufs"]) == 27
    assert "zz" not in dados["ufs"]
    assert all(u["swing"] > 0 for u in dados["ufs"].values())


def test_extensao_cita_imprensa_e_pendencia() -> None:
    t = _texto_da_pagina()
    assert "da imprensa e não foi verificado" in t
    assert "pendente" in t
    assert "divergem sobre o alcance" in t
