# Frontend Portal Engineer (Tailwind v4 + Bootstrap berkulit baru)

Folder ini berisi sumber CSS desain baru. Hasil build-nya sudah ada di `static/css/` dan ikut di-commit,
jadi app **tidak butuh Node** untuk berjalan. Backend Flask (model, rute, logika WO, izin per peran, login, CSRF) tidak disentuh.

## Isi

| Berkas | Fungsi |
|---|---|
| `src/tokens.css` | Token desain: warna kobalt dan abu-abu grafit, radius, bayangan, font |
| `src/shell.css` | Kerangka halaman: sidebar, top bar, bilah halaman `.page-bar`, navigasi bawah HP, chatbot |
| `src/patterns.css` | Pola bersama: `.seg`, `.field-group`, `.stat`, `.icon-btn`, `.jt-empty` |
| `src/legacy-skin.css` | Kulit untuk halaman Bootstrap lama: tombol, kartu, tabel, form, modal |
| `src/legacy-override.css` | Aturan `!important` yang harus menang atas Bootstrap dan CSS di dalam template |
| `src/app.css` | Titik masuk Tailwind (tema dan utilitas) |
| `vendor/` | Salinan Bootstrap 5.3.0 dan Bootstrap Icons 1.10.5, diwarnai ulang saat build |
| `build.mjs` | Skrip build |

## Hasil build (jangan diedit tangan)

- `static/css/app.css`: dimuat semua halaman.
- `static/css/preflight.css`: reset Tailwind, hanya untuk halaman asli Tailwind (login).
- `static/css/legacy.css`: Bootstrap, ikon, dan kulit, untuk halaman lama.

## Membangun ulang (hanya jika mengubah sumber)

Butuh Node 20 atau lebih baru.

```
cd frontend
npm install
npm run build
```

Sesudah itu naikkan angka `v=` pada tautan CSS di `templates/base.html` dan `templates/auth/login.html`,
serta angka versi `CACHE_NAME` di `static/sw.js`, supaya browser dan service worker memuat CSS yang baru.

## Urutan lapisan CSS

```
@layer properties, override, bootstrap, theme, base, skin, components, utilities;
```

- `!important` di lapisan `override` menang atas `!important` Bootstrap dan atas CSS tanpa lapisan.
- CSS biasa di dalam `<style>` template (tanpa lapisan) menang atas semua lapisan.
- Halaman baru: pakai kelas dari `patterns.css` dan token dari `tokens.css`, jangan menulis warna heksadesimal langsung.

## Browser

Tailwind v4 butuh Chrome 111+, Safari 16.4+, atau Firefox 128+. Browser yang lebih lama tidak menampilkan tata letak dengan benar.

## Font

Inter dan Plus Jakarta Sans dimuat dari Google Fonts. Tanpa internet, browser memakai font sistem.
