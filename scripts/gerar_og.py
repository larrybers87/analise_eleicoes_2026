"""Gera `web/img/og.png` (1200×627), a imagem de pré-visualização para redes sociais (D-032).

Captura o próprio site servido localmente (Playwright headless), no estado padrão de
"Brasil por município" com o modo mistura, e sobrepõe título e legenda num bloco à esquerda.
As cores são as do mapa (lidas de `data/meta.json` pelo próprio site), nada é recalculado.

Uso (com o site servido em http://127.0.0.1:8765/, ex. `cd web && python -m http.server 8765`):
    python scripts/gerar_og.py [--base http://127.0.0.1:8765/]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "web" / "img" / "og.png"
LARGURA, ALTURA = 1200, 627
LARGURA_TEXTO = 430

# CSS injetado ANTES dos scripts do site: o MapLibre já nasce no tamanho final e o
# `fitBounds` inicial enquadra o Brasil na área do mapa (à direita do bloco de texto).
CSS = f"""
#topo, #controles, #legenda, #painel, #pe, #tooltip, #carregando,
.maplibregl-control-container {{ display: none !important; }}
html, body {{ height: {ALTURA}px !important; overflow: hidden; }}
main {{ height: {ALTURA}px; }}
#mapa {{ left: {LARGURA_TEXTO}px !important; right: 0 !important; top: 0; bottom: 0 !important; }}
#og-texto {{
  position: fixed; left: 0; top: 0; bottom: 0; width: {LARGURA_TEXTO}px; z-index: 50;
  background: #ffffff; border-right: 1px solid #d8dde3;
  padding: 54px 40px; box-sizing: border-box;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: #1d2126;
  display: flex; flex-direction: column;
}}
#og-texto .kicker {{ font-size: 18px; color: #1b4f8a; font-weight: 600; letter-spacing: .04em;
  text-transform: uppercase; }}
#og-texto h1 {{ font-size: 46px; line-height: 1.08; margin: 14px 0 12px; }}
#og-texto .sub {{ font-size: 22px; color: #5d6670; line-height: 1.35; }}
#og-texto .leg {{ margin-top: auto; display: flex; flex-direction: column; gap: 9px;
  font-size: 19px; }}
#og-texto .leg i {{ display: inline-block; width: 18px; height: 18px; border-radius: 4px;
  margin-right: 10px; vertical-align: -3px; }}
#og-texto .url {{ margin-top: 22px; font-size: 15px; color: #5d6670; }}
"""

INJETAR = (
    "(() => { const css = %r; const pronto = () => { if (!document.head) return false;"
    " const s = document.createElement('style'); s.textContent = css;"
    " document.head.appendChild(s); return true; };"
    " if (!pronto()) { const o = new MutationObserver(() => { if (pronto()) o.disconnect(); });"
    " o.observe(document, { childList: true, subtree: true }); } })();"
)

TEXTO = """
(async () => {
  const meta = await (await fetch('data/meta.json')).json();
  const c = (nr) => meta.candidatos[String(nr)];
  const d = document.createElement('div');
  d.id = 'og-texto';
  d.innerHTML = `
    <div class="kicker">Mapa de resultados</div>
    <h1>Presidente 2026<br>1º turno</h1>
    <div class="sub">Brasil, estados e os 5.571 municípios, com dados oficiais do TSE</div>
    <div class="leg">
      <span><i style="background:${c(22).cor}"></i>Flávio Bolsonaro (PL)</span>
      <span><i style="background:${c(13).cor}"></i>Lula (PT)</span>
      <span style="color:#5d6670;font-size:16px">Cor de cada município: mistura dos votos</span>
    </div>
    <div class="url">larrybers87.github.io/analise_eleicoes_2026</div>`;
  document.body.appendChild(d);
})();
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="http://127.0.0.1:8765/")
    args = ap.parse_args()
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    erros: list[str] = []
    with sync_playwright() as pw:
        nav = pw.chromium.launch()
        pag = nav.new_page(viewport={"width": LARGURA, "height": ALTURA}, device_scale_factor=1)
        pag.on("pageerror", lambda e: erros.append(str(e)))
        pag.add_init_script(INJETAR % CSS)
        pag.goto(args.base + "index.html?camada=mun&modo=mistura", wait_until="networkidle")
        pag.wait_for_function(
            "() => document.querySelector('#carregando').hidden === true", timeout=90000
        )
        pag.evaluate(TEXTO)
        pag.wait_for_timeout(5000)
        pag.screenshot(path=str(SAIDA), clip={"x": 0, "y": 0, "width": LARGURA, "height": ALTURA})
        nav.close()
    if erros:
        print("erros na página:", erros)
        return 1
    print(f"{SAIDA} ({SAIDA.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
