/* Mapa Presidente 2026 — 1º turno. Vanilla JS, sem bundler (D-015 item 10).
 *
 * REGRA DE OURO: nenhuma cor é CALCULADA aqui. Toda cor de dado (mistura
 * OKLab, vencedor+margem, cor do candidato, rampa da legenda) chega pronta em
 * hex de `data/`, gerada por `scripts/exportar_web.py` via
 * `src/eleicao/cores.py`. Este arquivo só lê strings e as repassa ao MapLibre
 * / ao CSS.
 *
 * TopoJSON é convertido para GeoJSON AQUI, no navegador (`topojson-client`),
 * nunca no Python — é isso que preserva o ganho de tamanho do TopoJSON até o
 * cliente (D-015 item 5).
 */
'use strict';

(function () {

// ============================ estado global =================================

const S = {
  meta: null,
  br: null,                 // data/resultados/br.json
  indice: null,             // data/resultados/municipios_br.json (lazy)
  ufs: new Map(),           // sigla -> data/resultados/uf/uf_<sigla>.json
  geoUf: null,              // GeoJSON das 27 UFs
  geoMunBr: null,           // GeoJSON dos 5571 municípios (lazy)
  geoMunUf: new Map(),      // sigla -> GeoJSON dos municípios da UF
  exterior: null,           // data/exterior.json (lazy)

  resumo: null,             // data/resumo_candidatos.json (lazy)
  forca: new Map(),         // nr -> {p98, pct: [5571 números], mapas: Map(escopo -> Map(ibge->pct))}

  modo: 'mistura',          // modo BASE (sem candidato): 'mistura' | 'margem'
  candidato: null,          // nr do candidato destacado (null = "Nenhum")
  modoCand: 'venceu',       // modo COM candidato: 'venceu' | 'forca'
  camadaBr: 'uf',           // 'uf' | 'mun'  (só quando não há UF ativa)
  uf: null,                 // sigla da UF em drill-down
  municipio: null,          // cd_mun_ibge selecionado
  hover: null,              // {fonte, id}
  selecionado: null,        // {fonte, id}
  ordemExterior: { col: 'validos', desc: true },
  restaurando: false,       // true enquanto o estado vem da URL (não reescreve a URL)
};

const CAMPO_COR = { mistura: 'cor_mistura', margem: 'cor_margem' };

/** Modo de cor efetivo. Com candidato selecionado, os 2 modos novos
 *  ("Onde venceu"/"Força") substituem os 2 base; "Nenhum" devolve o
 *  comportamento original do mapa, sem nenhuma diferença. */
function modoEfetivo() {
  return S.candidato ? S.modoCand : S.modo;
}

/** Posição do candidato nos arrays posicionais `votos_cand` (ordem canônica
 *  declarada em `meta.json.ordem_candidatos` — votação nacional desc). */
function posCand(nr) {
  return S.meta.ordem_candidatos.indexOf(Number(nr));
}

/** % dos válidos do candidato numa entrada de `br.json.ufs[]` / `exterior`. */
function pctDe(reg, nr) {
  if (!reg || !reg.votos_cand) return null;
  const v = reg.votos_cand[posCand(nr)];
  const tot = reg.validos !== undefined ? reg.validos : reg.totais && reg.totais.validos;
  if (!tot) return null;
  return (v / tot) * 100;
}

function votosDe(reg, nr) {
  return reg && reg.votos_cand ? reg.votos_cand[posCand(nr)] : null;
}

/** Enquadramento do Brasil continental + arquipélagos próximos. */
const LIMITES_BR = [[-74.1, -33.9], [-32.3, 5.4]];

const FONTES = { uf: 'uf', munbr: 'munbr', munuf: 'munuf' };

// ============================== utilidades ==================================

const $ = (sel) => document.querySelector(sel);
const elTooltip = $('#tooltip');
const elCarregando = $('#carregando');

let pendentes = 0;
function ocupado(delta, texto) {
  pendentes = Math.max(0, pendentes + delta);
  if (pendentes > 0) {
    elCarregando.textContent = texto || 'Carregando…';
    elCarregando.hidden = false;
  } else {
    elCarregando.hidden = true;
  }
}

/** Fetch de JSON. `versionar` adiciona `?v=<idg>` (cache busting, D-015 item 7). */
async function obter(caminho, versionar) {
  const url = versionar && S.meta ? `${caminho}?v=${S.meta.snapshot.idg}` : caminho;
  const r = await fetch(url, versionar ? undefined : { cache: 'no-cache' });
  if (!r.ok) throw new Error(`falha ao carregar ${caminho}: HTTP ${r.status}`);
  return r.json();
}

/** TopoJSON -> GeoJSON, no navegador. Geometria não leva `?v=` (é estável). */
async function obterGeo(caminho) {
  const r = await fetch(caminho);
  if (!r.ok) throw new Error(`falha ao carregar ${caminho}: HTTP ${r.status}`);
  const topo = await r.json();
  const nome = Object.keys(topo.objects)[0];
  return topojson.feature(topo, topo.objects[nome]);
}

const nf = new Intl.NumberFormat('pt-BR');
const num = (v) => (v === null || v === undefined ? '—' : nf.format(v));
const pct = (v, casas) =>
  v === null || v === undefined || !isFinite(v)
    ? '—'
    : v.toLocaleString('pt-BR', { minimumFractionDigits: casas ?? 1, maximumFractionDigits: casas ?? 1 }) + '%';

const semAcento = (s) =>
  s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

/** Nome em caixa alta do TSE -> Caixa De Título, preservando siglas curtas. */
function titulo(s) {
  if (!s) return '';
  const miudas = new Set(['de', 'da', 'do', 'das', 'dos', 'e', 'd', 'a', 'o', 'em']);
  return s
    .toLocaleLowerCase('pt-BR')
    .split(/(\s|-|')/)
    .map((p, i) => {
      if (/^(\s|-|')$/.test(p) || !p) return p;
      if (i > 0 && miudas.has(p)) return p;
      return p.charAt(0).toLocaleUpperCase('pt-BR') + p.slice(1);
    })
    .join('');
}

function candidato(nr) {
  if (nr === 'outros') {
    return { nm_urna: 'Outros', partido: '', cor: S.meta.cor_outros };
  }
  return S.meta.candidatos[String(nr)] || { nm_urna: `nº ${nr}`, partido: '', cor: '#999999' };
}

/** Rótulo legível de totalização (`and` operacional + `tf` judicial). */
function rotuloTotalizacao(tot) {
  if (tot.tf_judicial === 's') return { texto: 'final (judicial)', classe: '' };
  if (tot.status_totalizacao === 'f') return { texto: 'final (operacional)', classe: '' };
  if (tot.status_totalizacao === 'n') return { texto: 'totalização não iniciada', classe: 'parcial' };
  return { texto: 'parcial', classe: 'parcial' };
}

function bbox(geom) {
  let x0 = 180, y0 = 90, x1 = -180, y1 = -90;
  const anda = (c) => {
    if (typeof c[0] === 'number') {
      if (c[0] < x0) x0 = c[0];
      if (c[0] > x1) x1 = c[0];
      if (c[1] < y0) y0 = c[1];
      if (c[1] > y1) y1 = c[1];
    } else for (const f of c) anda(f);
  };
  anda(geom.coordinates);
  return [[x0, y0], [x1, y1]];
}

// ============================= mapa (MapLibre) ==============================

const map = new maplibregl.Map({
  container: 'mapa',
  // Sem basemap de terceiros (D-015 item 6): fundo sólido + contornos de UF.
  style: {
    version: 8,
    sources: {},
    layers: [{ id: 'fundo', type: 'background', paint: { 'background-color': '#eaeef2' } }],
  },
  center: [-53.5, -14.5],
  zoom: 3.1,
  minZoom: 2,
  maxZoom: 11,
  attributionControl: false,
  dragRotate: false,
  pitchWithRotate: false,
});
map.touchZoomRotate.disableRotation();
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
map.addControl(
  new maplibregl.AttributionControl({
    compact: true,
    customAttribution: 'Resultados: TSE · Malha: IBGE/geobr',
  }),
  'bottom-right'
);

/** Injeta cor/nome/vencedor/margem (já prontos) nas properties do GeoJSON. */
function anexar(geojson, porId, chaveId) {
  for (const f of geojson.features) {
    const reg = porId.get(String(f.properties[chaveId]));
    if (!reg) continue;
    f.properties.nome = reg.nome;
    f.properties.cor_mistura = reg.cor_mistura;
    f.properties.cor_margem = reg.cor_margem;
    f.properties.vencedor = reg.vencedor === null ? -1 : reg.vencedor;
    f.properties.margem_pp = reg.margem_pp === null ? -1 : reg.margem_pp;
  }
  return geojson;
}

/* -------------------- expressões de cor (nunca cor calculada) --------------
 * Todas as cores abaixo vêm prontas de `meta.json` (geradas por
 * `src/eleicao/cores.py`). O que o JS monta é só a ESTRUTURA da expressão do
 * MapLibre: quais stops, em que valor numérico, e o que fazer fora da faixa.
 */

/** Rampa `interpolate` a partir de stops hex já calculados em Python.
 *  `valores[i]` é o valor de dado onde `stops[i]` se aplica. */
function interpolar(entrada, valores, stops) {
  const expr = ['interpolate', ['linear'], entrada];
  for (let i = 0; i < stops.length; i++) expr.push(valores[i], stops[i]);
  return expr;
}

/** Valores (em % dos válidos) de cada stop da escala "Força" do candidato. */
function valoresForca(nr) {
  const teto = S.meta.forca_p98[String(nr)];
  return S.meta.escala_forca_fracoes.map((f) => f * teto);
}

function expressaoCor() {
  const m = modoEfetivo();
  if (m === 'mistura' || m === 'margem') {
    return ['coalesce', ['get', CAMPO_COR[m]], '#dddddd'];
  }
  const nr = S.candidato;
  if (m === 'venceu') {
    // mesma rampa do modo "vencedor + margem", restrita a quem ele venceu:
    // já exportada em meta.escala_margem (0 a MARGEM_SATURACAO p.p.).
    const rampa = interpolar(
      ['get', 'margem_pp'],
      S.meta.escala_margem_pp,
      S.meta.escala_margem[String(nr)]
    );
    return ['case', ['==', ['get', 'vencedor'], nr], rampa, S.meta.cor_nao_venceu];
  }
  // 'forca': % dos válidos dele, de 0 ao percentil 98 (satura acima).
  const rampa = interpolar(['get', 'pct_cand'], valoresForca(nr), S.meta.escala_forca[String(nr)]);
  return ['case', ['has', 'pct_cand'], rampa, S.meta.cor_sem_votos];
}

function expressaoOpacidade() {
  if (modoEfetivo() !== 'venceu') {
    return [
      'case',
      ['boolean', ['feature-state', 'selecionado'], false], 1,
      ['boolean', ['feature-state', 'hover'], false], 0.86,
      1,
    ];
  }
  // onde ele NÃO foi 1º: opacidade baixa, para o mapa ler como "fundo"
  return [
    'case',
    ['boolean', ['feature-state', 'selecionado'], false], 1,
    ['boolean', ['feature-state', 'hover'], false], 0.9,
    ['==', ['get', 'vencedor'], S.candidato], 1,
    S.meta.opacidade_nao_venceu,
  ];
}

function adicionarCamada(id, geojson, promoteId, larguraLinha) {
  if (map.getSource(id)) return;
  map.addSource(id, { type: 'geojson', data: geojson, promoteId: promoteId });
  map.addLayer({
    id: `${id}-fill`,
    type: 'fill',
    source: id,
    paint: {
      'fill-color': expressaoCor(),
      'fill-opacity': expressaoOpacidade(),
    },
  });
  map.addLayer({
    id: `${id}-linha`,
    type: 'line',
    source: id,
    paint: {
      'line-color': 'rgba(255,255,255,.65)',
      'line-width': larguraLinha,
    },
  });
  map.addLayer({
    id: `${id}-realce`,
    type: 'line',
    source: id,
    paint: {
      'line-color': [
        'case',
        ['boolean', ['feature-state', 'selecionado'], false], '#15202b',
        '#ffffff',
      ],
      'line-width': [
        'case',
        ['boolean', ['feature-state', 'selecionado'], false], 2.4,
        ['boolean', ['feature-state', 'hover'], false], 1.8,
        0,
      ],
    },
  });
  ligarInteracao(id);
}

function ligarInteracao(id) {
  const camada = `${id}-fill`;
  map.on('mousemove', camada, (e) => {
    const f = e.features && e.features[0];
    if (!f) return;
    map.getCanvas().style.cursor = 'pointer';
    if (S.hover && (S.hover.fonte !== id || S.hover.id !== f.id)) limparHover();
    if (!S.hover || S.hover.id !== f.id) {
      S.hover = { fonte: id, id: f.id };
      map.setFeatureState({ source: id, id: f.id }, { hover: true });
    }
    mostrarTooltip(e.point, f.properties);
  });
  map.on('mouseleave', camada, () => {
    map.getCanvas().style.cursor = '';
    limparHover();
    elTooltip.hidden = true;
  });
  map.on('click', camada, (e) => {
    const f = e.features && e.features[0];
    if (!f) return;
    if (id === FONTES.uf) irParaUf(String(f.properties.uf));
    else selecionarMunicipio(String(f.properties.cd_mun_ibge), id === FONTES.munbr);
  });
}

function limparHover() {
  if (!S.hover) return;
  if (map.getSource(S.hover.fonte)) {
    map.setFeatureState({ source: S.hover.fonte, id: S.hover.id }, { hover: false });
  }
  S.hover = null;
}

function mostrarTooltip(ponto, p) {
  const venc = p.vencedor > 0 ? candidato(p.vencedor) : null;
  let corpo;
  if (!venc) {
    corpo = '<span>sem voto válido</span>';
  } else if (modoEfetivo() === 'forca') {
    const c = candidato(S.candidato);
    corpo =
      `<span>${c.nm_urna}: <b>${pct(p.pct_cand, 2)}</b> dos válidos</span>` +
      `<span>1º: ${venc.nm_urna}</span>`;
  } else if (modoEfetivo() === 'venceu') {
    const c = candidato(S.candidato);
    corpo =
      p.vencedor === S.candidato
        ? `<span>${c.nm_urna} foi 1º · ${pct(p.margem_pp, 1)} de margem</span>`
        : `<span>${c.nm_urna} não foi 1º aqui</span><span>1º: ${venc.nm_urna}</span>`;
  } else {
    corpo = `<span>${venc.nm_urna} · ${pct(p.margem_pp, 1)} de margem</span>`;
  }
  elTooltip.innerHTML = `<b>${titulo(p.nome || p.nm_uf || '')}</b>${corpo}`;
  elTooltip.hidden = false;
  elTooltip.style.left = `${ponto.x}px`;
  elTooltip.style.top = `${ponto.y - 12}px`;
}

function aplicarModoNoMapa() {
  for (const id of Object.values(FONTES)) {
    if (map.getLayer(`${id}-fill`)) {
      map.setPaintProperty(`${id}-fill`, 'fill-color', expressaoCor());
      map.setPaintProperty(`${id}-fill`, 'fill-opacity', expressaoOpacidade());
    }
  }
}

function visivel(id, mostrar) {
  for (const sufixo of ['-fill', '-linha', '-realce']) {
    if (map.getLayer(id + sufixo)) {
      map.setLayoutProperty(id + sufixo, 'visibility', mostrar ? 'visible' : 'none');
    }
  }
}

/** Seleção exclusiva. Guardamos o anterior porque o MapLibre v5 exige um id
 *  de feature para remover uma chave específica de `feature-state`. */
function marcarSelecionado(fonte, id) {
  if (S.selecionado && map.getSource(S.selecionado.fonte)) {
    map.setFeatureState(
      { source: S.selecionado.fonte, id: S.selecionado.id },
      { selecionado: false }
    );
  }
  S.selecionado = null;
  if (fonte && id !== null && id !== undefined && map.getSource(fonte)) {
    map.setFeatureState({ source: fonte, id: id }, { selecionado: true });
    S.selecionado = { fonte: fonte, id: id };
  }
}

// ============================= carregamentos =================================

async function garantirGeoUf() {
  if (S.geoUf) return S.geoUf;
  const geo = await obterGeo('data/geo/brasil_uf.topojson');
  const porId = new Map(S.br.ufs.map((u) => [String(u.cd_uf_ibge), u]));
  S.geoUf = anexar(geo, porId, 'cd_uf_ibge');
  return S.geoUf;
}

async function garantirIndice() {
  if (S.indice) return S.indice;
  ocupado(1, 'Carregando índice de municípios…');
  try {
    const bruto = await obter('data/resultados/municipios_br.json', true);
    const campos = bruto.formato;
    const mapa = new Map();
    for (const [ibge, arr] of Object.entries(bruto.municipios)) {
      const o = { cd_mun_ibge: ibge };
      campos.forEach((c, i) => { o[c] = arr[i]; });
      mapa.set(ibge, o);
    }
    S.indice = mapa;
  } finally {
    ocupado(-1);
  }
  return S.indice;
}

async function garantirGeoMunBr() {
  if (S.geoMunBr) return S.geoMunBr;
  ocupado(1, 'Carregando os 5.571 municípios…');
  try {
    const [geo] = await Promise.all([
      obterGeo('data/geo/brasil_municipios.topojson'),
      garantirIndice(),
    ]);
    S.geoMunBr = anexar(geo, S.indice, 'cd_mun_ibge');
  } finally {
    ocupado(-1);
  }
  return S.geoMunBr;
}

async function garantirResumo() {
  if (S.resumo) return S.resumo;
  ocupado(1, 'Carregando resumo do candidato…');
  try {
    S.resumo = await obter('data/resumo_candidatos.json', true);
  } finally {
    ocupado(-1);
  }
  return S.resumo;
}

/** `forca/cand_<nr>.json`: o % dos válidos do candidato nos 5.571 municípios,
 *  array POSICIONAL (ver `meta.forca_ordem`). Baixado uma vez por candidato. */
async function garantirForca(nr) {
  if (S.forca.has(nr)) return S.forca.get(nr);
  ocupado(1, 'Carregando % do candidato por município…');
  try {
    const bruto = await obter(`data/resultados/forca/cand_${nr}.json`, true);
    if (bruto.n !== S.meta.n_municipios_br) {
      throw new Error(
        `forca/cand_${nr}.json tem ${bruto.n} municípios, meta.json diz ${S.meta.n_municipios_br}`
      );
    }
    S.forca.set(nr, { p98: bruto.p98, pct: bruto.pct, mapas: new Map() });
  } finally {
    ocupado(-1);
  }
  return S.forca.get(nr);
}

/** `Map(cd_mun_ibge -> pct)` do candidato para um escopo: `'br'` (os 5.571) ou
 *  uma sigla de UF.
 *
 *  O array de `forca/cand_<nr>.json` está em ordem numérica crescente de
 *  `cd_mun_ibge`; como o código IBGE começa com o código da UF, isso agrupa os
 *  municípios por UF em blocos contíguos (garantido no build por
 *  `offsets_forca`). Então para uma UF basta `meta.forca_offsets[sigla]` + os
 *  códigos dela (que `uf_<sigla>.json` já trouxe) ordenados — não é preciso
 *  baixar o índice nacional de 380KB só para saber posições. */
async function mapaForca(nr, escopo) {
  const f = await garantirForca(nr);
  if (f.mapas.has(escopo)) return f.mapas.get(escopo);

  let codigos;
  let base = 0;
  if (escopo === 'br') {
    await garantirIndice();
    codigos = Array.from(S.indice.keys()).sort((a, b) => Number(a) - Number(b));
  } else {
    base = S.meta.forca_offsets[escopo];
    const dados = S.ufs.get(escopo);
    if (base === undefined || !dados) return new Map();
    codigos = dados.municipios.map((m) => String(m.cd_mun_ibge)).sort((a, b) => Number(a) - Number(b));
  }
  if (base + codigos.length > f.pct.length) {
    throw new Error(`fatia de força fora do array (escopo ${escopo})`);
  }
  const mapa = new Map();
  codigos.forEach((c, i) => mapa.set(c, f.pct[base + i]));
  f.mapas.set(escopo, mapa);
  return mapa;
}

/** Escreve/apaga `pct_cand` nas properties de um GeoJSON já carregado.
 *  É property (e não `feature-state`) porque o `feature-state` é apagado pelo
 *  `setData` do drill-down e não existe para tiles ainda não renderizados. */
function injetarPct(geojson, chaveId, buscar) {
  for (const f of geojson.features) {
    const v = buscar(String(f.properties[chaveId]));
    if (v === undefined || v === null) delete f.properties.pct_cand;
    else f.properties.pct_cand = v;
  }
}

function recarregarFonte(id, geojson) {
  const src = map.getSource(id);
  if (!src) return;
  src.setData(geojson);
  // `setData` zera o feature-state: refaz a marca de seleção.
  if (S.selecionado && S.selecionado.fonte === id) {
    map.setFeatureState({ source: id, id: S.selecionado.id }, { selecionado: true });
  }
}

/** Garante que as camadas visíveis tenham `pct_cand` do candidato atual.
 *  Só o modo "Força" precisa disso; "Onde venceu" usa `vencedor`/`margem_pp`,
 *  que já vêm nas properties desde o F2. O painel do município também usa o
 *  `pct_cand`, por isso carregamos a força sempre que a camada municipal está
 *  à vista com um candidato selecionado. */
async function prepararPctDoCandidato() {
  const nr = S.candidato;
  if (!nr) return;
  if (S.geoUf) {
    const porCodigo = new Map(S.br.ufs.map((u) => [String(u.cd_uf_ibge), pctDe(u, nr)]));
    injetarPct(S.geoUf, 'cd_uf_ibge', (id) => porCodigo.get(id));
    recarregarFonte(FONTES.uf, S.geoUf);
  }
  if (S.uf) {
    const mapa = await mapaForca(nr, S.uf);
    const geo = S.geoMunUf.get(S.uf);
    if (geo) {
      injetarPct(geo, 'cd_mun_ibge', (id) => mapa.get(id));
      recarregarFonte(FONTES.munuf, geo);
    }
  } else if (S.camadaBr === 'mun' && S.geoMunBr) {
    const mapa = await mapaForca(nr, 'br');
    injetarPct(S.geoMunBr, 'cd_mun_ibge', (id) => mapa.get(id));
    recarregarFonte(FONTES.munbr, S.geoMunBr);
  }
}

/** % do candidato selecionado no município `ibge`, se já carregado. */
function pctMunicipio(ibge) {
  const f = S.forca.get(S.candidato);
  if (!f) return null;
  for (const mapa of f.mapas.values()) {
    if (mapa.has(String(ibge))) return mapa.get(String(ibge));
  }
  return null;
}

async function garantirUf(sigla) {
  if (S.ufs.has(sigla) && S.geoMunUf.has(sigla)) return;
  ocupado(1, 'Carregando municípios…');
  try {
    const [dados, geo] = await Promise.all([
      S.ufs.get(sigla) || obter(`data/resultados/uf/uf_${sigla}.json`, true),
      S.geoMunUf.get(sigla) || obterGeo(`data/geo/municipios/uf_${sigla}.topojson`),
    ]);
    S.ufs.set(sigla, dados);
    const porId = new Map(dados.municipios.map((m) => [String(m.cd_mun_ibge), m]));
    S.geoMunUf.set(sigla, anexar(geo, porId, 'cd_mun_ibge'));
  } finally {
    ocupado(-1);
  }
}

// =============================== navegação ==================================

async function irParaBrasil(camada) {
  S.uf = null;
  S.municipio = null;
  if (camada) S.camadaBr = camada;

  if (S.camadaBr === 'mun') {
    const geo = await garantirGeoMunBr();
    adicionarCamada(FONTES.munbr, geo, 'cd_mun_ibge', 0.2);
  }
  visivel(FONTES.uf, S.camadaBr === 'uf');
  visivel(FONTES.munbr, S.camadaBr === 'mun');
  visivel(FONTES.munuf, false);
  marcarSelecionado(null, null);

  await prepararPctDoCandidato();
  // as camadas sobrevivem à navegação: reaplica a expressão de cor do modo
  // atual (a camada de UF, por exemplo, é criada no load, antes de a URL ter
  // sido lida).
  aplicarModoNoMapa();
  map.fitBounds(LIMITES_BR, { padding: 24, duration: 500 });
  pintarPainel(S.br.br, 'br');
  desenharLegenda();
  desenharTrilha();
  escreverUrl(true);
}

async function irParaUf(sigla) {
  if (sigla === 'zz' || !S.meta.ufs.some((u) => u.sigla === sigla && u.sigla !== 'zz')) return;
  await garantirUf(sigla);
  S.uf = sigla;
  S.municipio = null;

  // uma fonte só para "municípios da UF ativa": troca o dado em vez de
  // acumular 27 fontes no mapa (memória do navegador).
  const geo = S.geoMunUf.get(sigla);
  if (map.getSource(FONTES.munuf)) map.getSource(FONTES.munuf).setData(geo);
  else adicionarCamada(FONTES.munuf, geo, 'cd_mun_ibge', 0.5);

  visivel(FONTES.uf, false);
  visivel(FONTES.munbr, false);
  visivel(FONTES.munuf, true);
  marcarSelecionado(null, null);

  await prepararPctDoCandidato();
  aplicarModoNoMapa();
  const alvo = (S.geoUf.features || []).find((f) => String(f.properties.uf) === sigla);
  if (alvo) map.fitBounds(bbox(alvo.geometry), { padding: 30, duration: 600 });

  pintarPainel(S.ufs.get(sigla).uf, 'uf');
  desenharLegenda();
  desenharTrilha();
  escreverUrl(true);
}

async function selecionarMunicipio(ibge, vindoDoNacional) {
  if (vindoDoNacional) {
    const info = S.indice.get(ibge);
    if (info) {
      await irParaUf(info.uf);
    }
  }
  if (!S.uf) return;
  const reg = (S.ufs.get(S.uf).municipios || []).find((m) => String(m.cd_mun_ibge) === ibge);
  if (!reg) return;
  S.municipio = ibge;
  marcarSelecionado(FONTES.munuf, ibge);
  pintarPainel(reg, 'mun');
  desenharTrilha();
  escreverUrl(true);
  document.body.classList.remove('painel-fechado');
}

async function irParaMunicipioGlobal(ibge) {
  await garantirIndice();
  const info = S.indice.get(ibge);
  if (!info) return;
  await irParaUf(info.uf);
  await selecionarMunicipio(ibge, false);
  const geo = S.geoMunUf.get(info.uf);
  const alvo = geo.features.find((f) => String(f.properties.cd_mun_ibge) === ibge);
  if (!alvo) return;
  // folga proporcional à tela: o município fica enquadrado mas com vizinhos à
  // vista (um município grande ocupando 100% da tela perde todo o contexto).
  const c = map.getCanvas();
  const folga = Math.max(30, Math.min(c.clientWidth, c.clientHeight) * 0.3);
  map.fitBounds(bbox(alvo.geometry), { padding: folga, maxZoom: 8.5, duration: 700 });
}

function desenharTrilha() {
  const el = $('#trilha');
  const partes = [];
  const emBrasil = !S.uf;
  partes.push(
    emBrasil
      ? '<span class="atual">Brasil</span>'
      : '<button type="button" data-ir="br">Brasil</button>'
  );
  if (S.uf) {
    const nome = titulo(S.ufs.get(S.uf).uf.nome);
    partes.push('<span class="div">›</span>');
    partes.push(
      S.municipio
        ? `<button type="button" data-ir="uf">${nome}</button>`
        : `<span class="atual">${nome}</span>`
    );
  }
  if (S.municipio) {
    const reg = S.ufs.get(S.uf).municipios.find((m) => String(m.cd_mun_ibge) === S.municipio);
    partes.push('<span class="div">›</span>');
    partes.push(`<span class="atual">${titulo(reg.nome)}</span>`);
  }
  el.innerHTML = partes.join('');
  $('#btn-voltar').hidden = emBrasil && !S.municipio;
}

// ================================ painel ====================================

function barras(reg) {
  const total = reg.votos.reduce((a, v) => a + v[1], 0);
  if (!total) return '<p class="dica">Nenhum voto válido registrado nesta região.</p>';
  const max = reg.votos[0][1];
  return (
    '<div class="barras">' +
    reg.votos
      .map(([nr, votos]) => {
        const c = candidato(nr);
        const venceu = nr === reg.vencedor;
        return (
          `<div class="barra-item${venceu ? ' vencedor' : ''}">` +
          `<div class="rotulo"><span class="nome">${c.nm_urna}` +
          (c.partido ? ` <span class="partido">${c.partido}</span>` : '') +
          `</span><span class="pct">${pct((votos / total) * 100, 1)}</span></div>` +
          `<div class="trilho"><div class="preenche" style="width:${(votos / max) * 100}%;background:${c.cor}"></div></div>` +
          `<div class="votos">${num(votos)} votos</div>` +
          '</div>'
        );
      })
      .join('') +
    '</div>'
  );
}

function metricas(tot) {
  const linha = (rot, valor, extra) =>
    `<div><dt>${rot}</dt><dd>${valor}${extra ? ` <small>${extra}</small>` : ''}</dd></div>`;
  const el = tot.eleitorado || 0;
  const comp = tot.comparecimento || 0;
  const itens = [
    linha('Eleitorado', num(tot.eleitorado)),
    linha('Comparecimento', num(comp), el ? pct((comp / el) * 100, 1) : ''),
    linha('Abstenção', num(tot.abstencao), el ? pct(((tot.abstencao || 0) / el) * 100, 1) : ''),
    linha('Votos válidos', num(tot.validos), comp ? pct((tot.validos / comp) * 100, 1) : ''),
    linha('Brancos', num(tot.brancos), comp ? pct((tot.brancos / comp) * 100, 1) : ''),
    linha('Nulos (total)', num(tot.nulos_tvn), comp ? pct((tot.nulos_tvn / comp) * 100, 1) : ''),
    linha('Nulos na urna', num(tot.nulos_vn)),
    linha('Seções totalizadas', `${num(tot.secoes_totalizadas)}/${num(tot.secoes_total)}`),
  ];
  // `anulados`/`anulados_sub_judice` só vêm no JSON quando > 0 (docs/DADOS.md):
  // são votos de candidato com destinação anulada, não voto nulo de urna.
  if (tot.anulados) itens.push(linha('Anulados', num(tot.anulados)));
  if (tot.anulados_sub_judice) itens.push(linha('Anulados sub judice', num(tot.anulados_sub_judice)));
  return `<dl class="metricas">${itens.join('')}</dl>`;
}

function cartaoExterior() {
  const e = S.br.exterior;
  const venc = e.vencedor ? candidato(e.vencedor) : null;
  const r = S.candidato && S.resumo && S.resumo.candidatos[String(S.candidato)];
  return (
    '<div class="cartao">' +
    `<h3><i style="background:${e.cor_mistura}"></i> Exterior</h3>` +
    `<p>${num(e.n_locais)} seções no exterior · ${num(e.totais.validos)} votos válidos` +
    (venc ? ` · ${venc.nm_urna} à frente por ${pct(e.margem_pp, 1)}` : '') +
    ' — sem mapa nesta versão (o TSE não publica coordenadas dos postos).</p>' +
    (r
      ? `<p><b>${candidato(S.candidato).nm_urna}</b> no exterior: ${pct(r.exterior.pct, 2)} ` +
        `(${num(r.exterior.votos)} votos, ${r.exterior.posicao}º lugar), 1º em ` +
        `${num(r.exterior.locais_vencidos)} de ${num(r.exterior.locais_com_voto)} postos.</p>`
      : '') +
    '<button type="button" id="abrir-exterior">Ver os 186 locais</button>' +
    '</div>'
  );
}

function listaMunicipios(dados) {
  const itens = dados.municipios
    .slice()
    .sort((a, b) => b.totais.validos - a.totais.validos)
    .slice(0, 12);
  return (
    '<div class="secao"><h3>Maiores municípios (votos válidos)</h3><ul class="lista-mun">' +
    itens
      .map(
        (m) =>
          `<li data-ibge="${m.cd_mun_ibge}"><i style="background:${corDeRegiao(m)}"></i>` +
          `<span class="nm">${titulo(m.nome)}</span>` +
          `<span class="vl">${num(m.totais.validos)}</span></li>`
      )
      .join('') +
    '</ul></div>'
  );
}

/* --------------------- cor dos swatches do painel -------------------------
 * Mesmas cores do mapa, sempre lidas prontas: `cor_mistura`/`cor_margem` do
 * registro, `meta.cor_nao_venceu`, ou o stop de `meta.escala_forca` mais
 * próximo do valor — nenhuma interpolação é feita aqui. */

function corForca(valor) {
  const stops = S.meta.escala_forca[String(S.candidato)];
  if (valor === null || valor === undefined || !isFinite(valor)) return S.meta.cor_sem_votos;
  const teto = S.meta.forca_p98[String(S.candidato)];
  const i = Math.round(Math.max(0, Math.min(1, valor / teto)) * (stops.length - 1));
  return stops[i];
}

function pctDeRegiao(reg) {
  if (reg.votos_cand) return pctDe(reg, S.candidato);
  if (reg.cd_mun_ibge) return pctMunicipio(reg.cd_mun_ibge);
  return null;
}

function corDeRegiao(reg) {
  const m = modoEfetivo();
  if (m === 'mistura' || m === 'margem') return reg[CAMPO_COR[m]];
  if (m === 'venceu') {
    return reg.vencedor === S.candidato ? reg.cor_margem : S.meta.cor_nao_venceu;
  }
  return corForca(pctDeRegiao(reg));
}

// ====================== painel: candidato selecionado =======================

/** Ranking exato das 27 UFs pelo % do candidato — calculado dos votos
 *  absolutos de `br.json.ufs[].votos_cand`, que já está carregado. */
function rankingUfs(nr) {
  return S.br.ufs
    .map((u) => ({ uf: u.uf, nome: u.nome, pct: pctDe(u, nr), votos: votosDe(u, nr) }))
    .filter((x) => x.pct !== null)
    .sort((a, b) => b.pct - a.pct);
}

function topLista(rotulo, linhas, campos, porPct) {
  if (!linhas || !linhas.length) return '';
  const iPct = campos.indexOf('pct');
  const iVotos = campos.indexOf('votos');
  const iNome = campos.indexOf('nome');
  const iUf = campos.indexOf('uf');
  return (
    `<div class="secao"><h3>${rotulo}</h3><ol class="top-mun">` +
    linhas
      .map(
        (l) =>
          `<li data-ibge="${l[0]}"><span class="nm">${titulo(l[iNome])}` +
          `<span class="uf">${String(l[iUf]).toUpperCase()}</span></span>` +
          `<span class="vl">${porPct ? pct(l[iPct], 2) : num(l[iVotos])}</span>` +
          `<span class="vl2">${porPct ? `${num(l[iVotos])} v.` : pct(l[iPct], 2)}</span></li>`
      )
      .join('') +
    '</ol></div>'
  );
}

function blocoCandidato(reg, nivel) {
  const nr = S.candidato;
  const info = S.meta.candidatos[String(nr)];
  const r = S.resumo && S.resumo.candidatos[String(nr)];
  if (!info || !r) return '';

  let aqui;
  if (nivel === 'br') {
    aqui = { pct: info.pct_validos, votos: info.votos, rot: 'no Brasil' };
  } else if (nivel === 'uf') {
    const u = S.br.ufs.find((x) => x.uf === S.uf);
    aqui = { pct: pctDe(u, nr), votos: votosDe(u, nr), rot: titulo(u.nome) };
  } else {
    const par = (reg.votos || []).find((v) => v[0] === nr);
    aqui = { pct: pctDeRegiao(reg), votos: par ? par[1] : null, rot: titulo(reg.nome) };
  }

  const rank = rankingUfs(nr);
  const melhor = rank[0];
  const pior = rank[rank.length - 1];
  const ufsVencidas = S.br.ufs.filter((u) => u.vencedor === nr).length;
  const total = S.resumo.n_municipios_br;
  const e = r.exterior;

  const celula = (rot, valor, extra) =>
    `<div><dt>${rot}</dt><dd>${valor}${extra ? ` <small>${extra}</small>` : ''}</dd></div>`;

  let vencidos = `${num(r.municipios_vencidos)} <small>de ${num(total)}</small>`;
  if (nivel !== 'br' && S.uf) {
    const nUf = (S.meta.ufs.find((u) => u.sigla === S.uf) || {}).n_municipios;
    const nesta = r.municipios_vencidos_por_uf[S.uf] || 0;
    vencidos += `<br><small>${num(nesta)} de ${num(nUf)} em ${S.uf.toUpperCase()}</small>`;
  }

  const topUfs = Object.entries(r.municipios_vencidos_por_uf)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6);

  return (
    '<div class="secao cand-bloco">' +
    `<h3>Candidato selecionado</h3>` +
    `<div class="cand-cabeca"><i style="background:${info.cor}"></i>` +
    `<span class="nm">${info.nm_urna}` +
    (info.partido ? ` <span class="partido">${info.partido}</span>` : '') +
    '</span>' +
    `<span class="pct">${pct(aqui.pct, 2)}</span></div>` +
    `<p class="dica cand-aqui">${pct(aqui.pct, 2)} dos válidos ${
      nivel === 'br' ? 'no Brasil' : `em ${aqui.rot}`
    }${aqui.votos !== null && aqui.votos !== undefined ? ` · ${num(aqui.votos)} votos` : ''}</p>` +
    '<dl class="metricas">' +
    celula('Municípios vencidos', vencidos) +
    celula('UFs vencidas', `${num(ufsVencidas)} <small>de 27</small>`) +
    celula(
      'Melhor UF',
      melhor ? `${melhor.uf.toUpperCase()} <small>${pct(melhor.pct, 2)}</small>` : '—'
    ) +
    celula('Pior UF', pior ? `${pior.uf.toUpperCase()} <small>${pct(pior.pct, 2)}</small>` : '—') +
    celula(
      'Exterior',
      `${pct(e.pct, 2)} <small>${e.posicao}º lugar</small>`,
      `${num(e.votos)} votos`
    ) +
    celula(
      'Postos vencidos',
      `${num(e.locais_vencidos)} <small>de ${num(e.locais_com_voto)}</small>`
    ) +
    '</dl>' +
    (topUfs.length
      ? '<div class="chips">' +
        topUfs
          .map(
            ([sigla, n]) =>
              `<span class="chip" title="municípios vencidos em ${sigla.toUpperCase()}">` +
              `${sigla.toUpperCase()} ${num(n)}</span>`
          )
          .join('') +
        '</div>'
      : '') +
    '</div>' +
    topLista('Top 10 municípios por % dos válidos', r.top_pct, S.resumo.formato_top, true) +
    topLista('Top 10 municípios por votos absolutos', r.top_votos, S.resumo.formato_top, false)
  );
}

function pintarPainel(reg, nivel) {
  const tot = reg.totais;
  const st = rotuloTotalizacao(tot);
  const onde =
    nivel === 'mun'
      ? `${titulo(S.ufs.get(S.uf).uf.nome)} · município · TSE ${reg.cd_mun_tse} · IBGE ${reg.cd_mun_ibge}`
      : nivel === 'uf'
        ? `Unidade federativa · ${num(S.meta.ufs.find((u) => u.sigla === S.uf)?.n_municipios)} municípios`
        : 'Presidente · 1º turno · 04/10/2026';

  let html =
    '<div class="p-cabeca">' +
    `<h2>${titulo(reg.nome)}</h2>` +
    `<div class="onde">${onde}</div>` +
    `<span class="selo ${st.classe}">Totalização: ${st.texto}</span>` +
    (tot.matematicamente_definido === 's'
      ? '<span class="selo">2º turno matematicamente definido</span>'
      : '') +
    '</div>';

  if (S.candidato) html += blocoCandidato(reg, nivel);

  html += `<div class="secao"><h3>Votos válidos por candidato</h3>${barras(reg)}</div>`;
  html += `<div class="secao"><h3>Comparecimento e votos</h3>${metricas(tot)}</div>`;

  if (nivel === 'br') html += cartaoExterior();
  if (nivel === 'uf') html += listaMunicipios(S.ufs.get(S.uf));
  if (nivel === 'br') {
    html += '<p class="dica">Clique numa UF para abrir os municípios dela, ou use o campo de busca.</p>';
  } else if (nivel === 'uf') {
    html += '<p class="dica">Clique num município no mapa para ver o resultado dele.</p>';
  }

  $('#painel-conteudo').innerHTML = html;
  $('#painel').scrollTop = 0;

  const botao = $('#abrir-exterior');
  if (botao) botao.addEventListener('click', abrirExterior);
  document.querySelectorAll('.lista-mun li, .top-mun li').forEach((li) =>
    li.addEventListener('click', () => irParaMunicipioGlobal(li.dataset.ibge))
  );
}

// =============================== legenda ====================================

/** Candidatos que de fato vencem alguma região da camada visível. */
function vencedoresVisiveis() {
  let regs;
  if (S.uf) regs = S.ufs.get(S.uf).municipios;
  else if (S.camadaBr === 'mun' && S.indice) regs = Array.from(S.indice.values());
  else regs = S.br.ufs;
  const vistos = new Map();
  for (const r of regs) if (r.vencedor) vistos.set(r.vencedor, (vistos.get(r.vencedor) || 0) + 1);
  return Array.from(vistos.entries()).sort((a, b) => b[1] - a[1]);
}

/** `linear-gradient` a partir dos stops prontos, posicionados nas frações
 *  dadas. O CSS só interpola ENTRE stops vizinhos (em sRGB), e é por isso que
 *  o Python exporta vários: o erro por segmento fica imperceptível e a
 *  legenda bate com o mapa, que usa exatamente os mesmos stops. */
function gradiente(stops, fracoes) {
  return (
    'linear-gradient(to right,' +
    stops.map((hex, i) => `${hex} ${(fracoes[i] * 100).toFixed(3)}%`).join(',') +
    ')'
  );
}

function legendaCandidato() {
  const nr = String(S.candidato);
  const info = S.meta.candidatos[nr];
  const cabeca =
    `<h3><i class="sw-cand" style="background:${info.cor}"></i>${info.nm_urna}` +
    (info.partido ? ` <span class="partido">${info.partido}</span>` : '') +
    '</h3>';

  if (S.modoCand === 'venceu') {
    const paradas = S.meta.escala_margem_pp;
    const fim = paradas[paradas.length - 1];
    const fundo = gradiente(
      S.meta.escala_margem[nr],
      paradas.map((v) => v / fim)
    );
    return (
      cabeca +
      `<div class="rampa"><span class="barra" style="background:${fundo}"></span></div>` +
      `<div class="escala"><span>0 p.p. (empate)</span><span>${fim}+ p.p.</span></div>` +
      '<div class="sw sw-fora">' +
      `<i style="background:${S.meta.cor_nao_venceu};opacity:${S.meta.opacidade_nao_venceu}"></i>` +
      '<span>não foi 1º colocado</span></div>' +
      `<p class="nota">Só as regiões em que ${info.nm_urna} foi o 1º colocado, na cor dele, ` +
      `mais escura quanto maior a margem sobre o 2º (satura em ${fim} p.p.).</p>`
    );
  }

  const teto = S.meta.forca_p98[nr];
  const fr = S.meta.escala_forca_fracoes;
  const fundo = gradiente(S.meta.escala_forca[nr], fr);
  const ticks = [0, 1 / 3, 2 / 3, 1].map((t, i, arr) =>
    i === arr.length - 1 ? `≥ ${pct(teto, teto < 1 ? 3 : 1)}` : pct(t * teto, teto < 1 ? 3 : 1)
  );
  return (
    cabeca +
    `<div class="rampa"><span class="barra" style="background:${fundo}"></span></div>` +
    `<div class="escala ticks">${ticks.map((t) => `<span>${t}</span>`).join('')}</div>` +
    `<p class="nota">% dos votos válidos de ${info.nm_urna} em cada região. A escala vai de 0 ` +
    `ao percentil ${S.meta.forca_percentil} dele entre os ${num(S.meta.n_municipios_br)} ` +
    `municípios (${pct(teto, teto < 1 ? 3 : 1)}); acima disso satura.` +
    (info.acromatico
      ? ' Como a cor dele é cinza, a rampa é a <b>escala neutra única</b> usada pelos 7 ' +
        'candidatos com menos de 1% dos válidos.'
      : '') +
    '</p>'
  );
}

function desenharLegenda() {
  const el = $('#legenda');
  if (S.candidato) {
    el.innerHTML = legendaCandidato();
    return;
  }
  if (S.modo === 'mistura') {
    const principais = S.br.br.votos.map(([nr]) => nr);
    el.innerHTML =
      '<h3>Mistura ponderada</h3><div class="swatches">' +
      principais
        .map((nr) => {
          const c = candidato(nr);
          // dois rótulos: o longo para desktop, o curto (sigla) para celular —
          // a troca é só CSS (`#legenda .sw-nome { display: none }` no mobile).
          return (
            `<span class="sw" title="${c.nm_urna}"><i style="background:${c.cor}"></i>` +
            `<span class="sw-nome">${c.nm_urna}${c.partido ? ` (${c.partido})` : ''}</span>` +
            `<span class="sw-sigla">${c.partido || c.nm_urna}</span></span>`
          );
        })
        .join('') +
      '</div>' +
      '<p class="nota">A cor de cada região é a <b>combinação</b> das cores dos candidatos, ponderada pelos votos válidos (mistura em OKLab).</p>';
    return;
  }

  // Rampa com os stops EXPORTADOS do Python (`meta.escala_margem`): o CSS só
  // posiciona os stops, não interpola a cor de ponta a ponta — se deixássemos
  // `linear-gradient(neutro, cor)`, o navegador interpolaria em sRGB e a
  // legenda não bateria com o mapa, que interpola em OKLab.
  const paradas = S.meta.escala_margem_pp;
  const fim = paradas[paradas.length - 1];
  const rampa = (nr) => {
    const stops = S.meta.escala_margem[String(nr)];
    if (!stops) return '';
    const css = stops.map((hex, i) => `${hex} ${(paradas[i] / fim) * 100}%`).join(',');
    const c = candidato(nr);
    return (
      `<div class="rampa"><span class="nome">${c.partido || c.nm_urna}</span>` +
      `<span class="barra" title="${c.nm_urna}" style="background:linear-gradient(to right,${css})"></span></div>`
    );
  };
  const nrs = vencedoresVisiveis().map(([nr]) => nr).slice(0, 5);
  el.innerHTML =
    '<h3>Vencedor + margem</h3>' +
    (nrs.length ? nrs.map(rampa).join('') : rampa(13) + rampa(22)) +
    `<div class="escala"><span>0 p.p. (empate)</span><span>${fim}+ p.p.</span></div>` +
    '<p class="nota">Cor do 1º colocado, mais clara quanto menor a margem sobre o 2º. Satura em ' +
    `${fim} p.p.</p>`;
}

// ============================== busca =======================================

let idxBusca = null;

async function prepararBusca() {
  if (idxBusca) return;
  await garantirIndice();
  idxBusca = Array.from(S.indice.values()).map((m) => ({
    ibge: m.cd_mun_ibge,
    uf: m.uf,
    nome: titulo(m.nome),
    chave: semAcento(m.nome),
  }));
}

function desenharBusca(itens) {
  const ul = $('#busca-resultados');
  if (!itens) { ul.hidden = true; return; }
  ul.innerHTML = itens.length
    ? itens
        .map(
          (m) =>
            `<li role="option" data-ibge="${m.ibge}"><span>${m.nome}</span><span class="uf">${m.uf}</span></li>`
        )
        .join('')
    : '<li class="vazio">nenhum município encontrado</li>';
  ul.hidden = false;
  ul.querySelectorAll('li[data-ibge]').forEach((li) =>
    li.addEventListener('mousedown', (ev) => {
      ev.preventDefault();
      $('#busca').value = '';
      desenharBusca(null);
      irParaMunicipioGlobal(li.dataset.ibge);
    })
  );
}

// ============================== exterior ====================================

const COLUNAS_EXT_BASE = [
  { id: 'nome', rot: 'Local', tipo: 'txt' },
  { id: 'validos', rot: 'Válidos', tipo: 'n' },
  { id: 'eleitorado', rot: 'Eleitorado', tipo: 'n' },
  { id: 'comparecimento', rot: 'Compar.', tipo: 'n' },
  { id: 'abstencao', rot: 'Abstenção', tipo: 'n' },
  { id: 'brancos', rot: 'Brancos', tipo: 'n' },
  { id: 'nulos_tvn', rot: 'Nulos', tipo: 'n' },
  { id: 'vencedor', rot: '1º colocado', tipo: 'txt' },
  { id: 'margem_pp', rot: 'Margem', tipo: 'pp' },
];

/** Com um candidato selecionado, a tabela ganha 2 colunas dele (votos e % dos
 *  válidos do posto), calculadas do `votos_cand` de `exterior.json` — que traz
 *  os 12 candidatos, inclusive os que o `votos[]` agrupado esconde em
 *  "Outros". O exterior não tem mapa (F2.1), então é aqui que o candidato
 *  selecionado aparece. */
function colunasExt() {
  if (!S.candidato) return COLUNAS_EXT_BASE;
  const c = candidato(S.candidato);
  const cols = COLUNAS_EXT_BASE.slice();
  cols.splice(
    1,
    0,
    { id: 'cand_votos', rot: `${c.nm_urna} (votos)`, tipo: 'n' },
    { id: 'cand_pct', rot: `${c.nm_urna} (%)`, tipo: 'pp' }
  );
  return cols;
}

function valorExt(reg, col) {
  if (col.id === 'nome') return reg.nome;
  if (col.id === 'vencedor') return reg.vencedor ? candidato(reg.vencedor).nm_urna : '';
  if (col.id === 'margem_pp') return reg.margem_pp === null ? -1 : reg.margem_pp;
  if (col.id === 'cand_votos') {
    const v = votosDe(reg, S.candidato);
    return v === null || v === undefined ? -1 : v;
  }
  if (col.id === 'cand_pct') {
    const p = pctDe(reg, S.candidato);
    return p === null ? -1 : p;
  }
  return reg.totais[col.id] ?? 0;
}

function textoExt(reg, col) {
  if (col.id === 'nome') {
    return `<span class="cor" style="background:${corDeRegiao(reg)}"></span>${titulo(reg.nome)}`;
  }
  const v = valorExt(reg, col);
  if (col.tipo === 'txt') return v || '—';
  if (col.tipo === 'pp') return v < 0 ? '—' : pct(v, col.id === 'cand_pct' ? 2 : 1);
  return v < 0 ? '—' : num(v);
}

function desenharTabelaExterior() {
  const colunas = colunasExt();
  if (!colunas.some((c) => c.id === S.ordemExterior.col)) {
    S.ordemExterior = { col: 'validos', desc: true };
  }
  const { col, desc } = S.ordemExterior;
  const cfg = colunas.find((c) => c.id === col);
  const linhas = S.exterior.locais.slice().sort((a, b) => {
    const va = valorExt(a, cfg);
    const vb = valorExt(b, cfg);
    if (cfg.tipo === 'txt') return desc ? String(vb).localeCompare(String(va), 'pt-BR') : String(va).localeCompare(String(vb), 'pt-BR');
    return desc ? vb - va : va - vb;
  });

  $('#tabela-exterior thead').innerHTML =
    '<tr>' +
    colunas
      .map(
        (c) =>
          `<th data-col="${c.id}"${c.id.startsWith('cand_') ? ' class="cand"' : ''}>${c.rot}` +
          `<span class="ord">${c.id === col ? (desc ? ' ▼' : ' ▲') : ''}</span></th>`
      )
      .join('') +
    '</tr>';

  $('#tabela-exterior tbody').innerHTML = linhas
    .map(
      (reg) =>
        '<tr>' +
        colunas
          .map(
            (c) =>
              `<td${c.id.startsWith('cand_') ? ' class="cand"' : ''}>${textoExt(reg, c)}</td>`
          )
          .join('') +
        '</tr>'
    )
    .join('');

  $('#tabela-exterior thead').querySelectorAll('th').forEach((th) =>
    th.addEventListener('click', () => {
      const id = th.dataset.col;
      S.ordemExterior = {
        col: id,
        desc: S.ordemExterior.col === id ? !S.ordemExterior.desc : true,
      };
      desenharTabelaExterior();
    })
  );
}

async function abrirExterior() {
  if (!S.exterior) {
    ocupado(1, 'Carregando exterior…');
    try {
      S.exterior = await obter('data/exterior.json', true);
    } finally {
      ocupado(-1);
    }
  }
  const a = S.exterior.agregado;
  let nota =
    `${S.exterior.locais.length} locais de votação no exterior · ` +
    `${num(a.totais.eleitorado)} eleitores · ${num(a.totais.validos)} votos válidos · ` +
    `${num(a.totais.comparecimento)} compareceram. Sem mapa nesta versão: o config do TSE ` +
    'não traz país nem coordenadas dos postos (ver F2.1 no roadmap). Clique num título para ordenar.';
  if (S.candidato) {
    const c = candidato(S.candidato);
    const r = S.resumo && S.resumo.candidatos[String(S.candidato)];
    nota +=
      ` Ordenado pelos votos de ${c.nm_urna}` +
      (r
        ? `, que teve ${num(r.exterior.votos)} votos no exterior (${pct(r.exterior.pct, 2)}, ` +
          `${r.exterior.posicao}º lugar) e foi 1º em ${num(r.exterior.locais_vencidos)} ` +
          `dos ${num(r.exterior.locais_com_voto)} postos com voto válido.`
        : '.');
    S.ordemExterior = { col: 'cand_votos', desc: true };
  }
  $('#modal-nota').textContent = nota;
  desenharTabelaExterior();
  $('#modal-exterior').hidden = false;
}

// ========================== estado de navegação =============================

/** Redesenha painel + legenda + cores sem mexer no enquadramento do mapa. */
function redesenhar() {
  aplicarModoNoMapa();
  desenharLegenda();
  if (S.municipio) {
    const reg = S.ufs.get(S.uf).municipios.find((m) => String(m.cd_mun_ibge) === S.municipio);
    pintarPainel(reg, 'mun');
  } else if (S.uf) {
    pintarPainel(S.ufs.get(S.uf).uf, 'uf');
  } else {
    pintarPainel(S.br.br, 'br');
  }
  if (!$('#modal-exterior').hidden) desenharTabelaExterior();
}

/** Reflete `S` nos controles (usado também ao restaurar estado da URL). */
function sincronizarControles() {
  document
    .querySelectorAll('[data-camada]')
    .forEach((b) => b.classList.toggle('ativo', b.dataset.camada === S.camadaBr));
  document
    .querySelectorAll('[data-modo]')
    .forEach((b) => b.classList.toggle('ativo', b.dataset.modo === S.modo));
  document
    .querySelectorAll('[data-cmodo]')
    .forEach((b) => b.classList.toggle('ativo', b.dataset.cmodo === S.modoCand));
  $('#candidato').value = S.candidato ? String(S.candidato) : '';
  const bolinha = $('#cor-candidato');
  bolinha.hidden = !S.candidato;
  if (S.candidato) bolinha.style.background = S.meta.candidatos[String(S.candidato)].cor;
  $('#grupo-modo').hidden = !!S.candidato;
  $('#grupo-modo-cand').hidden = !S.candidato;
}

/** Aplica a troca de candidato (ou a saída dele): carrega o que falta,
 *  repinta e atualiza a URL. */
async function aplicarCandidato(nr) {
  S.candidato = nr || null;
  if (S.candidato) {
    await garantirResumo();
    await prepararPctDoCandidato();
  } else {
    // sem candidato o mapa volta exatamente ao comportamento original
    for (const [id, geo] of [
      [FONTES.uf, S.geoUf],
      [FONTES.munbr, S.geoMunBr],
      [FONTES.munuf, S.uf ? S.geoMunUf.get(S.uf) : null],
    ]) {
      if (!geo) continue;
      for (const f of geo.features) delete f.properties.pct_cand;
      recarregarFonte(id, geo);
    }
  }
  sincronizarControles();
  redesenhar();
  escreverUrl(false);
}

/** `?camada=&uf=&mun=&modo=&candidato=` — `modo` guarda o modo EFETIVO
 *  (mistura|margem|venceu|forca), como pedido na especificação do F2.2. */
function escreverUrl(push) {
  if (S.restaurando || !S.meta) return;
  const p = new URLSearchParams();
  if (S.uf) p.set('uf', S.uf);
  else if (S.camadaBr === 'mun') p.set('camada', 'mun');
  if (S.municipio) p.set('mun', S.municipio);
  p.set('modo', modoEfetivo());
  if (S.candidato) p.set('candidato', String(S.candidato));
  const url = `${location.pathname}?${p.toString()}`;
  if (push && url !== location.pathname + location.search) history.pushState(null, '', url);
  else history.replaceState(null, '', url);
}

async function aplicarUrl() {
  const p = new URLSearchParams(location.search);
  S.restaurando = true;
  try {
    const nr = Number(p.get('candidato'));
    S.candidato = S.meta.candidatos[String(nr)] ? nr : null;

    const modo = p.get('modo');
    if (modo === 'venceu' || modo === 'forca') S.modoCand = modo;
    else if (modo === 'mistura' || modo === 'margem') S.modo = modo;

    if (S.candidato) await garantirResumo();

    const uf = (p.get('uf') || '').toLowerCase();
    const temUf = uf && uf !== 'zz' && S.meta.ufs.some((u) => u.sigla === uf);
    S.camadaBr = p.get('camada') === 'mun' ? 'mun' : 'uf';
    if (temUf) {
      await irParaUf(uf);
      const mun = p.get('mun');
      if (mun) await selecionarMunicipio(String(mun), false);
    } else {
      await irParaBrasil(S.camadaBr);
    }
  } finally {
    S.restaurando = false;
  }
  sincronizarControles();
  escreverUrl(false);
}

// ================================ eventos ===================================

function ligarEventos() {
  document.querySelectorAll('[data-camada]').forEach((b) =>
    b.addEventListener('click', async () => {
      document.querySelectorAll('[data-camada]').forEach((o) => o.classList.remove('ativo'));
      b.classList.add('ativo');
      await irParaBrasil(b.dataset.camada);
    })
  );

  document.querySelectorAll('[data-modo]').forEach((b) =>
    b.addEventListener('click', () => {
      document.querySelectorAll('[data-modo]').forEach((o) => o.classList.remove('ativo'));
      b.classList.add('ativo');
      S.modo = b.dataset.modo;
      redesenhar();
      escreverUrl(false);
    })
  );

  document.querySelectorAll('[data-cmodo]').forEach((b) =>
    b.addEventListener('click', async () => {
      document.querySelectorAll('[data-cmodo]').forEach((o) => o.classList.remove('ativo'));
      b.classList.add('ativo');
      S.modoCand = b.dataset.cmodo;
      await prepararPctDoCandidato();
      redesenhar();
      escreverUrl(false);
    })
  );

  $('#candidato').addEventListener('change', (e) => {
    aplicarCandidato(e.target.value ? Number(e.target.value) : null);
  });

  window.addEventListener('popstate', () => aplicarUrl());

  $('#trilha').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-ir]');
    if (!b) return;
    if (b.dataset.ir === 'br') irParaBrasil();
    else irParaUf(S.uf);
  });

  $('#btn-voltar').addEventListener('click', () => {
    if (S.municipio) irParaUf(S.uf);
    else irParaBrasil();
  });

  $('#painel-alternar').addEventListener('click', () => {
    document.body.classList.toggle('painel-fechado');
    $('#painel-alternar').setAttribute(
      'aria-expanded',
      String(!document.body.classList.contains('painel-fechado'))
    );
    setTimeout(() => map.resize(), 220);
  });

  const busca = $('#busca');
  busca.addEventListener('focus', prepararBusca);
  busca.addEventListener('input', async () => {
    const q = semAcento(busca.value.trim());
    if (q.length < 2) return desenharBusca(null);
    await prepararBusca();
    desenharBusca(idxBusca.filter((m) => m.chave.includes(q)).slice(0, 25));
  });
  busca.addEventListener('blur', () => setTimeout(() => desenharBusca(null), 120));
  busca.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { busca.value = ''; desenharBusca(null); busca.blur(); }
  });

  $('#modal-fechar').addEventListener('click', () => { $('#modal-exterior').hidden = true; });
  $('#modal-exterior').addEventListener('click', (e) => {
    if (e.target.id === 'modal-exterior') $('#modal-exterior').hidden = true;
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') $('#modal-exterior').hidden = true;
  });
}

// ================================ início ====================================

function rodape() {
  const s = S.meta.snapshot;
  const st = rotuloTotalizacao({
    status_totalizacao: s.status_totalizacao,
    tf_judicial: s.tf_judicial,
  });
  $('#pe-fonte').innerHTML =
    `Fonte: <a href="${S.meta.fonte_url}" target="_blank" rel="noopener">${S.meta.fonte}</a>` +
    ` · snapshot de ${s.dg} ${s.hg} (totalização ${st.texto})`;
  $('#pe-extra').innerHTML =
    `· geração ${s.idg} · exportado em ${S.meta.gerado_em.slice(0, 16).replace('T', ' ')}` +
    ' · malha municipal: IBGE 2024 (geobr), simplificada';
}

/** Seletor de candidato: cor + nome + % nacional, na ordem de votação. */
function montarSeletor() {
  const sel = $('#candidato');
  for (const nr of S.meta.ordem_candidatos) {
    const c = S.meta.candidatos[String(nr)];
    const op = document.createElement('option');
    op.value = String(nr);
    op.textContent = `${c.nm_urna}${c.partido ? ` (${c.partido})` : ''} — ${pct(c.pct_validos, 2)}`;
    // o navegador não pinta o fundo de <option> em todas as plataformas; a
    // bolinha de cor fica ao lado do seletor (ver `#cor-candidato` no CSS) e é
    // atualizada em `sincronizarControles`.
    sel.appendChild(op);
  }
}

async function iniciar() {
  ocupado(1, 'Carregando resultados…');
  try {
    S.meta = await obter('data/meta.json', false);
    S.br = await obter('data/resultados/br.json', true);
    rodape();
    document.title = `Presidente 2026, 1º turno — mapa de resultados (TSE ${S.meta.snapshot.dg})`;
    montarSeletor();
    const geo = await garantirGeoUf();
    adicionarCamada(FONTES.uf, geo, 'cd_uf_ibge', 0.8);
    map.fitBounds(LIMITES_BR, { padding: 24, duration: 0 });
    pintarPainel(S.br.br, 'br');
    desenharLegenda();
    desenharTrilha();
    ligarEventos();
    await aplicarUrl();
  } catch (err) {
    $('#painel-conteudo').innerHTML =
      `<p class="dica">Não foi possível carregar os dados: ${err.message}<br><br>` +
      'Rode <code>python scripts/exportar_web.py</code> e sirva a pasta <code>web/</code> ' +
      'com <code>python -m http.server</code>.</p>';
    console.error(err);
  } finally {
    ocupado(-1);
  }
}

map.on('load', iniciar);

})();
