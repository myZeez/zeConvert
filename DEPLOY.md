# Deploy zeConvert ke VPS (Ubuntu 24.04)

Ganti `IP_VPS` dengan alamat IP dari email/dashboard Rumahweb. Jangan bagikan password root ke siapa pun.

## 1. Login dan amankan server (dari PowerShell di PC-mu)

```powershell
ssh root@IP_VPS
```

Di server:

```bash
apt update && apt upgrade -y
# swap 2 GB (RAM server cuma 2 GB)
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
# firewall: hanya SSH, HTTP, HTTPS
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable
```

## 2. Pasang Docker

```bash
curl -fsSL https://get.docker.com | sh
```

## 3. Kirim proyek ke server (dari PowerShell di PC-mu, di folder proyek)

```powershell
ssh root@IP_VPS "mkdir -p /opt/zeconvert"
scp -r backend frontend Dockerfile docker-compose.yml Caddyfile .dockerignore root@IP_VPS:/opt/zeconvert/
```

## 4. Jalankan

```bash
cd /opt/zeconvert
docker compose up -d --build
docker compose logs -f app
```

Buka `http://IP_VPS` di browser.

## 5. Domain + HTTPS (nanti, setelah punya domain)

Arahkan record A domain ke `IP_VPS`, lalu di server:

```bash
cd /opt/zeconvert
echo 'SITE_ADDRESS=namadomain.com' > .env
docker compose up -d
```

Caddy mengurus sertifikat HTTPS otomatis.

## Pengaturan (file `.env` di server)

| Variabel | Bawaan | Arti |
|---|---|---|
| `YT_DLP_ENABLED` | `false` | Fitur link YouTube. Nyalakan hanya untuk pemakaian pribadi. |
| `MAX_CONCURRENT_JOBS` | `1` | Konversi bersamaan (RAM 2 GB: biarkan 1). |
| `JOBS_PER_MINUTE` | `4` | Batas pembuatan pekerjaan per IP. |
| `MAX_UPLOAD_MB` | `200` | Batas unggahan. |

## Pembaruan dan perawatan

```bash
cd /opt/zeconvert && docker compose up -d --build   # setelah kirim ulang file
docker compose logs --tail 100 app                   # lihat log
docker system prune -f                               # bersihkan sisa build
```
