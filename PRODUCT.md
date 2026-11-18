# Product

<!-- impeccable:product-schema 1 -->

> Disusun dari isi repo dan percakapan dengan pemilik proyek (QA Engineer PT Jaya Teknik Indonesia), tanpa sesi wawancara terpisah.
> Baris bertanda "(asumsi)" belum dikonfirmasi pemilik dan boleh dikoreksi.

## Platform

web

## Users

- Teknisi lapangan: membuka web dari smartphone atau tablet di ruang mesin, atap, dan basement gedung; satu tangan, sering bersarung, cahaya terik atau remang. Pekerjaannya: melihat tugas hari ini, memindai QR aset, memperbarui status Work Order, mengisi checklist. (asumsi: sebagian besar sesi teknisi singkat, kurang dari dua menit)
- Supervisor dan Admin: memantau beberapa site dari laptop atau layar besar di kantor; memeriksa Work Order terlambat, kinerja PM, stok, aset kedaluwarsa, jadwal tim; mengatur layout dashboard sendiri. Ada mode TV untuk layar ruang kontrol.
- User (peminta layanan): hanya membuat dan memantau tiket Helpdesk.

## Product Purpose

Portal Engineer adalah CMMS (sistem manajemen pemeliharaan) PT Jaya Teknik Indonesia: Work Order korektif dan preventif, aset beserta QR, gudang dan permintaan PPM, pembelian, Helpdesk, jadwal tim dan absensi, logsheet operasional, pemantauan BAS dan chiller, laporan klien, asisten AI, serta aplikasi mobile yang memakai `/api/`. Berhasil berarti teknisi menyelesaikan Work Order tanpa bertanya "tombolnya di mana", dan supervisor melihat apa yang perlu ditindak dalam beberapa detik.

## Operating Context

- Flask + Jinja2 + SQLite; render di server; tidak ada langkah build bagi pemilik (CSS hasil kompilasi ikut di repo).
- Bahasa antarmuka: Indonesia, sebagian lewat Flask-Babel.
- Peran: Admin, Supervisor, Technician, User. Dashboard bisa disusun ulang per pengguna (seret, ubah lebar, tambah atau hapus widget; disimpan lewat `/api/dashboard/layout`).
- Dipakai juga lewat PWA/offline sync dan aplikasi Android; bentuk JSON `/api/` tidak boleh berubah.
- Versi produksi terbaru lebih baru dari repo ini; pemilik hanya bisa mengambil HTML-nya, bukan kode sumbernya.

## Capabilities and Constraints

- "Otak" aplikasi tidak boleh diubah: struktur DB dan model, alur status Work Order, perhitungan KPI, izin per peran, login dan CSRF. Python boleh ditambah (aditif, baca-saja), dan setiap tambahan harus diberi tahu ke pemilik.
- Satu desain modern saja; tidak ada mode ganda lama/baru.
- Browser dasar: Chrome 111+, Safari 16.4+, Firefox 128+.
- Halaman Login sudah dianggap cukup baik dan dibiarkan.
- Fitur baru di luar usulan yang sudah disetujui harus diusulkan dulu ke pemilik.
- Belum ada di repo: Portal Absensi `/absen`, modul Kontrol Dokumen, dan endpoint AI widget (ada di server produksi).

## Brand Commitments

- Nama: Portal Engineer; PT Jaya Teknik Indonesia. Logo ada di `static/images/` (`logo_white.png`, `Logo Jaya Teknik.png`).
- Pemilik menganggap halaman Login "sudah agak bagus"; sisanya boleh dirombak total sesuai pilihan perancang.

## Evidence on Hand

- Repo kerja: `faiztanjung26/redesainnnn` (cabang `redesain-tailwind`).
- Contoh HTML dashboard produksi terbaru dari pemilik: hanya referensi struktur, tidak untuk diikuti.
- Tidak ada data pengguna nyata, uji kegunaan, atau statistik pemakaian. Jangan mengarang angka.

## Product Principles

1. Lapangan dulu: aksi utama terjangkau ibu jari, terbaca di bawah sinar matahari, target sentuh minimal 44px.
2. Status terbaca sekilas: warna selalu disertai teks atau ikon, kontras tinggi, rona yang sama di semua halaman.
3. Hanya menyajikan data nyata: tidak ada dekorasi yang berpura-pura menjadi isi; angka berasal dari data yang sudah ada.
4. Presentasi saja: logika dan data tidak berubah; tambahan data bersifat aditif dan baca-saja.
5. Satu sistem untuk semua halaman, berbeda jelas dari tampilan lama.

## Accessibility & Inclusion

- Kontras teks minimal 4.5:1, teks besar 3:1, di mode terang dan gelap. (asumsi: WCAG 2.2 AA sebagai pegangan, belum diwajibkan pemilik)
- Dapat dioperasikan dengan keyboard; fokus terlihat jelas.
- Menghormati `prefers-reduced-motion`.
- Mode gelap untuk shift malam dan ruang mesin remang.
