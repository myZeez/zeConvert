import html
import os

from .config import FRONTEND_DIR

SITE_URL = os.getenv("SITE_URL", "https://zeconvert.cloud").rstrip("/")

HOME_DEFAULT = {
    "title": "zeConvert — Ubah Video jadi Musik MP3",
    "description": "Ubah video jadi musik MP3 atau MP4 secara gratis, cepat, dan privat.",
    "h1": "Ubah video jadi musik",
    "sub": "Konversi video ke MP3 atau MP4 dengan cepat. Unggah file atau tempel link file media, pilih format, lalu proses.",
    "extra": "",
}

# Halaman landing yang memakai konverter yang sama, dengan judul dan penjelasan sendiri (SEO).
HOME_PAGES = {
    "": HOME_DEFAULT,
    "mp4-ke-mp3": {
        "title": "Convert MP4 ke MP3 Online Gratis — zeConvert",
        "description": "Ubah file MP4 ke MP3 online gratis tanpa daftar. Pilih bitrate 128–320 kbps, hasil cepat dan privat.",
        "h1": "Convert MP4 ke MP3",
        "sub": "Ambil audio dari video MP4 dan simpan sebagai MP3 berkualitas tinggi. Unggah file, pilih bitrate, lalu proses.",
        "extra": """<h2>Cara mengubah MP4 ke MP3</h2>
<ol><li>Unggah file MP4 lewat bagian <em>Punya file sendiri?</em>, atau tempel link langsung ke file MP4.</li><li>Pilih format <strong>Audio MP3</strong> dan bitrate yang kamu mau.</li><li>Tekan tombol konversi, tunggu sampai selesai, lalu download hasilnya.</li></ol>
<h2>Bitrate mana yang sebaiknya dipilih?</h2>
<p>Bitrate menentukan kualitas dan ukuran file MP3. <strong>128 kbps</strong> cukup untuk suara seperti podcast atau ceramah. <strong>192 kbps</strong> seimbang untuk musik sehari-hari. <strong>256–320 kbps</strong> memberi kualitas terbaik untuk musik, dengan ukuran file lebih besar.</p>
<h2>Kenapa memakai zeConvert?</h2>
<p>Layanan ini gratis, tanpa daftar akun, dan memproses file langsung di server kami lalu menghapusnya otomatis. Hasil konversi hanya bisa diunduh oleh kamu sendiri dan tidak muncul di riwayat publik mana pun.</p>""",
    },
    "video-ke-musik": {
        "title": "Ubah Video jadi Musik MP3 Online — zeConvert",
        "description": "Ubah video jadi musik atau audio MP3 dengan mudah. Gratis, cepat, tanpa daftar, dan privat.",
        "h1": "Ubah video jadi musik",
        "sub": "Pisahkan suara dari video dan simpan sebagai file musik MP3. Cocok untuk video milikmu sendiri.",
        "extra": """<h2>Kapan konversi video ke musik berguna?</h2>
<ul><li>Menyimpan rekaman konser, acara, atau kelas yang kamu rekam sendiri sebagai audio.</li><li>Mengambil suara dari video wawancara atau rapat agar mudah didengar di perjalanan.</li><li>Membuat file audio yang lebih kecil untuk dibagikan ke teman atau dipakai di editor.</li></ul>
<h2>Format yang didukung</h2>
<p>zeConvert menerima format video dan audio yang umum seperti MP4, MKV, MOV, WebM, AVI, MP3, M4A, dan WAV, dengan ukuran file hingga 2 GB. Hasilnya dalam format MP3 atau MP4.</p>
<h2>Privasi</h2>
<p>File yang kamu unggah dihapus otomatis dari server, dan hanya sesi browsermu yang bisa mengunduh hasilnya.</p>""",
    },
}

STATIC_PAGES = {
    "panduan-konversi": ("Panduan Lengkap Konversi Video ke MP3 & MP4 — zeConvert", "Cara mengubah video ke MP3 atau MP4 dengan hasil jernih di HP dan laptop tanpa instal aplikasi.", """
<h1>Panduan Lengkap Konversi Video ke MP3 &amp; MP4</h1>
<p>zeConvert membantu kamu mengubah video menjadi audio MP3 atau menyimpan ulang video sebagai MP4 langsung dari browser, baik melalui tautan media maupun unggahan file dari perangkat sendiri.</p>
<h2>1. Memilih Sumber: Tautan vs File Lokal</h2>
<ul><li><strong>Melalui Tautan Online:</strong> Tempel URL publik ke kotak input di <a href="/">halaman utama</a>, pilih format MP4 atau MP3, lalu tekan <strong>Proses media</strong>. File akan langsung diunduh lewat browser.</li><li><strong>Melalui File Lokal:</strong> Buka panel <em>Punya file sendiri? Unggah dan konversi</em>, lalu seret file berformat MP4, MKV, MOV, WebM, AVI, M4A, atau WAV (maksimal 2 GB, durasi hingga 6 jam).</li></ul>
<h2>2. Kapan Sebaiknya Memilih MP3 vs MP4?</h2>
<ul><li>Pilih <strong>Audio MP3</strong> jika kamu hanya membutuhkan suara—misalnya rekaman kelas, wawancara, ceramah, atau musik latar—agar ukuran file jauh lebih kecil dan mudah diputar di pemutar musik apa pun.</li><li>Pilih <strong>Video MP4</strong> jika kamu membutuhkan tampilan visual beserta audio dalam format yang paling kompatibel untuk Android, iPhone, Smart TV, serta aplikasi editing video.</li></ul>
<h2>3. Tips Jika File Tidak Bersuara atau Gagal Diputar</h2>
<p>Sebagian video dari kamera atau rekaman layar memakai codec khusus seperti HEVC atau PCM yang tidak selalu didukung di semua ponsel lawas. Dengan mengonversinya ke <strong>MP4 (Standar 720p atau HD 1080p)</strong> di zeConvert, video dan audio disesuaikan ke format standar agar lancar diputar di seluruh perangkat.</p>
<h2>4. Etika &amp; Hak Cipta</h2>
<p>Pastikan setiap berkas atau tautan yang diproses adalah milikmu sendiri, berada di bawah lisensi bebas, atau memiliki izin resmi dari pemegang hak cipta.</p>"""),
    "panduan-bitrate-mp3": ("Panduan Memilih Bitrate MP3 & Resolusi Video MP4 — zeConvert", "Pahami perbedaan bitrate MP3 128, 192, 256, 320 kbps serta resolusi MP4 480p, 720p, dan 1080p.", """
<h1>Panduan Memilih Bitrate MP3 &amp; Resolusi Video MP4</h1>
<p>Memilih setelan kualitas yang tepat membuat hasil unduhan tetap nyaman didengar dan ditonton tanpa memboroskan ruang penyimpanan perangkat.</p>
<h2>Memahami Bitrate Audio MP3 (kbps)</h2>
<p><em>Bitrate</em> (kilobit per detik) menunjukkan seberapa banyak data audio yang disimpan setiap detik:</p>
<ul><li><strong>128 kbps (~0,9 MB per menit):</strong> Cukup jernih untuk suara manusia seperti podcast, diskusi, dan rekaman materi belajar.</li><li><strong>192 kbps (~1,4 MB per menit):</strong> Titik tengah terbaik untuk musik sehari-hari dengan ukuran file yang masih ringkas.</li><li><strong>256 kbps (~1,9 MB per menit):</strong> Kejernihan tinggi untuk pengguna earphone atau headphone berkualitas baik.</li><li><strong>320 kbps (~2,4 MB per menit):</strong> Standar tertinggi format MP3, menjaga detail instrumen dan dinamika suara mendekati sumber aslinya.</li></ul>
<h2>Memahami Resolusi Video MP4</h2>
<ul><li><strong>480p (Hemat):</strong> Ukuran paling kecil dan cepat diunduh, cocok saat kuota internet terbatas.</li><li><strong>720p (Standar HD):</strong> Gambar sudah tajam di layar smartphone dan laptop standar.</li><li><strong>1080p (Full HD):</strong> Memberikan ketajaman terbaik untuk layar besar, presentasi, dan dokumentasi jangka panjang.</li></ul>
<p>Siap mencoba? Kembali ke <a href="/">konverter utama zeConvert</a> atau baca <a href="/faq">FAQ lengkap</a>.</p>"""),
    "faq": ("Pertanyaan Umum (FAQ) — zeConvert", "Jawaban atas pertanyaan umum seputar cara kerja, batas ukuran, privasi, dan format di zeConvert.", """
<h1>Pertanyaan yang Sering Diajukan (FAQ)</h1>
<p>Halaman ini merangkum pertanyaan yang paling sering diajukan pengguna mengenai layanan konversi video dan audio di zeConvert.</p>
<h2>Apakah zeConvert gratis digunakan?</h2>
<p>Ya, seluruh fitur konversi MP4 dan MP3 di zeConvert gratis dan dapat dipakai tanpa membuat akun.</p>
<h2>Berapa batas ukuran dan durasi video?</h2>
<p>Ukuran berkas maksimal adalah <strong>2 GB</strong> dengan batas durasi hingga <strong>6 jam</strong> per proses. Untuk media berdurasi panjang di atas 1 jam, kami menyarankan setelan Standar 720p atau MP3 192 kbps.</p>
<h2>Apakah file saya aman dan privat?</h2>
<p>Ya. Tidak ada galeri atau riwayat unduhan publik. Hasil konversi hanya dapat diakses oleh sesi browser yang membuatnya, dan file sementara di server dibersihkan secara otomatis.</p>
<h2>Mengapa ukuran MP3 bisa berbeda untuk durasi yang sama?</h2>
<p>Ukuran MP3 berbanding lurus dengan bitrate yang dipilih. Lagu berdurasi 4 menit akan berukuran sekitar 3,6 MB pada 128 kbps, sekitar 5,6 MB pada 192 kbps, dan sekitar 9,6 MB pada 320 kbps.</p>
<h2>Browser apa saja yang didukung?</h2>
<p>zeConvert mendukung browser modern di desktop maupun mobile, termasuk Google Chrome, Mozilla Firefox, Microsoft Edge, dan Apple Safari.</p>"""),
    "tentang": ("Tentang zeConvert", "Tentang zeConvert, konverter video ke musik yang gratis, cepat, dan privat.", """
<h1>Tentang zeConvert</h1>
<p>zeConvert adalah layanan web untuk mengubah video menjadi musik (MP3) maupun menyimpan ulang video dalam format MP4 yang kompatibel di berbagai perangkat. Fokus kami adalah menyediakan alat yang ringan, jelas, bebas pendaftaran akun, dan mudah digunakan di ponsel maupun komputer.</p>
<h2>Prinsip kami</h2>
<ul><li><strong>Gratis dan sederhana.</strong> Langsung pakai dari browser tanpa perlu membuat akun atau memasang software tambahan.</li><li><strong>Privat.</strong> Tidak ada riwayat publik; akses hasil hanya berlaku untuk sesi browser yang memprosesnya.</li><li><strong>Bersih.</strong> Berkas sementara dibersihkan secara berkala dari server agar penyimpanan tetap terjaga.</li><li><strong>Edukasi pengguna.</strong> Selain alat konversi, kami menyediakan <a href="/panduan-konversi">panduan konversi</a> dan <a href="/panduan-bitrate-mp3">panduan kualitas audio/video</a> agar pengguna memilih format yang tepat.</li><li><strong>Bertanggung jawab.</strong> Gunakan hanya untuk konten yang kamu miliki atau yang boleh kamu simpan sesuai ketentuan hak cipta.</li></ul>
<h2>Didukung iklan</h2>
<p>Operasional server layanan ini didukung oleh iklan Google AdSense agar tetap dapat diakses secara gratis oleh pengunjung.</p>"""),
    "kebijakan-privasi": ("Kebijakan Privasi — zeConvert", "Kebijakan privasi zeConvert: data apa yang diproses, cookie, iklan, dan penghapusan file.", """
<h1>Kebijakan Privasi</h1>
<p>Terakhir diperbarui: 1 November 2026. Kebijakan ini menjelaskan bagaimana zeConvert (zeconvert.cloud) menangani data saat kamu memakai layanan ini.</p>
<h2>Data yang kami proses</h2>
<ul><li><strong>File yang kamu unggah atau link yang kamu masukkan</strong> diproses di server hanya untuk membuat hasil konversi. File sumber dan hasil dihapus otomatis, paling lama sekitar satu jam setelah pekerjaan dibuat.</li><li><strong>Alamat IP</strong> dipakai sementara untuk membatasi penyalahgunaan (pembatasan jumlah permintaan) dan tercatat di log server standar.</li><li>Kami tidak meminta nama, email, atau kata sandi, dan tidak membuat akun pengguna.</li></ul>
<h2>Cookie</h2>
<ul><li><strong>Cookie fungsional <code>zc_owner</code></strong>: pengenal acak yang berlaku sekitar 24 jam, supaya hanya browsermu yang bisa melihat dan mengunduh hasil konversimu. Cookie ini tidak dipakai untuk pelacakan.</li><li><strong>Cookie iklan</strong> dari Google dan mitranya (lihat di bawah).</li></ul>
<h2>Iklan Google AdSense</h2>
<p>Kami memakai Google AdSense untuk menampilkan iklan. Google dan mitra iklannya dapat memakai cookie untuk menayangkan iklan berdasarkan kunjunganmu ke situs ini dan situs lain. Kamu dapat mengelola atau menonaktifkan personalisasi iklan lewat <a href="https://adssettings.google.com" rel="noopener">Pengaturan Iklan Google</a> dan mempelajari cara Google memakai data di <a href="https://policies.google.com/technologies/partner-sites" rel="noopener">policies.google.com/technologies/partner-sites</a>.</p>
<h2>Berbagi data</h2>
<p>Kami tidak menjual data pribadi. File yang kamu proses tidak dibagikan ke pihak ketiga. Pihak ketiga yang berinteraksi dengan browsermu hanyalah penyedia iklan (Google) dan font (Google Fonts).</p>
<h2>Hak dan pertanyaan</h2>
<p>Karena kami tidak menyimpan data pribadi jangka panjang, tidak ada akun yang perlu dihapus. Kamu dapat menghapus cookie browsermu kapan saja. Kebijakan ini bisa diperbarui, dan tanggal perubahan akan tertera di atas.</p>"""),
    "syarat-layanan": ("Syarat Layanan — zeConvert", "Syarat dan ketentuan penggunaan layanan zeConvert.", """
<h1>Syarat Layanan</h1>
<p>Terakhir diperbarui: 1 November 2026. Dengan memakai zeConvert, kamu setuju dengan syarat berikut.</p>
<h2>Penggunaan yang diizinkan</h2>
<ul><li>Gunakan layanan hanya untuk file yang kamu miliki atau yang kamu punya izin untuk disimpan dan diubah.</li><li>Kamu bertanggung jawab penuh atas konten yang kamu proses dan atas kepatuhannya terhadap hukum hak cipta yang berlaku.</li></ul>
<h2>Yang dilarang</h2>
<ul><li>Memproses konten ilegal atau yang melanggar hak pihak lain.</li><li>Mengganggu layanan, misalnya dengan permintaan otomatis berlebihan atau mencoba menembus pembatasan keamanan.</li></ul>
<h2>Batas layanan</h2>
<p>Ada batas ukuran file (hingga 2 GB), durasi, dan jumlah permintaan per menit. Hasil konversi disimpan sementara dan dihapus otomatis, jadi segera unduh hasilmu.</p>
<h2>Tanpa jaminan</h2>
<p>Layanan disediakan apa adanya tanpa jaminan ketersediaan atau hasil tertentu. Kami tidak bertanggung jawab atas kerugian yang timbul dari penggunaan layanan. Kami dapat mengubah atau menghentikan layanan sewaktu-waktu.</p>
<h2>Privasi</h2>
<p>Penanganan data dijelaskan di <a href="/kebijakan-privasi">Kebijakan Privasi</a>.</p>"""),
}

LEGAL_SLUGS = {"kebijakan-privasi", "syarat-layanan"}
ADSENSE_SCRIPT = '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-6898176272342462" crossorigin="anonymous"></script>'

FOOTER_NAV = ('<nav class="foot-nav"><a href="/">Beranda</a><a href="/panduan-konversi">Panduan Konversi</a>'
              '<a href="/panduan-bitrate-mp3">Panduan Bitrate</a><a href="/faq">FAQ</a>'
              '<a href="/mp4-ke-mp3">MP4 ke MP3</a><a href="/video-ke-musik">Video ke Musik</a>'
              '<a href="/tentang">Tentang</a><a href="/kebijakan-privasi">Kebijakan Privasi</a>'
              '<a href="/syarat-layanan">Syarat Layanan</a></nav>')

LOGO = ('<svg viewBox="0 0 40 40" fill="none" aria-hidden="true">'
        '<defs><linearGradient id="zc-grad" x1="6" y1="6" x2="34" y2="34" gradientUnits="userSpaceOnUse">'
        '<stop offset="0%" stop-color="#38bdf8"/><stop offset="100%" stop-color="#34d399"/></linearGradient></defs>'
        '<rect x="1.5" y="1.5" width="37" height="37" rx="10" fill="#0b1120" stroke="rgba(148,163,184,0.28)" stroke-width="1.5"/>'
        '<path d="M10.5 14l6.5 6-6.5 6" stroke="url(#zc-grad)" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M20.5 15h9m0 0l-3.2-3.2M29.5 15l-3.2 3.2" stroke="url(#zc-grad)" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M20 26.5h9.5" stroke="#34d399" stroke-width="2.6" stroke-linecap="round" opacity="0.85"/></svg>')

STATIC_TEMPLATE = """<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="dark"><meta name="theme-color" content="#070b14">
<title>{title}</title><meta name="description" content="{description}"><link rel="canonical" href="{canonical}">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 40 40%27 fill=%27none%27%3E%3Crect x=%271.5%27 y=%271.5%27 width=%2737%27 height=%2737%27 rx=%2710%27 fill=%27%230b1120%27 stroke=%27%2338bdf8%27 stroke-width=%271.5%27/%3E%3Cpath d=%27M10.5 14l6.5 6-6.5 6%27 stroke=%27%2338bdf8%27 stroke-width=%272.6%27 stroke-linecap=%27round%27 stroke-linejoin=%27round%27/%3E%3Cpath d=%27M20.5 15h9m0 0l-3.2-3.2M29.5 15l-3.2 3.2%27 stroke=%27%2334d399%27 stroke-width=%272.4%27 stroke-linecap=%27round%27 stroke-linejoin=%27round%27/%3E%3Cpath d=%27M20 26.5h9.5%27 stroke=%27%2334d399%27 stroke-width=%272.6%27 stroke-linecap=%27round%27/%3E%3C/svg%3E">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500;600&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap">
<meta name="google-adsense-account" content="ca-pub-6898176272342462">
{ad_script}
<link rel="stylesheet" href="/static/style.css?v=21"></head>
<body><div class="page"><header class="topbar"><a class="brand" href="/">{logo}<span>ze<b>Convert</b></span></a></header>
<main class="card prose">{body}</main><footer>{nav}<p>Gunakan hanya untuk konten yang kamu miliki atau boleh kamu simpan.</p></footer></div></body></html>"""


def render_home(slug: str) -> str | None:
    meta = HOME_PAGES.get(slug)
    if meta is None:
        return None
    text = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    canonical = f"{SITE_URL}/{slug}" if slug else f"{SITE_URL}/"
    values = {"TITLE": html.escape(meta["title"]), "DESC": html.escape(meta["description"], quote=True), "CANON": canonical,
              "H1": html.escape(meta["h1"]), "SUB": html.escape(meta["sub"]), "EXTRA": meta["extra"], "NAV": FOOTER_NAV}
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def render_static(slug: str) -> str | None:
    page = STATIC_PAGES.get(slug)
    if page is None:
        return None
    title, description, body = page
    ad_script = "" if slug in LEGAL_SLUGS else ADSENSE_SCRIPT
    return STATIC_TEMPLATE.format(title=html.escape(title), description=html.escape(description, quote=True), canonical=f"{SITE_URL}/{slug}",
                                  logo=LOGO, body=body, nav=FOOTER_NAV, ad_script=ad_script)


def sitemap() -> str:
    slugs = [slug for slug in HOME_PAGES] + list(STATIC_PAGES)
    urls = "".join(f"<url><loc>{SITE_URL}/{slug}</loc></url>" for slug in slugs)
    return f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'


def robots() -> str:
    return f"User-agent: *\nDisallow: /api/\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n"
