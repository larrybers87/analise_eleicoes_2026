"""Regera os prints do site em `docs/img/` (mapa e página de análises) com Playwright.

Sobe um `http.server` local servindo `web/`, captura cada print da lista `PRINTS`
(arquivo, viewport, escala, URL com o estado, ação extra) e encerra o servidor.
Os números e carimbos dos prints saem do próprio site; nada é digitado aqui.

Uso:
    python scripts/capturar_prints.py                      # todos os da lista
    python scripts/capturar_prints.py --apenas mapa_preview_2_brasil_municipio
    python scripts/capturar_prints.py --listar

Requer `playwright` com o chromium instalado (`playwright install chromium`).
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

RAIZ = Path(__file__).resolve().parents[1]
WEB = RAIZ / "web"
SAIDA = RAIZ / "docs" / "img"

DESKTOP = (1440, 900, 1)
CELULAR = (375, 760, 2)  # sai em 750x1520
CELULAR_CURTO = (375, 740, 2)  # sai em 750x1480


@dataclass(frozen=True)
class Print:
    arquivo: str  # nome em docs/img/ (sem .png)
    pagina: str  # caminho relativo a web/, com a query string do estado
    viewport: tuple[int, int, int]  # largura, altura, device_scale_factor
    acao: str | None = None  # exterior | painel_fim | pagina_fim | buscar:<texto>:<ibge>
    elemento: str | None = None  # seletor: captura só o elemento
    pagina_inteira: bool = False


PRINTS: list[Print] = [
    # --- mapa: F2 (v1)
    Print("mapa_preview_1_brasil_uf", "index.html?modo=mistura", DESKTOP),
    Print("mapa_preview_2_brasil_municipio", "index.html?camada=mun&modo=mistura", DESKTOP),
    Print("mapa_preview_3_uf_drilldown", "index.html?uf=mg&modo=mistura", DESKTOP),
    Print(
        "mapa_preview_4_painel_municipio",
        "index.html?modo=mistura",
        DESKTOP,
        acao="buscar:uberlandia:3170206",  # pela busca: enquadra o município
    ),
    Print("mapa_preview_5_modo_vencedor_margem", "index.html?modo=margem", DESKTOP),
    Print("mapa_preview_6_celular_375px", "index.html?modo=mistura", CELULAR_CURTO),
    Print("mapa_preview_7_exterior", "index.html?modo=mistura", DESKTOP, acao="exterior"),
    # --- mapa: F2.2 (seleção de candidato)
    Print(
        "mapa_preview_f22_1_lula_venceu_municipios",
        "index.html?camada=mun&modo=venceu&candidato=13",
        DESKTOP,
    ),
    Print(
        "mapa_preview_f22_2_cury_forca_municipios",
        "index.html?camada=mun&modo=forca&candidato=70",
        DESKTOP,
    ),
    Print(
        "mapa_preview_f22_3_renan_forca_uf_mg", "index.html?uf=mg&modo=forca&candidato=14", DESKTOP
    ),
    Print(
        "mapa_preview_f22_4_painel_candidato",
        "index.html?uf=sp&mun=3550308&modo=venceu&candidato=22",
        DESKTOP,
    ),
    Print(
        "mapa_preview_f22_4b_painel_detalhe",
        "index.html?uf=sp&mun=3550308&modo=venceu&candidato=22",
        DESKTOP,
        elemento="#painel",
    ),
    Print(
        "mapa_preview_f22_5_celular_375px",
        "index.html?camada=mun&modo=forca&candidato=13",
        CELULAR_CURTO,
    ),
    Print(
        "mapa_preview_f22_7_exterior_candidato",
        "index.html?modo=forca&candidato=13",
        DESKTOP,
        acao="exterior",
    ),
    # --- mapa: F3 fase B (swing, empate) e rodapé
    Print("mapa_preview_f3b_empate_trabiju", "index.html?uf=sp&mun=3554755&modo=margem", DESKTOP),
    Print("mapa_preview_f3b_swing_municipios", "index.html?camada=mun&modo=swing", DESKTOP),
    Print("mapa_preview_f3b_swing_uf_mt", "index.html?uf=mt&modo=swing", DESKTOP),
    Print("mapa_preview_f3b_swing_celular", "index.html?camada=mun&modo=swing", CELULAR),
    Print("mapa_preview_rodape_celular", "index.html?modo=mistura", CELULAR, acao="painel_fim"),
    # --- página de análises
    Print("analises_preview_desktop_topo", "analises.html", DESKTOP),
    Print("analises_preview_desktop", "analises.html", DESKTOP, pagina_inteira=True),
    Print("analises_preview_celular_topo", "analises.html", CELULAR),
    Print("analises_preview_celular_rodape", "analises.html", CELULAR, acao="pagina_fim"),
    Print("analises_preview_celular_renda", "analises.html", CELULAR, elemento="#renda"),
]


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def subir_servidor(porta: int) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(porta), "--bind", "127.0.0.1"],
        cwd=WEB,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(100):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{porta}/index.html", timeout=1)
            return proc
        except OSError:
            time.sleep(0.1)
    proc.terminate()
    raise RuntimeError("http.server não respondeu")


def esperar_site(pag: Page, pagina: str) -> None:
    if pagina.startswith("index.html"):
        pag.wait_for_function(
            "() => document.querySelector('#carregando').hidden === true", timeout=90000
        )
        pag.wait_for_load_state("networkidle")
        pag.wait_for_timeout(3000)  # MapLibre termina de pintar os tiles vetoriais
    else:
        pag.wait_for_function(
            "() => !document.querySelector('[data-v=\"snapshot.data\"]').textContent.includes('…')",
            timeout=60000,
        )
        pag.wait_for_load_state("networkidle")
        pag.wait_for_timeout(1500)  # gráficos do Observable Plot


def aplicar_acao(pag: Page, acao: str | None) -> None:
    if acao is None:
        return
    if acao.startswith("buscar:"):
        _, texto, ibge = acao.split(":")
        pag.fill("#busca", texto)
        item = pag.locator(f'#busca-resultados li[data-ibge="{ibge}"]')
        item.wait_for()
        item.dispatch_event("mousedown")
        pag.wait_for_load_state("networkidle")
        pag.wait_for_timeout(3000)  # fitBounds anima por 700 ms; depois os tiles
    elif acao == "exterior":
        pag.click("#abrir-exterior")
        pag.wait_for_function("() => !document.querySelector('#modal-exterior').hidden")
        pag.wait_for_timeout(500)
    elif acao == "painel_fim":
        pag.evaluate(
            "() => { const p = document.querySelector('#painel'); p.scrollTop = p.scrollHeight; }"
        )
        pag.wait_for_timeout(300)
    elif acao == "pagina_fim":
        pag.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        pag.wait_for_timeout(300)
    else:
        raise ValueError(f"ação desconhecida: {acao}")


def capturar(prints: list[Print], base: str) -> list[str]:
    erros: list[str] = []
    with sync_playwright() as pw:
        nav = pw.chromium.launch()
        for p in prints:
            largura, altura, escala = p.viewport
            ctx = nav.new_context(
                viewport={"width": largura, "height": altura}, device_scale_factor=escala
            )
            pag = ctx.new_page()
            pag.on("pageerror", lambda e, n=p.arquivo: erros.append(f"{n}: {e}"))
            pag.on(
                "console",
                lambda m, n=p.arquivo: (
                    erros.append(f"{n}: {m.text}") if m.type == "error" else None
                ),
            )
            pag.goto(base + p.pagina, wait_until="domcontentloaded")
            esperar_site(pag, p.pagina)
            aplicar_acao(pag, p.acao)
            destino = SAIDA / f"{p.arquivo}.png"
            if p.elemento:
                pag.locator(p.elemento).screenshot(path=str(destino))
            else:
                pag.screenshot(path=str(destino), full_page=p.pagina_inteira)
            print(f"  {destino.name}")
            ctx.close()
        nav.close()
    return erros


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apenas", nargs="*", help="nomes (sem .png) a capturar")
    ap.add_argument("--listar", action="store_true")
    args = ap.parse_args()

    if args.listar:
        for p in PRINTS:
            print(f"{p.arquivo:45s} {p.viewport} {p.pagina} {p.acao or ''} {p.elemento or ''}")
        return 0
    prints = PRINTS
    if args.apenas:
        desconhecidos = set(args.apenas) - {p.arquivo for p in PRINTS}
        if desconhecidos:
            print(f"não estão na lista: {sorted(desconhecidos)}")
            return 2
        prints = [p for p in PRINTS if p.arquivo in args.apenas]

    porta = porta_livre()
    servidor = subir_servidor(porta)
    try:
        erros = capturar(prints, f"http://127.0.0.1:{porta}/")
    finally:
        servidor.terminate()
        servidor.wait(timeout=10)
    if erros:
        print("erros na página:", *erros, sep="\n  ")
        return 1
    print(f"{len(prints)} prints em {SAIDA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
