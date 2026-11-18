// Loader pekerjaan. Semua gerak dihitung dari waktu (rAF + easing eksponensial, tanpa bounce):
// panah unduh → kotak berputar (konversi) → centang. Bentuk berubah wujud, tidak potong/fade antar tahap.
(() => {
  const $ = (s) => document.querySelector(s);
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const N = 72;
  const MARKS = { arrow: 'M0 -8 L0 8 M-7 1 L0 8 L7 1', check: 'M-9 0 L-3 6 L9 -7', cross: 'M-7 -7 L7 7 M7 -7 L-7 7' };
  const PHASE = {
    download: { n: 2, R: 17, spin: 0, mark: 'arrow' },
    convert: { n: 4, R: 14, spin: 1.6, mark: null },
    done: { n: 2, R: 25, spin: 0, mark: 'check' },
    failed: { n: 2, R: 25, spin: 0, mark: 'cross' },
  };

  const s = { id: null, phase: 'download', step: 0, sawDownload: false, raw: null, indeterminate: true, active: false,
    p: 0, n: 2, R: 17, spin: 0, spinTarget: 0, rot: 0, ringSpin: 0, w: 1, markKind: 'arrow', markOpacity: 0,
    created: 0, updated: 0, last: 0, running: false };

  const ease = (dt, rate) => (reduce ? 1 : 1 - Math.exp(-dt * rate)); // exponential approach, never overshoots

  function shapePath(n, R, rot) {
    let d = '';
    for (let i = 0; i < N; i++) {
      const a = (i / N) * Math.PI * 2, c = Math.cos(a), si = Math.sin(a);
      const r = R / Math.pow(Math.abs(c) ** n + Math.abs(si) ** n, 1 / n);
      d += `${i ? 'L' : 'M'}${(r * Math.cos(a + rot)).toFixed(2)} ${(r * Math.sin(a + rot)).toFixed(2)}`;
    }
    return d + 'Z';
  }

  function fmtTime(ms) {
    const t = Math.max(0, Math.round(ms / 1000));
    return `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`;
  }

  function frame(now) {
    const dt = Math.min(0.1, (now - s.last) / 1000 || 0.016); s.last = now;
    const target = PHASE[s.phase];
    const kn = ease(dt, 7), kr = ease(dt, 6);
    const pn = s.n, pR = s.R;
    s.n += (target.n - s.n) * kn;
    s.R += (target.R - s.R) * kr;
    s.spin += (target.spin - s.spin) * ease(dt, 3);
    s.rot += s.spin * dt;
    s.w += ((s.indeterminate ? 1 : 0) - s.w) * ease(dt, 5);
    if (!s.indeterminate && s.raw != null) s.p += (s.raw - s.p) * ease(dt, 4);
    s.ringSpin = (s.ringSpin + dt * 280 * s.w) % 360;

    // tanda (panah/centang/silang): pudar keluar, ganti, pudar masuk
    if (s.markKind !== target.mark) {
      s.markOpacity += (0 - s.markOpacity) * ease(dt, 14);
      if (s.markOpacity < 0.05) { s.markKind = target.mark; $('#l-mark').setAttribute('d', target.mark ? MARKS[target.mark] : ''); }
    } else s.markOpacity += ((target.mark ? 1 : 0) - s.markOpacity) * ease(dt, 8);

    const shape = $('#l-shape');
    shape.setAttribute('d', shapePath(s.n, s.R, s.rot));
    const speed = (Math.abs(s.n - pn) * 4 + Math.abs(s.R - pR)) / dt; // blur mengikuti kecepatan perubahan bentuk
    const blur = Math.min(1.2, speed * 0.02);
    shape.style.filter = blur > 0.08 ? `blur(${blur.toFixed(2)}px)` : '';
    $('#l-mark').style.opacity = s.markOpacity.toFixed(3);

    const ring = $('#l-ring');
    const len = Math.max(0.01, s.w * (24 + 10 * Math.sin(now / 420)) + (1 - s.w) * s.p * 100);
    ring.style.strokeDasharray = `${len.toFixed(2)} ${(100 - len).toFixed(2)}`;
    ring.setAttribute('transform', `rotate(${(-90 + s.ringSpin * s.w).toFixed(1)})`);

    $('#progress-bar').style.transform = `scaleX(${Math.min(1, Math.max(0, s.indeterminate ? Math.max(s.p, 0.02) : s.p)).toFixed(4)})`;
    $('#job-progress').textContent = s.indeterminate && s.p < 0.01 ? '…' : `${Math.round(s.p * 100)}%`;
    $('#job-elapsed').textContent = fmtTime((s.active ? Date.now() : s.updated) - s.created);

    const settled = !s.active && Math.abs(s.n - target.n) < 0.01 && Math.abs(s.R - target.R) < 0.05 && s.markOpacity > 0.98 - (target.mark ? 0 : 1)
      && Math.abs(s.p - (s.raw ?? s.p)) < 0.002 && s.w < 0.01;
    if (settled) { s.running = false; return; }
    requestAnimationFrame(frame);
  }

  function start() {
    if (s.running) return;
    s.running = true; s.last = performance.now();
    requestAnimationFrame(frame);
  }

  function reset(job) {
    Object.assign(s, { id: job.id, sawDownload: false, raw: 0, p: 0, n: 2, R: 6, spin: 0, rot: 0, ringSpin: 0, w: 1, markKind: null, markOpacity: 0 });
    $('#l-mark').setAttribute('d', '');
  }

  function update(job) {
    if (job.id !== s.id) reset(job);
    s.created = (job.created_at || Date.now() / 1000) * 1000;
    s.updated = (job.updated_at || Date.now() / 1000) * 1000;
    const stage = job.stage || '';
    const downloading = /Mengunduh|Mengambil/.test(stage);
    const pct = job.progress == null ? null : job.progress / 100;
    s.active = job.status === 'queued' || job.status === 'processing';
    let state = 'active';

    if (job.status === 'completed') { s.phase = 'done'; s.step = 2; s.raw = 1; s.indeterminate = false; state = 'done'; }
    else if (job.status === 'failed' || job.status === 'canceled') { s.phase = 'failed'; s.indeterminate = false; s.raw = s.p; state = 'failed'; }
    else if (job.status === 'queued' || downloading || !stage || stage === 'Menunggu proses') {
      s.phase = 'download'; s.step = 0; s.sawDownload = s.sawDownload || downloading;
      s.indeterminate = pct == null || job.status === 'queued'; if (!s.indeterminate) s.raw = pct * 0.6;
    } else {
      s.phase = 'convert'; s.step = 1;
      const base = s.sawDownload ? 0.6 : 0;
      s.indeterminate = pct == null; if (!s.indeterminate) s.raw = base + (1 - base) * pct;
    }
    if (s.phase === 'convert' && s.p < 0.6 && s.sawDownload && s.indeterminate) s.p = Math.max(s.p, 0.6);

    $('#job-section').dataset.state = state;
    document.querySelectorAll('#job-steps li').forEach((li) => {
      const i = Number(li.dataset.step);
      li.className = state === 'done' || i < s.step || (state === 'failed' && i < s.step) ? 'done' : i === s.step && state !== 'failed' ? 'active' : '';
    });
    if (state === 'done') document.querySelectorAll('#job-steps li').forEach((li) => { li.className = 'done'; });
    start();
  }

  window.Loader = { update };
})();
