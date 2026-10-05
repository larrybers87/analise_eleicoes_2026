"""Rotina periódica: verifica se o TSE já atualizou os arquivos divergentes.

Rebaixa com `--force` SOMENTE o arquivo BR e os municípios/UFs listados em
`data/known_issues.csv` (extraídos dinamicamente do CSV — nunca hardcoded).
Compara a geração (`idg`/`dg`/`hg`) de cada um contra o que estava registrado
em `data/processed/snapshot_6257.json` (ou, na primeira verificação de um
item ainda não rastreado, contra a geração local atual antes do rebaixe).

Se algo mudou de geração:
  1. Reprocessa todos os Parquet (`scripts/processar_presidente.py`, via
     import — não subprocess, já expõe `main(eleicao)` reutilizável).
  2. Roda a suíte de testes (`pytest -q`).
  3. Atualiza `data/processed/snapshot_6257.json` com as novas gerações.
  4. Recalcula as divergências soma-município-vs-UF catalogadas em
     `data/known_issues.csv`; remove as linhas cuja divergência convergiu
     para 0 (reescreve o CSV).

Se nada mudou, só informa e termina — não rebaixa, reprocessa ou roda mais
nada (regra anti-bloqueio: minimizar requisições desnecessárias ao TSE).

Uso:
    python scripts/verificar_atualizacoes.py [--eleicao 6257]
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

RAIZ_PROJETO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ_PROJETO / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import coletar_presidente as coletor  # noqa: E402
import processar_presidente as processador  # noqa: E402

from eleicao import config  # noqa: E402

CAMINHO_KNOWN_ISSUES = config.RAIZ / "data" / "known_issues.csv"
CAMINHO_SNAPSHOT = config.DATA_PROCESSED / "snapshot_6257.json"

CAMPOS_TOTAIS = {"eleitorado", "comparecimento", "abstencao", "validos", "brancos", "nulos_tvn"}


def _carregar_known_issues() -> pd.DataFrame:
    if not CAMINHO_KNOWN_ISSUES.exists():
        return pd.DataFrame(columns=["uf", "cd_mun_tse", "campo", "diferenca"])
    return pd.read_csv(CAMINHO_KNOWN_ISSUES, dtype={"cd_mun_tse": "string"}, keep_default_na=False)


def _itens_a_verificar(known_issues: pd.DataFrame) -> list[tuple[str, str | None, str | None]]:
    """Monta a lista de itens a rebaixar: BR + UFs/municípios do known_issues.csv.

    Extraído dinamicamente das colunas `uf`/`cd_mun_tse` (pipe-separado) do
    CSV — nunca hardcoded aqui.
    """
    itens: set[tuple[str, str | None, str | None]] = {("br", None, None)}
    for uf, cd_mun_tse in zip(known_issues["uf"], known_issues["cd_mun_tse"], strict=True):
        if not uf:
            continue
        itens.add(("uf", uf, None))
        for codigo in str(cd_mun_tse).split("|"):
            codigo = codigo.strip()
            if codigo:
                itens.add(("mun", uf, codigo))
    return sorted(itens)


def _chave_item(tipo: str, uf: str | None, cd_mun: str | None) -> str:
    if tipo == "br":
        return "br"
    if tipo == "uf":
        return f"uf:{uf}"
    return f"mun:{uf}:{cd_mun}"


def _caminho_local_item(eleicao: int, tipo: str, uf: str | None, cd_mun: str | None) -> Path:
    if tipo == "br":
        caminho = config.caminho_resultado(eleicao, config.CARGO_PRESIDENTE, "br")
    elif tipo == "uf":
        caminho = config.caminho_resultado(eleicao, config.CARGO_PRESIDENTE, uf)
    else:
        caminho = config.caminho_resultado(eleicao, config.CARGO_PRESIDENTE, uf, cd_mun)
    return config.caminho_local(caminho)


def _ler_geracao(caminho_local: Path) -> dict | None:
    """Lê `idg`/`dg`/`hg`/`and` do JSON local, se existir."""
    if not caminho_local.exists():
        return None
    dado = json.loads(caminho_local.read_text(encoding="utf-8"))
    return {"idg": dado["idg"], "dg": dado["dg"], "hg": dado["hg"], "and": dado["and"]}


def _carregar_snapshot() -> dict:
    if not CAMINHO_SNAPSHOT.exists():
        raise FileNotFoundError(
            f"{CAMINHO_SNAPSHOT} não encontrado — rode a coleta completa e crie o snapshot "
            "antes de usar esta rotina de verificação."
        )
    return json.loads(CAMINHO_SNAPSHOT.read_text(encoding="utf-8"))


def _baseline_do_snapshot(snapshot: dict, chave: str) -> dict | None:
    if chave == "br":
        br = snapshot.get("br")
        if br:
            return {"idg": br["idg"], "dg": br["dg"], "hg": br["hg"], "and": br.get("and")}
        return None
    return snapshot.get("acompanhamento_known_issues", {}).get(chave)


def _recalcular_divergencias_por_uf() -> set[tuple[str, str, int]]:
    """Recalcula as divergências soma-município-vs-UF para TODAS as UFs (não só BA).

    Mesma lógica de `tests/test_invariantes.py`. Retorna o conjunto de
    `(uf, campo, diferenca)` ainda observado — usado para decidir quais
    linhas de `data/known_issues.csv` já convergiram (diferença virou 0,
    não aparece mais no conjunto retornado). Generalizado para qualquer UF
    porque o catálogo pode, no futuro, ter divergências em outros estados
    além de BA.
    """
    mun_totais = pd.read_parquet(config.DATA_PROCESSED / "presidente_t1_municipio_totais.parquet")
    uf_totais = pd.read_parquet(config.DATA_PROCESSED / "presidente_t1_uf_totais.parquet")
    mun_cand = pd.read_parquet(config.DATA_PROCESSED / "presidente_t1_municipio.parquet")
    uf_cand = pd.read_parquet(config.DATA_PROCESSED / "presidente_t1_uf.parquet")

    observadas: set[tuple[str, str, int]] = set()

    agregado = mun_totais.groupby("uf", as_index=False)[sorted(CAMPOS_TOTAIS)].sum()
    comparacao = agregado.merge(
        uf_totais[["uf", *sorted(CAMPOS_TOTAIS)]], on="uf", suffixes=("_soma", "_oficial")
    )
    for campo in sorted(CAMPOS_TOTAIS):
        dif = comparacao[f"{campo}_soma"] - comparacao[f"{campo}_oficial"]
        for uf, valor in zip(comparacao["uf"], dif, strict=True):
            if valor != 0:
                observadas.add((uf, campo, int(valor)))

    agregado_cand = mun_cand.groupby(["uf", "nr_candidato"], as_index=False)["votos"].sum()
    oficial_cand = uf_cand[["uf", "nr_candidato", "votos"]].rename(columns={"votos": "oficial"})
    comparacao_cand = agregado_cand.merge(oficial_cand, on=["uf", "nr_candidato"])
    comparacao_cand["diferenca"] = comparacao_cand["votos"] - comparacao_cand["oficial"]
    for row in comparacao_cand.itertuples():
        if row.diferenca != 0:
            observadas.add((row.uf, f"votos_candidato_{int(row.nr_candidato)}", int(row.diferenca)))

    return observadas


def main(eleicao: int) -> int:
    known_issues = _carregar_known_issues()
    if known_issues.empty:
        print("data/known_issues.csv está vazio — verificando só o arquivo BR.")

    # BR sempre é verificado, mesmo com o catálogo vazio (ver docstring do módulo);
    # _itens_a_verificar já inclui ("br", None, None) incondicionalmente.
    itens = _itens_a_verificar(known_issues)
    snapshot = _carregar_snapshot()

    gerado_antes: dict[str, dict | None] = {}
    for tipo, uf, cd_mun in itens:
        chave = _chave_item(tipo, uf, cd_mun)
        caminho = _caminho_local_item(eleicao, tipo, uf, cd_mun)
        atual_local = _ler_geracao(caminho)
        baseline = _baseline_do_snapshot(snapshot, chave) or atual_local
        gerado_antes[chave] = baseline

    apenas = ",".join(_chave_item(tipo, uf, cd_mun) for tipo, uf, cd_mun in itens)
    print(f"rebaixando com --force --apenas {apenas}")
    codigo = asyncio.run(coletor.main(eleicao, True, apenas))
    if codigo != 0:
        print("ERRO: coleta dirigida falhou — abortando verificação.", file=sys.stderr)
        return codigo

    mudou: dict[str, bool] = {}
    gerado_depois: dict[str, dict | None] = {}
    linhas_resumo = []
    for tipo, uf, cd_mun in itens:
        chave = _chave_item(tipo, uf, cd_mun)
        caminho = _caminho_local_item(eleicao, tipo, uf, cd_mun)
        depois = _ler_geracao(caminho)
        gerado_depois[chave] = depois
        antes = gerado_antes[chave]
        houve_mudanca = antes is None or depois is None or antes["idg"] != depois["idg"]
        mudou[chave] = houve_mudanca
        linhas_resumo.append(
            {
                "item": chave,
                "idg_antes": antes["idg"] if antes else None,
                "idg_depois": depois["idg"] if depois else None,
                "and_antes": antes["and"] if antes else None,
                "and_depois": depois["and"] if depois else None,
                "mudou": houve_mudanca,
            }
        )

    resumo_df = pd.DataFrame(linhas_resumo)
    print()
    print(resumo_df.to_string(index=False))
    print()

    if not any(mudou.values()):
        print("nenhuma geração mudou — nada a reprocessar.")
        return 0

    mudaram = [chave for chave, v in mudou.items() if v]
    print(f"{len(mudaram)} item(ns) com geração nova: {mudaram}")

    print("\nreprocessando Parquet...")
    codigo_proc = processador.main(eleicao)
    if codigo_proc != 0:
        print("ERRO: processar_presidente.main falhou.", file=sys.stderr)
        return codigo_proc

    print("\nrodando pytest -q...")
    resultado_pytest = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"], cwd=RAIZ_PROJETO, check=False
    )
    if resultado_pytest.returncode != 0:
        print(
            "AVISO: pytest -q terminou com falhas — revisar antes de confiar no snapshot "
            "atualizado (não abortamos a atualização do snapshot/CSV, mas o resultado "
            "merece atenção).",
            file=sys.stderr,
        )

    observadas = _recalcular_divergencias_por_uf()
    linhas_mantidas = []
    linhas_removidas = []
    for row in known_issues.itertuples():
        chave_divergencia = (row.uf, row.campo, int(row.diferenca))
        if chave_divergencia in observadas:
            linhas_mantidas.append(row.Index)
        else:
            linhas_removidas.append((row.uf, row.campo, row.diferenca))

    if linhas_removidas:
        print(f"\n{len(linhas_removidas)} divergência(s) catalogada(s) convergiram, removendo:")
        for uf, campo, diferenca in linhas_removidas:
            print(f"  uf={uf} campo={campo} diferenca_anterior={diferenca}")
        known_issues.loc[linhas_mantidas].to_csv(CAMINHO_KNOWN_ISSUES, index=False)
    else:
        print("\nnenhuma divergência catalogada convergiu — data/known_issues.csv mantido.")

    agora = datetime.now(UTC).astimezone().isoformat(timespec="seconds")
    snapshot.setdefault("acompanhamento_known_issues", {})
    for tipo, uf, cd_mun in itens:
        chave = _chave_item(tipo, uf, cd_mun)
        depois = gerado_depois[chave]
        if depois is None:
            continue
        if chave == "br":
            snapshot["br"].update(depois)
        else:
            snapshot["acompanhamento_known_issues"][chave] = depois
    snapshot["acompanhamento_known_issues"]["ultima_verificacao_em"] = agora
    CAMINHO_SNAPSHOT.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nsnapshot atualizado: {CAMINHO_SNAPSHOT}")

    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--eleicao", type=int, default=config.ELEICAO_FEDERAL_T1, help="código da eleição (TSE)"
    )
    args = parser.parse_args()
    sys.exit(main(args.eleicao))
