"""O vencedor publicado no mapa (`web/data/`) é o da função de análise (D-030).

`scripts/exportar_web.py` não tem lógica própria de vencedor: usa
`eleicao.analise.base.vencedor_municipal`, em que empate exato = sem vencedor. Este teste
confere que a contagem publicada (índice nacional e resumo do painel) bate com a função.
"""

from __future__ import annotations

import json
from collections import Counter

import pytest

from eleicao import config
from eleicao.analise import base, carga
from eleicao.cores import NEUTRO_EMPATE_HEX

WEB = config.RAIZ / "web" / "data"
pytestmark = pytest.mark.skipif(
    not (WEB / "resultados" / "municipios_br.json").exists(), reason="web/data não gerado"
)


@pytest.fixture(scope="module")
def vencedores():
    c = carga.candidatos_2026()
    return base.vencedor_municipal(c[c["uf"] != "zz"])


@pytest.fixture(scope="module")
def indice():
    obj = json.loads((WEB / "resultados" / "municipios_br.json").read_text(encoding="utf-8"))
    campos = obj["formato"]
    return [dict(zip(campos, arr, strict=True)) for arr in obj["municipios"].values()]


def test_contagem_de_vencidos_no_indice_bate_com_a_funcao(vencedores, indice):
    funcao = Counter(None if v is None else int(v) for v in vencedores["nr_vencedor"])
    publicado = Counter(m["vencedor"] for m in indice)
    assert publicado == funcao
    assert publicado[22] == 2906 and publicado[13] == 2663 and publicado[None] == 2


def test_empates_sem_vencedor_e_cor_neutra(indice):
    empates = {(m["uf"], m["cd_mun_tse"]) for m in indice if m["vencedor"] is None}
    assert empates == {("sp", "62448"), ("to", "73555")}
    for m in indice:
        if m["vencedor"] is None:
            assert m["cor_margem"] == NEUTRO_EMPATE_HEX
            assert m["margem_pp"] == 0


def test_resumo_do_painel_bate_com_a_funcao(vencedores):
    r = json.loads((WEB / "resumo_candidatos.json").read_text(encoding="utf-8"))
    funcao = Counter(int(v) for v in vencedores["nr_vencedor"].dropna())
    for nr, c in r["candidatos"].items():
        assert c["municipios_vencidos"] == funcao.get(int(nr), 0), nr
    assert len(r["empates"]) == 2
