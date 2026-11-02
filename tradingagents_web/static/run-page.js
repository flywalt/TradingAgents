/* The run page: the graph, the event trail, the clock, the rerun button.
 *
 * One file on purpose. The page is allowed exactly one <script>, and that
 * constraint is what keeps a stray nested tag from silently killing every
 * handler (see the native form post that once lost a submission).
 *
 * The topology and both layouts come from progress_graph.py; this file only
 * paints them and lights them from the recorded events.
 */
(function () {
  'use strict';

  var record = document.querySelector('.run-record');
  if (!record) return;
  var runId = record.dataset.runId;
  var terminal = record.dataset.terminal === 'true';

  var statusLabels = {queued: '排队中', running: '运行中', succeeded: '已完成', failed: '失败'};
  var profileLabels = {CN_A_SHARE: 'A 股', UPSTREAM_DEFAULT: '海外默认'};
  var reportLabels = {
    market_report: '市场', sentiment_report: '情绪', news_report: '新闻',
    fundamentals_report: '基本面', investment_plan: '研究结论',
    trader_investment_plan: '交易方案', final_trade_decision: '组合决策'
  };

  var svg = document.getElementById('progress-graph');
  var data = svg && svg.dataset.graph ? JSON.parse(svg.dataset.graph) : null;
  var trail = document.getElementById('timeline');
  var statusChip = document.getElementById('status');
  var elapsed = document.getElementById('elapsed');
  var roundNote = document.getElementById('graph-rounds');

  /* kernel node name → what the page calls it. Built from the graph data, so
   * the words live in one place (labels.py) instead of in this file. */
  var nodeLabels = {};
  var toGraphId = {};
  ['wide', 'narrow'].forEach(function (name) {
    if (!data) return;
    data[name].nodes.forEach(function (node) {
      nodeLabels[node.kernel] = node.label;
      toGraphId[node.kernel] = node.id;
    });
  });

  /* ---------------------------------------------------------------- graph */

  var SVG_NS = 'http://www.w3.org/2000/svg';
  var state = {nodes: {}, rounds: {research: 0, risk: 0}, debate: null};
  var layoutName = null;

  function element(name, attrs) {
    var node = document.createElementNS(SVG_NS, name);
    Object.keys(attrs || {}).forEach(function (key) { node.setAttribute(key, attrs[key]); });
    return node;
  }

  function currentLayout() {
    return window.matchMedia('(min-width: 720px)').matches ? 'wide' : 'narrow';
  }

  function draw() {
    if (!svg || !data) return;
    layoutName = currentLayout();
    var layout = data[layoutName];
    svg.setAttribute('viewBox', layout.viewBox);
    while (svg.firstChild) svg.removeChild(svg.firstChild);

    layout.edges.forEach(function (edge) {
      svg.appendChild(element('path', {
        d: edge.d, 'data-from': edge.from, 'data-to': edge.to, 'data-kind': edge.kind
      }));
    });

    layout.nodes.forEach(function (node) {
      var group = element('g', {
        'data-node': node.id, transform: 'translate(' + node.x + ',' + node.y + ')'
      });
      group.appendChild(element('rect', {width: node.w, height: node.h, rx: 6}));
      var text = element('text', {x: node.w / 2, y: node.h / 2 + 4, 'text-anchor': 'middle'});
      text.textContent = layoutName === 'wide' ? node.label : node.short;
      group.appendChild(text);
      svg.appendChild(group);
    });
    paint();
  }

  function paint() {
    if (!svg) return;
    Array.prototype.forEach.call(svg.querySelectorAll('[data-node]'), function (group) {
      group.setAttribute('class', 'node node--' + (state.nodes[group.dataset.node] || 'idle'));
    });
    Array.prototype.forEach.call(svg.querySelectorAll('[data-kind]'), function (path) {
      var from = state.nodes[path.dataset.from] || 'idle';
      var to = state.nodes[path.dataset.to] || 'idle';
      var classes = ['edge', 'edge--' + path.dataset.kind];
      // A hand-off is live while the next node works and the previous one is done.
      if (to === 'active' && from === 'done') classes.push('is-flowing');
      if (state.debate && state.debate.indexOf(path.dataset.from) >= 0 &&
          state.debate.indexOf(path.dataset.to) >= 0) {
        classes.push('is-debate');
      }
      path.setAttribute('class', classes.join(' '));
    });
    if (roundNote) {
      var parts = [];
      if (state.rounds.research) parts.push('研究辩论 第 ' + state.rounds.research + ' 轮');
      if (state.rounds.risk) parts.push('风险辩论 第 ' + state.rounds.risk + ' 轮');
      roundNote.textContent = parts.join(' · ');
    }
  }

  var DEBATES = [['bull', 'bear'],
                 ['risk-aggressive', 'risk-conservative'],
                 ['risk-conservative', 'risk-neutral'],
                 ['risk-neutral', 'risk-aggressive']];

  function noteActivity(id) {
    state.nodes[id] = 'active';
    // Rounds are counted where a round starts, not on hand-offs: the risk
    // debate has three speakers per round, the research debate two.
    if (id === 'bull') state.rounds.research += 1;
    if (id === 'risk-aggressive') state.rounds.risk += 1;
    state.debate = null;
    DEBATES.forEach(function (pair) {
      if (pair.indexOf(id) >= 0) {
        var other = pair[0] === id ? pair[1] : pair[0];
        if (state.nodes[other] === 'active' || state.nodes[other] === 'done') state.debate = pair;
      }
    });
    paint();
  }

  /* ---------------------------------------------------------------- trail */

  var startedAt = new Map();

  function add(text, kind, at) {
    if (!trail) return;
    if (trail.firstElementChild && trail.firstElementChild.hasAttribute('data-empty')) {
      trail.innerHTML = '';
    }
    var item = document.createElement('li');
    item.className = 'trail__item' + (kind ? ' trail__item--' + kind : '');
    var mark = document.createElement('span');
    mark.className = 'trail__mark';
    mark.setAttribute('aria-hidden', 'true');
    var body = document.createElement('span');
    body.className = 'trail__text';
    body.textContent = text;
    item.appendChild(mark);
    item.appendChild(body);
    if (at) {
      var time = document.createElement('time');
      time.className = 'trail__time mono';
      time.dateTime = at;
      time.textContent = at.slice(11, 19);
      item.appendChild(time);
    }
    trail.appendChild(item);
  }

  function elapsedSince(startIso, endIso) {
    var start = Date.parse(startIso);
    // A finished run is replayed from the log, so measure to the event's own
    // timestamp rather than to now.
    var end = endIso ? Date.parse(endIso) : Date.now();
    if (!startIso || Number.isNaN(start) || Number.isNaN(end)) return '';
    var seconds = Math.max(0, Math.round((end - start) / 1000));
    if (seconds < 60) return seconds + ' 秒';
    return Math.floor(seconds / 60) + ' 分 ' + String(seconds % 60).padStart(2, '0') + ' 秒';
  }

  function tick() {
    if (!elapsed || !elapsed.dataset.started) return;
    var start = Date.parse(elapsed.dataset.started);
    if (Number.isNaN(start)) return;
    var seconds = Math.max(0, Math.floor((Date.now() - start) / 1000));
    elapsed.textContent = String(Math.floor(seconds / 60)).padStart(2, '0') + ':' +
      String(seconds % 60).padStart(2, '0');
  }

  function duration() {
    if (!elapsed || !elapsed.dataset.finished) return;
    var start = Date.parse(elapsed.dataset.started);
    var end = Date.parse(elapsed.dataset.finished);
    if (Number.isNaN(start) || Number.isNaN(end)) return;
    var seconds = Math.max(0, Math.floor((end - start) / 1000));
    elapsed.textContent = String(Math.floor(seconds / 60)).padStart(2, '0') + ':' +
      String(seconds % 60).padStart(2, '0');
  }

  /* --------------------------------------------------------------- events */

  function settle() {
    // Runs recorded before node.finished existed would leave nodes spinning
    // forever; the run is over, so show them settled.
    Object.keys(state.nodes).forEach(function (id) {
      if (state.nodes[id] === 'active') state.nodes[id] = 'done';
    });
    state.debate = null;
    paint();
  }

  function handle(event) {
    var payload = event.payload || {};
    if (event.kind === 'run.started') {
      add('开始运行 ' + (profileLabels[payload.profile] || payload.profile || ''), 'start', event.at);
    } else if (event.kind === 'node.started') {
      startedAt.set(payload.node, event.at);
      var id = toGraphId[payload.node];
      if (id) noteActivity(id);
      add('开始 ' + (nodeLabels[payload.node] || payload.node), 'node', event.at);
    } else if (event.kind === 'node.finished') {
      var doneId = toGraphId[payload.node];
      if (doneId) { state.nodes[doneId] = 'done'; paint(); }
      var spent = elapsedSince(startedAt.get(payload.node), event.at);
      add('完成 ' + (nodeLabels[payload.node] || payload.node) + (spent ? ' · ' + spent : ''),
          'done', event.at);
    } else if (event.kind === 'report.ready') {
      add('报告已生成 · ' + (reportLabels[payload.key] || payload.key), 'report', event.at);
    } else if (event.kind === 'run.failed') {
      Object.keys(state.nodes).forEach(function (id) {
        if (state.nodes[id] === 'active') state.nodes[id] = 'failed';
      });
      state.debate = null;
      paint();
    }
  }

  draw();
  window.addEventListener('resize', function () {
    if (!svg || currentLayout() === layoutName) return;
    draw();
  });

  if (terminal) { duration(); } else { setInterval(tick, 1000); tick(); }

  if (runId) {
    var source = new EventSource('/api/runs/' + runId + '/events');
    if (terminal) {
      source.onmessage = function (message) {
        var event = JSON.parse(message.data);
        handle(event);
        if (event.payload && event.payload.final) { settle(); source.close(); }
      };
      source.onerror = function () {
        // The stream ends without a "final" payload whenever a run was
        // recovered rather than finished (a restart mid-run marks the job
        // failed without appending run.failed). The run is over either way:
        // settle it instead of leaving a node pulsing forever.
        settle();
        source.close();
      };
    } else {
      var polling = null;
      source.onmessage = function (message) {
        var event = JSON.parse(message.data);
        handle(event);
        if (event.payload && event.payload.final) location.reload();
      };
      source.onerror = function () {
        source.close();
        if (polling) return;
        polling = setInterval(async function () {
          var response = await fetch('/api/runs/' + runId);
          if (!response.ok) return;
          var job = await response.json();
          if (statusChip) statusChip.textContent = statusLabels[job.status] || job.status;
          if (job.status === 'succeeded' || job.status === 'failed') location.reload();
        }, 5000);
      };
    }
  }

  var rerun = document.getElementById('rerun');
  if (rerun) {
    rerun.addEventListener('click', async function () {
      rerun.disabled = true;
      rerun.textContent = '提交中…';
      var response = await fetch('/api/runs/' + runId + '/rerun', {
        method: 'POST', headers: {'X-Requested-With': 'fetch'}
      });
      var body = await response.json().catch(function () { return {}; });
      if (response.ok) {
        location.href = '/runs/' + body.id;
      } else {
        rerun.disabled = false;
        rerun.textContent = '重新运行';
        alert((body.error && body.error.message) || '提交失败');
      }
    });
  }
})();
