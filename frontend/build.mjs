// Build CSS Portal Engineer.
//   cd frontend && npm install && npm run build
// Hasil ditulis ke ../static/css dan ikut di-commit, jadi server produksi tidak butuh Node.
//
//   static/css/app.css        Tailwind v4: token, kerangka (sidebar, top bar), utilitas. Semua halaman.
//   static/css/preflight.css  Reset Tailwind. Hanya halaman asli Tailwind (login), bukan halaman Bootstrap.
//   static/css/legacy.css     Bootstrap 5.3 diwarnai ulang + Bootstrap Icons + kulit. Halaman lama.
//
// Env untuk lingkungan tanpa npm install: TW_DIR (folder paket tailwindcss), ESBUILD_BIN (biner esbuild).
import { readFileSync, writeFileSync, readdirSync, statSync, mkdirSync, existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { gzipSync } from 'node:zlib';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const SRC = path.join(HERE, 'src');
const OUT = path.join(ROOT, 'static', 'css');
const TW_DIR = process.env.TW_DIR || path.join(HERE, 'node_modules', 'tailwindcss');
const ESBUILD = process.env.ESBUILD_BIN || path.join(HERE, 'node_modules', '.bin', 'esbuild');

// "properties" paling awal, seperti keluaran Tailwind sendiri. Urutan ini harus sama di ketiga berkas.
const LAYERS = '@layer properties, override, bootstrap, theme, base, skin, components, utilities;';
const BANNER =
  '/*! Portal Engineer, hasil build: jangan edit, ubah sumbernya di frontend/src. ' +
  'Memuat Bootstrap 5.3.0 dan Bootstrap Icons 1.10.5 (MIT, The Bootstrap Authors) ' +
  'serta Tailwind CSS (MIT, Tailwind Labs, Inc.). */\n';

// Kelas polos yang akan bertabrakan dengan kelas komponen Bootstrap bila dibuat Tailwind jadi utilitas.
const DENY = new Set(['collapse', 'collapsing', 'table', 'container']);

// ---------- warna Bootstrap -> palet Portal Engineer v2 ----------
// Nilai baru tidak boleh sama dengan kunci lain, supaya penggantian berantai tidak terjadi.
const HEX = {
  // biru -> kobalt (aksi utama)
  '#0d6efd': '#254fd9', '#0b5ed7': '#1e3fb3', '#0a58ca': '#1d388f', '#0a53be': '#1c3272',
  '#86b7fe': '#8fb0ff', '#cfe2ff': '#dbe7ff', '#9ec5fe': '#bcd1ff', '#052c65': '#1c3272', '#031633': '#121d47',
  // hijau -> sukses
  '#198754': '#15803d', '#157347': '#126b34', '#146c43': '#0f5a2b', '#13653f': '#0d4f25',
  '#d1e7dd': '#dcf6e6', '#a3cfbb': '#a8e2c0', '#0a3622': '#0a3d1f', '#0f5132': '#0b6b3c',
  // merah -> bahaya
  '#dc3545': '#d92d20', '#bb2d3b': '#b42318', '#b02a37': '#912018', '#a52834': '#7a1a12',
  '#f8d7da': '#fde5e3', '#f1aeb5': '#fbc4bf', '#842029': '#912018', '#58151c': '#55160c',
  // kuning -> amber
  '#ffc107': '#f5a50b', '#ffca2c': '#f7b72e', '#ffc720': '#f7b72e', '#ffcd39': '#f9c75a',
  '#fff3cd': '#fdf0cc', '#ffe69c': '#fbe08a', '#997404': '#84470a', '#664d03': '#5e3306',
  // cyan -> info
  '#0dcaf0': '#1d9bf0', '#31d2f2': '#4db1f4', '#25cff2': '#4db1f4', '#3dd5f3': '#79c4f7',
  '#cff4fc': '#dcecff', '#9eeaf9': '#b9dcfb', '#087990': '#0b57a8', '#055160': '#0a4482',
  // abu -> grafit dingin
  '#6c757d': '#667085', '#5c636a': '#475467', '#565e64': '#384256', '#51585e': '#384256',
  '#c4c8cb': '#c9d0dc', '#e2e3e5': '#eceff5', '#2b2f32': '#1d2433', '#adb5bd': '#98a2b3',
  '#f8f9fa': '#f6f8fb', '#e9ecef': '#eceff5', '#dee2e6': '#e3e7ee', '#ced4da': '#c9d0dc',
  '#495057': '#475467', '#343a40': '#2b3445', '#212529': '#1d2433',
};
const RGB = {
  '13,110,253': '37,79,217', '49,132,253': '56,102,238', '10,88,202': '29,56,143',
  '25,135,84': '21,128,61', '20,108,67': '15,90,43', '60,153,110': '34,160,90',
  '220,53,69': '217,45,32', '176,42,55': '145,32,24', '225,83,97': '240,68,56',
  '255,193,7': '245,165,11', '217,164,6': '217,138,0',
  '13,202,240': '29,155,240', '11,172,204': '29,155,240',
  '108,117,125': '102,112,133', '130,138,145': '102,112,133',
  '248,249,250': '246,248,251', '211,212,213': '201,208,220',
  '33,37,41': '29,36,51', '52,58,64': '43,52,69', '66,70,73': '56,66,86',
};

function recolor(css) {
  for (const [from, to] of Object.entries(HEX)) {
    css = css.replaceAll(from, to);
    css = css.replaceAll('%23' + from.slice(1), '%23' + to.slice(1)); // di dalam data URI SVG
  }
  for (const [from, to] of Object.entries(RGB)) {
    const [a, b, c] = from.split(',');
    css = css.replace(new RegExp(`\\b${a}\\s*,\\s*${b}\\s*,\\s*${c}\\b`, 'g'), to);
  }
  return css;
}

const read = (p) => readFileSync(p, 'utf8');

function bootstrapCss() {
  const css = read(path.join(HERE, 'vendor', 'bootstrap-5.3.0.min.css'))
    .replace(/^@charset "UTF-8";/, '')
    .replace(/\/\*!?[\s\S]*?\*\//g, '');
  return recolor(css);
}

function iconsCss() {
  return read(path.join(HERE, 'vendor', 'bootstrap-icons-1.10.5.min.css'))
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replaceAll('url("fonts/', 'url("../vendor/bootstrap-icons/fonts/');
}

// ---------- pemindai kelas Tailwind ----------
function walk(dir, exts, out = []) {
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) {
      if (name !== 'node_modules' && name !== 'vendor') walk(full, exts, out);
    } else if (exts.some((e) => name.endsWith(e)) && !name.includes('.min.')) {
      out.push(full);
    }
  }
  return out;
}

function collectCandidates() {
  const files = [
    ...walk(path.join(ROOT, 'templates'), ['.html']),
    ...walk(path.join(ROOT, 'static', 'js'), ['.js']),
  ];
  const set = new Set();
  // "!x" di JS adalah negasi, bukan modifier important Tailwind; "col-6" milik grid Bootstrap
  const keep = (t) => t && !t.startsWith('!') && !DENY.has(t) && !/^col-\d+$/.test(t);
  for (const file of files) {
    for (const raw of read(file).match(/[^\s"'`<>=]+/g) ?? []) {
      if (raw.length > 120) continue;
      if (keep(raw)) set.add(raw);
      const trimmed = raw.replace(/^[,;:.(){}]+|[,;:.(){}]+$/g, '');
      if (keep(trimmed)) set.add(trimmed);
    }
  }
  return { files: files.length, list: [...set].sort() };
}

// ---------- Tailwind ----------
const tw = await import(pathToFileURL(path.join(TW_DIR, 'dist', 'lib.mjs')).href);

async function loadStylesheet(id, base) {
  let file;
  if (id === 'tailwindcss') file = path.join(TW_DIR, 'index.css');
  else if (id.startsWith('tailwindcss/')) {
    file = path.join(TW_DIR, id.slice('tailwindcss/'.length));
    if (!path.extname(file)) file += '.css';
  } else file = path.resolve(base, id);
  return { path: file, base: path.dirname(file), content: read(file) };
}

async function tailwind(entry, candidates) {
  const compiler = await tw.compile(read(path.join(SRC, entry)), {
    base: SRC,
    loadStylesheet,
    polyfills: tw.Polyfills.All,
  });
  return compiler.build(candidates);
}

function minify(css) {
  return execFileSync(
    ESBUILD,
    ['--loader=css', '--minify', '--legal-comments=none', '--target=chrome111,safari16.4,firefox128'],
    { input: css, maxBuffer: 256 * 1024 * 1024 },
  ).toString('utf8');
}

function emit(name, css) {
  const out = BANNER + css;
  writeFileSync(path.join(OUT, name), out);
  const kb = (n) => (n / 1024).toFixed(1) + ' KB';
  console.log(`${name.padEnd(14)} ${kb(Buffer.byteLength(out))}  (gzip ${kb(gzipSync(out).length)})`);
}

// ---------- jalankan ----------
mkdirSync(OUT, { recursive: true });
const cands = collectCandidates();
console.log(`memindai ${cands.files} berkas, ${cands.list.length} kandidat kelas`);

emit('app.css', minify(LAYERS + '\n' + (await tailwind('app.css', cands.list))));
emit('preflight.css', minify(LAYERS + '\n' + (await tailwind('preflight.css', []))));

const shimFile = path.join(SRC, 'icons.generated.css');
const legacy =
  LAYERS +
  `\n@layer bootstrap {\n${bootstrapCss()}\n${iconsCss()}\n` +
  `${existsSync(shimFile) ? read(shimFile) : ''}\n${read(path.join(SRC, 'legacy-skin.css'))}\n}\n` +
  `@layer override {\n${read(path.join(SRC, 'legacy-override.css'))}\n}\n`;
emit('legacy.css', minify(legacy));
