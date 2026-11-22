/*
  Form Buat Work Order (templates/work_orders/create.html).

  Isian wajib dan isi yang dikirim ke server sama seperti form lama:
  asset_id, project_code, suggested_start_date, suggested_completion_date,
  tasklist_id atau custom_procedures_json, checklist_id atau custom_checklists_json.
  Yang baru: galat per kolom (bukan alert), draf otomatis di peramban, daftar yang selalu terlihat,
  tombol simpan yang tidak bisa terkirim dua kali.
  Data dari server lewat <script type="application/json" id="woCreateData">.
*/
(function () {
  'use strict';

  var cfgEl = document.getElementById('woCreateData');
  var form = document.getElementById('woForm');
  if (!cfgEl || !form) { return; }
  var D;
  try { D = JSON.parse(cfgEl.textContent); } catch (e) { return; }
  if (!D || typeof D !== 'object') { return; }
  ['assets', 'tasklists', 'checklists'].forEach(function (k) { if (!Array.isArray(D[k])) { D[k] = []; } });
  var $ = window.jQuery;
  var hasS2 = !!($ && $.fn && $.fn.select2);

  // ---------- teks ----------
  var MSG = {
    asset: 'Silakan pilih Aset.',
    project: 'Silakan pilih Project Code.',
    start: 'Suggested Start Date wajib diisi.',
    end: 'Suggested End Date wajib diisi.',
    tasklist: 'Tasklist wajib diisi (Pilih template atau tambah tugas custom).',
    checklist: 'Checklist wajib diisi (Pilih template atau tambah parameter custom).'
  };
  var PH = { asset: 'Pilih aset', project: 'Pilih Project Code', tasklist: 'Tanpa template', checklist: 'Tanpa template', team: 'Tanpa tim', picker: 'Tambah orang' };
  var HINT_ASSET = 'Pilih aset untuk melihat site dan Project Code.';

  // ---------- pembantu DOM ----------
  function $id(id) { return document.getElementById(id); }
  function str(v) { return v == null ? '' : String(v); }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) { n.className = cls; }
    if (text != null) { n.textContent = text; }
    return n;
  }
  function icon(name) {
    var i = el('i', 'bi bi-' + name);
    i.setAttribute('aria-hidden', 'true');
    return i;
  }
  function option(value, text) {
    var o = document.createElement('option');
    o.value = value;
    o.textContent = text;
    return o;
  }
  function hasOpt(sel, v) {
    if (!v) { return false; }
    for (var i = 0; i < sel.options.length; i++) { if (sel.options[i].value === v) { return true; } }
    return false;
  }
  function ensureOption(sel, v) { if (v && !hasOpt(sel, v)) { sel.appendChild(option(v, v)); } }
  function pad2(n) { return (n < 10 ? '0' : '') + n; }
  function fill(url, id) { return url.replace(/\/0(?=\/|$)/, '/' + encodeURIComponent(id)); }

  // ---------- pembantu Select2 (bila gagal dimuat, <select> biasa tetap berfungsi) ----------
  // keepEmpty: pilihan yang boleh dikosongkan lagi (Project Code, template, tim). Select2 menyembunyikan baris placeholder
  // dari daftar, jadi untuk pilihan ini baris kosong dibiarkan sebagai pilihan biasa dan hanya tampilannya yang diredupkan.
  function enhance(sel, placeholder, keepEmpty) {
    if (!hasS2 || !sel) { return; }
    var cfg = {
      width: '100%',
      minimumResultsForSearch: 8,
      language: {
        noResults: function () { return 'Tidak ada hasil'; },
        searching: function () { return 'Mencari…'; }
      }
    };
    if (keepEmpty) {
      cfg.templateSelection = function (d) {
        if (d.id !== '') { return d.text; }
        var n = el('span', 'select2-selection__placeholder', d.text);
        return $(n);
      };
    } else {
      cfg.placeholder = placeholder;
    }
    $(sel).select2(cfg);
  }
  function sync(sel) { if (hasS2 && $(sel).data('select2')) { $(sel).trigger('change.select2'); } }
  function listen(sel, fn) { if ($) { $(sel).on('change', fn); } else { sel.addEventListener('change', fn); } }
  function selectionOf(sel) { return (hasS2 && $(sel).data('select2')) ? $(sel).next('.select2-container').find('.select2-selection') : null; }
  function focusCtl(c) {
    if (!c) { return; }
    var s = selectionOf(c);
    if (s && s.length) { s.trigger('focus'); return; }
    if (c.type === 'radio' || c.tagName === 'FIELDSET') {
      var r = (c.tagName === 'FIELDSET' ? c : c.form).querySelector('input[type=radio]:checked, input[type=radio]');
      if (r) { r.focus(); }
      return;
    }
    c.focus();
  }
  function describe(sel, labelId, describedBy, required) {
    sel.setAttribute('aria-describedby', describedBy);
    var s = selectionOf(sel);
    if (!s || !s.length) { return; }
    s.attr('aria-describedby', describedBy);
    if (required) { s.attr('aria-required', 'true'); }
    var cur = s.attr('aria-labelledby');
    s.attr('aria-labelledby', cur ? labelId + ' ' + cur : labelId);
  }

  // ---------- elemen ----------
  var assetSel = $id('asset_select'), projSel = $id('project_code_select'), lockedInp = $id('project_code_locked');
  var codeInp = $id('wo_code_input'), codeView = $id('woCodeView'), assetHint = $id('asset_hint');
  var descInp = $id('wo_description'), instrInp = $id('wo_instructions');
  var tlSel = $id('tasklist_select'), clSel = $id('checklist_select');
  var startInp = $id('suggested_start_date'), endInp = $id('suggested_completion_date');
  var teamSel = $id('team_select'), pickSel = $id('assignee_picker'), chipsEl = $id('assigneeChips');
  var procsInp = $id('custom_procedures_json'), chksInp = $id('custom_checklists_json'), partsInp = $id('custom_parts_json');
  var saveBtn = $id('cwfSave'), summaryEl = $id('cwfSummary'), summaryList = $id('cwfSummaryList'), summaryTitle = $id('cwfSummaryTitle');
  var draftBox = $id('cwfDraft'), draftText = $id('cwfDraftText'), draftNote = $id('cwfDraftNote');
  var mtRadios = form.querySelectorAll('input[name="maintenance_type"]');
  var prRadios = form.querySelectorAll('input[name="priority"]');

  function radioVal(list) { for (var i = 0; i < list.length; i++) { if (list[i].checked) { return list[i].value; } } return ''; }
  function setRadio(list, v) { for (var i = 0; i < list.length; i++) { if (list[i].value === v) { list[i].checked = true; return; } } }

  // ---------- data ----------
  function normProc(p) {
    return {
      name: str(p && p.name).trim(),
      estimated_minutes: Math.max(0, parseInt(p && p.estimated_minutes, 10) || 0),
      requires_attachment: !!(p && p.requires_attachment),
      min_photos: Math.max(0, parseInt(p && p.min_photos, 10) || 0)
    };
  }
  function normChk(c) { return { parameter: str(c && c.parameter).trim(), standard: str(c && c.standard).trim() }; }
  function normPart(c) { return { part_id: str(c && c.part_id), name: str(c && c.name), code: str(c && c.code), qty: parseFloat(c && c.qty) || 0 }; }
  function clean(list, norm, key) {
    return (Array.isArray(list) ? list : []).map(norm).filter(function (x) { return x[key]; });
  }

  var S = {
    procs: clean(D.sourceProcedures, normProc, 'name'),
    chks: clean(D.sourceChecklists, normChk, 'parameter'),
    parts: clean(D.sourceParts, normPart, 'part_id'),
    assignees: [],
    running: str(D.runningNumber),
    codeSeq: 0
  };
  var restoring = true;   // true selama pengisian awal dan pemulihan draf: perubahan program tidak dihitung sebagai ketikan pengguna
  var dirty = false;
  var submitting = false;
  var touched = {};

  function assetObj(id) {
    for (var i = 0; i < D.assets.length; i++) { if (String(D.assets[i].id) === String(id)) { return D.assets[i]; } }
    return null;
  }
  function projectCode() { return lockedInp ? lockedInp.value : projSel.value; }
  // Tautan "Create WO" di halaman aset membawa ?asset_id=. Form lama mengabaikannya; form baru memilih aset itu.
  function queryAsset() {
    try { return new URLSearchParams(window.location.search).get('asset_id') || ''; } catch (e) { return ''; }
  }

  // ---------- pilihan yang saling menyaring: Project Code, aset, template ----------
  function fillAssets(code, keep) {
    var cur = keep == null ? assetSel.value : str(keep);
    assetSel.textContent = '';
    assetSel.appendChild(option('', PH.asset));
    D.assets.forEach(function (a) {
      if (!code || a.project_code === code) {
        assetSel.appendChild(option(String(a.id), a.name + (a.code ? ' (' + a.code + ')' : '') + (a.site_name ? ' - ' + a.site_name : '')));
      }
    });
    assetSel.value = hasOpt(assetSel, cur) ? cur : '';
    sync(assetSel);
  }

  function fillTemplates(sel, list, code, placeholder, keep) {
    var cur = keep == null ? sel.value : str(keep);
    var groups = {}, keys = [];
    list.forEach(function (t) {
      if (code && t.project_code && t.project_code !== code) { return; }
      var g = t.project_code || '';
      if (!groups[g]) { groups[g] = []; keys.push(g); }
      groups[g].push(t);
    });
    keys.sort();
    sel.textContent = '';
    sel.appendChild(option('', placeholder));
    keys.forEach(function (g) {
      var og = document.createElement('optgroup');
      og.label = g || 'General (No Project Code)';
      groups[g].forEach(function (t) { og.appendChild(option(String(t.id), t.name)); });
      sel.appendChild(og);
    });
    sel.value = hasOpt(sel, cur) ? cur : '';
    sync(sel);
  }

  function updateHint() {
    var a = assetObj(assetSel.value);
    assetHint.textContent = a ? 'Site: ' + (a.site_name || '-') + ' | Project Code: ' + (a.project_code || 'Tidak ada') : HINT_ASSET;
  }

  // Project Code berubah: saring aset (kecuali perubahan itu datang dari aset) dan template.
  // Template yang tidak cocok lagi dilepas dan daftar isinya dikosongkan; template yang masih cocok tidak diambil ulang.
  function applyProject(fromAsset) {
    var code = projectCode();
    if (!fromAsset) { fillAssets(code); }
    var oldTl = tlSel.value, oldCl = clSel.value;
    fillTemplates(tlSel, D.tasklists, code, PH.tasklist);
    fillTemplates(clSel, D.checklists, code, PH.checklist);
    if (oldTl && !tlSel.value) { tplSeq.proc++; S.procs = []; renderProcs(); }
    if (oldCl && !clSel.value) { tplSeq.chk++; S.chks = []; renderChks(); }
    revalidate('tasklist');
    revalidate('checklist');
    updateHint();
    updateWoCode();
  }

  function onAsset() {
    var a = assetObj(assetSel.value);
    if (a && !lockedInp) {
      var code = str(a.project_code).trim();
      if (code && projSel.value !== code) {
        ensureOption(projSel, code);
        projSel.value = code;
        sync(projSel);
        applyProject(true);
      }
    }
    updateHint();
    updateWoCode();
    touch('asset');
    revalidate('asset');
    revalidate('project');
    markDirty();
  }

  function onProject() {
    applyProject(false);
    touch('project');
    revalidate('project');
    revalidate('asset');
    markDirty();
  }

  // ---------- kode WO (pratinjau; nomor akhir ditetapkan server saat disimpan) ----------
  function setCode(v) { codeInp.value = v; codeView.textContent = v; }
  function updateWoCode() {
    var a = assetObj(assetSel.value);
    var site = (a && a.site_name) ? a.site_name : 'Site';
    var pc = projectCode(), last4 = '0000';
    if (pc && pc.trim() !== '' && pc.toLowerCase() !== 'none') {
      var t = pc.trim();
      last4 = t.length >= 4 ? t.slice(-4) : ('0000' + t).slice(-4);
    }
    var mt = radioVal(mtRadios), tc = 'CM';
    if (mt === 'Preventive' || mt === 'PM') { tc = 'PM'; } else if (mt === 'Handling' || mt === 'HM') { tc = 'HM'; }
    var chosen = startInp.value || '', ms = str(D.month), ys = str(D.year);
    if (chosen) {
      var d = new Date(chosen);
      if (!isNaN(d.getTime())) { ms = pad2(d.getMonth() + 1); ys = String(d.getFullYear()); }
    }
    setCode('WO - ' + S.running + ' - ' + site + ' - ' + last4 + ' - ' + tc + ' - ' + ms + ' - ' + ys);

    var seq = ++S.codeSeq;
    var q = new URLSearchParams({ asset_id: assetSel.value || '', project_code: pc || '', maintenance_type: mt || 'Preventive', date: chosen });
    fetch(D.urls.nextCode + '?' + q.toString(), { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (seq !== S.codeSeq || !data || !data.code) { return; }
        setCode(data.code);
        if (data.running_number) { S.running = data.running_number; }
      })
      .catch(function () { /* pratinjau lokal tetap dipakai */ });
  }

  // ---------- daftar: tugas, parameter, suku cadang ----------
  function badge(tone, ico, text) {
    var b = el('span', 'jt-badge tone-' + tone);
    b.appendChild(icon(ico));
    b.appendChild(document.createTextNode(text));
    return b;
  }
  function removeBtn(kind, i, label) {
    var b = el('button', 'icon-btn is-danger');
    b.type = 'button';
    b.setAttribute('data-rm', kind);
    b.setAttribute('data-i', String(i));
    b.setAttribute('aria-label', label);
    b.appendChild(icon('trash'));
    return b;
  }
  function plural(n, one) { return n + ' ' + one; }

  function renderProcs(newIdx) {
    procsInp.value = JSON.stringify(S.procs);
    var ul = $id('procList');
    ul.textContent = '';
    $id('procCount').textContent = plural(S.procs.length, 'tugas');
    $id('procEmpty').hidden = S.procs.length > 0;
    ul.hidden = S.procs.length === 0;
    S.procs.forEach(function (p, i) {
      var li = el('li', i === newIdx ? 'is-new' : '');
      li.appendChild(el('span', 'cwf-item-n', String(i + 1)));
      var main = el('div', 'cwf-item-main');
      main.appendChild(el('div', 'cwf-item-name', p.name));
      var meta = el('div', 'cwf-item-meta');
      if (p.requires_attachment) { meta.appendChild(badge('info', 'camera', p.min_photos > 1 ? 'Foto wajib (' + p.min_photos + ')' : 'Foto wajib')); }
      if (p.estimated_minutes > 0) { meta.appendChild(badge('mute', 'clock', p.estimated_minutes + ' menit')); }
      main.appendChild(meta);
      li.appendChild(main);
      li.appendChild(removeBtn('proc', i, 'Hapus tugas ' + p.name));
      ul.appendChild(li);
    });
  }

  function renderChks(newIdx) {
    chksInp.value = JSON.stringify(S.chks);
    var ul = $id('chkList');
    ul.textContent = '';
    $id('chkCount').textContent = plural(S.chks.length, 'parameter');
    $id('chkEmpty').hidden = S.chks.length > 0;
    ul.hidden = S.chks.length === 0;
    S.chks.forEach(function (c, i) {
      var li = el('li', i === newIdx ? 'is-new' : '');
      li.appendChild(el('span', 'cwf-item-n', String(i + 1)));
      var main = el('div', 'cwf-item-main');
      main.appendChild(el('div', 'cwf-item-name', c.parameter));
      if (c.standard) { main.appendChild(el('div', 'cwf-item-std', 'Standar: ' + c.standard)); }
      li.appendChild(main);
      li.appendChild(removeBtn('chk', i, 'Hapus parameter ' + c.parameter));
      ul.appendChild(li);
    });
  }

  function renderParts(newIdx) {
    partsInp.value = JSON.stringify(S.parts);
    var ul = $id('partList');
    ul.textContent = '';
    $id('partCount').textContent = plural(S.parts.length, 'item');
    $id('partEmpty').hidden = S.parts.length > 0;
    ul.hidden = S.parts.length === 0;
    S.parts.forEach(function (p, i) {
      var li = el('li', i === newIdx ? 'is-new' : '');
      li.appendChild(el('span', 'cwf-item-n', String(i + 1)));
      var main = el('div', 'cwf-item-main');
      main.appendChild(el('div', 'cwf-item-name', p.name || p.code));
      var meta = el('div', 'cwf-item-meta');
      if (p.code) { meta.appendChild(badge('mute', 'upc-scan', p.code)); }
      meta.appendChild(badge('info', 'box-seam', 'Jumlah ' + p.qty));
      main.appendChild(meta);
      li.appendChild(main);
      li.appendChild(removeBtn('part', i, 'Hapus suku cadang ' + (p.name || p.code)));
      ul.appendChild(li);
    });
  }

  function removeFrom(kind, i) {
    var list = kind === 'proc' ? S.procs : (kind === 'chk' ? S.chks : S.parts);
    list.splice(i, 1);
    var ul = $id(kind === 'proc' ? 'procList' : (kind === 'chk' ? 'chkList' : 'partList'));
    if (kind === 'proc') { renderProcs(); } else if (kind === 'chk') { renderChks(); } else { renderParts(); }
    // fokus pindah ke tombol hapus berikutnya (atau sebelumnya), bila daftar sudah kosong ke tombol tambah
    var btns = ul.querySelectorAll('[data-rm]');
    var next = btns[Math.min(i, btns.length - 1)];
    if (next) { next.focus(); } else { var tg = $id(kind === 'proc' ? 'procToggle' : (kind === 'chk' ? 'chkToggle' : 'partToggle')); if (tg) { tg.focus(); } }
    if (kind === 'proc') { revalidate('tasklist'); } else if (kind === 'chk') { revalidate('checklist'); }
    markDirty();
  }
  ['procList', 'chkList', 'partList'].forEach(function (id) {
    $id(id).addEventListener('click', function (e) {
      var b = e.target.closest('[data-rm]');
      if (b) { removeFrom(b.getAttribute('data-rm'), parseInt(b.getAttribute('data-i'), 10)); }
    });
  });

  // ---------- template tasklist dan checklist ----------
  var tplSeq = { proc: 0, chk: 0 };
  var KIND = {
    proc: { url: D.urls.tasklist, norm: normProc, key: 'name', set: function (v) { S.procs = v; }, render: function () { renderProcs(); }, status: 'procStatus', what: 'tugas' },
    chk: { url: D.urls.checklist, norm: normChk, key: 'parameter', set: function (v) { S.chks = v; }, render: function () { renderChks(); }, status: 'chkStatus', what: 'parameter' }
  };
  function setStatus(kind, state) {
    var n = $id(KIND[kind].status);
    if (!state) { n.hidden = true; n.textContent = ''; n.className = 'cwf-empty'; return; }
    n.className = 'cwf-empty ' + (state === 'busy' ? 'is-busy' : 'is-bad');
    n.textContent = state === 'busy' ? 'Memuat ' + KIND[kind].what + '…' : 'Gagal memuat template. Pilih ulang, atau tambah sendiri.';
    n.hidden = false;
  }
  function loadTemplate(kind, id) {
    var k = KIND[kind], seq = ++tplSeq[kind];
    setStatus(kind, '');
    if (!id) { k.set([]); k.render(); return; }
    // pemuat baru muncul bila lebih dari 120 ms, supaya jawaban cepat tidak berkedip
    var timer = setTimeout(function () { if (seq === tplSeq[kind]) { setStatus(kind, 'busy'); } }, 120);
    fetch(fill(k.url, id), { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (r) { if (!r.ok) { throw new Error(String(r.status)); } return r.json(); })
      .then(function (data) {
        clearTimeout(timer);
        if (seq !== tplSeq[kind]) { return; }
        k.set(clean(data, k.norm, k.key));
        k.render();
        setStatus(kind, '');
        revalidate(kind === 'proc' ? 'tasklist' : 'checklist');
      })
      .catch(function () {
        clearTimeout(timer);
        if (seq === tplSeq[kind]) { setStatus(kind, 'bad'); }
      });
  }

  // ---------- panel tambah sendiri ----------
  function composer(id, onAdd, firstFocus) {
    var toggle = $id(id + 'Toggle'), panel = $id(id + 'Panel');
    function setOpen(on) {
      panel.hidden = !on;
      toggle.setAttribute('aria-expanded', on ? 'true' : 'false');
      if (on) { firstFocus(); } else { toggle.focus(); }
    }
    toggle.addEventListener('click', function () { setOpen(panel.hidden); });
    $id(id + 'Done').addEventListener('click', function () { setOpen(false); });
    $id(id + 'Add').addEventListener('click', function () { if (onAdd()) { firstFocus(); } });
    panel.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !e.defaultPrevented) { e.stopPropagation(); setOpen(false); return; }
      if (e.key === 'Enter' && e.target.tagName === 'INPUT') { e.preventDefault(); if (onAdd()) { firstFocus(); } }
    });
    return setOpen;
  }
  function composerError(id, msg) {
    var n = $id(id);
    n.textContent = msg || '';
    n.hidden = !msg;
  }

  var procName = $id('procName'), procMin = $id('procMin'), procPhoto = $id('procPhoto');
  composer('proc', function () {
    var name = procName.value.trim();
    if (!name) { composerError('procErr', 'Nama tugas wajib diisi.'); procName.focus(); return false; }
    composerError('procErr', '');
    S.procs.push({ name: name, estimated_minutes: Math.max(0, parseInt(procMin.value, 10) || 0), requires_attachment: procPhoto.checked, min_photos: procPhoto.checked ? 1 : 0 });
    procName.value = ''; procMin.value = ''; procPhoto.checked = false;
    renderProcs(S.procs.length - 1);
    revalidate('tasklist');
    markDirty();
    return true;
  }, function () { procName.focus(); });

  var chkParam = $id('chkParam'), chkStd = $id('chkStd');
  composer('chk', function () {
    var p = chkParam.value.trim(), s = chkStd.value.trim();
    if (!p || !s) { composerError('chkErr', 'Parameter dan standar wajib diisi.'); (p ? chkStd : chkParam).focus(); return false; }
    composerError('chkErr', '');
    S.chks.push({ parameter: p, standard: s });
    chkParam.value = ''; chkStd.value = '';
    renderChks(S.chks.length - 1);
    revalidate('checklist');
    markDirty();
    return true;
  }, function () { chkParam.focus(); });

  var partSel = $id('partPick'), partQty = $id('partQty');
  composer('part', function () {
    if (!partSel.value) { composerError('partErr', 'Pilih suku cadang.'); focusCtl(partSel); return false; }
    var qty = parseFloat(partQty.value);
    if (isNaN(qty) || qty <= 0) { composerError('partErr', 'Jumlah harus lebih dari 0.'); partQty.focus(); return false; }
    composerError('partErr', '');
    var o = partSel.options[partSel.selectedIndex];
    S.parts.push({ part_id: partSel.value, name: o.getAttribute('data-name') || '', code: o.getAttribute('data-code') || '', qty: qty });
    partSel.value = ''; sync(partSel); partQty.value = '';
    renderParts(S.parts.length - 1);
    markDirty();
    return true;
  }, function () { focusCtl(partSel); });

  // ---------- orang yang ditugaskan ----------
  function labelFor(id) {
    for (var i = 0; i < pickSel.options.length; i++) { if (pickSel.options[i].value === id) { return pickSel.options[i].textContent; } }
    return 'Pengguna #' + id;
  }
  function renderAssignees() {
    chipsEl.textContent = '';
    S.assignees.forEach(function (a) {
      var li = el('li', 'cwf-chip');
      li.appendChild(el('span', 'cwf-chip-name', a.label));
      var inp = document.createElement('input');
      inp.type = 'hidden'; inp.name = 'assigned_to'; inp.value = a.id;
      li.appendChild(inp);
      var b = el('button', 'cwf-chip-x');
      b.type = 'button';
      b.setAttribute('data-id', a.id);
      b.setAttribute('aria-label', 'Hapus ' + a.label);
      b.appendChild(icon('x-lg'));
      li.appendChild(b);
      chipsEl.appendChild(li);
    });
    chipsEl.hidden = S.assignees.length === 0;
    // yang sudah dipilih dinonaktifkan di daftar, supaya tidak ganda
    var taken = {};
    S.assignees.forEach(function (a) { taken[a.id] = true; });
    for (var i = 0; i < pickSel.options.length; i++) { pickSel.options[i].disabled = !!taken[pickSel.options[i].value] && pickSel.options[i].value !== ''; }
    sync(pickSel);
  }
  function addAssignee(id, label) {
    id = str(id);
    if (!id) { return false; }
    for (var i = 0; i < S.assignees.length; i++) { if (S.assignees[i].id === id) { return false; } }
    S.assignees.push({ id: id, label: label || labelFor(id) });
    renderAssignees();
    return true;
  }
  chipsEl.addEventListener('click', function (e) {
    var b = e.target.closest('.cwf-chip-x');
    if (!b) { return; }
    var id = b.getAttribute('data-id');
    S.assignees = S.assignees.filter(function (a) { return a.id !== id; });
    renderAssignees();
    var rest = chipsEl.querySelectorAll('.cwf-chip-x');
    if (rest.length) { rest[0].focus(); } else { focusCtl(pickSel); }
    markDirty();
  });
  listen(pickSel, function () {
    if (pickSel.value) {
      addAssignee(pickSel.value);
      pickSel.value = '';
      sync(pickSel);
      markDirty();
    }
  });
  listen(teamSel, function () {
    markDirty();
    var id = teamSel.value;
    if (!id) { return; }
    fetch(fill(D.urls.team, id), { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (r) { if (!r.ok) { throw new Error(String(r.status)); } return r.json(); })
      .then(function (users) {
        if (teamSel.value !== id || !Array.isArray(users)) { return; }
        users.forEach(function (u) { addAssignee(u.id, hasOpt(pickSel, str(u.id)) ? '' : str(u.name) + (u.role ? ' (' + u.role + ')' : '')); });
        markDirty();
      })
      .catch(function () { /* anggota tim tetap ditambahkan server saat disimpan */ });
  });

  // ---------- validasi: enam aturan yang sama dengan server ----------
  var F = {
    asset: { msg: MSG.asset, anchor: 'asset_select', ok: function () { return !!assetSel.value; }, ctl: function () { return assetSel; } },
    project: { msg: MSG.project, anchor: 'project_code_select', ok: function () { return !!projectCode().trim(); }, ctl: function () { return projSel; } },
    start: { msg: MSG.start, anchor: 'suggested_start_date', ok: function () { return !!startInp.value; }, ctl: function () { return startInp; } },
    end: { msg: MSG.end, anchor: 'suggested_completion_date', ok: function () { return !!endInp.value; }, ctl: function () { return endInp; } },
    tasklist: { msg: MSG.tasklist, anchor: 'tasklist_select', ok: function () { return !!tlSel.value || S.procs.length > 0; }, ctl: function () { return tlSel; } },
    checklist: { msg: MSG.checklist, anchor: 'checklist_select', ok: function () { return !!clSel.value || S.chks.length > 0; }, ctl: function () { return clSel; } }
  };
  var ORDER = ['asset', 'project', 'start', 'end', 'tasklist', 'checklist'];
  ORDER.forEach(function (k) {
    F[k].wrap = document.querySelector('[data-field="' + k + '"]');
    F[k].err = $id('err_' + k);
  });

  function touch(k) { touched[k] = true; }
  function setError(k, show) {
    var f = F[k], c = f.ctl(), s = selectionOf(c);
    if (show) { f.wrap.setAttribute('data-invalid', ''); f.err.textContent = f.msg; f.err.hidden = false; }
    else { f.wrap.removeAttribute('data-invalid'); f.err.textContent = ''; f.err.hidden = true; }
    c.setAttribute('aria-invalid', show ? 'true' : 'false');
    if (s && s.length) { s.attr('aria-invalid', show ? 'true' : 'false'); }
  }
  // Galat baru muncul setelah kolom disentuh atau form dicoba disimpan; hilang seketika begitu terisi.
  function revalidate(k) {
    var ok = F[k].ok();
    setError(k, !ok && !!touched[k]);
    if (!summaryEl.hidden) { showSummary(invalidKeys()); }
  }
  function invalidKeys() { return ORDER.filter(function (k) { return !F[k].ok() && touched[k]; }); }
  function showSummary(keys) {
    summaryList.textContent = '';
    keys.forEach(function (k) {
      var li = document.createElement('li');
      var a = el('a', '', F[k].msg);
      a.href = '#' + F[k].anchor;
      a.setAttribute('data-go', k);
      li.appendChild(a);
      summaryList.appendChild(li);
    });
    summaryTitle.lastChild.textContent = keys.length === 1 ? '1 isian wajib belum lengkap' : keys.length + ' isian wajib belum lengkap';
    summaryEl.hidden = keys.length === 0;
  }
  summaryList.addEventListener('click', function (e) {
    var a = e.target.closest('[data-go]');
    if (!a) { return; }
    e.preventDefault();
    var c = F[a.getAttribute('data-go')].ctl();
    c.scrollIntoView({ block: 'center', behavior: 'smooth' });
    focusCtl(c);
  });

  // ---------- draf otomatis ----------
  var DRAFT_TTL = 7 * 24 * 3600 * 1000;
  function readDraft() {
    try {
      var raw = window.localStorage.getItem(D.draftKey);
      if (!raw) { return null; }
      var d = JSON.parse(raw);
      if (!d || d.v !== 1 || !d.t || (Date.now() - d.t) > DRAFT_TTL) { window.localStorage.removeItem(D.draftKey); return null; }
      return d;
    } catch (e) { return null; }
  }
  function writeDraft(d) { try { window.localStorage.setItem(D.draftKey, JSON.stringify(d)); return true; } catch (e) { return false; } }
  function clearDraft() { try { window.localStorage.removeItem(D.draftKey); } catch (e) { /* abaikan */ } }
  function snapshot() {
    return {
      v: 1, t: Date.now(),
      f: {
        asset: assetSel.value, project: lockedInp ? '' : projSel.value, type: radioVal(mtRadios), priority: radioVal(prRadios),
        description: descInp.value, instructions: instrInp.value, tasklist: tlSel.value, checklist: clSel.value,
        start: startInp.value, end: endInp.value, team: teamSel.value
      },
      assignees: S.assignees, procs: S.procs, chks: S.chks, parts: S.parts
    };
  }
  function meaningful(d) {
    var f = d.f || {};
    return !!(f.asset || (f.description || '').trim() || (f.instructions || '').trim() || f.tasklist || f.checklist || f.start || f.end || f.team ||
      (d.assignees || []).length || (d.procs || []).length || (d.chks || []).length || (d.parts || []).length);
  }
  var draftTimer = 0;
  function saveDraft() {
    var d = snapshot();
    if (!meaningful(d)) { clearDraft(); draftNote.textContent = ''; return; }
    if (writeDraft(d)) {
      var t = new Date();
      draftNote.textContent = '';
      draftNote.appendChild(icon('check2-circle'));
      draftNote.appendChild(document.createTextNode('Draf tersimpan ' + pad2(t.getHours()) + ':' + pad2(t.getMinutes())));
    }
  }
  // Dipanggil juga oleh perubahan yang bukan ketikan di kolom form (daftar, orang)
  function markDirty() {
    if (restoring) { return; }
    dirty = true;
    clearTimeout(draftTimer);
    draftTimer = setTimeout(saveDraft, 600);
  }
  form.addEventListener('input', function (e) { if (!e.target.closest('.cwf-composer')) { markDirty(); } });
  form.addEventListener('change', function (e) { if (!e.target.closest('.cwf-composer')) { markDirty(); } });

  function renderAll() {
    renderProcs(); renderChks(); renderParts(); renderAssignees();
  }

  function applyDraft(d) {
    restoring = true;
    var f = d.f || {};
    if (!lockedInp) {
      ensureOption(projSel, f.project);
      projSel.value = hasOpt(projSel, f.project) ? f.project : '';
      sync(projSel);
    }
    var code = projectCode();
    fillAssets(code, f.asset);
    fillTemplates(tlSel, D.tasklists, code, PH.tasklist, f.tasklist);
    fillTemplates(clSel, D.checklists, code, PH.checklist, f.checklist);
    if (f.type) { setRadio(mtRadios, f.type); }
    if (f.priority) { setRadio(prRadios, f.priority); }
    descInp.value = f.description || '';
    instrInp.value = f.instructions || '';
    startInp.value = f.start || '';
    endInp.value = f.end || '';
    teamSel.value = hasOpt(teamSel, f.team) ? f.team : '';
    sync(teamSel);
    S.assignees = (Array.isArray(d.assignees) ? d.assignees : []).filter(function (a) { return a && a.id; }).map(function (a) { return { id: str(a.id), label: str(a.label) || labelFor(str(a.id)) }; });
    S.procs = clean(d.procs, normProc, 'name');
    S.chks = clean(d.chks, normChk, 'parameter');
    S.parts = clean(d.parts, normPart, 'part_id');
    renderAll();
    updateHint();
    updateWoCode();
    ORDER.forEach(function (k) { touched[k] = false; setError(k, false); });
    showSummary([]);
    restoring = false;
    dirty = true;
    saveDraft();
  }

  function offerDraft() {
    var d = readDraft();
    if (!d) { return; }
    var rejected = !!d.submittedAt;
    var danger = document.querySelector('.flash-stack .alert-danger');
    if (rejected && !danger) { clearDraft(); return; }   // terkirim dan berhasil: tidak ada yang perlu dipulihkan
    if (!meaningful(d)) { clearDraft(); return; }
    var when = '';
    try { when = new Intl.DateTimeFormat('id-ID', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(d.t)); } catch (e) { when = ''; }
    draftText.textContent = '';
    draftText.appendChild(el('b', '', rejected ? 'Server menolak simpan terakhir.' : 'Ada draf yang belum disimpan.'));
    draftText.appendChild(el('span', 'cwf-banner-sub', (rejected ? 'Isian Anda masih tersimpan di peramban ini' : 'Terakhir diubah') + (when ? ' (' + when + ')' : '') + '. Pulihkan untuk melanjutkan.'));
    draftBox.hidden = false;
    $id('cwfDraftRestore').onclick = function () { applyDraft(d); draftBox.hidden = true; focusCtl(assetSel); };
    $id('cwfDraftDiscard').onclick = function () { clearDraft(); draftBox.hidden = true; };
  }

  // ---------- kirim ----------
  function setBusy(on) {
    submitting = on;
    saveBtn.disabled = on;
    saveBtn.setAttribute('aria-busy', on ? 'true' : 'false');
    var lbl = saveBtn.querySelector('.cwf-save-label'), ic = saveBtn.querySelector('.cwf-save-icon');
    if (lbl) { lbl.textContent = on ? 'Menyimpan…' : 'Simpan WO'; }
    if (ic) { ic.className = on ? 'cwf-spin cwf-save-icon' : 'bi bi-check2 cwf-save-icon'; }
  }
  form.addEventListener('submit', function (e) {
    if (submitting) { e.preventDefault(); return; }
    ORDER.forEach(function (k) { touched[k] = true; setError(k, !F[k].ok()); });
    var bad = ORDER.filter(function (k) { return !F[k].ok(); });
    if (bad.length) {
      e.preventDefault();
      showSummary(bad);
      summaryEl.scrollIntoView({ block: 'center', behavior: 'smooth' });
      summaryEl.focus();
      return;
    }
    var d = snapshot();
    d.submittedAt = Date.now();
    writeDraft(d);
    setBusy(true);
  });
  // Enter di kolom isian tidak mengirim form; hanya tombol Simpan WO (sama seperti form lama)
  form.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && e.target.tagName === 'INPUT' && e.target.type !== 'submit' && e.target.type !== 'button') { e.preventDefault(); }
  });
  // kembali dari server lewat tombol Back: tombol simpan hidup lagi
  window.addEventListener('pageshow', function (e) { if (e.persisted) { setBusy(false); } });

  // ---------- pasang ----------
  // Project Code dan pilihan yang diisi server (salinan WO, tiket) menjadi nilai awal
  var preAsset = str(D.selected && D.selected.asset) || (D.mode === 'new' ? queryAsset() : '');
  fillAssets(projectCode(), preAsset);
  fillTemplates(tlSel, D.tasklists, projectCode(), PH.tasklist, D.selected && D.selected.tasklist);
  fillTemplates(clSel, D.checklists, projectCode(), PH.checklist, D.selected && D.selected.checklist);
  if (lockedInp) { ensureOption(projSel, lockedInp.value); projSel.value = lockedInp.value; }

  enhance(assetSel, PH.asset);
  enhance(projSel, PH.project, true);
  enhance(tlSel, PH.tasklist, true);
  enhance(clSel, PH.checklist, true);
  enhance(teamSel, PH.team, true);
  enhance(pickSel, PH.picker);
  enhance(partSel, 'Pilih suku cadang');
  describe(assetSel, 'lbl_asset', 'asset_hint err_asset', true);
  describe(projSel, 'lbl_project', 'project_hint err_project', true);
  describe(tlSel, 'lbl_tasklist', 'tasklist_hint err_tasklist', true);
  describe(clSel, 'lbl_checklist', 'checklist_hint err_checklist', true);
  describe(teamSel, 'lbl_team', 'team_hint', false);
  describe(pickSel, 'lbl_picker', 'picker_hint', false);

  (Array.isArray(D.sourceAssignees) ? D.sourceAssignees : []).forEach(function (id) { addAssignee(id); });
  renderAll();
  updateHint();
  if (assetSel.value) { onAsset(); }   // aset dari ?asset_id=: isi Project Code dan saring template

  listen(assetSel, onAsset);
  listen(projSel, onProject);
  listen(tlSel, function () { touch('tasklist'); loadTemplate('proc', tlSel.value); revalidate('tasklist'); markDirty(); });
  listen(clSel, function () { touch('checklist'); loadTemplate('chk', clSel.value); revalidate('checklist'); markDirty(); });
  [['start', startInp], ['end', endInp]].forEach(function (p) {
    p[1].addEventListener('blur', function () { touch(p[0]); revalidate(p[0]); });
    p[1].addEventListener('input', function () { revalidate(p[0]); });
    p[1].addEventListener('change', function () { touch(p[0]); revalidate(p[0]); if (p[0] === 'start') { updateWoCode(); } });
  });
  Array.prototype.forEach.call(mtRadios, function (r) { r.addEventListener('change', updateWoCode); });

  updateWoCode();
  restoring = false;
  offerDraft();
  window.__woCreateReady = true;
})();
