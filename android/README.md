# Panduan Aplikasi Android Offline CMMS (Progressive Web App & Native APK)

Folder ini berisi konfigurasi dan panduan lengkap untuk menjalankan serta membangun (**build**) aplikasi **CMMS Mobile** berbasis **Android Offline-First**.

---

## 📁 Struktur Folder & File PWA Offline

```text
cmms2/
├── static/
│   ├── manifest.json         # PWA Web App Manifest (Icon, Nama App, Theme Color)
│   ├── sw.js                  # Service Worker (Cache Static Files & Offline Interceptor)
│   └── js/
│       ├── offline-db.js      # Inisialisasi IndexedDB (Dexie.js)
│       └── offline-sync.js    # Pengelola Download WO & Upload Outbox Offline
├── sync.py                    # API Server Sync (/sync/api/download-assigned-wo & upload)
└── android/
    ├── capacitor.config.json  # Konfigurasi Capacitor Hybrid Android App
    ├── twa-manifest.json      # Konfigurasi Bubblewrap CLI (PWA to APK)
    └── README.md              # Dokumentasi & Panduan Build APK
```

---

## 🚀 3 Cara Menjalankan & Membangun Aplikasi di Android

### Opsi 1: PWA Direct Install ("Add to Home Screen" - Tanpa Build APK)
Cara tercepat dan paling mudah tanpa perlu install Android Studio / Gradle.

1. Buka browser Chrome di Smartphone Android teknisi.
2. Akses URL server CMMS Anda (contoh: `https://cmms.jayateknik.co.id`).
3. Tekan menu titik tiga di Chrome $\rightarrow$ pilih **"Add to Home Screen"** / **"Install App"**.
4. Aplikasi akan terpasang di layar utama HP seperti aplikasi Android native dan bisa dijalankan offline!

---

### Opsi 2: Build Aplikasi `.apk` Menggunakan Capacitor
Mengubah web ini menjadi project Android Native yang bisa di-build menggunakan Android Studio / Android CLI.

1. Install Node.js dan `@capacitor/cli`:
   ```bash
   npm install @capacitor/core @capacitor/cli
   ```
2. Inisialisasi Capacitor pada folder ini:
   ```bash
   npx cap init "CMMS Engineer Mobile" "com.jayateknik.cmms"
   ```
3. Tambahkan platform Android:
   ```bash
   npx cap add android
   npx cap open android
   ```
4. Buka Android Studio atau jalankan command line build untuk menghasilkan file **`app-release.apk`**:
   ```bash
   cd android && ./gradlew assembleRelease
   ```

---

### Opsi 3: Build APK Instan Menggunakan Bubblewrap CLI (TWA)
Mengonversi PWA manifest menjadi file `.apk` secara otomatis dari terminal command line.

1. Install Bubblewrap CLI:
   ```bash
   npm install -g @bubblewrap/cli
   ```
2. Jalankan perintah build APK:
   ```bash
   cd android
   bubblewrap init --manifest=../static/manifest.json
   bubblewrap build
   ```
3. File `.apk` siap di-distribusikan dan di-install di HP teknisi Android!

---

## ⚡ Fitur Utama Pengerjaan Offline di Android:
1. **Tombol "Download Offline"**: Berada di toolbar daftar Work Order. Teknisi menekan tombol ini di kantor (saat online) untuk mengunduh seluruh WO, Prosedur, dan Checklist yang ditugaskan ke dirinya.
2. **Pengerjaan Lapangan (Offline Mode)**: Teknisi dapat membuka WO, mencentang prosedur, mengambil foto, dan mengisi nilai checklist meskipun tidak ada sinyal seluler/WiFi.
3. **Otomatis Sync Back saat Re-connect**: Begitu perangkat HP kembali mendapat jaringan internet, Service Worker dan `offline-sync.js` akan otomatis mengirimkan (*Outbox Sync*) seluruh data dan foto ke server secara latar belakang.
