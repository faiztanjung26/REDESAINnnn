---
name: Portal Engineer
description: "Konsol Lapangan: CMMS PT Jaya Teknik Indonesia. Bingkai gelap, lembar terang, panel bergaris rambut, biru kobalt hanya untuk aksi."
colors:
  brand-solid: "#254fd9"
  brand-text: "#1e3fb3"
  brand-strong: "#1d388f"
  brand-soft: "#dbe7ff"
  brand-softer: "#eef4ff"
  brand-edge: "#bcd1ff"
  signal: "#e5252b"
  frame: "#0b1020"
  frame-raised: "#151c30"
  canvas: "#f1f3f8"
  surface: "#ffffff"
  surface-2: "#f8f9fd"
  sunken: "#f6f8fb"
  line: "#e3e7ee"
  line-strong: "#c9d0dc"
  ink: "#0f1626"
  ink-soft: "#384256"
  ink-muted: "#5b6579"
  ink-faint: "#98a2b3"
  ok: "#15803d"
  ok-bg: "#dcf6e6"
  ok-ink: "#0b6b3c"
  warn: "#d98a00"
  warn-bg: "#fdf0cc"
  warn-ink: "#84470a"
  bad: "#d92d20"
  bad-bg: "#fde5e3"
  bad-ink: "#a8231a"
  info: "#1d7fe0"
  info-bg: "#dcecff"
  info-ink: "#0b57a8"
  violet: "#7a3fe0"
  violet-bg: "#ece6fd"
  violet-ink: "#5226b5"
  orange: "#e8590c"
  orange-bg: "#ffe8d9"
  orange-ink: "#a23a05"
  mute-bg: "#eaedf3"
  mute-ink: "#475467"
typography:
  page-title:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  page-bar-title:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  panel-title:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.3
  body:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.55
  item-title:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
    lineHeight: 1.4
  meta:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.4
  label-badge:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1
    fontFeature: "tabular-nums"
  stat-value:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "-0.02em"
rounded:
  badge: "6px"
  ctl: "10px"
  card: "14px"
  pop: "24px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  panel: "20px"
  page-gutter: "32px"
  page-gutter-mobile: "14px"
  touch-target: "44px"
components:
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "20px"
  badge-status:
    backgroundColor: "{colors.info-bg}"
    textColor: "{colors.info-ink}"
    typography: "{typography.label-badge}"
    rounded: "{rounded.badge}"
    height: "24px"
    padding: "0 8px"
  badge-priority:
    backgroundColor: "transparent"
    textColor: "{colors.orange-ink}"
    typography: "{typography.label-badge}"
    rounded: "{rounded.badge}"
    height: "24px"
    padding: "0 8px"
  button-primary:
    backgroundColor: "{colors.brand-solid}"
    textColor: "{colors.surface}"
    rounded: "{rounded.ctl}"
    padding: "8px 16px"
    height: "40px"
  button-primary-hover:
    backgroundColor: "{colors.brand-text}"
  button-primary-active:
    backgroundColor: "{colors.brand-strong}"
  button-outline:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.brand-text}"
    rounded: "{rounded.ctl}"
    height: "40px"
  input:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.ink}"
    rounded: "{rounded.ctl}"
    height: "40px"
  tab:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.pill}"
    height: "36px"
    padding: "0 12px"
  tab-active:
    backgroundColor: "{colors.brand-solid}"
    textColor: "{colors.surface}"
  chip:
    backgroundColor: "{colors.brand-softer}"
    textColor: "{colors.brand-text}"
    rounded: "{rounded.pill}"
    height: "32px"
  icon-btn:
    backgroundColor: "transparent"
    textColor: "{colors.ink-muted}"
    rounded: "{rounded.ctl}"
    size: "36px"
  item:
    textColor: "{colors.ink}"
    height: "56px"
    padding: "12px 20px"
  empty-state:
    textColor: "{colors.ink-muted}"
    padding: "48px 24px"
---

# Design System: Portal Engineer

> Dicatat dari kode yang dikirim (cabang `redesain-tailwind`), bukan dari rencana. Sumber nilai: `frontend/src/tokens.css` (token), `patterns.css` (komponen), `shell.css`, `surface-*.css`, `legacy-skin.css`, `legacy-override.css`, `templates/_ui/macros.html`, `templates/base.html`. Nilai di frontmatter adalah nilai terang; nilai gelap ada di bagian Colors dan di `frontend/src/tokens.css`. Baris bertanda "(asumsi)" belum dikonfirmasi pemilik produk (PRODUCT.md dan kontrak arah disusun tanpa wawancara terpisah).

## Overview

**Creative North Star: "Konsol Lapangan"** (nama dari komentar `tokens.css` dan kontrak arah).

Bingkai navy gelap (`--color-frame`) membungkus sidebar dan satu lembar konten terang yang membulat (`--color-canvas`, radius 24px). Di dalam lembar, isi tersusun dari panel bergaris tepi 1px dan baris berpemisah garis rambut, bukan kartu bersusun. Biru kobalt hanya untuk aksi utama dan pilihan aktif; status memakai rona tetap yang selalu bersama teks atau titik/ikon. Merah `--color-signal` hanya penanda identitas Jaya Teknik (satu titik kecil di sidebar), bukan warna status.

Pembaca utamanya teknisi di HP (satu tangan, cahaya terik atau remang) dan supervisor/manajer di laptop atau TV. Karena itu: sasaran ketuk 44px, huruf 16px di input HP, mode gelap, angka tabular di kolom. Kepadatan sedang: teks dasar 14px, panel berlapis garis tipis, hampir tanpa bayangan saat diam.

**Key Characteristics:**
- Terang-gelap lewat token yang sama; `data-bs-theme` pada `<html>`, pilihan di `localStorage` kunci `jt-theme`, bawaan terang.
- Satu keluarga font (Inter); hierarki dari ukuran dan bobot 400/500/600, bukan dari ganti font.
- Status = lencana berisi dengan titik; prioritas = lencana bergaris dengan ikon chevron.
- Halaman lama (Bootstrap) memakai desain yang sama lewat kulit `legacy-skin.css`, bukan lewat penulisan ulang.

## Colors

Palet dingin dan tertahan: grafit kebiruan untuk netral, satu kobalt untuk aksi, enam rona status berpasangan.

### Primary (kobalt)
- **Kobalt Aksi** (`--jt-brand-solid` #254fd9 terang / #3d66f2 gelap): tombol utama, tab aktif, tautan fokus. Putih di atasnya: 6.56:1 (terang), 4.79:1 (gelap), diukur dari nilai token.
- **Teks Kobalt** (`--jt-brand-text` #1e3fb3 / #9db8ff): tautan dan teks aktif di atas latar muda. Di atas `--jt-brand-soft` 6.99:1 terang, 7.31:1 gelap.
- Pendukung: `--jt-brand-strong` #1d388f / #bcd0ff (hover tautan), `--jt-brand-soft` #dbe7ff / #1a2756, `--jt-brand-softer` #eef4ff / #131c40 (chip, filter aktif), `--jt-brand-edge` #bcd1ff / #2b4095 (garis chip). Tangga mentah `--color-brand-50..950` ada di `tokens.css`; komponen memakai token semantik `--jt-brand-*` karena yang itu berbalik di mode gelap.

### Neutral
- **Bingkai** `--color-frame` #0b1020 / #05080f dan `--color-frame-raised` #151c30 / #0d1322: sidebar, kepala mode TV, toast.
- **Kanvas** `--color-canvas` #f1f3f8 / #0b101d: lembar konten. **Permukaan** `--color-surface` #ffffff / #121a2b: panel, tab, input fokus. `--color-surface-2` #f8f9fd / #172036: isian form. `--color-sunken` #f6f8fb / #0e1524: alur segmen, kaki panel.
- **Garis** `--color-line` #e3e7ee / #202b44 (pemisah, tepi panel) dan `--color-line-strong` #c9d0dc / #324064 (tepi kontrol).
- **Tinta** `--color-ink` #0f1626 / #e8ecf6, `--color-ink-soft` #384256 / #c2cae0, `--color-ink-muted` #5b6579 / #93a0bd (5.86:1 di atas surface terang), `--color-ink-faint` #98a2b3 / #67738f.

### Status (rona berpasangan: titik/aksen `--color-X`, latar `-bg`, teks `-ink`)

| Rona | Terang (solid / bg / ink) | Gelap (solid / bg / ink) | Dipakai untuk |
|---|---|---|---|
| ok | #15803d / #dcf6e6 / #0b6b3c | #34d27b / #0f2c1f / #6ee7a7 | Completed, tertib |
| warn | #d98a00 / #fdf0cc / #84470a | #f5b13a / #33260a / #fcd477 | Hold, Medium, menunggu |
| bad | #d92d20 / #fde5e3 / #a8231a | #f2685c / #351513 / #ffa59c | Highest, terlambat, galat |
| info | #1d7fe0 / #dcecff / #0b57a8 | #4ea3f2 / #0e2845 / #8cc8fb | In Progress, Low |
| violet | #7a3fe0 / #ece6fd / #5226b5 | #a78bfa / #241a4a / #c9b8ff | Assigned |
| orange | #e8590c / #ffe8d9 / #a23a05 | #fb923c / #38200d / #ffbf8a | Incompleted, High |
| mute | `--color-ink-faint` / #eaedf3 / #475467 | (ink-faint) / #1b2540 / #aab5d0 | Draft, netral |
| brand (tone) | `--jt-brand-solid` / `--jt-brand-soft` / `--jt-brand-text` | idem | Solved |

Pemetaan status WO ke rona ada satu sumber di makro `status_tone` (`macros.html`): Draft mute, Assigned violet, In Progress info, Hold warn, Solved brand, Completed ok, Incompleted orange; status buatan sendiri jatuh ke `control_type` (Draft mute, Pending warn, Active info, Closed ok), lainnya mute. Prioritas di `priority_badge`: Highest bad, High orange, Medium warn, Low info, lainnya mute.
Pasangan teks-latar `-ink` di atas `-bg` terukur 5.66:1 sampai 7.51:1 (terang) dan 7.38:1 sampai 10.42:1 (gelap). Pegangan WCAG AA 4.5:1 adalah asumsi di PRODUCT.md.

### Named Rules
**The Paired Tone Rule.** Rona selalu dipakai sebagai pasangan (`-bg` + `-ink`, atau solid hanya untuk titik, garis tipis, dan ikon). Teks berwarna tidak pernah memakai nilai solid; gunakan `-ink`. Komponen mengambilnya lewat kelas `tone-*` yang menyetel `--tone`, `--tone-bg`, `--tone-ink`.
**The Faint Is Not Text Rule.** `--color-ink-faint` (2.58:1 di atas surface terang, 3.66:1 gelap) hanya untuk ikon, chevron, dan penanda non-teks. Jangan dipakai untuk teks yang harus terbaca.
**The Cobalt Is Action Rule.** Kobalt hanya untuk aksi utama, tautan, dan pilihan aktif. Jangan dipakai sebagai rona status atau dekorasi.
**The Signal Is Identity Rule.** `--color-signal` hanya penanda identitas Jaya Teknik; tidak pernah menandai galat atau status (itu tugas `bad`).

## Typography

**Display dan Body Font:** Inter (dengan `ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif`). `--font-display` sengaja sama dengan `--font-sans`.
**Mono:** `ui-monospace, "SF Mono", SFMono-Regular, "JetBrains Mono", Menlo, Consolas, "Liberation Mono", monospace` (`--font-mono`).

**Character:** satu keluarga netral; hierarki lewat ukuran dan bobot, judul diketatkan sedikit (`-0.02em`).

### Hierarchy (skala yang benar-benar dipakai)
- **Judul halaman** (600, 1.75rem, 1.2, -0.02em): `.ph-title`; juga angka besar `.jt-attn-n`, `.stat-value` (1.75rem).
- **Judul bar halaman** (600, 1.5rem, 1.15): heading di dalam `.page-bar`; judul mode TV 1.5rem/500.
- **Judul panel** (600, 1rem, 1.3): `.jt-panel-title`, `.jt-empty strong`.
- **Isi** (400, 0.875rem, 1.55): dasar `--bs-body-font-size`; 1rem pada input di layar sentuh (cegah zoom iOS).
- **Judul baris** (600, 0.875rem, 1.4): `.jt-item-title`; **meta** (400, 0.75rem, 1.4): `.jt-item-sub`, catatan.
- **Label lencana, hitungan** (600, 0.75rem, 1): `.jt-badge`, `.jt-count`, `.jt-tab-n`.
- Ukuran antara yang juga muncul: 0.8125rem (tombol sempit, bar jaringan), 0.9375rem (kepala kartu lama).

Bobot yang dimuat: 400, 500, 600 (Google Fonts, `base.html` baris 12). `max-width: 65ch` untuk kalimat di bawah judul (`.ph-sub`).

### Named Rules
**The Tabular Numbers Rule.** Angka dalam kolom, lencana, hitungan, dan kode WO memakai `font-variant-numeric: tabular-nums` (`.jt-n`, `.jt-count`, `.jt-badge`, `.jt-code`, `.wol-link`).
**The Text Beside Color Rule.** Status tidak pernah hanya warna: lencana status membawa teks nama status + titik `jt-dot`; prioritas membawa teks + ikon chevron; tenggat berupa chip bertulisan.

## Layout

- **Kerangka:** sidebar tetap lebar `--jt-sidebar-w` 17rem; lembar konten `margin: 0.625rem (--jt-frame)`; top bar `--jt-topbar-h` 4rem, lengket; area isi `padding: 0.5rem 2rem 3rem`.
- **HP (lebar 768px ke bawah):** bingkai hilang (lembar penuh, radius 0), sidebar jadi laci, navigasi bawah melayang (`.bottom-nav`, kiri-kanan 0.75rem, radius 1.75rem, tombol Scan QR bulat 3.75rem menjorok ke atas), isi `padding` samping 0.875rem dan bawah `7.25rem + safe-area`. Top bar 3.5rem.
- **Sasaran ketuk:** pada `(pointer: coarse), (max-width: 768px)` semua kontrol minimal 44px (2.75rem): `.seg-item`, `.field-group`, `.jt-tab`, `.icon-btn`, `.jt-search`, `.jt-panel-link`, tombol Bootstrap `.btn` 2.875rem, input 2.875rem. Chip tertutup tetap 2.25rem tetapi area tombol hapusnya diperluas ke 44px lewat `::after`.
- **Dasbor:** kepala (`.dash-head`), bar penyaring, jalur Perlu Perhatian (`.jt-attn-grid`: `auto-fit, minmax(9.5rem, 1fr)`), lalu kisi widget (`.jt-grid`); indikator `auto-fit minmax(11rem, 1fr)`. Di HP (640px ke bawah) aksi cepat jadi tiga petak sama lebar, ikon di atas label.
- **Daftar WO:** `.wol-row` adalah grid yang berubah menurut lebar wadah (`@container wol`): kartu per baris di HP, dua baris dengan kode di kiri mulai 36rem, satu baris bergaya tabel dengan kepala kolom lengket mulai 58rem. Tidak ada gulir horizontal di HP.
- **Baris sempit:** `jt-item--stack` memakai container query pada `li` induk (`@container jt-row (max-width: 27rem)`): lencana sisi turun ke baris sendiri, jadi kode WO dan nama aset tidak terpotong, termasuk di widget sempit pada layar lebar.
- **Irama jarak:** 0.25 / 0.5 / 0.75 / 1 / 1.25rem; padding panel 1.25rem, tinggi minimum kepala panel 3.5rem dan baris daftar 3.5rem.
- **Lapisan CSS:** `@layer override, bootstrap, theme, base, skin, components, utilities` (README; Tailwind menambah `properties`). `!important` di `override` menang atas Bootstrap; CSS tanpa lapisan di dalam `<style>` template menang atas semua lapisan. Halaman baru: pakai kelas `patterns.css` dan token, tanpa hex.

## Elevation & Depth

Hibrida tertahan: panel diam hanya punya garis tepi 1px dan bayangan sangat tipis; bayangan besar hanya untuk benda yang melayang. Kedalaman utama datang dari lapisan tonal: bingkai gelap, lembar kanvas, panel permukaan.

### Shadow Vocabulary
- **Kartu** (`--shadow-card`: `0 1px 2px rgb(15 22 38 / 0.05)`; gelap: `inset 0 1px 0 rgb(255 255 255 / 0.04)`): `.jt-panel`, `.card`, `.jt-filters`.
- **Terangkat** (`--shadow-raised`: `0 14px 32px -14px rgb(15 22 38 / 0.22), 0 2px 6px rgb(15 22 38 / 0.05)`): navigasi bawah HP, tombol Scan QR.
- **Angkat** (`--shadow-lift`: `0 18px 40px -16px rgb(15 22 38 / 0.28), 0 4px 10px -4px rgb(15 22 38 / 0.08)`) dan **Pop** (`--shadow-pop`: `0 22px 48px -14px rgb(16 24 40 / 0.32), 0 2px 8px rgb(16 24 40 / 0.06)`): menu, toast, jendela melayang. Nilai gelap lebih pekat (lihat `tokens.css` 152-155).
- **Cincin fokus** (`--jt-focus-ring`: `rgb(56 102 238 / 0.32)` terang, `rgb(120 158 255 / 0.4)` gelap): `0 0 0 3px` pada `.field-group:focus-within`, `0 0 0 4px` pada `.form-control:focus`.

### Named Rules
**The Hairline Panel Rule.** Panel dibatasi garis 1px (`--color-line`), bukan bayangan. Bayangan di atas `--shadow-card` hanya untuk benda yang benar-benar melayang di atas isi.
**The Inset Ring Rule.** Tepi kontrol segmen, lencana, dan field-group digambar dengan `box-shadow: inset 0 0 0 1px`, supaya ukuran tidak bergeser saat keadaan berubah.

## Shapes

Tiga radius dari token: kontrol **10px** (`--radius-ctl`), panel dan kartu **14px** (`--radius-card`), lembar, jendela melayang, modal, dan toast-bingkai **24px** (`--radius-pop`). Tab, chip, dan lencana koneksi berbentuk pil (999px); lencana status dan prioritas 6px (0.375rem); inisial orang dan titik bulat. Segmen di dalam `.seg` memakai radius kontrol dikurangi 4px. Radius dalam panel = radius panel dikurangi 1px.

## Components

### Panel (`jt-panel`)
Wadah dasar: permukaan, garis 1px, radius 14px, `--shadow-card`. Bagian: `-head` (min 3.5rem, garis bawah), `-title` (1rem/600, ikon `--color-ink-faint`), `-tools`, `-link` (teks kobalt, 44px di sentuh), `-body` (padding 1.25rem, `--flush` tanpa padding), `-foot` (latar `--color-sunken`). `jt-panel--clip` memakai `overflow: clip` agar kepala tabel lengket tetap jalan.

### Lencana (`jt-badge`)
Tinggi 1.5rem, radius 6px, teks 0.75rem/600, tabular. **Status** = berisi (`--tone-bg`, teks `--tone-ink`, cincin tipis 30% rona) + `jt-dot` 0.5rem di depan nama. **Prioritas** = `jt-badge--outline` (tanpa isi, cincin 55%) + ikon `bi-chevron-double-up / chevron-up / dash / chevron-down`. Dua bentuk ini sengaja berbeda supaya tidak tertukar saat dipindai. Tenggat: `due_badge` (berisi, ikon `calendar-event`, teks seperti "Terlambat 2 hari").

### Baris daftar (`jt-list`, `jt-item`, `jt-item--stack`)
Baris dengan garis pemisah hanya antar baris yang terlihat. `a.jt-item` punya hover `--jt-hover`, aktif `--jt-press`, fokus outline 2px `--jt-brand-solid` (inset). Chevron `jt-item-go` bergeser 2px saat hover. `wo_item` (macro) memakai `jt-item--stack` (lihat Layout, 27rem).

### Tab status (`jt-tabs`, `jt-tab`)
Pil 2.25rem (2.75rem di sentuh) dengan hitungan `jt-tab-n`; aktif = `--jt-brand-solid` + teks putih; bisa digeser horizontal dengan scroll-snap. Dipakai lewat `aria-current="page"`.

### Chip saringan (`jt-chips`, `jt-chip`)
Pil 2rem berlatar `--jt-brand-softer`, garis `--jt-brand-edge`, tombol hapus bulat 1.75rem; `jt-chip--fixed` netral tanpa tombol hapus; `jt-chips-clear` tautan "hapus semua". Berperan `role="group"` dengan `aria-label`.

### Segmen (`seg`) dan gugus kolom (`field-group`)
`seg`: alur `--color-sunken` dengan cincin garis, butir 2rem (2.75rem di sentuh), aktif = permukaan + teks kobalt + cincin kuat. `field-group`: ikon + isian dalam satu bingkai setinggi tombol (2.5rem; 2.75rem di sentuh); filter yang sedang aktif (`.form-select.is-set`) menyorot seluruh gugus dengan `--jt-brand-softer`.

### Tombol ikon (`icon-btn`)
Transparan 2.25rem (2.75rem di sentuh), radius kontrol, hover netral; varian `is-brand` dan `is-danger` hanya berubah saat hover.

### Keadaan kosong (`jt-empty`, makro `empty_state`)
Ikon 2.75rem di kotak rona mute (`is-ok` untuk kosong yang menggembirakan), judul 1rem/600, kalimat maks 36ch yang mengajarkan langkah berikutnya, `jt-empty-actions` untuk tombol. Pada tabel HP baris kosong tetap di tengah tanpa label kolom.

### Kulit tombol dan form Bootstrap lama (`legacy-skin.css`)
`.btn`: radius 10px, teks 0.875rem/600, tinggi minimum 2.5rem (2.875rem di sentuh), tekan = `scale(0.97)`. `.btn-primary` memakai `--jt-brand-solid` dengan hover `--jt-brand-solid-hover` dan aktif `--jt-brand-solid-active`; `.btn-outline-primary` permukaan + garis `--jt-brand-edge`. `.form-control`/`.form-select`: tepi `--color-line-strong`, latar `--color-surface-2`, tinggi 2.5rem, fokus = tepi kobalt + cincin 4px; 16px dan 2.875rem di sentuh. `.card` memakai token panel. Alias variabel lama (`--color-primary`, `--color-border`, dst.) diarahkan ke token baru.

### Navigasi
Sidebar menempel langsung di atas bingkai gelap (tautan aktif terang, subitem bergaris); top bar lembar dengan pencarian, lencana koneksi, tema, pengguna; di HP navigasi bawah melayang dengan Scan QR di tengah. Lencana koneksi `.tb-net` (`#jtNetBadge`): pil 2rem berwarna warn (Offline), info (Belum terkirim + hitungan), ok (Tersambung kembali); di bawah 30rem hanya ikon dan hitungan.

### Perilaku dan gerak
- **Transisi:** 0.15s `--jt-ease-std` (`cubic-bezier(0.4, 0, 0.2, 1)`) untuk hover/warna di pola bersama; 0.18s sampai 0.28s di kerangka dan tombol; `--jt-ease` (`cubic-bezier(0.16, 1, 0.3, 1)`) untuk masuk dan tekan. Batang tren/meter tumbuh 0.5s sampai 0.55s (`jt-grow-x/y`); toast masuk 0.2s (`jt-pop-in`); kerangka pemuatan berkilau 1.6s (`jt-shimmer`).
- **Keadaan:** hover = latar `--jt-hover`; aktif = `--jt-press`; fokus = outline 2px `--jt-brand-solid` dengan offset 1-2px; nonaktif = opacity 0.5. Hover hanya penegas, bukan satu-satunya jalan ke aksi.
- **Mode gelap:** `data-bs-theme="dark"`, nilai token ditukar di `tokens.css`; dibungkus `@media screen` sehingga cetak laporan tetap terang. `color-scheme: dark` membuat kontrol bawaan ikut gelap.
- **Gerak berkurang:** `app.css` menetapkan durasi 0.01ms untuk semua animasi/transisi (kecuali spinner) di `prefers-reduced-motion: reduce`; `jt-skel` dan `jt-toast` juga dimatikan.
- **Mode TV (dasbor):** tombol "Mode TV" membuka `.jt-tv`, hamparan layar penuh (`position: fixed; inset: 0`) dengan kepala `--color-frame`, judul "Menampilkan data: {site}" 1.5rem, dan iframe yang bergilir antar site; `body.tv-mode-iframe` dan `body.is-fullscreen` menyembunyikan kepala halaman dan bingkai. Interval gilir tidak dicatat di sini.
- **Grafik:** `window.jtChartTheme()` mengisi `Chart.defaults.color` dengan `--color-ink-muted` dan `borderColor` dengan `--color-line`; tema ganti mengirim event `jt-theme`. Halaman yang menggambar ulang grafik sendiri memberi `<body data-theme-live>`.

## Do's and Don'ts

### Do:
- **Do** ambil warna dari token (`var(--color-*)`, `var(--jt-*)`) atau kelas `tone-*`; komponen baru tanpa hex.
- **Do** pasangkan setiap warna status dengan teks, titik, atau ikon.
- **Do** beri status lencana berisi + titik, prioritas lencana bergaris + ikon chevron.
- **Do** beri kontrol di layar sentuh dan lebar 768px ke bawah tinggi minimal 44px (2.75rem), input 16px.
- **Do** bungkus wadah grafik dengan `var(--color-surface)` agar teks grafik terbaca di mode gelap.
- **Do** pakai `jt-item--stack` pada baris dengan lencana sisi agar kode dan nama aset tidak terpotong.
- **Do** pakai `@layer override` hanya bila harus mengalahkan `!important` Bootstrap, dan kunci ke kelas halaman (`woe-`, `wol-`, `cwf-`).

### Don't:
- **Don't** menulis hex langsung di komponen baru (README: "jangan menulis warna heksadesimal langsung").
- **Don't** memakai putih tetap di wadah grafik atau permukaan; teks grafik hilang di mode gelap.
- **Don't** bergantung pada hover di layar sentuh untuk menampilkan aksi atau informasi penting.
- **Don't** memakai `--color-ink-faint` untuk teks, atau `--color-signal` untuk status.
- **Don't** menandai baris dengan garis berwarna tebal di sisi (kontrak daftar WO: "tanpa garis warna di sisi baris").
- **Don't** menumpuk kartu di dalam kartu; pakai panel + baris berpemisah garis rambut (`.card .card` hanya jatuh ke `--color-surface-2` tanpa bayangan).
- **Don't** memakai `backdrop-filter`; `legacy-override.css` baris 442 memaksanya mati untuk `.form-glass`.
- **Don't** meniru rona prioritas dengan lencana berisi atau status dengan lencana bergaris.

## Utang yang diketahui (tercatat, tidak dikanonkan)

Ini ada di build, bukan aturan untuk permukaan baru.
- **Heksadesimal di CSS inti:** `shell.css` 29 baris (warna teks sidebar di atas bingkai, mis. `#9ba7bf`, `#2a3550`), `legacy-skin.css` 37, `legacy-override.css` 15; `patterns.css` dan `surface-dashboard.css` hanya `#fff` di atas solid/bingkai.
- **Template lama (dihitung dari `templates/`, 95 berkas .html):** 51 memuat hex enam digit, 3 memuat `border-left` 3px atau lebih, 4 memuat `backdrop-filter`; 76 tidak memakai kelas `jt-*` maupun `_ui/macros` sama sekali, hanya kulit global. (Hitungan dari grep sederhana atas `class="...jt-..."` dan `_ui/macros`, bukan audit per berkas.)
- **Pustaka CDN tidak dipin:** `dexie@latest` (`base.html` 788); lainnya berversi (`sortablejs@1.15.0`, `html5-qrcode@2.3.8`, `marked@4.3.0`).
- **Font belum di-host sendiri:** Inter dari Google Fonts; tanpa internet jatuh ke font sistem.
- **Bobot 550** muncul tiga kali di `shell.css`, padahal hanya 400/500/600 yang dimuat.
- **Label huruf kapital berjarak** (`.sb-product` "Portal Engineer" di sidebar; kepala kartu aset di `surface-wo-edit.css`): dibawa build, bukan gaya untuk permukaan baru.
- **Meta `theme-color` terang** `#ffffff` (`base.html` baris 18) tidak sama dengan kanvas `#f1f3f8`; skrip di baris 32-33 menukarnya ke `#0b101d` di mode gelap, sama dengan kanvas gelap.
- **Kontrak arah vs build:** kontrak dasbor menyebut aksi cepat HP "2x2"; CSS `.dash-actions` di 640px ke bawah memakai tiga kolom.
- **Cincin fokus tidak seragam:** 3px di `.field-group`, 4px di `.form-control`.
- **Tidak diverifikasi dari kode:** kontras pasangan di luar yang tercantum, perilaku tooltip batang tren di layar sentuh, interval gilir mode TV, tampilan di peramban nyata.
