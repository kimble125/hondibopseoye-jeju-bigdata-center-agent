/* Jeju Evidence Mate UI. Talks only to 127.0.0.1 (same origin). User text is inserted with
   textContent; card_html comes from the local server, which escapes every string. */
(function () {
  'use strict';
  var state = { status: null, guide: null, catalog: null, report: null, memo: [], purpose: '', start: {} };
  var EXAMPLES = [
    '2025년 6월 호텔업 카드 이용 현황을 알려 주세요',
    '일식 음식점업은 외국인이 도민보다 많이 썼다',
    '2025년 6월 카드 이용금액 2위 업종은 슈퍼마켓이다'
  ];

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = String(text);
    return e;
  }
  function clearNode(n) { while (n.firstChild) n.removeChild(n.firstChild); }

  function api(path, body) {
    var opt = body === undefined ? { method: 'GET' } : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    };
    return fetch(path, opt).then(function (r) {
      return r.json().then(function (j) { j.__status = r.status; return j; },
        function () { return { __status: r.status, error: '응답을 읽지 못했습니다.' }; });
    });
  }

  /* ---------------- copy ---------------- */
  function copyText(text, btn) {
    function done() { if (btn) { var t = btn.textContent; btn.textContent = '복사했습니다'; setTimeout(function () { btn.textContent = t; }, 1200); } }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { fallback(); });
    } else { fallback(); }
    function fallback() {
      var ta = el('textarea'); ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); done(); } catch (e) { /* ignore */ }
      document.body.removeChild(ta);
    }
  }

  /* ---------------- status / board ---------------- */
  function applyStatus(st) {
    if (!st) return;
    state.status = st;
    var b = st.branding || {};
    document.title = b.product_name || '';
    $('product-name').textContent = b.product_name || '';
    $('tagline').textContent = b.tagline || '';
    $('home-title').textContent = b.product_name || '';
    $('home-greeting').textContent = (b.mate_name ? b.mate_name + '가 받을 자료 고르기부터 초안과 반출 신청 준비까지 함께합니다.' : '');
    var fl = b.contest_line || ''; if (b.team_name) fl += ' · ' + b.team_name;
    $('footer-line').textContent = fl;
    if (st.mascot) { $('mascot-small').hidden = false; $('mascot-big').hidden = false; }
    var a = st.active || {};
    var kind = a.kind || '';
    $('chip-data').textContent = '자료: ' + (a.synthetic ? '가상 데이터' : (kind === 'hub_biz_sex' || !kind ? '공개 실측' : (kind === 'generic' ? '그 밖의 CSV' : '센터 CSV')));
    $('chip-export').textContent = '반출 사전 점검: ' + (a.export_check ? '켜짐' : '꺼짐');
    var dl = $('active-info'); clearNode(dl);
    function row(k, v) { dl.appendChild(el('dt', null, k)); dl.appendChild(el('dd', null, v)); }
    row('지금 쓰는 자료', a.label || '없음');
    row('출처', a.source || '');
    row('파일', (a.files || []).join(', '));
    var ms = a.months || [];
    row('기간', ms.length ? (ms.length > 1 ? ms[0] + '–' + ms[ms.length - 1] : ms[0]) : '');
    row('행 수', a.rows !== undefined ? Number(a.rows).toLocaleString('ko-KR') + (a.skipped_rows ? ' (건너뛴 행 ' + a.skipped_rows + ')' : '') : '');
    var mb = Math.floor((st.max_body || 60000000) / 1000000);
    $('limit-line').textContent = '파일은 ' + mb + 'MB까지 넣을 수 있습니다. 넣은 파일은 이 PC의 메모리에만 있고 저장하거나 밖으로 보내지 않습니다.';
    var sm = $('samples'); clearNode(sm);
    (st.samples || []).forEach(function (n) {
      if (n.indexOf('SYNTHETIC_') !== 0) return;
      var btn = el('button', 'sample', '가상 센터 CSV로 해 보기: ' + n);
      btn.type = 'button';
      btn.addEventListener('click', function () { loadSample(n); });
      sm.appendChild(btn);
    });
    var pb = el('button', 'sample', '공개 실측 자료로 돌아가기'); pb.type = 'button';
    pb.addEventListener('click', function () { loadSample(st.public_file); });
    sm.appendChild(pb);
    var pol = $('policies'); clearNode(pol);
    (st.policies || []).forEach(function (p) { pol.appendChild(el('li', null, p.text)); });
    var generic = kind === 'generic';
    $('start-card').hidden = generic;
    $('generic-back').hidden = !generic;
    if (state.reportCatalog) renderFormats();
  }
  function boardMsg(t, bad) { var m = $('board-msg'); m.textContent = t || ''; m.className = 'msgline' + (bad ? ' bad' : ''); }

  function refresh() { return api('/api/status').then(applyStatus); }

  function loadSample(name) {
    api('/api/load_sample', { name: name }).then(function (j) {
      if (j.__status !== 200) { boardMsg(j.error || '불러오지 못했습니다.', true); return; }
      applyStatus(j.status);
      boardMsg(j.message || ((j.loaded && j.loaded.label ? j.loaded.label : name) + ' 파일을 넣었습니다.' + (j.loaded && j.loaded.notice ? ' ' + j.loaded.notice : '')));
    });
  }

  function loadFile(file) {
    var max = (state.status && state.status.max_body) || 60000000;
    if (file.size > max - 1000) { boardMsg('파일이 너무 큽니다. ' + Math.floor(max / 1000000) + 'MB까지 넣을 수 있습니다.', true); return; }
    var fr = new FileReader();
    fr.onload = function () {
      api('/api/load', { name: file.name, text: String(fr.result || '') }).then(function (j) {
        if (j.__status !== 200) {
          var msg = j.error || '이 파일은 아직 읽을 수 없습니다.';
          if (j.missing && j.missing.length) msg += ' 없는 열: ' + j.missing.join(', ');
          boardMsg(msg, true); return;
        }
        applyStatus(j.status);
        var l = j.loaded || {};
        boardMsg((l.label || '') + ' 파일을 넣었습니다(' + Number(l.rows || 0).toLocaleString('ko-KR') + '행).' + (l.notice ? ' ' + l.notice : ''));
      });
    };
    fr.onerror = function () { boardMsg('파일을 읽지 못했습니다.', true); };
    fr.readAsText(file, 'utf-8');
  }

  /* ---------------- conversation ---------------- */
  function ask(sentence) {
    sentence = String(sentence || '').trim();
    if (!sentence) return;
    if (sentence.length > 300) sentence = sentence.slice(0, 300);
    var conv = $('conversation');
    var u = el('div', 'bubble user', sentence);
    conv.appendChild(u);
    var wait = el('div', 'bubble wait', '확인하고 있습니다…');
    conv.appendChild(wait);
    api('/api/ask', { sentence: sentence }).then(function (j) { conv.removeChild(wait); showResult(j, sentence); },
      function () { conv.removeChild(wait); conv.appendChild(el('div', 'bubble bad', '연결이 끊겼습니다. 프로그램 창이 켜져 있는지 확인해 주세요.')); });
    $('chat').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function showResult(j, sentence) {
    var conv = $('conversation');
    if (j.__status !== 200) { conv.appendChild(el('div', 'bubble bad', j.error || '처리하지 못했습니다.')); return; }
    var box = el('div', 'bubble mate');
    box.innerHTML = j.card_html || '';   // escaped by the local server (evm/report.py)
    wireCard(box, sentence);
    conv.appendChild(box);
    if (j.active) applyStatus(Object.assign({}, state.status, { active: j.active }));
    box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function replaceAmbiguous(sentence, slot, label) {
    var words = slot === 'group' ? ['관광객'] : ['음식점', '식당', '외식'];
    if (slot === 'group') {
      var re = /(내국인 |외국인 |전체 )?관광객( 전체)?/g, m, out = null;
      while ((m = re.exec(sentence)) !== null) {
        if (!m[1] && !m[2]) { out = sentence.slice(0, m.index) + label + sentence.slice(m.index + m[0].length); break; }
      }
      if (out) return out;
    } else {
      for (var i = 0; i < words.length; i++) {
        var k = sentence.indexOf(words[i]);
        if (k >= 0) return sentence.slice(0, k) + label + sentence.slice(k + words[i].length);
      }
    }
    return label + ' ' + sentence;
  }

  function wireCard(box, sentence) {
    box.querySelectorAll('button.copy').forEach(function (b) {
      b.addEventListener('click', function () { copyText(b.getAttribute('data-copy') || '', b); });
    });
    box.querySelectorAll('button.ask').forEach(function (b) {
      b.addEventListener('click', function () { ask(b.getAttribute('data-ask')); });
    });
    box.querySelectorAll('button.choice').forEach(function (b) {
      b.addEventListener('click', function () { ask(replaceAmbiguous(sentence, b.getAttribute('data-slot'), b.getAttribute('data-choice'))); });
    });
    box.querySelectorAll('button.dslink').forEach(function (b) {
      b.addEventListener('click', function () { openCatalog(b.getAttribute('data-dataset')); });
    });
    box.querySelectorAll('a.sheet').forEach(function (a) {
      a.addEventListener('click', function () {
        var href = a.getAttribute('href').split('#')[0];
        a.setAttribute('href', state.purpose ? href + '#purpose=' + encodeURIComponent(state.purpose) : href);
      });
    });
    box.querySelectorAll('.hint').forEach(function (h) { fillHint(h, h.getAttribute('data-hint')); });
    box.querySelectorAll('.card[data-behavior="document"] .msg').forEach(function (p) { addSentenceChecks(p); });
  }

  function addSentenceChecks(p) {
    var parts = (p.textContent || '').split(/(?<=[.다음함])\s+/).filter(function (s) { return s.trim().length > 8; });
    if (!parts.length) return;
    var wrap = el('div', 'checks');
    wrap.appendChild(el('span', 'lbl', '이 문장 검산하기'));
    parts.slice(0, 6).forEach(function (s) {
      var b = el('button', 'ask', s.trim()); b.type = 'button';
      b.addEventListener('click', function () { ask(s.trim()); });
      wrap.appendChild(b);
    });
    p.parentNode.insertBefore(wrap, p.nextSibling);
  }

  function guideStep(id) {
    var g = state.guide || {};
    return (g.steps || []).filter(function (s) { return s.id === id; })[0] || null;
  }

  function fillHint(node, id) {
    var s = guideStep(id);
    if (!s) { node.hidden = true; return; }
    var d = el('details', 'hintbox');
    d.appendChild(el('summary', null, id === 'export' ? '반출 신청하는 법' : '자료 받는 법'));
    renderStepItems(d, s);
    clearNode(node); node.appendChild(d);
  }

  function renderStepItems(parent, s) {
    if (s.summary) parent.appendChild(el('p', 'muted', s.summary));
    var ul = el('ul');
    (s.items || []).forEach(function (it) {
      var li = el('li', null, it.text || '');
      if (it.source) li.appendChild(el('span', 'src', ' 출처: ' + it.source));
      if (it.ref) li.appendChild(el('span', 'ref', ' ' + it.ref));
      ul.appendChild(li);
    });
    parent.appendChild(ul);
  }

  /* ---------------- overlay panels ---------------- */
  function openOverlay(title) {
    $('ov-title').textContent = title;
    var body = $('ov-body'); clearNode(body);
    $('overlay').hidden = false;
    return body;
  }
  function closeOverlay() { $('overlay').hidden = true; }

  function openGuide(onlyStep) {
    var g = state.guide || {};
    var body = openOverlay('센터 이용 안내');
    if (!g.steps || !g.steps.length) { body.appendChild(el('p', null, '안내 자료를 읽지 못했습니다.')); return; }
    if (g.disclaimer) body.appendChild(el('p', 'muted', g.disclaimer));
    var c = g.contact;
    if (c) {
      var cd = el('div', 'contact');
      [c.name, c.address, c.hours, c.tel, c.email].forEach(function (v) { if (v) cd.appendChild(el('span', null, v)); });
      if (c.source) cd.appendChild(el('span', 'src', '출처: ' + c.source));
      body.appendChild(cd);
    }
    g.steps.forEach(function (s) {
      if (onlyStep && s.id !== onlyStep) return;
      var sec = el('section', 'gstep');
      sec.appendChild(el('h3', null, s.title || ''));
      renderStepItems(sec, s);
      body.appendChild(sec);
    });
    if (!onlyStep && g.unconfirmed && g.unconfirmed.length) {
      var u = el('section', 'gstep unconf');
      u.appendChild(el('h3', null, '아직 확인되지 않은 것'));
      if (g.unconfirmed_note) u.appendChild(el('p', 'muted', g.unconfirmed_note));
      var ul = el('ul');
      g.unconfirmed.forEach(function (x) { ul.appendChild(el('li', null, x.text || '')); });
      u.appendChild(ul); body.appendChild(u);
    }
  }

  function popularSet() {
    var p = (state.catalog || {}).popular || {};
    var s = {};
    (p.search_top10 || []).concat(p.export_top10 || []).forEach(function (l) { s[l] = true; });
    return s;
  }

  function openCatalog(detailLabel) {
    var cat = state.catalog || {};
    var ds = cat.datasets || [];
    var body = openOverlay('데이터 둘러보기');
    if (!ds.length) { body.appendChild(el('p', null, '데이터 목록을 읽지 못했습니다.')); return; }
    if (detailLabel) {
      var hit = ds.filter(function (d) { return d.label === detailLabel; })[0];
      if (hit) { showDetail(body, hit); return; }
    }
    if (cat.notice) body.appendChild(el('p', 'muted', cat.notice));
    var q = el('input', 'search'); q.type = 'search'; q.placeholder = '데이터 이름, 설명, 칸 이름으로 찾기'; q.maxLength = 40;
    body.appendChild(q);
    var chips = el('div', 'chips2');
    var sel = { cat: null, popular: false };
    var all = el('button', 'chipbtn on', '전체'); all.type = 'button'; chips.appendChild(all);
    var btns = [all];
    (cat.categories || []).forEach(function (c) {
      var b = el('button', 'chipbtn', c); b.type = 'button'; b.setAttribute('data-cat', c); chips.appendChild(b); btns.push(b);
    });
    var pop = el('button', 'chipbtn', '많이 찾는 데이터'); pop.type = 'button'; pop.setAttribute('data-pop', '1'); chips.appendChild(pop); btns.push(pop);
    body.appendChild(chips);
    var popLine = el('p', 'muted small', ''); body.appendChild(popLine);
    var count = el('p', 'muted small'); body.appendChild(count);
    var list = el('div', 'dslist'); body.appendChild(list);
    var popular = popularSet();
    btns.forEach(function (b) {
      b.addEventListener('click', function () {
        btns.forEach(function (x) { x.className = 'chipbtn'; }); b.className = 'chipbtn on';
        sel.cat = b.getAttribute('data-cat'); sel.popular = !!b.getAttribute('data-pop');
        draw();
      });
    });
    q.addEventListener('input', draw);
    function hay(d) {
      var parts = [d.label, d.description];
      (d.columns || []).forEach(function (c) { parts.push(c.ko, c.en); });
      return parts.join(' ').toLowerCase();
    }
    function draw() {
      clearNode(list);
      var term = (q.value || '').trim().toLowerCase();
      popLine.textContent = sel.popular ? ('기준: ' + (((cat.popular || {}).source) || '')) : '';
      var shown = ds.filter(function (d) {
        if (sel.cat && d.category !== sel.cat) return false;
        if (sel.popular && !popular[d.label]) return false;
        if (term && hay(d).indexOf(term) < 0) return false;
        return true;
      });
      count.textContent = '데이터 ' + shown.length + '개';
      shown.forEach(function (d) {
        var c = el('button', 'dscard'); c.type = 'button';
        c.appendChild(el('b', null, d.label));
        c.appendChild(el('span', 'meta', (d.category || '') + ' · ' + (d.provider || '')));
        c.appendChild(el('span', d.export_ok === false ? 'badge warnb' : 'badge okb', d.export_ok === false ? '가공 결과만 반출' : '원본 반출 가능'));
        c.addEventListener('click', function () { showDetail(body, d); });
        list.appendChild(c);
      });
    }
    draw();
  }

  function reportCatalogEntry(label) {
    var rc = state.reportCatalog || {};
    return (rc.datasets || []).filter(function (d) { return d.label === label; })[0] || null;
  }

  function showDetail(body, d) {
    clearNode(body);
    $('ov-title').textContent = d.label;
    var back = el('button', null, '목록으로'); back.type = 'button';
    back.addEventListener('click', function () { openCatalog(); });
    body.appendChild(back);
    body.appendChild(el('p', 'meta', (d.category || '') + ' · ' + (d.provider || '') + (d.registered ? ' · 등록 ' + d.registered : '') + (d.export ? ' · ' + d.export : '')));
    body.appendChild(el('p', 'desc', d.description || ''));
    var t = el('table', 'ev'); var th = el('tr');
    ['한글 이름', '영문 이름', '예시', '비고'].forEach(function (h) { th.appendChild(el('th', null, h)); });
    var thead = el('thead'); thead.appendChild(th); t.appendChild(thead);
    var tb = el('tbody'); var hidden = 0;
    (d.columns || []).forEach(function (c) {
      if (c.partition) { hidden++; return; }
      var tr = el('tr');
      [c.ko, c.en, c.example, c.note].forEach(function (v) { tr.appendChild(el('td', null, v || '')); });
      tb.appendChild(tr);
    });
    t.appendChild(tb); body.appendChild(t);
    if (hidden && (state.catalog || {}).csv_note) body.appendChild(el('p', 'muted small', state.catalog.csv_note));
    var rc = reportCatalogEntry(d.label);
    if (rc) {
      body.appendChild(el('p', null, '쓰임: ' + (rc.why || '')));
      if (rc.menu_hint) body.appendChild(el('p', null, '받을 때: ' + rc.menu_hint));
    }
    var add = el('button', 'primary', '받을 목록에 담기'); add.type = 'button';
    add.addEventListener('click', function () {
      if (state.memo.indexOf(d.label) < 0) state.memo.push(d.label);
      $('memo-count').textContent = String(state.memo.length);
      add.textContent = '담았습니다';
    });
    body.appendChild(add);
  }

  function memoText() {
    var lines = ['받을 자료 메모'];
    state.memo.forEach(function (l, i) {
      var rc = reportCatalogEntry(l);
      lines.push((i + 1) + ') ' + l + (rc && rc.menu_hint ? ' - ' + rc.menu_hint : ''));
    });
    var s = guideStep('download');
    if (s) { lines.push(''); lines.push(s.title || ''); (s.items || []).forEach(function (it) { lines.push('- ' + (it.text || '')); }); }
    return lines.join('\n');
  }

  function openMemo() {
    var body = openOverlay('받을 자료 메모');
    if (!state.memo.length) body.appendChild(el('p', null, '아직 담은 자료가 없습니다. 데이터 둘러보기에서 "받을 목록에 담기"를 눌러 주세요.'));
    var ol = el('ol');
    state.memo.forEach(function (l) {
      var rc = reportCatalogEntry(l);
      var li = el('li', null, l);
      if (rc && rc.menu_hint) li.appendChild(el('span', 'muted', ' · ' + rc.menu_hint));
      ol.appendChild(li);
    });
    body.appendChild(ol);
    var s = guideStep('download');
    if (s) { var sec = el('section', 'gstep'); sec.appendChild(el('h3', null, s.title || '')); renderStepItems(sec, s); body.appendChild(sec); }
    var cp = el('button', null, '복사'); cp.type = 'button';
    cp.addEventListener('click', function () { copyText(memoText(), cp); });
    var pr = el('button', null, '인쇄'); pr.type = 'button';
    pr.addEventListener('click', function () { window.print(); });
    body.appendChild(cp); body.appendChild(pr);
  }

  /* ---------------- journey / start card ---------------- */
  var ACTIONS = {
    open_catalog: function () { openCatalog(); },
    start_card: function () { $('start-card').scrollIntoView({ behavior: 'smooth' }); },
    open_guide: function () { openGuide(); },
    load_csv: function () { $('file').click(); },
    try_sample: function () {
      var s = ((state.status || {}).samples || []).filter(function (n) { return n.indexOf('SYNTHETIC_card') === 0; });
      if (s.length) loadSample(s[s.length - 1]);
    },
    open_export_help: function () { openGuide('export'); },
    open_wait_help: function () { openGuide('wait'); },
    open_home: function () { $('home').scrollIntoView({ behavior: 'smooth' }); },
    open_memo: function () { openMemo(); },
    open_docs: function () { $('docs').scrollIntoView({ behavior: 'smooth' }); },
    back_public: function () { loadSample((state.status || {}).public_file); }
  };
  var JOURNEY_KEYS = ['open_catalog', 'start_card', 'open_guide', 'load_csv', 'try_sample', 'open_export_help', 'open_wait_help'];

  function renderJourney() {
    var g = state.guide || {};
    var j = $('journey'); clearNode(j);
    if (!g.journey || !g.journey.length) { $('plain-steps').hidden = false; return; }
    $('plain-steps').hidden = true;
    g.journey.forEach(function (c) {
      var card = el('div', 'jcard');
      card.appendChild(el('h3', null, c.title || ''));
      card.appendChild(el('p', null, c.promise || ''));
      (c.actions || []).forEach(function (a) {
        if (JOURNEY_KEYS.indexOf(a.key) < 0) return;
        var b = el('button', null, a.label || ''); b.type = 'button';
        b.addEventListener('click', ACTIONS[a.key]);
        card.appendChild(b);
      });
      j.appendChild(card);
    });
  }

  function wireStartCard() {
    var form = $('start-card');
    form.querySelectorAll('.opts').forEach(function (grp) {
      var name = grp.getAttribute('data-name');
      grp.querySelectorAll('button').forEach(function (b) {
        b.addEventListener('click', function () {
          grp.querySelectorAll('button').forEach(function (x) { x.classList.remove('on'); });
          b.classList.add('on'); state.start[name] = b.getAttribute('data-v');
        });
      });
    });
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var region = ($('sc-region').value || '').trim().slice(0, 30);
      var biz = ($('sc-biz').value || '').trim().slice(0, 30);
      var what = state.start.what || '';
      var parts = [region, biz];
      if (what && what !== '그 밖') parts.push(what + ' 작성에');
      var sentence = parts.filter(function (x) { return x; }).join(' ');
      sentence = (sentence ? sentence + ' ' : '') + '어떤 자료를 받아야 하나요';
      var who = state.start.who && state.start.who !== '그 밖' ? state.start.who : '';
      state.purpose = [who, what && what !== '그 밖' ? what : ''].filter(function (x) { return x; }).join(' ');
      ask(sentence);
    });
  }

  function resetBrowser() {
    clearNode($('conversation'));
    state.memo = []; $('memo-count').textContent = '0';
    state.purpose = ''; state.start = {};
    $('start-card').reset();
    document.querySelectorAll('#start-card .opts button').forEach(function (b) { b.classList.remove('on'); });
    ['doc-biz', 'doc-bjd', 'doc-month', 'brief-biz', 'sentence'].forEach(function (id) { $(id).value = ''; });
    closeOverlay();
  }

  /* ---------------- documents ---------------- */
  function docRequest(tpl) {
    var params = {};
    if (tpl === 'bizplan_market') { params.biz = $('doc-biz').value.trim(); params.bjd = $('doc-bjd').value.trim(); }
    if (tpl === 'consumption_trend') { params.month = $('doc-month').value.trim(); params.group = $('doc-group').value; }
    if (tpl === 'data_brief') { params.biz = $('brief-biz').value.trim(); }
    var conv = $('conversation');
    conv.appendChild(el('div', 'bubble user', '문서 초안 요청'));
    api('/api/doc', { template: tpl, params: params }).then(function (j) { showResult(j, ''); });
    $('chat').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  /* ---------------- format catalog ("틀 고르기", 10.8-2) ---------------- */
  var DOC_INPUT = { bizplan_market: 'doc-biz', consumption_trend: 'doc-month', data_brief: 'brief-biz' };
  function renderFormats() {
    var box = $('formats'); clearNode(box);
    var fam = ((state.reportCatalog || {}).families) || {};
    var kind = (((state.status || {}).active) || {}).kind || '';
    var keys = Object.keys(fam);
    var show = kind === 'generic' ? keys.filter(function (k) { return k !== 'card'; }) : keys.filter(function (k) { return k === 'card'; });
    if (!show.length) return;
    box.appendChild(el('h3', null, '틀 고르기'));
    show.forEach(function (k) {
      var f = fam[k] || {};
      (f.formats || []).forEach(function (fm) {
        var c = el('div', 'fmt');
        c.appendChild(el('b', null, fm.title || ''));
        c.appendChild(el('span', 'muted small', ' · ' + (f.label || '') + ' · ' + (fm.for_whom || '')));
        c.appendChild(el('div', 'small', '차례: ' + (fm.blocks || []).join(' / ')));
        var b = fm.basis || {};
        c.appendChild(el('div', 'src', b.type === 'public_form' ? '본뜬 양식: ' + (b.form || '') + (b.url ? ' (' + b.url + ')' : '') : '자체 제작: ' + (b.note || '')));
        var btn = el('button', null, fm.status === 'implemented' ? '이 틀로 쓰기' : '차례만 보기(자료 요약을 함께 붙입니다)'); btn.type = 'button';
        btn.addEventListener('click', function () {
          if (fm.status === 'implemented' && DOC_INPUT[fm.id]) { var inp = $(DOC_INPUT[fm.id]); inp.scrollIntoView({ behavior: 'smooth', block: 'center' }); inp.focus(); }
          else { ask('이 자료를 요약해 주세요'); }
        });
        c.appendChild(btn);
        box.appendChild(c);
      });
    });
  }

  /* ---------------- init ---------------- */
  function init() {
    var ex = $('examples');
    EXAMPLES.forEach(function (s) {
      var b = el('button', 'ask', s); b.type = 'button';
      b.addEventListener('click', function () { ask(s); });
      ex.appendChild(b);
    });
    $('ask-form').addEventListener('submit', function (e) { e.preventDefault(); ask($('sentence').value); $('sentence').value = ''; });
    $('sentence').addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask($('sentence').value); $('sentence').value = ''; } });
    $('file').addEventListener('change', function (e) { var f = e.target.files && e.target.files[0]; if (f) loadFile(f); e.target.value = ''; });
    $('clear').addEventListener('click', function () {
      api('/api/clear', {}).then(function (j) { resetBrowser(); applyStatus(j.status); boardMsg(j.message || ''); });
    });
    $('ov-close').addEventListener('click', closeOverlay);
    $('overlay').addEventListener('click', function (e) { if (e.target === $('overlay')) closeOverlay(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeOverlay(); });
    document.querySelectorAll('[data-action]').forEach(function (b) {
      var f = ACTIONS[b.getAttribute('data-action')];
      if (f) b.addEventListener('click', f);
    });
    document.querySelectorAll('[data-doc]').forEach(function (b) {
      b.addEventListener('click', function () { docRequest(b.getAttribute('data-doc')); });
    });
    wireStartCard();
    refresh();
    api('/api/guide').then(function (g) {
      state.guide = g; renderJourney();
      if (!g.steps || !g.steps.length) document.querySelectorAll('[data-action="open_guide"]').forEach(function (b) { b.hidden = true; });
    });
    api('/api/catalog').then(function (c) {
      state.catalog = c;
      if (!c.datasets || !c.datasets.length) document.querySelectorAll('[data-action="open_catalog"]').forEach(function (b) { b.hidden = true; });
    });
    api('/api/report_catalog').then(function (r) { state.reportCatalog = r.__status === 200 ? r : {}; renderFormats(); });
  }
  document.addEventListener('DOMContentLoaded', init);
})();
