"""
app.py — playground GUI. 왼쪽 입력창(생성/수정 방식 선택 + 지시문 + 로그) /
오른쪽 미리보기(iframe) 2단 화면.

생성 방식(J/S)과 수정 방식(K/S)을 독립적으로 고를 수 있다 — 단, K(patch)는
구조화된 plan이 있을 때만 동작하므로(apply_patch가 {"blocks":[...]} 구조를
전제), plan이 없으면(S로 생성했거나 템플릿을 불러왔거나, 한 번이라도 S로
수정한 뒤라면) 서버가 명시적으로 거부하고 클라이언트도 K 옵션을 비활성화한다.

로직은 core.py를 그대로 쓴다 — CLI(generate.py/edit.py)와 완전히 같은
함수라, GUI에서 나온 결과와 CLI 결과가 다를 일이 없다. 서버는 상태를
안 들고 있고(plan/html_raw/session_dir을 응답에 실어 클라이언트가 다음
요청에 그대로 돌려줌), 매 단계를 CLI와 동일하게 playground/output/
아래에 파일로도 남긴다.

실행:
    python playground/app.py
    (기본 http://127.0.0.1:5050 — PLAYGROUND_BACKEND=ollama가 기본이라
    로컬 Ollama가 떠 있어야 한다)
"""
import os
import sys

from flask import Flask, jsonify, request, Response

from backend import DEFAULT_MODEL
from core import generate_page, generate_page_html, edit_page, edit_block_direct, blocks_in_html
from template_loader import load_template, load_event_css, TEMPLATE_LABELS
from util import new_session_dir, save_step, wrap_full_html, wrap_with_css

app = Flask(__name__)

KNOWN_MODELS = ["qwen2.5:7b", "qwen2.5-coder:7b", "exaone3.5:7.8b", "gemma3:4b"]
_EVENT_CSS = load_event_css()

INDEX_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>playground</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; font-family: -apple-system, "Segoe UI", sans-serif; height: 100vh; display: flex; }
  #left { width: 420px; min-width: 340px; display: flex; flex-direction: column; border-right: 1px solid #ddd; padding: 12px; }
  /* 오른쪽 미리보기 패널 — template/index.html의 쇼케이스 뷰어에서 그대로 가져옴 */
  #right {
    flex: 1; display: flex; flex-direction: column;
    background: #090d16; color: #f8fafc;
  }
  #previewHeader {
    background: #1e293b; border-bottom: 1px solid #334155;
    padding: 8px 16px; display: flex; align-items: center; justify-content: flex-end;
    gap: 8px; flex-wrap: wrap;
  }
  .view-btn {
    background: #0f172a; border: 1px solid #334155; color: #94a3b8;
    padding: 7px 12px; border-radius: 8px; font-size: 12px; font-weight: 600;
    cursor: pointer; display: flex; align-items: center; gap: 6px; transition: all .2s;
  }
  .view-btn:hover { color: #fff; border-color: #94a3b8; }
  .view-btn.active { background: #334155; color: #fff; border-color: #64748b; }
  .view-btn.toggle-admin { border-color: #f59e0b; color: #fbbf24; }
  .view-btn.toggle-admin.on { background: #b45309; color: #fff; }
  #previewMain {
    flex: 1; display: flex; align-items: center; justify-content: center;
    padding: 20px; overflow: hidden;
  }
  .preview-wrapper {
    width: 100%; height: 100%; max-width: 900px; background: #fff;
    border-radius: 16px; box-shadow: 0 20px 50px rgba(0,0,0,.5), 0 0 0 1px rgba(255,255,255,.1);
    overflow: hidden; display: flex; flex-direction: column;
    transition: max-width .3s cubic-bezier(.4,0,.2,1);
  }
  .preview-wrapper.mobile {
    max-width: 375px; border-radius: 36px;
    box-shadow: 0 0 0 8px #1e293b, 0 25px 60px rgba(0,0,0,.7);
  }
  .preview-wrapper iframe { flex: 1; border: 0; width: 100%; background: #fff; }
  h1 { font-size: 15px; margin: 0 0 8px; }
  .row { display: flex; gap: 6px; margin-bottom: 8px; align-items: center; }
  .row label { font-size: 12px; color: #555; width: 44px; flex-shrink: 0; }
  select, input[list] { flex: 1; padding: 4px; font-size: 12px; min-width: 0; }
  #log { flex: 1; overflow-y: auto; border: 1px solid #eee; border-radius: 6px; padding: 6px; margin-bottom: 8px; font-size: 12px; background: #fafafa; }
  .entry { margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px dashed #ddd; }
  .entry .who { font-weight: bold; }
  .entry pre { white-space: pre-wrap; background: #f0f0f0; padding: 4px; border-radius: 4px; font-size: 11px; margin: 4px 0 0; }
  .entry.rejected { color: #b00; }
  textarea { width: 100%; resize: vertical; min-height: 60px; font-size: 13px; padding: 6px; }
  .btnrow { display: flex; gap: 6px; margin-top: 6px; }
  button { padding: 8px 14px; font-size: 13px; cursor: pointer; }
  button.secondary { background: #eee; }
  #status { font-size: 11px; color: #888; margin-top: 4px; height: 14px; }
  .hint { font-size: 11px; color: #888; margin: -4px 0 8px; }
</style>
</head>
<body>
  <div id="left">
    <h1>playground — 왼쪽 입력 / 오른쪽 미리보기</h1>
    <div class="row">
      <label>모델</label>
      <input id="model" list="models" value="__DEFAULT_MODEL__">
      <datalist id="models">__MODEL_OPTIONS__</datalist>
    </div>
    <div class="row">
      <label>생성</label>
      <select id="genMode">
        <option value="plan">J — plan JSON</option>
        <option value="html">S — 직접 HTML</option>
      </select>
      <label style="width:auto;margin-left:6px;">수정</label>
      <select id="editMode">
        <option value="patch">K — patch</option>
        <option value="html">S — 직접 편집</option>
      </select>
    </div>
    <div class="hint">K는 plan이 있을 때만(J로 생성한 직후) 선택 가능 — S로 한 번 고치면 이후 K 불가</div>
    <div class="row">
      <label>템플릿</label>
      <select id="templateId">__TEMPLATE_OPTIONS__</select>
      <button id="loadTemplate" class="secondary">불러오기(S)</button>
    </div>
    <div class="row" id="blockRow" style="display:none;">
      <label>수정영역</label>
      <select id="blockKey"></select>
    </div>
    <div id="log"></div>
    <textarea id="instruction" placeholder="처음엔 페이지 설명(생성), 그 다음부터는 수정 지시문
예) 혜택 항목 마지막 하나 삭제해줘 / 글자 크기를 18px로 키워줘 / 투표 기능 추가해줘"></textarea>
    <div class="btnrow">
      <button id="send">전송</button>
      <button id="reset" class="secondary">새로 시작</button>
    </div>
    <div id="status"></div>
  </div>
  <div id="right">
    <div id="previewHeader">
      <button class="view-btn toggle-admin" id="btn-admin" onclick="toggleAdminMode()"
        title="관리자 전용 문구(공통 승인 문구 배지 등) 표시 토글 — event.css의 .admin-preview 규칙, 실제 템플릿/S 생성 결과에서만 보임">
        🛡️ 관리자 뷰: <span id="adminStatus">OFF</span>
      </button>
      <button class="view-btn active" id="btn-pc" onclick="setViewMode('pc')">🖥️ 데스크톱</button>
      <button class="view-btn" id="btn-mo" onclick="setViewMode('mo')">📱 모바일</button>
    </div>
    <div id="previewMain">
      <div class="preview-wrapper" id="previewWrap">
        <iframe id="preview"></iframe>
      </div>
    </div>
  </div>

<script>
let currentPlan = null;   // null이면 K(patch) 불가 — S로 생성/편집했거나 템플릿을 불러온 상태
let currentHtml = null;   // 항상 최신 조각(raw fragment)
let currentTheme = '';    // "theme-sports" 등 — event.css 색상이 여기 스코프돼 있어 body에 유지해야 함
let sessionDir = null;
let started = false;      // false면 다음 전송은 "생성", true면 "수정"

const logEl = document.getElementById('log');
const statusEl = document.getElementById('status');
const previewEl = document.getElementById('preview');
const instructionEl = document.getElementById('instruction');
const modelEl = document.getElementById('model');
const genModeEl = document.getElementById('genMode');
const editModeEl = document.getElementById('editMode');
const templateIdEl = document.getElementById('templateId');
const blockKeyEl = document.getElementById('blockKey');
const blockRowEl = document.getElementById('blockRow');

// ── 오른쪽 미리보기 — template/index.html의 PC/모바일·관리자 뷰 토글 그대로 ──
let isAdminMode = false;

function setViewMode(m) {
  const wrap = document.getElementById('previewWrap');
  const btnPc = document.getElementById('btn-pc');
  const btnMo = document.getElementById('btn-mo');
  if (m === 'mo') {
    wrap.classList.add('mobile'); btnMo.classList.add('active'); btnPc.classList.remove('active');
  } else {
    wrap.classList.remove('mobile'); btnPc.classList.add('active'); btnMo.classList.remove('active');
  }
}

function applyAdminModeToFrame() {
  try {
    if (previewEl.contentDocument && previewEl.contentDocument.body) {
      previewEl.contentDocument.body.classList.toggle('admin-preview', isAdminMode);
    }
  } catch (e) { /* srcdoc 문서라 보통 안 걸리지만 방어적으로 무시 */ }
}

function toggleAdminMode() {
  isAdminMode = !isAdminMode;
  document.getElementById('btn-admin').classList.toggle('on', isAdminMode);
  document.getElementById('adminStatus').textContent = isAdminMode ? 'ON' : 'OFF';
  applyAdminModeToFrame();
}

// srcdoc을 새로 채울 때마다(생성/수정 결과 갱신) 관리자 뷰 상태를 다시 적용한다
previewEl.addEventListener('load', applyAdminModeToFrame);

function addLog(who, text, extra, rejected) {
  const div = document.createElement('div');
  div.className = 'entry' + (rejected ? ' rejected' : '');
  let html = `<div class="who">${who}</div><div>${text}</div>`;
  if (extra) html += `<pre>${JSON.stringify(extra, null, 2)}</pre>`;
  div.innerHTML = html;
  logEl.appendChild(div);
  logEl.scrollTop = logEl.scrollHeight;
}

function setBusy(busy) {
  document.getElementById('send').disabled = busy;
  statusEl.textContent = busy ? '모델 호출 중...' : '';
}

function setBlocks(blocks) {
  blocks = blocks || [];
  blockKeyEl.innerHTML = blocks.map(b => `<option value="${b}">${b}</option>`).join('');
  blockRowEl.style.display = blocks.length ? '' : 'none';
}

function updateEditModeAvailability() {
  const patchOption = editModeEl.querySelector('option[value="patch"]');
  if (currentPlan === null) {
    patchOption.disabled = true;
    if (editModeEl.value === 'patch') editModeEl.value = 'html';
  } else {
    patchOption.disabled = false;
  }
}

async function loadTemplate() {
  setBusy(true);
  try {
    const resp = await fetch('/api/load_template', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({template_id: templateIdEl.value}),
    });
    const data = await resp.json();
    if (data.error) { addLog('오류', data.error, null, true); return; }
    currentPlan = null;
    currentHtml = data.html_raw;
    currentTheme = data.theme || '';
    sessionDir = data.session_dir;
    started = true;
    previewEl.srcdoc = data.html;
    setBlocks(data.blocks);
    updateEditModeAvailability();
    logEl.innerHTML = '';
    addLog('시스템', `템플릿 ${templateIdEl.value} 로드 완료(S 방식 — event.css 적용됨, theme="${currentTheme}"). ` +
      `"수정영역"에서 고칠 블록을 고르고 지시문을 입력하세요.`);
  } catch (e) {
    addLog('오류', String(e), null, true);
  } finally {
    setBusy(false);
  }
}

async function doGenerate(text, model) {
  const url = genModeEl.value === 'plan' ? '/api/generate' : '/api/generate_html';
  const resp = await fetch(url, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({prompt: text, model}),
  });
  const data = await resp.json();
  if (data.error) { addLog('오류', data.error, null, true); return; }
  currentPlan = data.plan || null;
  currentHtml = data.html_raw;
  currentTheme = '';  // J/S 생성 결과는 theme-* 클래스가 없다(합성 마크업이거나 무테마 S 생성)
  sessionDir = data.session_dir;
  started = true;
  previewEl.srcdoc = data.html;
  setBlocks(data.blocks);
  updateEditModeAvailability();
  addLog('모델', `생성 완료 (${genModeEl.value === 'plan' ? 'J' : 'S'})`);
}

async function doEditPatch(text, model) {
  if (currentPlan === null) {
    addLog('시스템', 'K는 plan이 있을 때만 가능합니다 — 수정 방식을 S로 바꾸세요.', null, true);
    return;
  }
  const resp = await fetch('/api/edit', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({plan: currentPlan, instruction: text, model, session_dir: sessionDir}),
  });
  const data = await resp.json();
  if (data.error) { addLog('오류', data.error, null, true); return; }
  currentPlan = data.plan;
  currentHtml = data.html_raw;
  previewEl.srcdoc = data.html;
  setBlocks(data.blocks);
  addLog(data.rejected ? '모델 (거부)' : '모델',
         data.rejected ? '이 요청을 거부했습니다.' : '수정 적용됨 (K)', data.patch, data.rejected);
}

async function doEditBlock(text, model) {
  if (!blockKeyEl.value) { addLog('시스템', '수정영역을 먼저 선택하세요.', null, true); return; }
  const resp = await fetch('/api/edit_block', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      html_raw: currentHtml, block_key: blockKeyEl.value,
      instruction: text, model, session_dir: sessionDir, theme: currentTheme,
    }),
  });
  const data = await resp.json();
  if (data.error) { addLog('오류', data.error, null, true); return; }
  const hadPlan = currentPlan !== null;
  currentPlan = null;
  currentHtml = data.html_raw;
  currentTheme = data.theme || currentTheme;
  previewEl.srcdoc = data.html;
  setBlocks(data.blocks);
  updateEditModeAvailability();
  if (hadPlan) addLog('시스템', 'S로 직접 수정했습니다 — plan과 어긋나서 이제부터 K는 쓸 수 없습니다.');
  addLog('모델', `[${blockKeyEl.value}] 영역 수정 결과 (S)`,
         {수정_전: data.block_before, 수정_후: data.block_after});
}

async function send() {
  const text = instructionEl.value.trim();
  if (!text) return;
  addLog('나', text);
  instructionEl.value = '';
  setBusy(true);
  try {
    const model = modelEl.value.trim();
    if (!started) {
      await doGenerate(text, model);
    } else if (editModeEl.value === 'patch') {
      await doEditPatch(text, model);
    } else {
      await doEditBlock(text, model);
    }
  } catch (e) {
    addLog('오류', String(e), null, true);
  } finally {
    setBusy(false);
  }
}

document.getElementById('send').addEventListener('click', send);
document.getElementById('loadTemplate').addEventListener('click', loadTemplate);
instructionEl.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) send();
});
document.getElementById('reset').addEventListener('click', () => {
  currentPlan = null; currentHtml = null; currentTheme = ''; sessionDir = null; started = false;
  previewEl.srcdoc = '';
  setBlocks([]);
  updateEditModeAvailability();
  logEl.innerHTML = '';
  addLog('시스템', '새로 시작 — 생성 방식을 고르고 입력하거나, 템플릿을 불러오세요.');
});

updateEditModeAvailability();
addLog('시스템', '생성 방식(J/S)을 고르고 페이지를 설명하거나, 템플릿을 불러와 시작하세요.');
</script>
</body>
</html>"""


def render_index():
    options = "".join(f'<option value="{m}">' for m in KNOWN_MODELS)
    template_options = "".join(
        f'<option value="{tid}">{label}</option>' for tid, label in TEMPLATE_LABELS.items())
    return (INDEX_HTML
            .replace("__DEFAULT_MODEL__", DEFAULT_MODEL)
            .replace("__MODEL_OPTIONS__", options)
            .replace("__TEMPLATE_OPTIONS__", template_options))


@app.route("/")
def index():
    return Response(render_index(), mimetype="text/html")


def _record_step(session_dir, plan_like, html_raw, instruction=None):
    if not session_dir or not os.path.isdir(session_dir):
        return
    existing = [f for f in os.listdir(session_dir) if f.endswith(".plan.json")]
    step_no = len(existing) + 1
    label = ("generate" if instruction is None else
             "edit_" + "".join(c if c.isalnum() else "_" for c in instruction[:20]))
    save_step(session_dir, step_no, label, plan_like, html_raw)


@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.get_json(force=True)
    model = (data.get("model") or DEFAULT_MODEL).strip()
    try:
        result = generate_page(data["prompt"], model)
    except Exception as e:
        return jsonify({"error": f"생성 실패: {e}"}), 200

    session_dir = new_session_dir("gui_j")
    _record_step(session_dir, result["plan"], result["html"])
    return jsonify({
        "plan": result["plan"],
        "html_raw": result["html"],
        "html": wrap_full_html(result["html"], title="generate"),
        "blocks": blocks_in_html(result["html"]),
        "session_dir": session_dir,
    })


@app.route("/api/generate_html", methods=["POST"])
def api_generate_html():
    data = request.get_json(force=True)
    model = (data.get("model") or DEFAULT_MODEL).strip()
    try:
        result = generate_page_html(data["prompt"], model)
    except Exception as e:
        return jsonify({"error": f"생성 실패: {e}"}), 200

    session_dir = new_session_dir("gui_s")
    _record_step(session_dir, {"html": result["html"]}, result["html"])
    return jsonify({
        "plan": None,
        "html_raw": result["html"],
        "html": wrap_with_css(result["html"], _EVENT_CSS, title="generate"),
        "blocks": blocks_in_html(result["html"]),
        "session_dir": session_dir,
    })


@app.route("/api/edit", methods=["POST"])
def api_edit():
    data = request.get_json(force=True)
    model = (data.get("model") or DEFAULT_MODEL).strip()
    if data.get("plan") is None:
        return jsonify({"error": "K(patch)는 plan이 있어야 합니다 — J로 생성한 뒤에만 쓸 수 있습니다."}), 200
    try:
        result = edit_page(data["plan"], data["instruction"], model)
    except Exception as e:
        return jsonify({"error": f"수정 실패: {e}"}), 200

    if not result["rejected"]:
        _record_step(data.get("session_dir"), result["plan"], result["html"], data["instruction"])

    return jsonify({
        "patch": result["patch"],
        "plan": result["plan"],
        "html_raw": result["html"],
        "html": wrap_full_html(result["html"], title="edit"),
        "blocks": blocks_in_html(result["html"]),
        "rejected": result["rejected"],
    })


@app.route("/api/edit_block", methods=["POST"])
def api_edit_block():
    data = request.get_json(force=True)
    model = (data.get("model") or DEFAULT_MODEL).strip()
    try:
        result = edit_block_direct(
            data["html_raw"], data["block_key"], data["instruction"], model)
    except Exception as e:
        return jsonify({"error": f"수정 실패: {e}"}), 200

    _record_step(data.get("session_dir"), {"html": result["html"]}, result["html"], data["instruction"])

    # theme(예: "theme-sports")는 <div class="ev-container"> 바깥의 <body>에
    # 있어서 블록 조각(html_raw) 안에는 안 들어있다 — 클라이언트가 로드/생성
    # 시점에 알아낸 theme을 매 edit_block 요청에 그대로 실어 보내고, 여기서
    # 다시 같은 값을 돌려줘서 미리보기를 감쌀 때 유지되게 한다.
    theme = data.get("theme", "")
    return jsonify({
        "html_raw": result["html"],
        "html": wrap_with_css(result["html"], _EVENT_CSS, title="edit", theme=theme),
        "blocks": blocks_in_html(result["html"]),
        "theme": theme,
        "block_before": result["block_before"],
        "block_after": result["block_after"],
    })


@app.route("/api/load_template", methods=["POST"])
def api_load_template():
    data = request.get_json(force=True)
    try:
        template_id = int(data["template_id"])
        tpl = load_template(template_id)
    except Exception as e:
        return jsonify({"error": f"템플릿 로드 실패: {e}"}), 200

    session_dir = new_session_dir(f"gui_tpl{template_id}")
    _record_step(session_dir, {"html": tpl["html"]}, tpl["html"])
    return jsonify({
        "html_raw": tpl["html"],
        "html": wrap_with_css(tpl["html"], _EVENT_CSS, title=tpl["label"], theme=tpl["theme"]),
        "blocks": tpl["blocks"],
        "theme": tpl["theme"],
        "session_dir": session_dir,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PLAYGROUND_PORT", "5050"))
    print(f"[playground] http://127.0.0.1:{port} 에서 실행 중", file=sys.stderr)
    app.run(host="127.0.0.1", port=port, debug=False)
