"""Testes de invariantes das 3 fontes de enriquecimento (F3, ver docs/DADOS.md):

1. Presidente 2022 (Dados Abertos TSE) — `presidente_2022_t<turno>_municipio*.parquet`
2. Perfil do eleitorado 2026 (Dados Abertos TSE) — `eleitorado_perfil_2026_municipio.parquet`
3. IBGE (população Censo 2022 + PIB per capita) — `ibge_municipio.parquet`

Mesma regra do `tests/test_invariantes.py`: divergência real não é escondida
dentro do teste — é documentada em `docs/DADOS.md` (Armadilhas) e o teste
verifica que ela continua sendo exatamente a esperada (nem mais, nem menos).
Todos os testes são pulados automaticamente se o Parquet correspondente
ainda não existir (rode os scripts `scripts/processar_*.py` antes).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from eleicao import config

# --------------------------------------------------------------------------
# 1. Presidente 2022
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cand_2022_t1() -> pd.DataFrame:
    return pd.read_parquet(config.DATA_PROCESSED / "presidente_2022_t1_municipio.parquet")


@pytest.fixture(scope="module")
def tot_2022_t1() -> pd.DataFrame:
    return pd.read_parquet(config.DATA_PROCESSED / "presidente_2022_t1_municipio_totais.parquet")


@pytest.fixture(scope="module")
def cand_2022_t2() -> pd.DataFrame:
    return pd.read_parquet(config.DATA_PROCESSED / "presidente_2022_t2_municipio.parquet")


@pytest.fixture(scope="module")
def config_municipios_2026() -> dict:
    caminho = config.caminho_local(config.caminho_config_municipios(config.ELEICAO_FEDERAL_T1))
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


@pytest.mark.skipif(
    not (config.DATA_PROCESSED / "presidente_2022_t1_municipio_totais.parquet").exists(),
    reason=(
        "presidente_2022_t1_municipio*.parquet não gerado — "
        "rode scripts/processar_presidente_2022.py"
    ),
)
class TestPresidente2022:
    def test_soma_nacional_lula_bolsonaro_1o_turno_bate_com_referencia(self, cand_2022_t1):
        """Números de referência (usuário, conferidos contra o próprio arquivo baixado).

        Lula 57.259.504 / Bolsonaro 51.072.345 — EXATO, sem tolerância: são
        o resultado oficial do 1º turno de 2022, já consolidado (`tf`
        judicial encerrado há anos), não uma totalização em andamento como
        em 2026.
        """
        soma = cand_2022_t1.groupby("nr_candidato")["votos"].sum()
        assert int(soma.loc[13]) == 57_259_504, "Lula (13) não bate com a referência"
        assert int(soma.loc[22]) == 51_072_345, "Bolsonaro (22) não bate com a referência"

    def test_soma_nacional_2o_turno_bate_com_referencia_publica(self, cand_2022_t2):
        """2º turno 2022: Lula 60.345.999 / Bolsonaro 58.206.354 (resultado oficial)."""
        soma = cand_2022_t2.groupby("nr_candidato")["votos"].sum()
        assert int(soma.loc[13]) == 60_345_999
        assert int(soma.loc[22]) == 58_206_354

    def test_soma_votos_candidatos_por_municipio_igual_validos(self, cand_2022_t1, tot_2022_t1):
        """Soma de `votos` de todos os candidatos no município == `validos` do município.

        Vale porque, no arquivo de 2022, 100% das linhas têm
        `NM_TIPO_DESTINACAO_VOTOS == "Válido"` (sem voto anulado/sub judice
        na amostra de Presidente — diferente de 2026, onde o campo existe
        mas também é 0 em toda a amostra até 05/10/2026).
        """
        soma = cand_2022_t1.groupby(["uf", "cd_mun_tse"])["votos"].sum()
        comparacao = tot_2022_t1.set_index(["uf", "cd_mun_tse"])["validos"].sort_index()
        soma = soma.sort_index()
        pd.testing.assert_series_equal(soma, comparacao, check_names=False)

    def test_validos_mais_brancos_mais_nulos_mais_anulados_igual_comparecimento(self, tot_2022_t1):
        diferenca = (
            tot_2022_t1["validos"]
            + tot_2022_t1["brancos"]
            + tot_2022_t1["nulos_tvn"]
            + tot_2022_t1["anulados"]
            + tot_2022_t1["anulados_sub_judice"]
            - tot_2022_t1["comparecimento"]
        )
        assert (diferenca == 0).all()

    def test_comparecimento_mais_abstencao_quase_sempre_igual_eleitorado(self, tot_2022_t1):
        """42 municípios divergem (todos no exterior salvo Manaus) — ver docs/DADOS.md.

        Mesmo padrão documentado para 2026 (`extra_e_esi` != `eleitorado`
        quando há seção não instalada): postos no exterior sem seção
        instalada têm `comparecimento=abstencao=0` mas `eleitorado>0`. O
        arquivo de 2022 não traz os campos `esni`/`esnt` que permitiriam o
        invariante exato (como em 2026) — por isso este teste só garante que
        a divergência continua restrita ao conjunto já investigado e que a
        soma nacional residual é pequena, em vez de recalcular a condição
        exata.
        """
        diferenca = (
            tot_2022_t1["comparecimento"] + tot_2022_t1["abstencao"] - tot_2022_t1["eleitorado"]
        )
        divergentes = tot_2022_t1[diferenca != 0]
        assert len(divergentes) == 42, (
            f"número de municípios divergentes mudou ({len(divergentes)} != 42) — "
            "revisar docs/DADOS.md (Armadilhas, Presidente 2022)"
        )
        assert int(diferenca.sum()) == -657
        # todos exceto Manaus (AM 02550) são do exterior sem seção instalada
        # (comparecimento==abstencao==0, eleitorado>0)
        nao_manaus = divergentes[
            ~((divergentes["uf"] == "am") & (divergentes["cd_mun_tse"] == "02550"))
        ]
        assert (nao_manaus["uf"] == "zz").all()
        assert (nao_manaus["comparecimento"] == 0).all()
        assert (nao_manaus["abstencao"] == 0).all()

    def test_join_com_config_2026_tem_so_as_divergencias_catalogadas(
        self, tot_2022_t1, config_municipios_2026
    ):
        """Município criado/extinto entre as duas eleições — investigado manualmente.

        - Só em 2022: `zz99252` (VATICANO) — posto consular fechado até 2026.
        - Só em 2026: `mt73709` (BOA ESPERANÇA DO NORTE) — município novo,
          emancipado depois de 2022; e 6 postos consulares novos no exterior
          (`zz29629` DACCA, `zz99279` STA. ELENA DE UAIRÉN, `zz99295`
          PYONGYANG, `zz99490` ORLANDO, `zz99503` EDIMBURGO, `zz99511`
          MARSELHA).
        """
        municipios_2022 = {
            f"{uf}{cd}" for uf, cd in zip(tot_2022_t1["uf"], tot_2022_t1["cd_mun_tse"], strict=True)
        }
        municipios_2026 = {
            f"{abrangencia['cd']}{m['cd']}"
            for abrangencia in config_municipios_2026["abr"]
            for m in abrangencia["mu"]
        }
        so_2022 = municipios_2022 - municipios_2026
        so_2026 = municipios_2026 - municipios_2022
        assert so_2022 == {"zz99252"}
        assert so_2026 == {
            "mt73709",
            "zz29629",
            "zz99279",
            "zz99295",
            "zz99490",
            "zz99503",
            "zz99511",
        }


# --------------------------------------------------------------------------
# 2. Perfil do eleitorado 2026
# --------------------------------------------------------------------------


@pytest.mark.skipif(
    not (config.DATA_PROCESSED / "eleitorado_perfil_2026_municipio.parquet").exists(),
    reason=(
        "eleitorado_perfil_2026_municipio.parquet não gerado — rode scripts/processar_eleitorado.py"
    ),
)
class TestEleitoradoPerfil2026:
    @pytest.fixture(scope="class")
    @classmethod
    def perfil(cls) -> pd.DataFrame:
        return pd.read_parquet(config.DATA_PROCESSED / "eleitorado_perfil_2026_municipio.parquet")

    def test_uma_linha_por_municipio_do_config(self, perfil, config_municipios_2026):
        chaves_perfil = {
            f"{uf}{cd}" for uf, cd in zip(perfil["uf"], perfil["cd_mun_tse"], strict=True)
        }
        chaves_config = {
            f"{abrangencia['cd']}{m['cd']}"
            for abrangencia in config_municipios_2026["abr"]
            for m in abrangencia["mu"]
        }
        faltando = chaves_config - chaves_perfil
        sobrando = chaves_perfil - chaves_config
        assert not faltando, f"{len(faltando)} município(s) do config sem linha no perfil"
        assert not sobrando, f"{len(sobrando)} chave(s) no perfil sem município no config"

    def test_percentuais_por_sexo_somam_100(self, perfil):
        colunas = [c for c in perfil.columns if c.startswith("pct_sexo_")]
        soma = perfil[colunas].sum(axis=1)
        # tolerância de arredondamento (4 casas decimais por categoria)
        assert ((soma - 100.0).abs() < 0.01).all()

    def test_percentuais_por_faixa_etaria_somam_100(self, perfil):
        """`pct_faixa_<slug>` é uma PARTIÇÃO — exclui as 2 colunas derivadas (`*_facultativa_*`)."""
        colunas = [
            c for c in perfil.columns if c.startswith("pct_faixa_") and "facultativa" not in c
        ]
        soma = perfil[colunas].sum(axis=1)
        assert ((soma - 100.0).abs() < 0.01).all()

    def test_percentuais_por_grau_instrucao_somam_100(self, perfil):
        colunas = [c for c in perfil.columns if c.startswith("pct_grau_")]
        soma = perfil[colunas].sum(axis=1)
        assert ((soma - 100.0).abs() < 0.01).all()

    def test_faixas_facultativas_16_17_e_70_mais_presentes(self, perfil):
        """Voto facultativo: colunas dedicadas (não são bins nativos do TSE, ver docs/DADOS.md)."""
        assert "pct_faixa_facultativa_16_17" in perfil.columns
        assert "pct_faixa_facultativa_70_mais" in perfil.columns
        assert (perfil["pct_faixa_facultativa_16_17"] >= 0).all()
        assert (perfil["pct_faixa_facultativa_70_mais"] >= 0).all()

    def test_total_nacional_perto_do_eleitorado_oficial_ea20(self, perfil):
        """158.745.463 (perfil, gerado 14/07/2026) vs 158.745.502 (EA20 BR, 05/10/2026) — dif. 39.

        Duas fontes/gerações distintas do TSE (perfil do eleitorado é um
        corte do cadastro antes da eleição; EA20 é o resultado do dia da
        votação) — não precisam bater exatamente, mas a proximidade (<0,001%)
        é uma boa conferência cruzada. Só roda se o Parquet de 2026 do F1/F2
        já existir (não é um pré-requisito desta tarefa).
        """
        caminho_br = config.DATA_PROCESSED / "presidente_t1_br_totais.parquet"
        if not caminho_br.exists():
            pytest.skip("presidente_t1_br_totais.parquet não disponível")
        br = pd.read_parquet(caminho_br)
        eleitorado_ea20 = int(br["eleitorado"].iloc[0])
        total_perfil = int(perfil["total"].sum())
        diferenca = abs(eleitorado_ea20 - total_perfil)
        assert diferenca < 1000, (
            f"diferença entre perfil ({total_perfil}) e EA20 BR ({eleitorado_ea20}) "
            f"cresceu para {diferenca} — investigar"
        )


# --------------------------------------------------------------------------
# 3. IBGE (população Censo 2022 + PIB per capita)
# --------------------------------------------------------------------------


@pytest.mark.skipif(
    not (config.DATA_PROCESSED / "ibge_municipio.parquet").exists(),
    reason="ibge_municipio.parquet não gerado — rode scripts/processar_ibge.py",
)
class TestIbgeMunicipio:
    @pytest.fixture(scope="class")
    @classmethod
    def ibge(cls) -> pd.DataFrame:
        return pd.read_parquet(config.DATA_PROCESSED / "ibge_municipio.parquet")

    def test_5570_municipios_sem_duplicata(self, ibge):
        assert len(ibge) == 5570
        assert ibge["cd_mun_ibge"].is_unique

    def test_nenhum_municipio_sem_populacao_ou_pib(self, ibge):
        assert ibge["populacao_censo_2022"].notna().all()
        assert ibge["pib_per_capita_reais"].notna().all()
        assert ibge["pib_mil_reais"].notna().all()

    def test_populacao_total_bate_com_censo_2022(self, ibge):
        """203.080.756 — população residente total, Censo 2022 (1ª apuração), IBGE."""
        assert int(ibge["populacao_censo_2022"].sum()) == 203_080_756

    def test_pib_per_capita_positivo(self, ibge):
        assert (ibge["pib_per_capita_reais"] > 0).all()
