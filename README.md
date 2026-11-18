# zeConvert — Video & Audio Converter

Live Demo: **https://www.zeconvert.cloud/**

Aplikasi web konverter video dan audio cepat berbasis FastAPI + FFmpeg dengan dukungan ekstraksi link (YouTube, TikTok, Instagram, Facebook, direct HTTPS media) serta upload file lokal ke MP4 (H.264/AAC) dan MP3 (128–320 kbps).

## Batas dukungan

- Link YouTube, Instagram, dan Facebook diperiksa oleh provider masing-masing. Metadata YouTube dicoba lewat oEmbed; endpoint metadata tersebut tidak menyediakan file video.
- Pengambilan file Instagram/Facebook hanya dicoba jika token resmi Meta dan izin pemilik/Page tersedia di environment. Tanpa izin, embed tetap tersedia dan aplikasi menjelaskan integrasi belum dikonfigurasi.
- Pemutaran memakai elemen audio/video HTML5. Format dan codec yang bisa diputar bergantung pada browser dan perangkat.
- Untuk URL file media, gunakan HTTPS yang langsung menghasilkan konten `video/*`, `audio/*`, atau `application/octet-stream`. URL halaman web biasa ditolak.
- URL pratinjau dan unduhan harus HTTPS dan langsung menghasilkan konten `video/*`, `audio/*`, atau `application/octet-stream`. URL halaman web biasa ditolak. Pratinjau disimpan sementara, maksimal 3 aktif dan kedaluwarsa dalam 10 menit.
- URL tujuan dan setiap redirect di-resolve ulang; IP privat, loopback, link-local, host lokal, serta alamat khusus diblokir. Proxy lingkungan tidak digunakan.
- Upload diproses berdasarkan isi media yang diperiksa FFprobe, bukan ekstensi saja. Batas default upload dan unduhan 500 MB, hasil 1 GB, durasi media 3 jam, waktu proses 30 menit, antrean 10 pekerjaan, maksimal 2 konversi simultan.
- File sementara dihapus sesudah pemrosesan. Hasil dan riwayat pekerjaan disimpan sementara selama satu jam; pekerjaan dibersihkan otomatis.

## Link YouTube → MP4/MP3

Tempel link YouTube, tekan **Tampilkan**, pilih MP4 atau MP3, lalu **Proses media**. Backend mengunduh video publik lewat `yt-dlp` (tanpa cookie/login), lalu FFmpeg mengonversinya. Perlu `yt-dlp` terpasang di venv dan Node.js di PATH (untuk ekstraksi YouTube). Matikan dengan `YT_DLP_ENABLED=false` di `.env`. Gunakan hanya untuk konten yang boleh kamu simpan; mengunduh dari YouTube dapat melanggar ketentuan layanannya.

## Persyaratan

- Python 3.11–3.15.
- FFmpeg dan FFprobe. Build Windows essentials sudah disimpan lokal di `tools/ffmpeg/`; file `.env` mengarahkan backend ke binary tersebut. Halaman unduhan resmi FFmpeg mencantumkan penyedia build Windows: [ffmpeg.org/download.html](https://www.ffmpeg.org/download.html).

### Integrasi platform opsional

- YouTube: metadata publik dicoba lewat oEmbed. API YouTube tidak menyediakan berkas media untuk diunduh; gunakan ekspor resmi video milik sendiri lalu unggah file.
- Instagram: isi `META_INSTAGRAM_ACCESS_TOKEN` dan `META_INSTAGRAM_USER_ID` di `.env` untuk memeriksa media akun profesional yang diotorisasi.
- Facebook: isi `META_GRAPH_ACCESS_TOKEN` dan, bila perlu, `META_GRAPH_API_VERSION` di `.env`. Graph API harus memberi akses ke video dan mengembalikan field sumber.
- Token hanya dibaca backend, jangan letakkan di URL/frontend atau commit `.env`. Token harus diperoleh melalui OAuth resmi dan izin minimum yang sesuai.

Untuk proyek ini, cek versi dengan:

```powershell
.\tools\ffmpeg\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe -version
.\tools\ffmpeg\ffmpeg-9.0.2-essentials_build\bin\ffprobe.exe -version
```

Jika memasang FFmpeg terpisah, pastikan `ffmpeg -version` dan `ffprobe -version` berhasil atau isi `FFMPEG_PATH`/`FFPROBE_PATH` di `.env`.

## Instalasi Windows

Dari PowerShell di folder proyek:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Jika perintah `py` tidak tersedia, gunakan `python` sebagai gantinya. Salin `.env.example` ke `.env` jika ingin mengubah konfigurasi. Variabel environment Windows juga dapat digunakan.

## Menjalankan

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

Buka [http://127.0.0.1:8001](http://127.0.0.1:8001). Server hanya bind ke loopback komputer lokal. Hentikan dengan `Ctrl+C`. Port dapat diganti melalui variabel `PORT`.

## Menjalankan pemeriksaan

Pasang dependency pengujian dengan `.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt`, lalu jalankan `.\.venv\Scripts\python.exe -m pytest backend\tests -q`. Tes konversi otomatis dilewati bila FFmpeg/FFprobe tidak tersedia.

## Fitur yang tersedia

- Auto-detect YouTube, Instagram, dan Facebook untuk pemutaran embed platform.
- Metadata URL dipisahkan dari pemrosesan media; header sumber langsung diperiksa tanpa mengunduh isi file.
- Status header hanya kandidat sumber; tombol proses membuat job yang mengunduh file, lalu FFprobe memvalidasi isi sebelum FFmpeg dimulai. UI baru menyatakan sumber tersedia setelah pratinjau berhasil mengambil dan membaca file.
- Pemutar audio/video HTML5 untuk URL HTTPS langsung dan file lokal.
- Pratinjau URL menggunakan salinan sementara di backend yang melewati validasi SSRF.
- Ambil file media langsung melalui backend aman, lalu transcode ke MP4 atau MP3.
- Upload audio/video lokal untuk dikonversi ke MP4 (H.264/AAC) atau MP3 dengan bitrate 128, 192, 256, atau 320 kbps. MP4 yang kompatibel memakai stream copy; lainnya di-encode ulang.
- Pilihan kualitas video tinggi, standar, atau ukuran kecil; pekerjaan aktif dapat dibatalkan.
- Progres aktual dari byte unduhan atau waktu proses FFmpeg; durasi konversi tidak dibuat-buat.
- Status job membedakan antrean, pengunduhan, validasi, konversi, selesai, dan gagal. URL halaman YouTube tetap metadata/embed saja; API metadata YouTube bukan sumber video.
- Polling status, daftar pekerjaan, download hasil, hapus pekerjaan/riwayat, dan pembersihan otomatis.

## API

Semua endpoint berada di origin yang sama dengan frontend.

### `GET /api/health`

Contoh response: `{"status":"ok","ffmpeg_available":true,"ffprobe_available":true}`.

### `POST /api/jobs/upload`

`multipart/form-data`: `file` (wajib), `output` (`mp4` atau `mp3`, default `mp3`), `bitrate` (128, 192, 256, atau 320; default 192), `quality` (`high`, `standard`, atau `compact`; default `standard`). Video MP4 memakai stream copy bila kompatibel, selain itu H.264/AAC. Mengembalikan job dengan HTTP 202.

### `POST /api/media/classify`

JSON: `{"url":"https://…"}`. Mengenali provider dan memvalidasi bentuk URL secara lokal. Endpoint ini tidak membuka koneksi ke sumber dan tidak mengklaim file tersedia.

### `POST /api/media/inspect`

JSON: `{"url":"https://…"}`. Mengambil metadata publik dan memeriksa header kandidat sumber melalui provider resmi atau URL langsung. `source.access: "candidate"` berarti job boleh dimulai, tetapi file penuh tetap harus diunduh dan diperiksa FFprobe. Endpoint lama `/api/media/info` tetap tersedia untuk kompatibilitas.

### `POST /api/media/resolve`

JSON: `{"url":"https://…"}`. Menjalankan pemeriksaan yang sama dengan `inspect` dan mengembalikan `source` terstruktur: jenis sumber, status akses kandidat, status verifikasi, dan referensi internal `server_managed`. URL sumber provider yang bersifat sementara atau bertoken tidak pernah dikirim ke browser.

### `POST /api/previews`

JSON: `{"url":"https://host.example/path/video.mp4"}`. Mengambil dan memeriksa URL media HTTPS langsung, lalu mengembalikan metadata, `id`, dan `player_url`. File pratinjau berlaku 10 menit.

### `GET /api/previews/{preview_id}/media`

Menyajikan file pratinjau tervalidasi ke pemutar HTML5 lokal.

### `POST /api/jobs/download` dan `POST /api/jobs/convert`

JSON: `{"url":"https://host.example/path/video.mp4","output":"mp4","quality":"standard","bitrate":192}` atau `{"preview_id":"<id pratinjau>","output":"mp3","bitrate":192}`. Backend mengunduh sumber, memeriksa isi dengan FFprobe, lalu menjalankan FFmpeg. `output` adalah `mp4` atau `mp3`; kualitas hanya digunakan untuk encode MP4, bitrate hanya untuk MP3. Memulai pemrosesan dan mengembalikan job dengan HTTP 202. Endpoint lama `/api/jobs/url` tetap tersedia untuk kompatibilitas.

### `GET /api/jobs/{job_id}` dan `GET /api/jobs`

Membaca status satu pekerjaan atau 30 pekerjaan terbaru. Status: `queued`, `processing`, `completed`, `failed`, `canceled`. `progress` adalah progres tahapan aktual atau `null` bila sumber tidak menyediakan ukuran total.

### `POST /api/jobs/{job_id}/cancel`

Membatalkan pekerjaan yang masih antre atau berjalan, menghentikan prosesnya, dan menghapus input sementara.

### `GET /api/jobs/{job_id}/download`

Mengunduh hasil hanya setelah pekerjaan selesai.

### `DELETE /api/jobs/{job_id}`

Menghapus hasil dan pekerjaan terkait dari storage lokal.

### `GET /`

Frontend aplikasi.

## Catatan implementasi dan pemeriksaan

Tes backend ada di `backend/tests/test_api.py` dan memeriksa klasifikasi provider, akses metadata, penolakan sumber platform yang tidak diotorisasi, URL langsung, upload lokal MP3/MP4, hasil codec H.264/AAC, batas upload, serta pembatalan. Jalankan dengan perintah pemeriksaan di atas setelah dependency dev dipasang.

Output video dikonversi ke H.264/AAC dalam kontainer MP4. Output audio memakai MP3. YouTube metadata/embedding tidak membuka akses berkas videonya. Instagram/Facebook hanya dapat diproses jika Graph API mengembalikan file untuk akun yang terotorisasi dan token/izin telah dikonfigurasi; hasilnya bergantung pada akses tiap media. Tanpa itu, unggah file hasil ekspor resmi. Tidak ada ekstraktor platform atau mekanisme bypass DRM, login, paywall, iklan, maupun pembatasan unduhan.
