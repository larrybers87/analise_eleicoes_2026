"""Aba "2º turno: projeção" (D-036, D-037): JSON, HTML sem números e trava por lista fechada.

1. `web/data/projecao_backtest.json` tem as chaves esperadas, as 27 UFs e erros que batem
   com `data/interim/projecao_t2/backtest_*.csv` (pula se o interim não existir: ele não é
   versionado e sai de `scripts/backtest_2018_2022.py`).
2. `web/projecao.html` não tem número digitado (só anos e ordinais de turno) e só usa
   chaves que existem no JSON (`data-v` no backtest, `data-p` no bloco 2026).
3. O exportador lê arquivos de 2026 só por lista fechada e só com `--publicar-projecao-2026`;
   sem a flag, `projecao_2026` é null e nada de 2026 é lido.
4. O bloco publicado (placar, faixas, veredito, cenários, 27 UFs) bate com os parquet da
   projeção, e a regra do veredito (D-034 item 4) vale dentro e fora da faixa.
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
PROC = config.RAIZ / "data" / "processed"
ARQ = config.RAIZ / "web" / "data" / "projecao_backtest.json"
HTML = config.RAIZ / "web" / "projecao.html"
SCRIPT = config.RAIZ / "scripts" / "exportar_projecao_web.py"
ANOS_PERMITIDOS = {"2018", "2022", "2026"}
MODELOS_TABELA = ["regter_nac", "base_nac", "regter_uf", "baseline_a", "baseline_b"]
MODELOS_MAPA = ["regter_nac", "base_nac", "baseline_a", "baseline_b"]
PERMITIDOS_2026 = {
    "data/processed/projecao_t2_2026_br.parquet",
    "data/processed/projecao_t2_2026_uf.parquet",
}

sem_interim = pytest.mark.skipif(
    not (INTERIM / "backtest_resumo.csv").exists(),
    reason="data/interim/projecao_t2 ausente (rode scripts/backtest_2018_2022.py)",
)
sem_json = pytest.mark.skipif(not ARQ.exists(), reason="rode scripts/exportar_projecao_web.py")
sem_projecao = pytest.mark.skipif(
    not (PROC / "projecao_t2_2026_br.parquet").exists(),
    reason="parquet da projeção 2026 ausente (scripts/projetar_t2_2026.py)",
)


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
        "projecao_2026",
        "comparacao_t2",
    } <= set(dados)
    assert dados["modelo_referencia"] == "regter_nac"
    assert [m["id"] for m in dados["tabela"]] == MODELOS_TABELA
    assert [m["id"] for m in dados["modelos_mapa"]] == MODELOS_MAPA
    assert set(dados["valores"]) == set(dados["textos"])
    assert dados["comparacao_t2"] is None  # estrutura reservada para o pós-T2


@sem_json
def test_mapa_tem_27_ufs_sem_exterior(dados):
    for mid in MODELOS_MAPA:
        ufs = set(dados["mapa"][mid])
        assert len(ufs) == 27 and "zz" not in ufs, mid
        for d in dados["mapa"][mid].values():
            assert re.fullmatch(r"#[0-9a-f]{6}", d["cor"])


@sem_json
def test_fontes_de_2026_so_da_lista_fechada(dados):
    assert dados["fontes"]
    for f in dados["fontes"]:
        assert "2026" not in f or f in PERMITIDOS_2026, f


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
    """Texto visível (fora de <script>/<style>) e chaves `data-v`/`data-p` do HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.pedacos: list[str] = []
        self.chaves: list[str] = []
        self.chaves_p: list[str] = []
        self._ignorar = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._ignorar += 1
        self.chaves += [v for k, v in attrs if k == "data-v"]
        self.chaves_p += [v for k, v in attrs if k == "data-p"]

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


@sem_json
def test_html_bloco_2026_so_usa_chaves_existentes(html, dados):
    assert html.chaves_p, "o bloco da projeção 2026 não usa nenhum data-p"
    if dados["projecao_2026"] is None:
        pytest.skip("JSON gerado sem --publicar-projecao-2026")
    desconhecidas = set(html.chaves_p) - set(dados["projecao_2026"]["textos"])
    assert not desconhecidas, sorted(desconhecidas)


# ------------------------------------------------- trava: lista fechada + flag


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
        "data/processed/projecao_t2_2026_uf.parquet",
        "data/interim/projecao_t2/projecao_t2_2026_linhas_compostas.csv",
        "data/interim/projecao_t2/METODO_secao7_resultados.md",
        "data/processed/presidente_t1_municipio.parquet_2026",
    ],
)
def test_sem_flag_todo_caminho_de_2026_aborta(exportador, nome):
    with pytest.raises(SystemExit, match="ABORTADO"):
        exportador.checar_caminho(config.RAIZ / nome)


@pytest.mark.parametrize(
    "nome",
    [
        "data/processed/projecao_t2_2026_municipio.parquet",
        "data/processed/projecao_t2_2026_linhas_compostas.csv",
        "data/processed/projecao_t2_2026_sem_par.csv",
        "data/interim/projecao_t2/projecao_t2_2026_linhas_compostas.csv",
        "data/interim/projecao_t2/METODO_secao7_resultados.md",
    ],
)
def test_com_flag_fora_da_lista_fechada_aborta(exportador, nome):
    with pytest.raises(SystemExit, match="ABORTADO"):
        exportador.checar_caminho(config.RAIZ / nome, publicar=True)


def test_lista_fechada_e_exatamente_br_e_uf(exportador):
    nomes = {p.relative_to(config.RAIZ).as_posix() for p in exportador.PERMITIDOS_COM_FLAG}
    assert nomes == PERMITIDOS_2026


def test_leitura_sem_flag_nao_tem_2026(exportador):
    lidos = [
        *exportador.CSV_BACKTEST.values(),
        *exportador.TOTAIS.values(),
        exportador.CAND_2022_T2,
    ]
    for p in lidos:
        assert "2026" not in p.relative_to(config.RAIZ).as_posix(), p


@sem_interim
def test_sem_flag_projecao_null_e_nada_de_2026_lido(exportador):
    dados, lidos = exportador.gerar(publicar=False)
    assert dados["projecao_2026"] is None
    assert dados["comparacao_t2"] is None
    assert lidos and not any("2026" in p.relative_to(config.RAIZ).as_posix() for p in lidos)


# ------------------------------------------------- bloco da projeção 2026 (D-037)


@pytest.fixture(scope="module")
def publicado(exportador):
    if not (INTERIM / "backtest_resumo.csv").exists():
        pytest.skip("data/interim/projecao_t2 ausente")
    if not (PROC / "projecao_t2_2026_br.parquet").exists():
        pytest.skip("parquet da projeção 2026 ausente")
    return exportador.gerar(publicar=True)


@pytest.fixture(scope="module")
def parquet_proj():
    br = pd.read_parquet(PROC / "projecao_t2_2026_br.parquet")
    uf = pd.read_parquet(PROC / "projecao_t2_2026_uf.parquet")
    return br, uf


@sem_projecao
def test_com_flag_bloco_preenchido_e_so_br_uf_de_2026(publicado):
    dados, lidos = publicado
    assert dados["projecao_2026"] is not None
    de_2026 = {
        p.relative_to(config.RAIZ).as_posix()
        for p in lidos
        if "2026" in p.relative_to(config.RAIZ).as_posix()
    }
    assert de_2026 == PERMITIDOS_2026


@sem_json
@sem_projecao
def test_json_publicado_igual_ao_gerado(dados, publicado):
    """O web/data versionado foi gerado COM a flag e está em dia com os parquet."""
    assert dados["projecao_2026"] == publicado[0]["projecao_2026"]


@sem_projecao
def test_placar_faixas_e_veredito_batem_com_o_parquet(publicado, parquet_proj):
    from eleicao.projecao_t2 import veredito

    q = publicado[0]["projecao_2026"]
    br, _ = parquet_proj
    b = br[(br["cenario"] == "base") & (br["recorte"] == "total_oficial_com_zz")].iloc[0]
    pl, pt, f = b["pct_pl_validos"], b["pct_pt_validos"], b["faixa_pl_pp"]
    assert q["recorte_placar"] == "total_oficial_com_zz"
    assert q["placar"]["pct_pl"] == pytest.approx(pl, abs=1e-4)
    assert q["placar"]["pct_pt"] == pytest.approx(pt, abs=1e-4)
    assert q["placar"]["faixa_pl"] == pytest.approx([pl - f, pl + f], abs=1e-4)
    assert q["placar"]["faixa_pt"] == pytest.approx([pt - f, pt + f], abs=1e-4)
    assert q["placar"]["veredito"] == veredito(pl, f) == b["veredito"]
    t = q["textos"]
    pl_txt, pt_txt = formatar(pl, 1, "pct"), formatar(pt, 1, "pct")
    assert t["placar"] == f"Flávio Bolsonaro {pl_txt} × Lula {pt_txt} dos válidos"
    if abs(pl - 50) <= f:
        frase = "o método não distingue vencedor"
    else:
        frase = "vencedor projetado: " + ("Flávio Bolsonaro" if pl > 50 else "Lula")
    assert t["veredito"].endswith(frase)
    assert t["faixas"] == (
        f"PL {formatar(pl - f, 1, 'pct')}–{formatar(pl + f, 1, 'pct')}, "
        f"PT {formatar(pt - f, 1, 'pct')}–{formatar(pt + f, 1, 'pct')}"
    )


@sem_projecao
def test_cenarios_principais_batem_com_o_parquet(publicado, parquet_proj):
    q = publicado[0]["projecao_2026"]
    br, _ = parquet_proj
    tot = br[br["recorte"] == "total_oficial_com_zz"].set_index("cenario")["pct_pl_validos"]
    ids = ["base", "desmob_2018", "analogos", "analogos_desmob_2018"]
    assert [c["id"] for c in q["cenarios"]] == ids
    for c in q["cenarios"]:
        assert c["pct_pl"] == pytest.approx(tot[c["id"]], abs=1e-4)
    e = q["eixo_mobilizacao"]
    assert e["delta_pl_base_pp"] == pytest.approx(tot["desmob_2018"] - tot["base"], abs=1e-4)
    assert e["delta_pl_analogos_pp"] == pytest.approx(
        tot["analogos_desmob_2018"] - tot["analogos"], abs=1e-4
    )
    vals = [tot[i] for i in ids]
    esperado = f"{formatar(min(vals), 1, 'pct')} e {formatar(max(vals), 1, 'pct')}"
    assert q["textos"]["cenarios_faixa"] == esperado


@sem_projecao
def test_27_ufs_e_exterior_batem_com_o_parquet(publicado, parquet_proj):
    from eleicao.cores import NEUTRO_EMPATE_HEX, carregar_paleta
    from eleicao.projecao_t2 import veredito

    q = publicado[0]["projecao_2026"]
    _, uf = parquet_proj
    base = uf[uf["cenario"] == "base"].set_index("uf")
    paleta = carregar_paleta()
    cor = {"PL": paleta[22], "PT": paleta[13], "indistinguivel": NEUTRO_EMPATE_HEX}
    assert len(q["ufs"]) == 27 and "zz" not in q["ufs"]
    contagem = {"PL": 0, "PT": 0, "indistinguivel": 0}
    for sigla, d in q["ufs"].items():
        r = base.loc[sigla]
        v = veredito(r["pct_pl_validos"], r["faixa_pp"])
        assert d["pct_pl"] == pytest.approx(r["pct_pl_validos"], abs=1e-4), sigla
        assert d["veredito"] == v == r["veredito"], sigla
        assert d["cor"] == cor[v], sigla
        contagem[v] += 1
    assert q["contagem_ufs"] == contagem
    assert q["exterior"]["pct_pl"] == pytest.approx(base.loc["zz", "pct_pl_validos"], abs=1e-4)


@sem_projecao
def test_snapshot_do_t1_e_data_do_commit(publicado, parquet_proj):
    q = publicado[0]["projecao_2026"]
    br, _ = parquet_proj
    assert q["t1"]["idg"] == str(br["t1_idg"].iloc[0])
    assert q["t1"]["and"] == "f" and q["t1"]["tf"] == "s"
    assert re.fullmatch(r"[0-9a-f]{40}", q["commit"]["hash"])
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}", q["commit"]["data_iso"]
    )
    assert q["commit"]["url"].endswith(q["commit"]["hash"])


@pytest.mark.parametrize(
    ("pct_pl", "faixa", "codigo", "trecho"),
    [
        (51.9, 2.0, "indistinguivel", "o método não distingue vencedor"),
        (52.0, 2.0, "indistinguivel", "o método não distingue vencedor"),  # borda: ≤
        (48.0, 2.0, "indistinguivel", "o método não distingue vencedor"),
        (52.01, 2.0, "PL", "vencedor projetado: Flávio Bolsonaro"),
        (47.5, 2.0, "PT", "vencedor projetado: Lula"),
        (52.5, 2.5, "indistinguivel", "o método não distingue vencedor"),  # borda da UF
        (53.0, 2.0, "PL", "vencedor projetado: Flávio Bolsonaro"),
    ],
)
def test_regra_do_veredito(pct_pl, faixa, codigo, trecho):
    from eleicao.projecao_web import frase_veredito

    assert frase_veredito(pct_pl, faixa) == (codigo, trecho)
