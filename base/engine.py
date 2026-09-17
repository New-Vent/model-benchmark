"""
engine.py — 공통 엔진 (아무도 개별로 건드리지 않음)
====================================================
Case 실행, 캘리브레이션, 환경 스냅샷, CSV 저장, 메인 루프를 담당한다.
새 군(cases_*.py)을 추가할 때 이 파일을 고칠 필요는 원칙적으로 없다
— Case의 mode/hook 필드로 대부분의 새로운 검증 방식을 표현할 수
있게 설계했다. 정말 새로운 실행 방식(예: C군의 누적 체인)이
필요하면 이 파일에 함수를 "추가"하되, 기존 함수는 건드리지 않는다.

바꿔도 되는 것: RUNNER, MODELS (run.py에서 지정), OLLAMA_HOST/base/.ollama_host (아래)
바꾸면 안 되는 것: BASE_OPTIONS, NUM_PREDICT, SEEDS, KEEP_ALIVE
                  (아래 상수들 — 팀 합의 없이 개인이 수정 금지)
"""

import csv
import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

import requests

def _resolve_ollama_host():
    """
    우선순위: OLLAMA_HOST 환경변수 > base/.ollama_host 파일 > localhost 기본값.

    환경변수는 셸을 새로 열 때마다 초기화돼서(특히 PowerShell에서
    cmd식 set을 잘못 쓰는 실수까지 겹치면) 원격 서버 사용자가 매번
    같은 문제를 반복해서 겪는다. .ollama_host 파일은 한 번 만들면
    터미널을 새로 열어도 계속 적용되고, .gitignore에 있어서 개인
    설정이 팀 공용 저장소로 새 나가지 않는다.
    """
    env_val = os.environ.get("OLLAMA_HOST")
    if env_val:
        return env_val.strip(), "환경변수 OLLAMA_HOST"

    local_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".ollama_host")
    if os.path.isfile(local_file):
        with open(local_file, encoding="utf-8") as f:
            file_val = f.read().strip()
        if file_val:
            return file_val, "base/.ollama_host 파일"

    return "http://localhost:11434", "기본값"


OLLAMA, OLLAMA_SOURCE = _resolve_ollama_host()

# ── 팀 전체 고정값 — 개인이 임의로 바꾸지 않는다 ─────────────────
BASE_OPTIONS = {
    "temperature": 0.2,
    "top_p": 0.9,
    "top_k": 40,
    "repeat_penalty": 1.1,
    "num_ctx": 8192,
}
KEEP_ALIVE = "30m"

NUM_PREDICT = {
    "html": 1536,
    "plan": 512,
    "patch": 256,
    "router": 128,
}

SEEDS = [42, 43, 44, 45, 46]

CALIB_MODEL = "exaone3.5:7.8b"
CALIB_PROMPT = "1부터 100까지 쉼표로 구분해 쓰세요. 다른 말은 쓰지 마세요."


# ══════════════════════════════════════════════════════════════
#  Case — 모든 cases_*.py가 이 타입의 리스트(CASES)를 만들어 낸다
# ══════════════════════════════════════════════════════════════

@dataclass
class Case:
    pid: str
    kind: str
    group: str                    # D | E | JS | N | S | J | K | C | R
    system: str
    prompt: str
    mode: str                     # "html" | "plan" | "patch" | "router" | "custom"
    keep: list = field(default_factory=list)
    forbid: list = field(default_factory=list)
    pair: str = ""
    current_plan: Optional[dict] = None
    allow_script: bool = False    # JS군만 True — script 태그 허용
    extra_check: Optional[Callable[[str, str], list]] = None
    # extra_check(raw, html) -> list[str]  추가 fail 코드.
    # 일반 check_html/check_plan/check_patch로 표현 안 되는 군별
    # 규칙(D군의 환각 검출, JS군의 스크립트 구조 검사 등)은 이
    # 훅으로 자기 파일(cases_*.py) 안에서만 정의한다.
    custom_run: Optional[Callable] = None
    # mode=="custom"일 때, run_one 대신 이 함수가 전체 실행을 담당한다.
    # (C군의 누적 체인처럼 Case 하나로 표현이 안 되는 경우에 씀)
    json_schema: Optional[dict] = None
    # mode가 plan/patch/router일 때 Ollama의 format 필드에 넣을 실제
    # JSON Schema. None이면 느슨한 format="json"(그냥 유효한 JSON이면
    # 통과)으로 폴백한다 — 이 경우 unknown_type/unknown_variant/
    # missing_필드 같은 실패가 훨씬 잦아진다(실측으로 확인됨). 가능하면
    # registry.build_plan_json_schema() / build_patch_json_schema()로
    # 만든 값을 반드시 넣을 것.
    num_predict: Optional[int] = None
    # 이 케이스만 NUM_PREDICT[mode] 기본값 대신 이 값을 쓴다. None이면
    # 기존과 동일(전역 NUM_PREDICT 사용) — v1·v2 케이스는 전부 그대로다.
    # v3에서 "truncated 실패가 캡 부족 때문"임을 실측으로 확인했는데
    # (docs/methodology.md 원칙상 전역 NUM_PREDICT 변경은 새 버전 사유),
    # 전역 상수를 건드리면 v1·v2를 재실행할 때도 값이 바뀌어버려
    # "예전 버전은 그 조건 그대로 재현 가능해야 한다"는 원칙과 충돌한다.
    # 케이스 단위 오버라이드로 이 충돌을 피한다(v3 README §5 참고).


# ══════════════════════════════════════════════════════════════
#  Ollama 호출
# ══════════════════════════════════════════════════════════════

def call(model, messages, mode="html", as_json=False, seed=None, timeout=900,
         max_network_retry=2, retry_backoff_sec=5, json_schema=None,
         num_predict_override=None):
    """
    max_network_retry: 네트워크 계층 실패(타임아웃/연결끊김/서버다운)일 때
    재시도할 횟수. run_one()의 max_retry(LLM 출력이 검증에 실패했을 때
    다시 프롬프트하는 것)와는 완전히 다른 개념이다 — 여긴 "요청 자체가
    도착·응답을 못 받은 경우"를 다룬다. 이게 없으면 무인으로 몇 시간
    돌리는 실행이 한 번의 네트워크 삐끗으로 전체가 죽어버린다.

    json_schema: 넘기면 format 필드에 이 스키마 객체를 그대로 넣는다
    (Ollama가 토큰 생성 단계에서 이 구조를 벗어난 출력을 문법적으로
    차단함). None인데 as_json=True면 느슨한 format="json"으로
    폴백한다 — "그냥 유효한 JSON이면 통과"라는 매우 약한 조건이라,
    unknown_type/unknown_variant류 실패가 훨씬 잦아진다는 게 실측으로
    확인됐다. 가능하면 항상 json_schema를 넘길 것.

    num_predict_override: 넘기면 NUM_PREDICT[mode] 대신 이 값을 쓴다.
    Case.num_predict를 통해 케이스 단위로만 캡을 올리기 위한 통로
    (전역 NUM_PREDICT를 바꾸면 v1·v2 재실행 조건까지 바뀌어버림).
    """
    options = dict(BASE_OPTIONS)
    options["num_predict"] = (num_predict_override if num_predict_override is not None
                               else NUM_PREDICT.get(mode, 512))
    if seed is not None:
        options["seed"] = seed
    body = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": options,
        "keep_alive": KEEP_ALIVE,
    }
    if json_schema is not None:
        body["format"] = json_schema
    elif as_json:
        body["format"] = "json"

    last_exc = None
    for attempt in range(max_network_retry + 1):
        try:
            started = time.time()
            r = requests.post(f"{OLLAMA}/api/chat", json=body, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            data["_wall_sec"] = round(time.time() - started, 2)
            return data
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.ChunkedEncodingError) as e:
            last_exc = e
            if attempt < max_network_retry:
                wait = retry_backoff_sec * (attempt + 1)
                print(f"    네트워크 오류({type(e).__name__}), {wait}초 후 재시도 "
                      f"({attempt + 1}/{max_network_retry})... {e}")
                time.sleep(wait)
            else:
                print(f"    네트워크 오류 재시도 소진 — {OLLAMA} 서버 상태를 확인하세요.")
    raise last_exc


def warmup(model):
    try:
        call(model, [{"role": "user", "content": "안녕"}])
    except Exception as e:
        print(f"  경고: {model} 워밍업 실패 — {e}")


def unload(model):
    """다음 모델 전에 반드시 호출 — 안 하면 VRAM에 두 모델이 겹쳐
    뒤에 도는 모델이 부당하게 느려진다."""
    try:
        requests.post(f"{OLLAMA}/api/chat",
                       json={"model": model, "messages": [], "keep_alive": 0},
                       timeout=30)
    except Exception as e:
        print(f"  경고: {model} 언로드 실패 — {e}")


def calibrate():
    """기기 계수 — 시작/종료 두 번 재서 드리프트(발열)를 확인한다."""
    warmup(CALIB_MODEL)
    er, pr = [], []
    for _ in range(3):
        res = call(CALIB_MODEL, [{"role": "user", "content": CALIB_PROMPT}], mode="html")
        ec, ed = res.get("eval_count", 0), res.get("eval_duration", 1)
        pc, pd = res.get("prompt_eval_count", 0), res.get("prompt_eval_duration", 1)
        er.append(ec / (ed / 1e9) if ed else 0)
        pr.append(pc / (pd / 1e9) if pd else 0)
    return {"eval_rate": round(sum(er) / 3, 1), "prompt_rate": round(sum(pr) / 3, 1)}


def _sh(cmd):
    """
    명령을 조용히 실행한다. 명령이 없거나(nvidia-smi 등) 실패해도
    빈 문자열만 반환하고, 그 과정에서 OS가 콘솔에 찍는 지저분한
    에러 메시지("...은(는) 내부 또는 외부 명령이 아닙니다" 등)는
    stderr를 DEVNULL로 돌려서 화면에 안 보이게 한다. 통합그래픽
    (Intel Iris Xe 등) 컴퓨터에서는 nvidia-smi가 항상 없으므로
    이 경로를 정상적으로, 자주 타게 된다 — 에러가 아니라 예상된
    분기다.
    """
    try:
        return subprocess.check_output(
            cmd, shell=True, text=True, timeout=5,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def snapshot_env(models, runner):
    env = {
        "runner": runner,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "os": platform.platform(),
        "cpu": platform.processor(),
        "gpu": _sh("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader")
               or _sh("system_profiler SPDisplaysDataType | grep Chipset")
               or "cpu-only 또는 감지 실패 (통합그래픽 가능성 — 수동 확인 필요)",
        "backend": "cuda" if _sh("nvidia-smi") else ("metal" if sys.platform == "darwin" else "cpu"),
        "ollama": _sh("ollama --version"),
        "python": platform.python_version(),
        "base_options": BASE_OPTIONS,
        "num_predict": NUM_PREDICT,
        "seeds": SEEDS,
        "keep_alive": KEEP_ALIVE,
        "models": {},
    }
    try:
        tags = requests.get(f"{OLLAMA}/api/tags", timeout=5).json()
        by_name = {m["name"]: m for m in tags.get("models", [])}
    except Exception:
        by_name = {}

    for m in models:
        try:
            show = requests.post(f"{OLLAMA}/api/show", json={"model": m}, timeout=5).json()
        except Exception:
            show = {}
        d = show.get("details", {})
        env["models"][m] = {
            "digest": by_name.get(m, {}).get("digest", "")[:16],
            "size_bytes": by_name.get(m, {}).get("size"),
            "parameters": d.get("parameter_size"),
            "quantization": d.get("quantization_level"),
            "family": d.get("family"),
        }
    return env


def save_env(env, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(env, f, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════════
#  단일 케이스 실행
# ══════════════════════════════════════════════════════════════

CSV_COLUMNS = [
    "runner", "model", "digest", "backend",
    "group", "prompt_id", "kind", "pair", "repeat_no", "seed", "attempt",
    "hard_ok", "all_ok", "fails", "soft_fails",
    "wall_sec", "load_ms", "prompt_ms", "eval_ms",
    "prompt_tokens", "eval_count", "ctx_used",
    "prompt_rate", "eval_rate",
    "out_len", "html_len", "baseline_len", "patch_ratio",
    "done_reason",
]


def _empty_row(**overrides):
    row = {c: "" for c in CSV_COLUMNS}
    row.update(overrides)
    return row


def run_one(model, case: Case, runner, digest, backend, repeat_no, seed, rows,
            out_dir, max_retry=3):
    """
    HTML/plan/patch/router 4가지 표준 모드를 처리한다. mode=="custom"인
    경우 case.custom_run(model, case, ...)에 전부 위임한다 — C군처럼
    Case 하나로 표현이 안 되는 실행 방식을 위한 탈출구다.
    """
    if case.mode == "custom":
        if case.custom_run is None:
            raise NotImplementedError(
                f"{case.pid}: mode=custom인데 custom_run이 없습니다. "
                f"해당 cases_*.py에서 구현하세요.")
        return case.custom_run(model, case, runner, digest, backend, repeat_no, seed,
                                rows, out_dir)

    from checks import check_html, check_plan, check_patch, extract

    messages = [
        {"role": "system", "content": case.system},
        {"role": "user", "content": case.prompt},
    ]
    first_hard_ok = None

    for attempt in range(1, max_retry + 1):
        try:
            res = call(model, messages, mode=case.mode,
                       as_json=(case.mode in ("plan", "patch", "router")), seed=seed,
                       json_schema=case.json_schema,
                       num_predict_override=case.num_predict)
        except Exception as e:
            rows.append(_empty_row(
                runner=runner, model=model, digest=digest, backend=backend,
                group=case.group, prompt_id=case.pid, kind=case.kind, pair=case.pair,
                repeat_no=repeat_no, seed=seed, attempt=attempt,
                hard_ok=0, all_ok=0, fails="request_error",
            ))
            return 0, 0

        raw = res["message"]["content"]
        rendered = None  # plan/patch 모드에서만 채워짐 — 실제 렌더링된 HTML

        if case.mode == "plan":
            fails, note, plan, rendered = check_plan(raw, case.keep, case.forbid)
            out_len, html_len = len(raw.strip()), len(rendered)
        elif case.mode == "patch":
            fails, note, merged, rendered = check_patch(raw, case.current_plan,
                                                          case.keep, case.forbid)
            out_len, html_len = len(raw.strip()), len(rendered)
        elif case.mode == "router":
            # R군 — 렌더링 없이 라우팅 정확도만 본다. 실제 판정은
            # cases_r.py의 extra_check가 전담한다(정답 op 비교).
            fails, note = [], ""
            out_len = html_len = len(raw.strip())
        else:  # html
            html = extract(raw)
            fails, note = check_html(raw, html, case.keep, case.forbid, True,
                                      allow_script=case.allow_script)
            out_len = html_len = len(html)

        if case.extra_check is not None:
            fails += case.extra_check(raw, raw if case.mode == "router" else
                                       (html if case.mode == "html" else raw))

        if res.get("done_reason") == "length":
            fails.append("truncated")

        from checks import SOFT_FAILS
        soft = [f for f in fails if f in SOFT_FAILS]
        hard = [f for f in fails if f not in SOFT_FAILS]
        hard_ok = int(not hard)
        if first_hard_ok is None:
            first_hard_ok = hard_ok

        pc, ec = res.get("prompt_eval_count", 0), res.get("eval_count", 0)
        pd, ed = res.get("prompt_eval_duration", 1), res.get("eval_duration", 1)

        rows.append(_empty_row(
            runner=runner, model=model, digest=digest, backend=backend,
            group=case.group, prompt_id=case.pid, kind=case.kind, pair=case.pair,
            repeat_no=repeat_no, seed=seed, attempt=attempt,
            hard_ok=hard_ok, all_ok=int(not fails),
            fails="|".join(hard), soft_fails="|".join(soft),
            wall_sec=res["_wall_sec"],
            load_ms=res.get("load_duration", 0) // 1_000_000,
            prompt_ms=pd // 1_000_000, eval_ms=ed // 1_000_000,
            prompt_tokens=pc, eval_count=ec, ctx_used=pc + ec,
            prompt_rate=round(pc / (pd / 1e9), 1) if pd else 0,
            eval_rate=round(ec / (ed / 1e9), 1) if ed else 0,
            out_len=out_len, html_len=html_len,
            done_reason=res.get("done_reason", ""),
        ))

        safe = model.replace(":", "_")
        base_name = f"{out_dir}/{safe}_{case.pid}_r{repeat_no}_s{seed}_try{attempt}"

        # 원본(raw) — LLM이 실제로 낸 텍스트 그대로. html 모드는 HTML,
        # plan/patch 모드는 JSON이 그대로 들어간다.
        with open(f"{base_name}.txt", "w", encoding="utf-8") as f:
            f.write(raw)

        # plan/patch 모드는 원본이 JSON이라 "눈으로 보이는 결과물"이
        # 따로 필요하다 — check_plan/check_patch가 이미 계산해둔
        # rendered(실제 HTML)를 별도 파일로 저장한다. 이게 없으면
        # J/K군 결과를 브라우저에서 확인할 방법이 없었다.
        if rendered:
            with open(f"{base_name}.rendered.html", "w", encoding="utf-8") as f:
                f.write(rendered)

        if hard_ok:
            return first_hard_ok, 1

        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user",
                          "content": f"방금 출력에 문제가 있습니다. {note} 다시 출력하세요."})

    return first_hard_ok, 0


# ══════════════════════════════════════════════════════════════
#  메인 루프
#
#  ★ 회차마다 전체 케이스를 한 바퀴 돈다 (군별로 몰아 돌리지 않음).
#  군별로 몰아 돌리면 뒤쪽 군이 항상 뜨거운 상태에서 측정되어,
#  "생성(S·J) 대 수정(K)" 같은 핵심 비교가 시간상 왜곡된다.
# ══════════════════════════════════════════════════════════════

def self_check_all(case_modules):
    """각 cases_*.py가 self_check() 함수를 정의해뒀다면 실행한다.
    없는 모듈은 건너뛴다 — 담당자가 아직 구현 전인 스텁 상태일 수 있음."""
    print("=" * 74)
    print("  self_check (군별)")
    print("=" * 74)
    for name, mod in case_modules.items():
        fn = getattr(mod, "self_check", None)
        if fn is None:
            print(f"  [{name}] self_check 없음 — 스텁 상태이거나 검증 불필요")
            continue
        fn()
        print(f"  [{name}] self_check 통과")
    print()


def collect_cases(case_modules, group_filter=None):
    """각 cases_*.py의 CASES를 한 리스트로 모은다.

    group_filter가 주어지면 그 군의 케이스만 남긴다 — 한 모듈이 두 군을
    담당하는 경우(cases_ns.py = N군 + S군)에 `run.py v1 N`처럼 한쪽만
    돌릴 수 있어야 하기 때문이다.
    """
    all_cases = []
    for name, mod in case_modules.items():
        cases = getattr(mod, "CASES", None) or []
        if group_filter is not None:
            cases = [c for c in cases if c.group in group_filter]
        if not cases:
            print(f"  [{name}] 실행할 케이스 없음 — 스텁 상태이거나 선택한 군에 해당 없음")
        all_cases += cases
    return all_cases


def main(models, runner, case_modules, version, version_dir, group_filter=None):
    """
    models: 이번 실행에서 돌릴 모델 리스트 (RUNNER별로 다를 수 있음)
    runner: 실행자 이름 (예: "장지원") — 결과 파일명에 들어감
    case_modules: {"cases_d": <module>, ...} 형태의 dict.
                  각 모듈은 CASES 리스트를 갖고 있어야 한다.
    version: "v1" / "v2" — 결과 파일명과 raw 폴더 이름에 들어간다
    version_dir: versions/<version> 의 절대경로. 결과가 전부 여기로 들어간다
    group_filter: 일부 군만 돌릴 때 그 군 이름 리스트. None이면 전부

    결과 저장 위치 (전부 version_dir 안):
        result_csv/results_<version>_<runner>_<타임스탬프>.csv
        result_json/env_<version>_<runner>_<타임스탬프>.json
        raw_<version>/                시도별 원문
    """
    print(f"  Ollama 서버: {OLLAMA}  ({OLLAMA_SOURCE})")
    try:
        tags_resp = requests.get(f"{OLLAMA}/api/tags", timeout=5)
        tags_resp.raise_for_status()
    except Exception as e:
        raise SystemExit(
            f"\n  ✗ Ollama 서버에 연결할 수 없습니다: {OLLAMA}\n"
            f"    ({type(e).__name__}: {e})\n\n"
            f"  확인할 것:\n"
            f"    1. 이 주소가 맞는지 — 원격 서버를 쓴다면 OLLAMA_HOST를 이 창에서\n"
            f"       설정했는지 확인 (새 창/새 탭을 열면 초기화됨):\n"
            f"         PowerShell: $env:OLLAMA_HOST = \"http://<주소>:11434\"\n"
            f"         cmd.exe   : set OLLAMA_HOST=http://<주소>:11434\n"
            f"         bash      : export OLLAMA_HOST=\"http://<주소>:11434\"\n"
            f"    2. 그 서버에서 Ollama가 실제로 떠 있는지 — "
            f"curl {OLLAMA}/api/tags 로 직접 확인\n"
            f"    3. 방화벽/포트(11434)가 막혀있지 않은지\n"
        )

    # 서버는 떠 있어도 모델이 안 받아져 있으면 워밍업/캘리브레이션 단계에서
    # /api/chat이 404를 낸다 — "주소가 틀렸다"와 똑같은 증상이라 원인을
    # 헷갈리기 쉬우므로 여기서 미리 구분해서 알려준다.
    pulled = {m.get("name") for m in tags_resp.json().get("models", [])}
    missing = [m for m in models if m not in pulled]
    if missing:
        pulled_list = "\n".join(f"      - {m}" for m in sorted(pulled)) or "      (없음)"
        raise SystemExit(
            f"\n  ✗ 이 서버({OLLAMA})에 없는 모델이 있습니다: {missing}\n"
            f"    이 서버에 실제로 받아진 모델:\n{pulled_list}\n\n"
            f"    ollama pull {missing[0]} 로 받거나, run.py의 MODELS 목록을 "
            f"이 서버에 있는 모델로 맞추세요.\n"
            f"    (OLLAMA_HOST가 의도한 서버를 가리키는지도 다시 확인할 것 — "
            f"엉뚱한 서버에 연결됐을 때도 이 증상이 납니다.)\n"
        )

    self_check_all(case_modules)

    all_cases = collect_cases(case_modules, group_filter)
    if not all_cases:
        raise SystemExit("실행할 케이스가 하나도 없습니다 — 군 선택을 확인하세요.")

    csv_dir = os.path.join(version_dir, "result_csv")
    json_dir = os.path.join(version_dir, "result_json")
    out_dir = os.path.join(version_dir, f"raw_{version}")
    for d in (csv_dir, json_dir, out_dir):
        os.makedirs(d, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    env = snapshot_env(models, runner)
    env["version"] = version
    env["groups"] = sorted({c.group for c in all_cases})
    env["partial_run"] = group_filter is not None
    env["calibration_start"] = calibrate()

    rows = []
    for model in models:
        digest = env["models"].get(model, {}).get("digest", "")
        backend = env["backend"]
        print(f"\n{'=' * 74}\n  {model}  (digest={digest})\n{'=' * 74}")
        warmup(model)

        # ★ 핵심: 바깥 루프가 회차(seed), 안쪽 루프가 케이스.
        for repeat_no, seed in enumerate(SEEDS, 1):
            print(f"\n  -- 회차 {repeat_no}/{len(SEEDS)} (seed={seed}) --")
            for case in all_cases:
                print(f"    [{case.group}] {case.pid}")
                run_one(model, case, runner, digest, backend, repeat_no, seed,
                        rows, out_dir)

        unload(model)  # ★ 다음 모델 전에 반드시

    env["calibration_end"] = calibrate()
    start_rate = env["calibration_start"]["eval_rate"]
    end_rate = env["calibration_end"]["eval_rate"]
    env["drift"] = round(end_rate / start_rate, 3) if start_rate else None

    results_path = os.path.join(csv_dir, f"results_{version}_{runner}_{stamp}.csv")
    env_path = os.path.join(json_dir, f"env_{version}_{runner}_{stamp}.json")

    with open(results_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    save_env(env, env_path)

    print("\n" + "=" * 74)
    drift = env["drift"]
    if drift is None:
        drift_msg = "계산 불가"
    elif drift >= 0.95:
        drift_msg = f"{drift} — 정상, 시간 지표 그대로 사용 가능"
    elif drift >= 0.85:
        drift_msg = f"{drift} — 주의, 보고서에 드리프트 명시할 것"
    else:
        drift_msg = f"{drift} — 이 실행의 시간 지표는 신뢰하지 말 것 (토큰·통과율만 사용)"
    print(f"  드리프트: {drift_msg}")
    print(f"  {results_path}")
    print(f"  {env_path}")
    print(f"  {out_dir}/ 에 시도별 원본 저장됨")
