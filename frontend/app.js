const $ = (selector) => document.querySelector(selector);
const input = $('#media-url');
const preview = $('#preview-section');
const player = $('#preview-player');
const fileInput = $('#media-file');
const fileLabel = $('#file-label');
const uploadButton = $('#process-upload');
const pasteButton = $('#paste-url');
let currentJobId = null;
let pollTimer = null;
let selectedFile = null;
let previewObjectUrl = null;
let currentPreviewId = null;
let previewSourceValue = null;

(function initHeroTypewriter() {
  const h1 = $('.hero-copy h1');
  if (!h1) return;
  const text = h1.textContent.trim();
  if (!/^Ubah\s+.+\s+jadi\s+musik$/i.test(text)) return;

  h1.setAttribute('aria-label', 'Ubah video jadi musik, ubah link jadi video MP4 dan audio MP3');

  const wrap = document.createElement('span');
  wrap.className = 'hero-typed-wrap';
  wrap.setAttribute('aria-hidden', 'true');

  const srcSpan = document.createElement('span');
  srcSpan.className = 'hero-src';
  srcSpan.textContent = 'video';

  const midSpan = document.createElement('span');
  midSpan.className = 'hero-mid';
  midSpan.textContent = ' jadi ';

  const dstSpan = document.createElement('span');
  dstSpan.id = 'hero-typed';
  dstSpan.className = 'hero-typed';
  dstSpan.textContent = 'musik';

  const caret = document.createElement('span');
  caret.className = 'hero-caret';

  wrap.append(srcSpan, midSpan, dstSpan, caret);
  h1.textContent = '';
  h1.append(document.createTextNode('Ubah '), wrap);

  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const pairs = [
    { src: 'video', dst: 'musik' },
    { src: 'link', dst: 'video' },
    { src: 'Shorts & Reels', dst: 'MP3' },
    { src: 'tautan media', dst: 'MP4 HD' },
  ];

  let pairIndex = 0;
  let charIndex = `${pairs[0].src} jadi ${pairs[0].dst}`.length;
  let isDeleting = true;

  function renderPhrase(pair, count) {
    const mid = ' jadi ';
    const srcLen = pair.src.length;
    const midEnd = srcLen + mid.length;

    srcSpan.textContent = pair.src.slice(0, Math.min(count, srcLen));
    midSpan.textContent = count > srcLen ? mid.slice(0, Math.min(count - srcLen, mid.length)) : '';
    dstSpan.textContent = count > midEnd ? pair.dst.slice(0, count - midEnd) : '';
  }

  function step() {
    const pair = pairs[pairIndex];
    const fullLen = `${pair.src} jadi ${pair.dst}`.length;

    if (isDeleting) {
      charIndex -= 1;
      renderPhrase(pair, charIndex);
      caret.classList.add('is-typing');
      if (charIndex === 0) {
        isDeleting = false;
        pairIndex = (pairIndex + 1) % pairs.length;
        window.setTimeout(step, 260);
        return;
      }
      window.setTimeout(step, 42);
      return;
    }

    charIndex += 1;
    renderPhrase(pair, charIndex);
    if (charIndex === fullLen) {
      caret.classList.remove('is-typing');
      isDeleting = true;
      window.setTimeout(step, 1900);
      return;
    }
    caret.classList.add('is-typing');
    window.setTimeout(step, 78);
  }

  window.setTimeout(step, 1900);
}());

function setButtonLabel(button, text) {
  const target = button.querySelector('.btn-text') || button;
  target.textContent = text;
}

function syncPasteButton() {
  if (!pasteButton) return;
  const hasValue = Boolean(input.value.trim());
  setButtonLabel(pasteButton, hasValue ? 'Hapus' : 'Tempel');
  const label = hasValue ? 'Hapus URL' : 'Tempel dari clipboard';
  pasteButton.title = label;
  pasteButton.setAttribute('aria-label', label);
  const icon = pasteButton.querySelector('svg');
  if (icon) {
    icon.innerHTML = hasValue
      ? '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>'
      : '<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>';
  }
}

input.addEventListener('input', syncPasteButton);
input.addEventListener('paste', () => {
  window.setTimeout(() => {
    syncPasteButton();
    const value = input.value.trim();
    if (value.startsWith('https://')) inspectUrl(value, { silent: true });
  }, 0);
});
input.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    event.preventDefault();
    $('#process-url').click();
  }
});

if (pasteButton) {
  pasteButton.addEventListener('click', async () => {
    if (input.value.trim()) {
      input.value = '';
      currentPreviewId = null;
      previewSourceValue = null;
      $('#source-status').classList.add('hidden');
      preview.classList.add('hidden');
      syncPasteButton();
      input.focus();
      return;
    }
    try {
      const text = await navigator.clipboard.readText();
      if (text && text.trim()) {
        input.value = text.trim();
        syncPasteButton();
        input.focus();
        if (input.value.startsWith('https://')) inspectUrl(input.value, { silent: true });
      } else {
        showStatus('Clipboard kosong. Salin tautan terlebih dahulu.', 'error');
        input.focus();
      }
    } catch {
      showStatus('Akses clipboard diblokir browser. Tempel manual dengan Ctrl+V.', 'error');
      input.focus();
    }
  });
}

function openUploadSection(triggerPicker = false) {
  const details = $('#upload-details');
  if (!details) return;
  details.open = true;
  details.scrollIntoView({ behavior: 'smooth', block: 'center' });
  if (triggerPicker && fileInput) {
    window.setTimeout(() => fileInput.click(), 180);
  }
}

$('#omni-upload-btn')?.addEventListener('click', () => openUploadSection(true));
$('#chip-upload')?.addEventListener('click', () => openUploadSection(false));

function showStatus(message, variant = 'error', stateLabel = null) {
  const status = $('#source-status');
  $('#source-state').textContent = stateLabel || (variant === 'success' ? 'Siap' : 'Perlu tindakan');
  $('#source-message').textContent = message;
  status.className = `source-status ${variant}`;
  status.classList.remove('hidden');
}

function sourceState(resolution) {
  if (resolution.can_process) return 'Sumber media terdeteksi · validasi file diperlukan';
  if (resolution.metadata_available) return 'Metadata tersedia · file sumber tidak tersedia';
  if (resolution.can_embed) return 'Embed tersedia · sumber media belum tersedia';
  if (resolution.status === 'invalid_url') return 'URL tidak valid';
  return 'Sumber media tidak dapat diproses';
}

function errorText(detail, fallback) {
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') return [detail.message, detail.next_step].filter(Boolean).join(' ');
  return fallback;
}

function getPlatformLink(value, resolution = null) {
  try {
    let url;
    try {
      url = new URL(resolution?.webpage_url || value);
    } catch {
      url = new URL(value);
    }
    const host = url.hostname.toLowerCase().replace(/^www\./, '');
    const isHost = (domain) => host === domain || host.endsWith(`.${domain}`);
    if (isHost('youtu.be') || isHost('youtube.com')) {
      const pathId = isHost('youtu.be')
        ? url.pathname.split('/').filter(Boolean)[0]
        : url.pathname.replace(/\/$/, '') === '/watch'
          ? url.searchParams.get('v')
          : url.pathname.match(/^\/(?:embed|shorts|live|v)\/([^/?]+)/)?.[1];
      const id = (pathId && /^[\w-]{11}$/.test(pathId) ? pathId : null)
        || (resolution?.video_id && /^[\w-]{11}$/.test(String(resolution.video_id)) ? String(resolution.video_id) : null);
      return id ? { platform: 'YouTube', embed: `https://www.youtube-nocookie.com/embed/${encodeURIComponent(id)}` } : { platform: 'YouTube', error: 'Tautan YouTube tidak dikenali. Gunakan link video, Shorts, atau Live yang valid.' };
    }
    if (isHost('instagram.com')) {
      const match = url.pathname.match(/^\/(?:[\w.-]+\/)?(p|reel|reels|tv)\/([^/]+)/);
      if (match) {
        const kind = match[1] === 'reels' ? 'reel' : match[1];
        return { platform: 'Instagram', embed: `https://www.instagram.com/${kind}/${encodeURIComponent(match[2])}/embed/` };
      }
      return { platform: 'Instagram', error: 'Instagram hanya bisa menampilkan postingan atau Reel publik yang menyediakan embed.' };
    }
    if (isHost('facebook.com') || isHost('fb.watch')) {
      const embed = new URL('https://www.facebook.com/plugins/video.php');
      embed.searchParams.set('href', url.href); embed.searchParams.set('show_text', 'false'); embed.searchParams.set('width', '720');
      return { platform: 'Facebook', embed: embed.href };
    }
    if (isHost('tiktok.com')) {
      const pathId = url.pathname.match(/^\/@[^/]+\/(?:video|photo)\/(\d+)/)?.[1] || url.pathname.match(/^\/(?:v|embed(?:\/v2)?)\/(\d+)/)?.[1];
      const id = pathId || (/^\d+$/.test(String(resolution?.video_id || '')) ? String(resolution.video_id) : null);
      return id ? { platform: 'TikTok', embed: `https://www.tiktok.com/embed/v2/${encodeURIComponent(id)}` } : { platform: 'TikTok' };
    }
    return null;
  } catch { return null; }
}

function setExpanded(on) {
  preview.classList.toggle('expanded', on);
  const button = $('#expand-preview');
  button.textContent = on ? 'Perkecil' : 'Perbesar'; button.setAttribute('aria-pressed', String(on));
}
$('#expand-preview').addEventListener('click', () => setExpanded(!preview.classList.contains('expanded')));

function showPreview({ title, details, url, element }) {
  if (element) {
    player.classList.remove('hidden');
    player.replaceChildren(element);
  } else {
    player.replaceChildren();
    player.classList.add('hidden');
  }
  $('#preview-title').textContent = title;
  $('#preview-details').textContent = details;
  preview.classList.remove('hidden');
  setExpanded(false);
}

function formatDuration(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  if (!total) return '';
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`;
}

function triggerBrowserDownload(url, filename) {
  const link = document.createElement('a');
  link.href = url;
  if (filename) link.download = filename;
  link.style.display = 'none';
  document.body.append(link);
  link.click();
  link.remove();
}

async function inspectUrl(value, { silent = false } = {}) {
  const button = $('#show-link');
  button.disabled = true;
  if (!silent) setButtonLabel(button, 'Memeriksa…');
  try {
    const classifyResponse = await fetch('/api/media/inspect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: value }) });
    if (!classifyResponse.ok) {
      if (!silent) throw new Error('Backend tidak dapat memeriksa metadata. Pastikan server sedang berjalan.');
      return;
    }
    const resolution = await classifyResponse.json();
    if (resolution.can_embed) {
      const platform = getPlatformLink(value, resolution);
      let element = null;
      if (platform?.embed) {
        const frame = document.createElement('iframe'); frame.src = platform.embed; frame.title = `${platform.platform} video embed`;
        frame.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share';
        frame.referrerPolicy = 'strict-origin-when-cross-origin'; frame.allowFullscreen = true;
        element = frame;
      } else if (resolution.thumbnail) {
        const img = document.createElement('img');
        img.src = resolution.thumbnail;
        img.alt = resolution.title || 'Pratinjau';
        img.referrerPolicy = 'no-referrer';
        element = img;
      }
      if (!element && !resolution.can_process && !resolution.metadata_available) {
        if (!silent) showStatus(platform?.error || resolution.message, 'error');
        return;
      }
      if (previewObjectUrl) { URL.revokeObjectURL(previewObjectUrl); previewObjectUrl = null; }
      currentPreviewId = null; previewSourceValue = value;
      const platformName = platform?.platform || resolution.provider || 'Platform';
      const metadata = [resolution.author, resolution.duration && formatDuration(resolution.duration)].filter(Boolean).join(' · ');
      showPreview({ title: resolution.title || `Video ${platformName}`, details: metadata || `Embed ${platformName}`, element });
      showStatus([resolution.message, resolution.next_step].filter(Boolean).join(' '), resolution.can_process || resolution.metadata_available ? 'success' : 'error', sourceState(resolution));
      return;
    }
    if (silent) return;
    if (!resolution.can_process) { showStatus(`${resolution.message} ${resolution.next_step}`, 'error', sourceState(resolution)); return; }
    const response = await fetch('/api/previews', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: value }) });
    const data = await response.json();
    if (!response.ok) throw new Error(errorText(data.detail, 'Media tidak dapat dipratinjau.'));
    currentPreviewId = data.id; previewSourceValue = value;
    if (previewObjectUrl) { URL.revokeObjectURL(previewObjectUrl); previewObjectUrl = null; }
    const isVideo = data.mime_type.startsWith('video/');
    const media = document.createElement(isVideo ? 'video' : 'audio');
    media.controls = true; media.preload = 'metadata';
    const source = document.createElement('source'); source.src = data.player_url; source.type = data.mime_type;
    media.append(source);
    const details = [data.format || data.mime_type, data.resolution, data.video_codec && `Video ${data.video_codec}`, data.audio_codec && `Audio ${data.audio_codec}`, formatDuration(data.duration), `${(data.size / 1024 / 1024).toFixed(2)} MB`].filter(Boolean).join(' · ');
    showPreview({ title: data.title, details, element: media });
    showStatus('Media siap diputar atau langsung dikonversi ke MP4/MP3.', 'success', 'Sumber media tersedia');
  } catch (error) {
    if (!silent) showStatus(error.message, 'error');
  } finally {
    button.disabled = false;
    setButtonLabel(button, 'Tampilkan');
  }
}

$('#show-link').addEventListener('click', () => {
  const value = input.value.trim();
  if (!value) { input.focus(); return; }
  inspectUrl(value, { silent: false });
});

$('#url-output').addEventListener('change', () => {
  const mp3 = $('#url-output').value === 'mp3';
  $('#url-bitrate-field').classList.toggle('hidden', !mp3);
  $('#url-quality-field').classList.toggle('hidden', mp3);
});
$('#url-output').dispatchEvent(new Event('change'));

function updateUploadOutput() {
  const output = $('#upload-output').value;
  $('#upload-bitrate-field').classList.toggle('hidden', output !== 'mp3');
  $('#upload-quality-field').classList.toggle('hidden', output !== 'mp4');
  setButtonLabel(uploadButton, `Konversi ke ${output.toUpperCase()}`);
}
$('#upload-output').addEventListener('change', updateUploadOutput);

function setSelectedFile(file) {
  if (!file) return;
  if (previewObjectUrl) { URL.revokeObjectURL(previewObjectUrl); previewObjectUrl = null; }
  selectedFile = null;
  uploadButton.disabled = true;
  if (file.size > 2048 * 1024 * 1024) { fileLabel.textContent = 'Pilih atau jatuhkan file di sini'; alert('Ukuran file maksimal 2 GB.'); return; }
  selectedFile = file;
  currentPreviewId = null; previewSourceValue = null;
  fileLabel.textContent = `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} MB`;
  uploadButton.disabled = false;
  if (file.type.startsWith('video/') || file.type.startsWith('audio/')) {
    previewObjectUrl = URL.createObjectURL(file);
    const media = document.createElement(file.type.startsWith('video/') ? 'video' : 'audio');
    media.controls = true; media.preload = 'metadata'; media.src = previewObjectUrl;
    const kind = file.type.startsWith('video/') ? 'Video lokal' : 'Audio lokal';
    showPreview({ title: file.name, details: `${kind} · ${(file.size / 1024 / 1024).toFixed(1)} MB`, element: media });
    media.addEventListener('loadedmetadata', () => {
      const duration = Number.isFinite(media.duration) ? ` · ${Math.round(media.duration)} detik` : '';
      $('#preview-details').textContent = `${kind} · ${(file.size / 1024 / 1024).toFixed(1)} MB${duration}`;
    }, { once: true });
  } else preview.classList.add('hidden');
}
fileInput.addEventListener('change', () => setSelectedFile(fileInput.files[0]));
const drop = $('#drop-zone');
drop.addEventListener('dragover', (event) => { event.preventDefault(); drop.classList.add('drag'); });
drop.addEventListener('dragleave', () => drop.classList.remove('drag'));
drop.addEventListener('drop', (event) => { event.preventDefault(); drop.classList.remove('drag'); setSelectedFile(event.dataTransfer.files[0]); });

function showJob(job) {
  $('#job-section').classList.remove('hidden');
  $('#job-name').textContent = job.output_name || job.filename;
  $('#job-status').textContent = job.stage;
  $('#job-message').textContent = job.message || '';
  Loader.update(job);
  const badge = $('#job-badge'); badge.textContent = job.status === 'completed' ? 'Selesai' : job.status === 'failed' ? 'Gagal' : job.status === 'queued' ? 'Antrean' : 'Memproses';
  badge.className = `badge ${job.status === 'completed' ? 'done' : ['failed', 'canceled'].includes(job.status) ? 'failed' : ''}`;
  if (job.status === 'completed') showStatus(job.message || 'File siap diunduh.', 'success', 'Konversi selesai');
  else if (job.status === 'failed') showStatus(job.message || 'Pemrosesan gagal.', 'error', 'Sumber/proses gagal');
  else if (job.status === 'canceled') showStatus(job.message || 'Pekerjaan dibatalkan.', 'error', 'Dibatalkan');
  else {
    const processingState = job.status === 'queued' ? 'Menunggu pemrosesan'
      : job.stage === 'Mengunduh media' || job.stage === 'Mengambil media' ? 'Sedang mengunduh'
        : job.stage === 'Memvalidasi media' || job.stage === 'Memvalidasi hasil' ? 'Sedang memvalidasi'
          : job.stage.startsWith('Mengonversi') || job.stage === 'Menggabungkan bagian' ? 'Sedang mengonversi' : 'Sedang diproses';
    showStatus(job.message || job.stage, 'success', processingState);
  }
  $('#job-ad').classList.remove('hidden'); // iklan muncul begitu tombol proses ditekan
  $('#cancel-job').classList.toggle('hidden', !['queued', 'processing'].includes(job.status));
  const result = $('#job-result');
  if (job.status === 'completed') {
    result.classList.remove('hidden');
    $('#result-name').textContent = job.output_name;
    $('#result-size').textContent = job.output_size ? `${(job.output_size / 1024 / 1024).toFixed(2)} MB` : '';
    const dl = $('#download-result');
    dl.href = job.download_url || `/api/jobs/${encodeURIComponent(job.id)}/download`;
    if (job.output_name) dl.download = job.output_name;
  } else result.classList.add('hidden');
  $('#job-privacy').classList.toggle('hidden', job.status !== 'completed');
}

function showQuickReady(data) {
  clearInterval(pollTimer);
  currentJobId = null;
  if (data.title || data.thumbnail) {
    let element = null;
    if (data.thumbnail) {
      const img = document.createElement('img');
      img.src = data.thumbnail;
      img.alt = data.title || 'Pratinjau';
      img.referrerPolicy = 'no-referrer';
      element = img;
    }
    const details = [data.author, data.duration && formatDuration(data.duration), data.filesize && `${(data.filesize / 1024 / 1024).toFixed(2)} MB`].filter(Boolean).join(' · ') || 'Siap diunduh via browser';
    if (element || preview.classList.contains('hidden')) {
      showPreview({ title: data.title || data.output_name, details, element });
    }
  }
  const nowSec = Date.now() / 1000;
  showJob({
    id: data.token,
    filename: data.output_name,
    output_name: data.output_name,
    output_kind: data.output_kind,
    output_size: data.filesize || null,
    download_url: data.download_url,
    status: 'completed',
    stage: 'Siap diunduh via browser',
    progress: 100,
    message: 'Pengunduhan langsung dimulai di Chrome. Klik Download jika perlu mengunduh ulang.',
    created_at: nowSec,
    updated_at: nowSec,
  });
  showStatus('Link siap! Pengunduhan langsung dimulai di browser.', 'success', 'Langsung diunduh');
}

async function watchJob(job) {
  currentJobId = job.id;
  showJob(job);
  clearInterval(pollTimer);
  if (['completed', 'failed', 'canceled'].includes(job.status)) return;
  pollTimer = setInterval(async () => {
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(currentJobId)}`);
      if (!response.ok) throw new Error('Pekerjaan tidak tersedia.');
      const latest = await response.json(); showJob(latest);
      if (['completed', 'failed', 'canceled'].includes(latest.status)) clearInterval(pollTimer);
    } catch (error) {
      clearInterval(pollTimer); $('#job-message').textContent = error.message;
    }
  }, 400);
}

$('#process-url').addEventListener('click', async () => {
  const value = input.value.trim();
  if (!value) { showStatus('Masukkan URL HTTPS langsung ke file media.', 'error'); return; }
  const button = $('#process-url'); button.disabled = true; setButtonLabel(button, 'Membaca link…');
  try {
    const body = { output: $('#url-output').value, bitrate: Number($('#url-bitrate').value), quality: $('#url-quality').value };
    if (currentPreviewId && previewSourceValue === value) {
      body.preview_id = currentPreviewId;
    } else {
      body.url = value;
      const quickRes = await fetch('/api/media/quick', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const quickData = await quickRes.json().catch(() => ({}));
      if (quickRes.ok && quickData.download_url) {
        showQuickReady(quickData);
        triggerBrowserDownload(quickData.download_url, quickData.output_name);
        return;
      }
      const detail = quickData.detail;
      const shouldFallback = quickRes.status >= 500 || (detail && typeof detail === 'object' && detail.code === 'stream_unavailable' && String(detail.message || '').includes('Stream langsung tidak tersedia'));
      if (!shouldFallback) {
        if (detail && typeof detail === 'object') showStatus([detail.message, detail.next_step].filter(Boolean).join(' '), 'error', 'Sumber tidak dapat diproses');
        else throw new Error(errorText(detail, 'Tidak dapat memproses URL.'));
        return;
      }
      setButtonLabel(button, 'Memulai…');
    }

    const response = await fetch('/api/jobs/download', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await response.json(); if (!response.ok) {
      const detail = data.detail;
      if (detail && typeof detail === 'object') showStatus([detail.message, detail.next_step].filter(Boolean).join(' '), 'error', 'Sumber tidak dapat diproses');
      else throw new Error(errorText(detail, 'Tidak dapat memproses URL.'));
      return;
    }
    currentPreviewId = null; previewSourceValue = null;
    showStatus('Permintaan diterima. Sedang menyiapkan media sebelum konversi.', 'success', 'Menunggu pemrosesan');
    await watchJob(data);
  } catch (error) { showStatus(error.message, 'error'); }
  finally { button.disabled = false; setButtonLabel(button, 'Proses media'); }
});

uploadButton.addEventListener('click', async () => {
  const file = selectedFile; if (!file) return;
  uploadButton.disabled = true; setButtonLabel(uploadButton, 'Mengunggah…');
  try {
    const form = new FormData(); form.append('file', file); form.append('output', $('#upload-output').value); form.append('bitrate', $('#upload-bitrate').value); form.append('quality', $('#upload-quality').value);
    const response = await fetch('/api/jobs/upload', { method: 'POST', body: form });
    const data = await response.json(); if (!response.ok) throw new Error(errorText(data.detail, 'Upload gagal.'));
    await watchJob(data);
  } catch (error) { alert(error.message); }
  finally { uploadButton.disabled = false; updateUploadOutput(); }
});

$('#cancel-job').addEventListener('click', async () => {
  if (!currentJobId) return;
  const button = $('#cancel-job'); button.disabled = true; setButtonLabel(button, 'Membatalkan…');
  try {
    const response = await fetch(`/api/jobs/${encodeURIComponent(currentJobId)}/cancel`, { method: 'POST' });
    const data = await response.json();
    if (!response.ok) throw new Error(errorText(data.detail, 'Pekerjaan tidak dapat dibatalkan.'));
    clearInterval(pollTimer); showJob(data);
  } catch (error) { $('#job-message').textContent = error.message; }
  finally { button.disabled = false; setButtonLabel(button, 'Batalkan pekerjaan'); }
});

syncPasteButton();
updateUploadOutput();
