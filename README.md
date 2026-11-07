# 🏢 CMMS 2.0 (Computerized Maintenance Management System)

> **Panduan Pengembangan & Redesign UI untuk Rekan Magang / Frontend Developer**  
> Proyek ini adalah sistem manajemen operasional pemeliharaan gedung (*Facility & Maintenance Management*) berbasis web dengan Python Flask dan Bootstrap 5.

---

## 📑 Daftar Isi
1. [Ringkasan & Tech Stack](#-ringkasan--tech-stack)
2. [Langkah Cepat Menjalankan Aplikasi](#-langkah-cepat-menjalankan-aplikasi-quick-start)
3. [Akun Login Demo (Siap Pakai)](#-akun-login-demo-siap-pakai)
4. [Panduan Redesign UI untuk Anak Magang](#-panduan-redesign-ui-untuk-anak-magang)
5. [Peta File & Struktur Proyek](#-peta-file--struktur-proyek)
6. [Konfigurasi Database & Keamanan](#-konfigurasi-database--keamanan)
7. [Troubleshooting & FAQ](#-troubleshooting--faq)

---

## 🛠️ Ringkasan & Tech Stack

- **Backend:** Python 3.10+ (Flask, Flask-SQLAlchemy, Flask-Login, Flask-Babel)
- **Database:** SQLite (`cmms.db` / `instance/cmms.db`) — *Default, langsung jalan tanpa install MySQL server*
- **Frontend Saat Ini:** Jinja2 Template, Bootstrap 5, Bootstrap Icons, Chart.js, HTML5 & Vanilla JavaScript
- **PWA Ready:** Tersedia Service Worker (`static/sw.js`) dan manifest offline

---

## ⚡ Langkah Cepat Menjalankan Aplikasi (Quick Start)

### 1. Buat Virtual Environment & Install Dependensi
Buka Terminal / PowerShell di folder proyek ini:

```bash
# Buat virtual environment
python -m venv venv

# Aktifkan virtual environment
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Windows (CMD):
.\venv\Scripts\activate.bat
# Linux / macOS:
source venv/bin/activate

# Install dependensi
pip install -r requirements.txt
```

### 2. Siapkan File Konfigurasi Lingkungan (`.env`)
Proyek ini sudah dilengkapi file `.env` default yang mengarah ke SQLite.  
Jika file `.env` belum ada, cukup salin dari template:
```bash
copy .env.example .env
```

### 3. (Opsional) Generate / Reset Data Demo
Database `cmms.db` sudah terisi data mockup realistis (aset, tiket helpdesk, work order, suku cadang).  
Jika Anda ingin mereset ulang data demo kapan saja:
```bash
python seed_demo_data.py
```

### 4. Jalankan Server Development
```bash
python app.py
```
Aplikasi akan menyala di: **[http://127.0.0.1:5003](http://127.0.0.1:5003)**

> 💡 **Tip:** Buka browser dan kunjungi `http://127.0.0.1:5003/login`.

---

## 🔑 Akun Login Demo (Siap Pakai)

Semua akun demo sudah disetujui (`is_approved = True`) dan siap dipakai untuk eksplorasi berbagai level hak akses:

| Peran (Role) | Username (NRP) | Password | Akses & Tujuan Pengujian |
| :--- | :--- | :--- | :--- |
| **Admin** | `admin` | `admin123` | Akses penuh: Dashboard, Work Orders, Assets, Warehouse, Helpdesk, Settings, User Management |
| **Supervisor** | `supervisor` | `supervisor123` | Persetujuan tiket, penugasan teknisi, monitoring performa tim |
| **Teknisi HVAC** | `TK001` | `technician123` | Melihat tugas WO sendiri, centang checklist & prosedur kerja, upload foto bukti |
| **Teknisi Listrik** | `TK002` | `technician123` | Melihat tugas WO elektrikal/genset |
| **Tenant / User** | `client01` | `user123` | Pelaporan komplain via portal Helpdesk |

---

## 🎨 Panduan Redesign UI untuk Anak Magang

Fokus utama redesign adalah membuat tampilan sistem lebih **modern, intuitif, responsif, dan nyaman digunakan oleh teknisi lapangan maupun manajemen kantor**.

### 1. Template Layout Induk (`templates/base.html`)
- File ini adalah kerangka global untuk hampir seluruh halaman di aplikasi.
- Berisi:
  - **Sidebar Navigasi:** Menu modul (Dashboard, Work Orders, Assets, Warehouse, Helpdesk, dll.)
  - **Top Navbar:** Profil pengguna, status online/offline, tombol ganti tema/notifikasi
  - **Breadcrumbs & Content Area:** Tempat konten tiap halaman di-render via `{% block content %}`
  - **Flash Messages:** Notifikasi sukses / error / warning sistem

### 2. Halaman-Halaman Prioritas untuk Di-redesign:

| No | Modul | Path File Template | Rekomendasi Fokus Redesign |
| :---: | :--- | :--- | :--- |
| **1** | **Halaman Login** | `templates/auth/login.html` | Desain card login modern, branding logo yang rapi, ilustrasi/grafis bertema maintenance, input form clean dengan icon |
| **2** | **Main Dashboard** | `templates/dashboard/index.html` | Redesign KPI Summary Cards (total WO, aset kritis, tiket pending), visualisasi Chart.js yang lebih atraktif, aktivitas teknisi terkini |
| **3** | **Daftar Work Orders** | `templates/work_orders/index.html` | Filter tab status (All, In Progress, Assigned, Closed) yang lebih modern, status badge dengan warna jelas, kartu ringkasan atau tabel yang rapi |
| **4** | **Detail / Edit Work Order** | `templates/work_orders/edit.html` | Layout form prosedur teknisi, tombol checklist yang mudah di-tap di layar sentuh/mobile, preview foto lampiran bukti |
| **5** | **Manajemen Aset** | `templates/assets/index.html` & `view.html` | Grid/card view aset dengan indikator status (*Online*, *Maintenance*), QR/barcode scanner trigger, tab riwayat perbaikan |
| **6** | **Gudang & Suku Cadang** | `templates/warehouse/index.html` | Tabel stok barang, indikator stok menipis (*low stock warning*), tombol cepat penyesuaian stok |
| **7** | **Helpdesk Tiket** | `templates/helpdesk/index.html` | Kanban board / list view komplain, tagging divisi/urgensi yang mudah dibaca |

### 3. Folder Asset Statis (`static/`)
- `static/css/` : Masukkan stylesheet custom Anda di sini (misal: `custom-theme.css`, `modern-dashboard.css`).
- `static/js/` : JavaScript interaktif komponen UI, filter client-side, dan charting.
- `static/images/` : Logo, icon, avatar default, dan ilustrasi kosong (*empty state illustration*).
- `static/uploads/` : Folder upload foto bukti dari pengguna (sudah otomatis di-ignore oleh Git).

### 4. Tips Redesign:
- **Mobile First / Tablet Friendly:** Teknisi sering membuka aplikasi dari smartphone atau tablet saat di lapangan. Pastikan tombol aksi dan form mudah ditekan dengan jari.
- **Micro-interactions:** Gunakan hover states, transisi halus, badge status yang kontras dan mudah dibedakan.
- **Dark Mode / Clean Modern Light:** Bootstrap 5.3+ mendukung `data-bs-theme="dark"` atau `data-bs-theme="light"`.

---

## 📁 Peta File & Struktur Proyek

```text
cmms2/
├── app.py                  # Entry point aplikasi Flask & konfigurasi utama
├── auth.py                 # Blueprint autentikasi (login, logout, profil)
├── models.py               # Definisi schema database (SQLAlchemy models)
├── seed_demo_data.py       # Script seeder data mockup aman untuk development
│
├── templates/              # File template HTML Jinja2 (Target Redesign)
│   ├── base.html           # Master layout induk (Sidebar + Topbar)
│   ├── auth/               # Template login, register, profil
│   ├── dashboard/          # Template dashboard & KPI statistik
│   ├── work_orders/        # Template daftar & pengerjaan surat tugas
│   ├── assets/             # Template inventaris & detail aset mesin
│   ├── warehouse/          # Template gudang & suku cadang
│   ├── helpdesk/           # Template tiket komplain & keluhan fasilitas
│   ├── settings/           # Template pengaturan sistem & master data
│   └── reports/            # Template laporan operasional
│
├── static/                 # File aset statis
│   ├── css/                # Custom stylesheets
│   ├── js/                 # JavaScript kustom & offline sync
│   ├── images/             # Gambar & logo sistem
│   └── uploads/            # Tempat file upload (lampiran foto bukti)
│
├── instance/
│   └── cmms.db             # Database SQLite lokal
├── .env                    # Variabel konfigurasi lingkungan lokal (Aman / Dummy)
├── .env.example            # Template konfigurasi variabel lingkungan
├── requirements.txt        # Daftar dependensi Python
└── README.md               # Dokumentasi proyek ini
```

---

## 🔒 Konfigurasi Database & Keamanan

1. **Keamanan Data:**
   - Semua kredensial produksi asli (token API pihak ketiga, password database produksi, bucket storage) **telah dibersihkan dan disanitasi**.
   - Variabel yang ada di `.env` hanya menggunakan nilai placeholder atau dummy yang aman untuk lingkungan development.
   - File dump produksi (`*.sql`, backup dump) sudah dikeluarkan dari repository dan ditambahkan ke `.gitignore`.

2. **Pilihan Database:**
   - **SQLite (Default):** `DATABASE_URL=sqlite:///cmms.db` — Tidak perlu instalasi MySQL, file database otomatis disimpan secara mandiri di `instance/cmms.db` dan `cmms.db`.
   - **MySQL (Opsional):** Jika Anda ingin menggunakan database MySQL server di masa mendatang, cukup sesuaikan string koneksi di file `.env`:
     ```env
     DATABASE_URL=mysql+mysqlconnector://root:password@127.0.0.1:3306/cmms_db
     ```

---

## ❓ Troubleshooting & FAQ

**Q: Port 5003 sudah digunakan oleh aplikasi lain?**  
> Buka baris paling bawah di [app.py](file:///d:/github/cmms2/app.py) dan ubah nilai `port=5003` menjadi port lain, misalnya `port=5005`.

**Q: Ingin menambahkan aset atau work order baru untuk keperluan pengetesan UI?**  
> Anda bisa langsung membuatnya via antarmuka web saat login sebagai `admin`, atau tambahkan entri baru di [seed_demo_data.py](file:///d:/github/cmms2/seed_demo_data.py) lalu jalankan kembali `python seed_demo_data.py`.

**Q: Bagaimana cara melihat perubahan HTML/CSS secara langsung?**  
> Server Flask berjalan dalam mode `debug=True`. Saat Anda menyimpan perubahan pada file `.html` atau `.css`, Anda cukup me-refresh halaman browser (`Ctrl + F5` untuk membersihkan cache).

---
*Selamat berkreasi dan semoga sukses mendesain antarmuka CMMS yang lebih keren dan modern!* 🚀
