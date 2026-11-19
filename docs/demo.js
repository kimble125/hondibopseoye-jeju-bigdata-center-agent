/* Web demo shim (not part of the product). Replaces fetch() for the app's own api/ URLs with
   responses recorded from the real local server. No data files, no network calls. */
(function () {
  'use strict';
  var BANNER = "웹 체험판: 미리 계산해 둔 실제 응답으로 화면을 보여 드립니다. 데이터 파일은 이 사이트에 들어 있지 않습니다. 숫자의 출처: 제주데이터허브(제공처 제주빅데이터센터). 전체 기능은 제출한 프로그램을 PC에서 실행해야 쓸 수 있습니다.";
  var NOT_RECORDED = "웹 체험판에서는 준비된 문장만 답합니다. 아래 예시 단추를 눌러 보거나, ZIP을 내려받아 실행하면 어떤 문장이든 확인할 수 있습니다.";
  var SAMPLE_ONLY = "웹 체험판에서는 이 가상 파일 하나만 준비되어 있습니다";
  var NO_UPLOAD = "웹 체험판에서는 파일을 올릴 수 없습니다(파일은 어디에도 전송되지 않습니다)";
  var data = null, table = 'public';
  var ready = (function () {
    var real = window.fetch.bind(window);
    return real('demo_data.json').then(function (r) { return r.json(); }).then(function (j) { data = j; return j; });
  })();

  function norm(s) { return String(s || '').trim().replace(/\s+/g, ' '); }
  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#x27;');
  }
  function status() { return data.get[table === 'synthetic' ? 'status_synthetic' : 'status_public']; }
  function reply(obj, code) {
    return new Response(JSON.stringify(obj), { status: code || 200, headers: { 'Content-Type': 'application/json; charset=utf-8' } });
  }
  function docKey(tpl, params) {
    var items = Object.keys(params || {}).map(function (k) { return [k, norm(params[k])]; })
      .filter(function (kv) { return kv[1]; }).sort(function (a, b) { return a[0] < b[0] ? -1 : (a[0] > b[0] ? 1 : 0); });
    return tpl + '|' + items.map(function (kv) { return kv[0] + '=' + kv[1]; }).join('&');
  }
  function notRecorded() {
    var sugg = (data.suggest[table] || []).filter(function (s) { return (data.ask[table] || {})[s]; });
    var h = '<div class="card" data-behavior="demo_notice"><div class="ai-line">웹 체험판 안내</div>' +
      '<div class="verdict v-none b-demo_notice">준비된 문장이 아닙니다</div><p class="msg">' + esc(NOT_RECORDED) + '</p>';
    if (sugg.length) {
      h += '<div class="sugg"><span class="lbl">이어서 확인해 볼 문장</span>' + sugg.map(function (s) {
        return '<button type="button" class="ask" data-ask="' + esc(s) + '">' + esc(s) + '</button>';
      }).join('') + '</div>';
    }
    h += '<div class="foot"></div></div>';
    return { behavior: 'demo_notice', verdict: 'none', message: NOT_RECORDED, notices: [], data: {}, decisions: [],
      evidence: null, choices: [], suggestions: sugg, card_html: h, report_id: null, doc_id: null, active: status().active };
  }
  function body(opt) { try { return JSON.parse((opt && opt.body) || '{}'); } catch (e) { return {}; } }

  function handle(name, opt) {
    var method = ((opt && opt.method) || 'GET').toUpperCase();
    if (method === 'GET') {
      if (name === 'status') return reply(status());
      if (data.get[name]) return reply(data.get[name]);
      return reply({ error: '찾는 주소가 없습니다.' }, 404);
    }
    var b = body(opt);
    if (name === 'ask') {
      var hit = (data.ask[table] || {})[norm(b.sentence)];
      return reply(hit || notRecorded());
    }
    if (name === 'doc') {
      var d = (data.doc[table] || {})[docKey(b.template, b.params)];
      return reply(d || notRecorded());
    }
    if (name === 'load_sample') {
      if (b.name === data.synthetic_sample) { table = 'synthetic'; return reply(data.load_sample_synthetic); }
      if (b.name === status().public_file) { table = 'public'; return reply(data.load_sample_public); }
      return reply({ loaded: null, status: status(), message: SAMPLE_ONLY });
    }
    if (name === 'load') return reply({ error: NO_UPLOAD, missing: [] }, 400);
    if (name === 'clear') { table = 'public'; return reply(data.clear); }
    return reply({ error: '찾는 주소가 없습니다.' }, 404);
  }

  var realFetch = window.fetch.bind(window);
  window.fetch = function (input, opt) {
    var url;
    try { url = new URL(typeof input === 'string' ? input : input.url, location.href); } catch (e) { return realFetch(input, opt); }
    var base = location.pathname.replace(/[^\/]*$/, '');
    if (url.origin === location.origin && url.pathname.indexOf(base) === 0) {
      var rest = url.pathname.slice(base.length);
      var m = /^api\/([a-z_]+)$/.exec(rest);
      if (m) return ready.then(function () { return handle(m[1], opt); });
      if (/^static\//.test(rest)) return realFetch(rest.slice(7), opt);
    }
    return realFetch(input, opt);
  };

  document.addEventListener('DOMContentLoaded', function () {
    var bar = document.createElement('div');
    bar.id = 'demo-banner';
    bar.setAttribute('role', 'note');
    bar.textContent = BANNER;
    bar.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:30;background:#fff4c2;color:#222;' +
      'border-bottom:2px solid #c9a400;padding:6px 14px;font-size:14px;line-height:1.45;text-align:center';
    document.body.insertBefore(bar, document.body.firstChild);
    var st = document.createElement('style');
    document.head.appendChild(st);
    function fit() {
      var h = bar.offsetHeight;
      document.body.style.paddingTop = h + 'px';
      st.textContent = 'header{top:' + h + 'px!important}#overlay{padding-top:' + (h + 20) + 'px!important}' +
        '@media print{#demo-banner{display:none}body{padding-top:0!important}}';
    }
    fit(); window.addEventListener('resize', fit);
    var pre = { 'doc-biz': '한식 음식점업', 'doc-month': '202506', 'brief-biz': '체인화 편의점' };
    Object.keys(pre).forEach(function (id) { var e = document.getElementById(id); if (e && !e.value) e.value = pre[id]; });
  });
})();
