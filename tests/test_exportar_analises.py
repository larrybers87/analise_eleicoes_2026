"""Consistência da página de análises (D-030).

1. Cada número de `web/data/analises.json` (texto já formatado, o que a página mostra)
   aparece, como número, na seção do achado de origem em `docs/ANALISES.md`. É o teste
   "os números do site batem com o ANALISES.md": se o TSE mudar o dado (reexport) ou alguém
   mudar o .md, ele aponta a chave que divergiu.
2. `web/analises.html` não tem número digitado (só os anos de referência 2022, 2023 e 2026) e
   só referencia chaves que existem no JSON.

Pula se `web/data/analises.json` ainda não foi gerado (`python scripts/exportar_analises.py`).
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser

import pytest

from eleicao import config
from eleicao.analise import site

ARQ = config.RAIZ / "web" / "data" / "analises.json"
HTML = config.RAIZ / "web" / "analises.html"
MD = config.RAIZ / "docs" / "ANALISES.md"
ANOS_PERMITIDOS = {"2022", "2023", "2026"}  # anos de referência: eleições e PIB do IBGE

pytestmark = pytest.mark.skipif(not ARQ.exists(), reason="rode scripts/exportar_analises.py")


@pytest.fixture(scope="module")
def analises() -> dict:
    return json.loads(ARQ.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def secoes_md() -> dict[int, str]:
    """{nº do achado: texto da seção}. 0 = tudo antes do achado 1 (título + escopo)."""
    texto = MD.read_text(encoding="utf-8")
    partes = re.split(r"^## (\d+)\.", texto, flags=re.M)
    secoes = {0: partes[0]}
    for i in range(1, len(partes), 2):
        secoes[int(partes[i])] = partes[i + 1]
    return secoes


def _aparece(numero: str, texto: str) -> bool:
    """`numero` aparece como número inteiro no texto (não como pedaço de outro número)."""
    return re.search(rf"(?<![\d,.]){re.escape(numero)}(?![\d])", texto) is not None


def test_chaves_do_json_sao_exatamente_as_da_spec(analises):
    esperadas = {c.chave for c in site.CHAVES}
    assert set(analises["valores"]) == esperadas
    assert set(analises["textos"]) == esperadas
    assert analises["achado_de"] == {c.chave: c.achado for c in site.CHAVES}


def test_textos_sao_a_formatacao_dos_valores(analises):
    for c in site.CHAVES:
        assert analises["textos"][c.chave] == site.formatar(
            analises["valores"][c.chave], c.casas, c.tipo
        ), c.chave


@pytest.mark.parametrize("chave", [c for c in site.CHAVES], ids=lambda c: c.chave)
def test_numero_do_site_bate_com_o_achado_no_analises_md(chave, analises, secoes_md):
    texto = analises["textos"][chave.chave]
    numero = site.nucleo(texto, chave.tipo)
    secao = secoes_md[chave.achado]
    assert _aparece(numero, secao), (
        f"{chave.chave} = {texto!r} não aparece no achado {chave.achado} de docs/ANALISES.md"
    )


def test_numeros_pedidos_explicitamente(analises):
    t = analises["textos"]
    assert t["s1.pl.n_municipios"] == "2.906"
    assert t["s1.pt.n_municipios"] == "2.663"
    assert t["geral.empates"] == "2"
    assert t["s2.br.delta_margem"].endswith("p.p.")


def test_delta_margem_e_diferenca_dos_swings(analises):
    v = analises["valores"]
    assert v["s2.br.delta_margem"] == pytest.approx(v["s2.br.pl"] - v["s2.br.pt"])


def test_status_provisorio_segue_tf_judicial(analises):
    s = analises["snapshot"]
    assert s["provisorio"] is (s["tf_judicial"] != "s")


def test_formatar_ptbr():
    assert site.formatar(-3.278, 1, "pp") == "−3,3 p.p."
    assert site.formatar(7.113, 1, "pp") == "+7,1 p.p."
    assert site.formatar(-0.04, 1, "pp") == "0,0 p.p."  # sem "−0,0"
    assert site.formatar(2906, 0, "int") == "2.906"
    assert site.formatar(52.17, 1, "pct") == "52,2%"
    assert site.formatar(0.2312, 0, "pct100") == "23%"
    assert site.formatar(5.63, 1, "x") == "5,6×"


# ------------------------------------------------------------------- HTML


class _Texto(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.pedacos: list[str] = []
        self.chaves: list[str] = []
        self._ignorar = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._ignorar += 1
        for nome, valor in attrs:
            if nome == "data-v":
                self.chaves.append(valor)

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._ignorar -= 1

    def handle_data(self, data):
        if not self._ignorar:
            self.pedacos.append(data)


@pytest.fixture(scope="module")
def html() -> _Texto:
    p = _Texto()
    p.feed(HTML.read_text(encoding="utf-8"))
    return p


def test_html_nao_tem_numero_digitado(html):
    texto = " ".join(html.pedacos)
    numeros = set(re.findall(r"\d+(?:[.,]\d+)*", texto))
    assert numeros <= ANOS_PERMITIDOS, (
        f"números digitados no HTML: {sorted(numeros - ANOS_PERMITIDOS)}"
    )


def test_html_so_usa_chaves_existentes(html, analises):
    assert html.chaves, "a página não usa nenhum data-v"
    desconhecidas = set(html.chaves) - set(analises["textos"])
    assert not desconhecidas, f"data-v sem valor no JSON: {sorted(desconhecidas)}"
