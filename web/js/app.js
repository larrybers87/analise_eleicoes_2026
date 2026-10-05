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

  modo: 'mistura',          // 'mistura' | 'margem'
  camadaBr: 'uf',           // 'uf' | 'mun'  (só quando não há UF ativa)
  uf: null,                 // sigla da UF em drill-down
  municipio: null,          // cd_mun_ibge selecionado
  hover: null,              // {fonte, id}
  selecionado: null,        // {fonte, id}
  ordemExterior: { col: 'validos', desc: true },
};

const CAMPO_COR = { mistura: 'cor_mistura', margem: 'cor_margem' };

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

function adicionarCamada(id, geojson, promoteId, larguraLinha) {
  if (map.getSource(id)) return;
  map.addSource(id, { type: 'geojson', data: geojson, promoteId: promoteId });
  map.addLayer({
    id: `${id}-fill`,
    type: 'fill',
    source: id,
    paint: {
      'fill-color': ['coalesce', ['get', CAMPO_COR[S.modo]], '#dddddd'],
      'fill-opacity': [
        'case',
        ['boolean', ['feature-state', 'selecionado'], false], 1,
        ['boolean', ['feature-state', 'hover'], false], 0.86,
        1,
      ],
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
  elTooltip.innerHTML =
    `<b>${titulo(p.nome || p.nm_uf || '')}</b>` +
    (venc
      ? `<span>${venc.nm_urna} · ${pct(p.margem_pp, 1)} de margem</span>`
      : '<span>sem voto válido</span>');
  elTooltip.hidden = false;
  elTooltip.style.left = `${ponto.x}px`;
  elTooltip.style.top = `${ponto.y - 12}px`;
}

function aplicarModoNoMapa() {
  for (const id of Object.values(FONTES)) {
    if (map.getLayer(`${id}-fill`)) {
      map.setPaintProperty(`${id}-fill`, 'fill-color', [
        'coalesce', ['get', CAMPO_COR[S.modo]], '#dddddd',
      ]);
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

  map.fitBounds(LIMITES_BR, { padding: 24, duration: 500 });
  pintarPainel(S.br.br, 'br');
  desenharLegenda();
  desenharTrilha();
}

async function irParaUf(sigla) {
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

  const alvo = (S.geoUf.features || []).find((f) => String(f.properties.uf) === sigla);
  if (alvo) map.fitBounds(bbox(alvo.geometry), { padding: 30, duration: 600 });

  pintarPainel(S.ufs.get(sigla).uf, 'uf');
  desenharLegenda();
  desenharTrilha();
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
  return (
    '<div class="cartao">' +
    `<h3><i style="background:${e.cor_mistura}"></i> Exterior</h3>` +
    `<p>${num(e.n_locais)} seções no exterior · ${num(e.totais.validos)} votos válidos` +
    (venc ? ` · ${venc.nm_urna} à frente por ${pct(e.margem_pp, 1)}` : '') +
    ' — sem mapa nesta versão (o TSE não publica coordenadas dos postos).</p>' +
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
          `<li data-ibge="${m.cd_mun_ibge}"><i style="background:${m[CAMPO_COR[S.modo]]}"></i>` +
          `<span class="nm">${titulo(m.nome)}</span>` +
          `<span class="vl">${num(m.totais.validos)}</span></li>`
      )
      .join('') +
    '</ul></div>'
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
  document.querySelectorAll('.lista-mun li').forEach((li) =>
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

function desenharLegenda() {
  const el = $('#legenda');
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

const COLUNAS_EXT = [
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

function valorExt(reg, col) {
  if (col.id === 'nome') return reg.nome;
  if (col.id === 'vencedor') return reg.vencedor ? candidato(reg.vencedor).nm_urna : '';
  if (col.id === 'margem_pp') return reg.margem_pp === null ? -1 : reg.margem_pp;
  return reg.totais[col.id] ?? 0;
}

function desenharTabelaExterior() {
  const { col, desc } = S.ordemExterior;
  const cfg = COLUNAS_EXT.find((c) => c.id === col);
  const linhas = S.exterior.locais.slice().sort((a, b) => {
    const va = valorExt(a, cfg);
    const vb = valorExt(b, cfg);
    if (cfg.tipo === 'txt') return desc ? String(vb).localeCompare(String(va), 'pt-BR') : String(va).localeCompare(String(vb), 'pt-BR');
    return desc ? vb - va : va - vb;
  });

  $('#tabela-exterior thead').innerHTML =
    '<tr>' +
    COLUNAS_EXT.map(
      (c) =>
        `<th data-col="${c.id}">${c.rot}<span class="ord">${c.id === col ? (desc ? ' ▼' : ' ▲') : ''}</span></th>`
    ).join('') +
    '</tr>';

  $('#tabela-exterior tbody').innerHTML = linhas
    .map((reg) => {
      const venc = reg.vencedor ? candidato(reg.vencedor) : null;
      return (
        '<tr>' +
        `<td><span class="cor" style="background:${reg[CAMPO_COR[S.modo]]}"></span>${titulo(reg.nome)}</td>` +
        `<td>${num(reg.totais.validos)}</td>` +
        `<td>${num(reg.totais.eleitorado)}</td>` +
        `<td>${num(reg.totais.comparecimento)}</td>` +
        `<td>${num(reg.totais.abstencao)}</td>` +
        `<td>${num(reg.totais.brancos)}</td>` +
        `<td>${num(reg.totais.nulos_tvn)}</td>` +
        `<td>${venc ? venc.nm_urna : '—'}</td>` +
        `<td>${reg.margem_pp === null ? '—' : pct(reg.margem_pp, 1)}</td>` +
        '</tr>'
      );
    })
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
  $('#modal-nota').textContent =
    `${S.exterior.locais.length} locais de votação no exterior · ` +
    `${num(a.totais.eleitorado)} eleitores · ${num(a.totais.validos)} votos válidos · ` +
    `${num(a.totais.comparecimento)} compareceram. Sem mapa nesta versão: o config do TSE ` +
    'não traz país nem coordenadas dos postos (ver F2.1 no roadmap). Clique num título para ordenar.';
  desenharTabelaExterior();
  $('#modal-exterior').hidden = false;
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
      aplicarModoNoMapa();
      desenharLegenda();
      // redesenha o painel para as cores de lista/cartão acompanharem o modo
      if (S.municipio) {
        const reg = S.ufs.get(S.uf).municipios.find((m) => String(m.cd_mun_ibge) === S.municipio);
        pintarPainel(reg, 'mun');
      } else if (S.uf) {
        pintarPainel(S.ufs.get(S.uf).uf, 'uf');
      } else {
        pintarPainel(S.br.br, 'br');
      }
      if (!$('#modal-exterior').hidden) desenharTabelaExterior();
    })
  );

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

async function iniciar() {
  ocupado(1, 'Carregando resultados…');
  try {
    S.meta = await obter('data/meta.json', false);
    S.br = await obter('data/resultados/br.json', true);
    rodape();
    document.title = `Presidente 2026, 1º turno — mapa de resultados (TSE ${S.meta.snapshot.dg})`;
    const geo = await garantirGeoUf();
    adicionarCamada(FONTES.uf, geo, 'cd_uf_ibge', 0.8);
    map.fitBounds(LIMITES_BR, { padding: 24, duration: 0 });
    pintarPainel(S.br.br, 'br');
    desenharLegenda();
    desenharTrilha();
    ligarEventos();
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
