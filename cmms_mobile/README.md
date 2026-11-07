# 📱 CMMS Teknisi Mobile (Aplikasi Android Flutter Offline-First)

Aplikasi mobile Android berbasis **Flutter** untuk **Role Teknisi Lapangan** pada sistem **CMMS PT Jaya Teknik Indonesia**.
Aplikasi ini dirancang dengan prinsip **Offline-First**, memungkinkan teknisi menjalankan seluruh alur kerja penugasan (*Work Order*), pemeriksaan prosedur, pengisian parameter checklist, pengambilan foto bukti, dan pencatatan suku cadang di lokasi tanpa sinyal internet (seperti ruang bawah tanah/basement, gardu, atau ruang mesin kedap sinyal).

---

## ✨ Fitur Utama Role Teknisi

### 1. 🔐 Autentikasi & Sesi Teknisi
- Login aman menggunakan **NRP (Nomor Registrasi Pegawai)** dan **Kata Sandi**.
- Token autentikasi berbasis Bearer Token dengan masa aktif sesi 30 hari.
- Penyimpanan profil dan sesi di SQLite & SharedPreferences untuk login instan secara offline.
- Konfigurasi alamat URL Server API yang fleksibel langsung dari aplikasi.

### 2. 📊 Dashboard Ringkasan & KPI Teknisi
- Indikator status jaringan real-time (**Online** / **Offline**).
- Kartu statistik penugasan:
  - **Ditugaskan**: Total WO yang ditugaskan ke teknisi.
  - **Sedang Dikerjakan**: WO yang sedang dalam proses pengerjaan.
  - **Ditunda (Hold)**: WO yang tertunda karena kendala material / izin kerja.
  - **Terlambat (Overdue)**: WO yang telah melewati batas target penyelesaian.
- Bagian **"Work Order Hari Ini"**: Daftar pekerjaan yang terjadwal jatuh tempo hari ini.
- Bagian **"Pekerjaan Mendesak"**: WO dengan prioritas Tinggi/Tertinggi.
- Kartu notifikasi antrean sinkronisasi offline.

### 3. 📋 Manajemen Lengkap Work Order
- **Daftar & Filter Interaktif**:
  - Tab status: *Semua*, *Ditugaskan*, *Dikerjakan*, *Ditunda*, *Selesai*.
  - Filter tingkat prioritas: *Tertinggi*, *Tinggi*, *Sedang*, *Rendah*.
  - Pencarian cepat berdasarkan nomor WO, deskripsi, atau nama aset.
- **Transisi Status Lifecycle**:
  - **Mulai Pengerjaan**: Mengubah status menjadi *In Progress* dan mencatat timestamp waktu mulai aktual.
  - **Tunda (Hold)**: Membuka dialog alasan penundaan (*delay reason*) seperti menunggu suku cadang.
  - **Lanjutkan (Resume)**: Melanjutkan kembali pekerjaan dari status Hold.
  - **Selesaikan (Solve)**: Menyelesaikan pekerjaan dengan validasi otomatis (semua prosedur wajib dicentang, foto bukti wajib diunggah sesuai kuota, dan checklist parameter wajib terisi).
- **6 Tab Pengerjaan di Detail Work Order**:
  1. **Tab Informasi**: Rincian aset, nomor seri, model, lokasi gedung, jadwal target, tim, dan instruksi kerja SOP.
  2. **Tab Prosedur**: Checklist tugas teknis, estimasi menit, indikator minimal foto bukti, pengambilan foto kamera/galeri, dan catatan temuan lapangan.
  3. **Tab Parameter**: Formulir checklist parameter teknis (nilai standar acuan vs nilai aktual hasil ukur).
  4. **Tab Suku Cadang**: Daftar suku cadang yang digunakan + Dialog penambahan suku cadang dari gudang/katalog.
  5. **Tab Log & Catatan**: Catatan riwayat aktivitas pengerjaan oleh teknisi.
  6. **Tab Tanda Tangan**: Kanvas tanda tangan digital interaktif untuk teknisi dan PIC/pelanggan lengkap dengan nama dan jabatan.

### 4. ⚡ Arsitektur Offline-First & Sinkronisasi
- **Penyimpanan Lokal (SQLite)**: Seluruh data penugasan, aset, prosedur, checklist, suku cadang, dan log tersimpan di database lokal perangkat.
- **Antrean Outbox (Sync Queue)**: Setiap tindakan yang dilakukan saat offline (centang prosedur, isi checklist, simpan foto, ubah status) disimpan ke dalam antrean lokal outbox SQLite.
- **Auto-Sync saat Re-connect**: Ketika mendeteksi sinyal internet kembali aktif, aplikasi otomatis mengirimkan seluruh antrean ke server di latar belakang.
- **Halaman Sinkronisasi**: Layar khusus untuk memantau status koneksi, jumlah item tertunda, dan tombol sinkronisasi manual.

### 5. 👤 Pengaturan & Profil Teknisi
- **Digital ID Card**: Kartu tanda pengenal teknisi dengan gradien modern, NRP, role, dan unit/site kerja.
- **Ubah Profil**: Pembaruan nama tampilan dan nomor telepon/WhatsApp.
- **Ubah Kata Sandi**: Dialog penggantian kata sandi dengan verifikasi kata sandi lama.
- **Konfigurasi URL Server**: Pengaturan host backend API (cth: `http://10.0.2.2:5000` untuk emulator atau IP LAN `http://192.168.x.x:5000`).
- **Mode Gelap / Terang (Dark Mode)**: Tampilan visual modern minimalis Material 3 yang nyaman untuk mata teknisi di lapangan.
- **Pembersih Cache Lokal**: Opsi mengosongkan cache offline perangkat.

---

## 📁 Struktur Folder Project Flutter

```text
cmms_mobile/
├── pubspec.yaml                 # Dependensi Flutter (provider, sqflite, http, intl, dll)
├── README.md                    # Panduan instalasi dan dokumentasi
├── android/                     # Konfigurasi native Android (Gradle, Manifest, Permissions)
│   ├── app/
│   │   ├── build.gradle
│   │   └── src/main/
│   │       ├── AndroidManifest.xml
│   │       └── kotlin/com/jayateknik/cmms/MainActivity.kt
│   ├── build.gradle
│   └── settings.gradle
└── lib/
    ├── main.dart                # Entry point aplikasi & MultiProvider
    ├── core/
    │   ├── constants/
    │   │   ├── api_constants.dart    # Endpoint URL REST API backend
    │   │   ├── app_colors.dart       # Skema warna modern minimalis
    │   │   └── app_theme.dart        # Tema Material 3 Light & Dark
    │   ├── database/
    │   │   └── database_helper.dart  # SQLite offline database & outbox queue
    │   ├── network/
    │   │   ├── api_service.dart      # HTTP client, token interceptor, base URL
    │   │   └── network_info.dart     # Pemantau konektivitas internet / WiFi
    │   ├── sync/
    │   │   └── sync_service.dart     # Layanan download paket offline & upload batch
    │   └── utils/
    │       └── formatters.dart       # Formatter tanggal & mata uang Indonesia
    ├── data/
    │   ├── models/
    │   │   ├── user_model.dart       # Model data profil teknisi
    │   │   ├── work_order_model.dart # Model data Work Order
    │   │   ├── procedure_model.dart  # Model prosedur pengerjaan & foto bukti
    │   │   ├── checklist_model.dart  # Model parameter checklist
    │   │   ├── part_model.dart       # Model suku cadang & pemakaian part
    │   │   ├── work_log_model.dart   # Model log catatan pengerjaan
    │   │   ├── dashboard_model.dart  # Model metrik KPI dashboard
    │   │   └── sync_queue_item.dart  # Model item antrean outbox offline
    │   └── repositories/
    │       ├── auth_repository.dart       # Manajemen sesi dan akun
    │       └── work_order_repository.dart # Repository data Offline-First
    ├── providers/
    │   ├── auth_provider.dart        # State management login & profil
    │   ├── dashboard_provider.dart   # State management statistik dashboard
    │   ├── work_order_provider.dart  # State management daftar & filter WO
    │   ├── sync_provider.dart        # State management sinkronisasi & outbox
    │   └── theme_provider.dart       # State management tema gelap/terang
    ├── screens/
    │   ├── splash_screen.dart        # Layar pembuka / splash screen
    │   ├── main_navigation_screen.dart# Navigasi utama 4 tab bawah
    │   ├── auth/
    │   │   ├── login_screen.dart           # Layar login NRP & kata sandi
    │   │   └── server_settings_dialog.dart # Dialog ubah alamat URL server
    │   ├── dashboard/
    │   │   └── dashboard_screen.dart       # Layar dashboard teknisi
    │   ├── work_orders/
    │   │   ├── work_orders_screen.dart       # Layar daftar & filter WO
    │   │   ├── work_order_detail_screen.dart # Layar lengkap 6 tab detail WO
    │   │   └── dialogs/
    │   │       ├── hold_reason_dialog.dart   # Dialog alasan penundaan
    │   │       ├── add_part_dialog.dart      # Dialog input suku cadang
    │   │       ├── add_log_dialog.dart       # Dialog catatan progres
    │   │       └── signature_dialog.dart     # Kanvas tanda tangan digital
    │   ├── sync/
    │   │   └── sync_screen.dart            # Layar kelola antrean offline & sinkronisasi
    │   └── profile/
    │       ├── profile_screen.dart         # Layar digital ID card & profil teknisi
    │       └── change_password_dialog.dart # Dialog ubah kata sandi
    └── widgets/
        ├── connection_banner.dart    # Banner status online/offline
        ├── status_badge.dart         # Badge status WO warna lembut
        ├── priority_badge.dart       # Badge indikator prioritas
        ├── stat_card.dart            # Kartu metrik KPI dashboard
        ├── work_order_card.dart      # Kartu ringkasan WO & progress bar
        └── empty_state.dart          # Komponen tampilan kosong
```

---

## 🔌 API Endpoint Web Backend yang Disediakan (`mobile_api.py`)

Backend Flask telah dilengkapi dengan blueprint `/api/mobile` yang bebas dari hambatan CSRF untuk autentikasi berbasis Bearer Token:

| Method | Endpoint | Keterangan |
| :--- | :--- | :--- |
| `POST` | `/api/mobile/login` | Login NRP & Kata Sandi, mengembalikan Token dan Profil |
| `GET` | `/api/mobile/profile` | Mengambil detail profil dan metrik statistik teknisi |
| `POST` | `/api/mobile/profile/update` | Mengubah nama tampilan & nomor telepon |
| `POST` | `/api/mobile/profile/change-password` | Mengganti kata sandi dengan verifikasi kata sandi lama |
| `GET` | `/api/mobile/dashboard` | Mengambil KPI statistik, WO hari ini, dan WO mendesak |
| `GET` | `/api/mobile/work-orders` | Mengambil daftar WO dengan filter status, prioritas, & pencarian |
| `GET` | `/api/mobile/work-orders/<id>` | Mengambil detail lengkap WO, prosedur, checklist, suku cadang, log, & tanda tangan |
| `POST` | `/api/mobile/work-orders/<id>/status` | Memperbarui status WO (*start*, *hold*, *resume*, *solve*) |
| `POST` | `/api/mobile/work-orders/<id>/procedures/<proc_id>` | Menyimpan centang selesai, catatan, dan foto bukti prosedur |
| `POST` | `/api/mobile/work-orders/<id>/checklists` | Menyimpan input nilai aktual parameter checklist teknis |
| `GET` | `/api/mobile/parts` | Pencarian katalog suku cadang |
| `POST` | `/api/mobile/work-orders/<id>/parts` | Mencatat penggunaan suku cadang pada WO |
| `DELETE`| `/api/mobile/work-orders/<id>/parts/<part_id>` | Menghapus catatan suku cadang |
| `POST` | `/api/mobile/work-orders/<id>/logs` | Menambahkan catatan log aktivitas pengerjaan |
| `POST` | `/api/mobile/work-orders/<id>/signature` | Menyimpan tanda tangan digital teknisi & pelanggan |
| `GET` | `/api/mobile/sync/download` | Unduhan bundle lengkap seluruh WO penugasan untuk mode offline |
| `POST` | `/api/mobile/sync/upload` | Unggah batch seluruh antrean outbox offline saat terhubung kembali |

---

## 🚀 Panduan Menjalankan & Membangun Aplikasi

### Langkah 1: Menjalankan Server Backend CMMS
Pastikan server backend Flask berjalan di terminal:
```bash
# Jalankan seed data contoh jika database baru
python seed_mobile_demo.py

# Jalankan server Flask
python app.py
```
*Server akan berjalan di `http://127.0.0.1:5000`*.

### Langkah 2: Akun Demo Teknisi
- **NRP**: `TK001`
- **Kata Sandi**: `Password123`
- **Nama**: Budi Santoso
- **Role**: Technician
- **Site**: Menara Jaya Pusat

### Langkah 3: Menjalankan Aplikasi Flutter di Android
Masuk ke folder `cmms_mobile`:
```bash
cd cmms_mobile

# Unduh paket dependensi Flutter
flutter pub get

# Jalankan di Emulator Android atau HP Fisik
flutter run
```

> **Catatan Konfigurasi Jaringan:**
> - Jika menggunakan **Android Emulator**, URL server default adalah `http://10.0.2.2:5000` (alamat loopback host dari emulator).
> - Jika menggunakan **HP Android Fisik**, hubungkan HP dan laptop ke jaringan WiFi yang sama, lalu ubah URL server pada tombol **"Konfigurasi URL Server API"** di layar Login menjadi alamat IP laptop Anda (contoh: `http://192.168.1.15:5000`).

### Langkah 4: Membangun File APK Android Release
Untuk menghasilkan file installer `.apk` yang siap di-install di smartphone teknisi:
```bash
cd cmms_mobile
flutter build apk --release
```
File APK akan dibuat pada lokasi:
`cmms_mobile/build/app/outputs/flutter-apk/app-release.apk`
