"""Testes do cliente HTTP do TSE: rate limit, cache em disco e abort após 404s.

Sem dependência de `respx`/`pytest-asyncio`: o transporte HTTP é substituído por
um stub (monkeypatch em `TseClient._cliente.get`) e as corrotinas são
conduzidas com `asyncio.run` dentro de testes síncronos.
"""

from __future__ import annotations

import asyncio
import time
from itertools import pairwise

import httpx
import pytest

from eleicao import config
from eleicao.tse_client import (
    MAX_404_ANTES_DE_ABORTAR,
    TseAbortadoPor404Error,
    TseArquivoNaoEncontradoError,
    TseClient,
    _LimitadorTaxaGlobal,
)


def test_limitador_taxa_nao_excede_limite_global():
    """N requisições concorrentes não podem começar mais rápido que 1/max_por_segundo."""
    max_por_segundo = 20.0  # intervalo mínimo de 50ms; mais rápido só pra não pesar o teste
    limitador = _LimitadorTaxaGlobal(max_por_segundo=max_por_segundo)
    n = 6
    timestamps: list[float] = []

    async def tarefa() -> None:
        await limitador.aguardar()
        timestamps.append(time.monotonic())

    async def main() -> None:
        await asyncio.gather(*(tarefa() for _ in range(n)))

    asyncio.run(main())

    timestamps.sort()
    intervalo_min = 1.0 / max_por_segundo
    for anterior, atual in pairwise(timestamps):
        # tolerância pequena para jitter do event loop
        assert atual - anterior >= intervalo_min - 0.01

    duracao_total = timestamps[-1] - timestamps[0]
    assert duracao_total >= (n - 1) * intervalo_min - 0.02


class _RespostaFalsa:
    """Stub mínimo de httpx.Response para os testes de cache/404."""

    def __init__(self, status_code: int, content: bytes = b"{}") -> None:
        self.status_code = status_code
        self.content = content

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://exemplo.invalido/x")
            resposta = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("erro", request=request, response=resposta)


def test_cache_evita_segunda_requisicao(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_RAW", tmp_path)

    chamadas = {"n": 0}

    async def get_fake(caminho: str, *args: object, **kwargs: object) -> _RespostaFalsa:
        chamadas["n"] += 1
        return _RespostaFalsa(200, content=b'{"ok": true}')

    async def main() -> None:
        async with TseClient() as cliente:
            monkeypatch.setattr(cliente._cliente, "get", get_fake)
            caminho = "/oficial/ele2026/6257/dados/br/br-c0001-e006257-u.json"

            destino1 = await cliente.baixar(caminho)
            assert destino1.exists()
            assert destino1.read_bytes() == b'{"ok": true}'
            assert chamadas["n"] == 1

            # segunda chamada: arquivo já existe em disco -> não deve requisitar de novo
            destino2 = await cliente.baixar(caminho)
            assert destino2 == destino1
            assert chamadas["n"] == 1

    asyncio.run(main())


def test_force_ignora_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_RAW", tmp_path)

    chamadas = {"n": 0}

    async def get_fake(caminho: str, *args: object, **kwargs: object) -> _RespostaFalsa:
        chamadas["n"] += 1
        return _RespostaFalsa(200, content=b"{}")

    async def main() -> None:
        async with TseClient() as cliente:
            monkeypatch.setattr(cliente._cliente, "get", get_fake)
            caminho = "/oficial/ele2026/6257/dados/br/br-c0001-e006257-u.json"
            await cliente.baixar(caminho)
            await cliente.baixar(caminho, force=True)
            assert chamadas["n"] == 2

    asyncio.run(main())


def test_404_individual_nao_e_retentado_e_e_logado(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_RAW", tmp_path)

    chamadas = {"n": 0}

    async def get_404(caminho: str, *args: object, **kwargs: object) -> _RespostaFalsa:
        chamadas["n"] += 1
        return _RespostaFalsa(404)

    async def main() -> None:
        async with TseClient() as cliente:
            monkeypatch.setattr(cliente._cliente, "get", get_404)
            with pytest.raises(TseArquivoNaoEncontradoError):
                await cliente.baixar("/oficial/ele2026/6257/dados/zz/zz99999-c0001-e006257-u.json")

    asyncio.run(main())
    # sem retry: exatamente 1 requisição para o 404
    assert chamadas["n"] == 1


def test_aborta_apos_mais_de_5_404s(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_RAW", tmp_path)

    async def get_404(caminho: str, *args: object, **kwargs: object) -> _RespostaFalsa:
        return _RespostaFalsa(404)

    async def main() -> None:
        async with TseClient() as cliente:
            monkeypatch.setattr(cliente._cliente, "get", get_404)
            caminho = "/oficial/ele2026/6257/dados/zz/zz00000-c0001-e006257-u.json"

            # as primeiras MAX_404_ANTES_DE_ABORTAR chamadas devem só logar/contar
            for _ in range(MAX_404_ANTES_DE_ABORTAR):
                with pytest.raises(TseArquivoNaoEncontradoError):
                    await cliente.baixar(caminho, force=True)

            # a próxima (6ª) deve abortar a execução inteira
            with pytest.raises(TseAbortadoPor404Error):
                await cliente.baixar(caminho, force=True)

            assert cliente.contagem_404 == MAX_404_ANTES_DE_ABORTAR + 1

    asyncio.run(main())
