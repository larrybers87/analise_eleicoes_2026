"""Aba "2º turno: projeção" (D-036): JSON do backtest, HTML sem números e trava contra 2026.

1. `web/data/projecao_backtest.json` tem as chaves esperadas, as 27 UFs e erros que batem
   com `data/interim/projecao_t2/backtest_*.csv` (pula se o interim não existir: ele não é
   versionado e sai de `scripts/backtest_2018_2022.py`).
2. `web/projecao.html` não tem número digitado (só anos e ordinais de turno) e só usa
   chaves que existem no JSON.
3. O exportador recusa caminhos de 2026.
"""

from __future__ import annotations

import importlib.util
import json
import re
from html.parser import HTMLParser

import pandas as pd
import pytest

from eleicao import config
from eleicao.analise.site import formatar

INTERIM = config.RAIZ / "data" / "interim" / "projecao_t2"
ARQ = config.RAIZ / "web" / "data" / "projecao_backtest.json"
HTML = config.RAIZ / "web" / "projecao.html"
SCRIPT = config.RAIZ / "scripts" / "exportar_projecao_web.py"
ANOS_PERMITIDOS = {"2018", "2022", "2026"}
MODELOS_TABELA = ["regter_nac", "base_nac", "regter_uf", "baseline_a", "baseline_b"]
MODELOS_MAPA = ["regter_nac", "base_nac", "baseline_a", "baseline_b"]

sem_interim = pytest.mark.skipif(
    not (INTERIM / "backtest_resumo.csv").exists(),
    reason="data/interim/projecao_t2 ausente (rode scripts/backtest_2018_2022.py)",
)
sem_json = pytest.mark.skipif(not ARQ.exists(), reason="rode scripts/exportar_projecao_web.py")


@pytest.fixture(scope="module")
def dados() -> dict:
    return json.loads(ARQ.read_text(encoding="utf-8"))


@sem_json
def test_chaves_de_topo(dados):
    assert {
        "modelo_referencia",
        "tabela",
        "modelos_mapa",
        "mapa",
        "escala",
        "mobilizacao",
        "valores",
        "textos",
        "fontes",
    } <= set(dados)
    assert dados["modelo_referencia"] == "regter_nac"
    assert [m["id"] for m in dados["tabela"]] == MODELOS_TABELA
    assert [m["id"] for m in dados["modelos_mapa"]] == MODELOS_MAPA
    assert set(dados["valores"]) == set(dados["textos"])


@sem_json
def test_mapa_tem_27_ufs_sem_exterior(dados):
    for mid in MODELOS_MAPA:
        ufs = set(dados["mapa"][mid])
        assert len(ufs) == 27 and "zz" not in ufs, mid
        for d in dados["mapa"][mid].values():
            assert re.fullmatch(r"#[0-9a-f]{6}", d["cor"])


@sem_json
def test_nenhuma_fonte_e_de_2026(dados):
    assert dados["fontes"]
    for f in dados["fontes"]:
        assert "2026" not in f and "projecao_t2_2026" not in f, f


@sem_json
def test_textos_sao_a_formatacao_dos_valores(dados):
    for chave, texto in dados["textos"].items():
        v = dados["valores"][chave]
        opcoes = {formatar(v, c, tp) for c in (1, 2) for tp in ("pp", "pct", "dec")}
        assert texto in opcoes, (chave, texto)


@sem_json
@sem_interim
def test_erros_por_uf_batem_com_o_csv(dados):
    csv = pd.read_csv(INTERIM / "backtest_erros_uf.csv", dtype={"uf": str}).set_index("uf")
    assert len(csv) == 27
    for mid in MODELOS_MAPA:
        for uf, d in dados["mapa"][mid].items():
            assert d["erro_pp"] == pytest.approx(csv.loc[uf, mid], abs=1e-4), (mid, uf)


@sem_json
@sem_interim
def test_tabela_bate_com_o_resumo(dados):
    res = pd.read_csv(INTERIM / "backtest_resumo.csv").set_index("modelo")
    erros = pd.read_csv(INTERIM / "backtest_erros_uf.csv", dtype={"uf": str})
    for linha in dados["tabela"]:
        r = res.loc[linha["id"]]
        assert linha["erro_br_pp"] == pytest.approx(r["erro_br_pp"], abs=1e-4)
        assert linha["uf_media_abs_pp"] == pytest.approx(r["uf_media_abs"], abs=1e-4)
        assert linha["mae_municipal_pp"] == pytest.approx(r["mae_municipal_pp"], abs=1e-4)
        assert linha["erro_abst_br_pp"] == pytest.approx(r["erro_abst_br_pp"], abs=1e-4)
        assert linha["vencedor_uf_certos"] == round(r["acerto_vencedor_uf"] * 27)
        pior = erros.loc[erros[linha["id"]].abs().idxmax()]
        assert linha["pior_uf"] == pior["uf"]


@sem_json
@sem_interim
def test_valores_conhecidos_do_metodo(dados):
    """Números da seção 5 de docs/METODO_PROJECAO.md (backtest) e da seção 2 (mobilização)."""
    t = dados["textos"]
    assert t["ref.erro_br"] == "−0,06 p.p."
    assert t["blocos.erro_br"] == "−1,8 p.p."
    assert t["ablacao.linha_abst_abst"] == "+0,77 p.p."
    assert t["mob.2018.delta_abst"] == "+0,97 p.p."
    assert t["mob.2022.delta_abst"] == "−0,36 p.p."
    assert t["mob.2018.bn_t1"] == "7,0%"
    assert t["mob.2022.bn_t1"] == "3,5%"
    assert t["real_2022.pct_pl"] == "49,10%"


# ------------------------------------------------------------------- HTML


class _Texto(HTMLParser):
    """Texto visível (fora de <script>/<style>) e chaves `data-v` do HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.pedacos: list[str] = []
        self.chaves: list[str] = []
        self._ignorar = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._ignorar += 1
        self.chaves += [v for k, v in attrs if k == "data-v"]

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
    texto = re.sub(r"(?<!\d)[12]º", "", " ".join(html.pedacos))
    numeros = set(re.findall(r"\d+(?:[.,]\d+)*", texto))
    assert numeros <= ANOS_PERMITIDOS, f"números digitados: {sorted(numeros - ANOS_PERMITIDOS)}"


@sem_json
def test_html_so_usa_chaves_existentes(html, dados):
    assert html.chaves
    desconhecidas = set(html.chaves) - set(dados["textos"])
    assert not desconhecidas, sorted(desconhecidas)


# ------------------------------------------------------- trava contra 2026


@pytest.fixture(scope="module")
def exportador():
    spec = importlib.util.spec_from_file_location("exportar_projecao_web", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(
    "nome",
    [
        "data/processed/projecao_t2_2026_br.parquet",
        "data/interim/projecao_t2/projecao_t2_2026_linhas_compostas.csv",
        "data/interim/projecao_t2/METODO_secao7_resultados.md",
        "data/processed/presidente_t1_municipio.parquet_2026",
    ],
)
def test_exportador_aborta_em_caminho_de_2026(exportador, nome):
    with pytest.raises(SystemExit, match="ABORTADO"):
        exportador.checar_caminho(config.RAIZ / nome)


def test_exportador_so_le_arquivos_permitidos(exportador):
    lidos = [
        *exportador.CSV_BACKTEST.values(),
        *exportador.TOTAIS.values(),
        exportador.CAND_2022_T2,
    ]
    for p in lidos:
        assert "2026" not in p.relative_to(config.RAIZ).as_posix(), p
