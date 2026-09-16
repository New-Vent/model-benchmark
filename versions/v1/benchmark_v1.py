"""
benchmark_v1.py — LLM 이벤트 페이지 생성 벤치마크
===================================================
실험계획 문서의 D · E · JS · N · S · C · R 군을 구현한다.
J(조합 계획) · K(패치) 군은 이번 회차에서 제외 — 추후 확장.

실행
    pip install requests beautifulsoup4
    set RUNNER=지원            (Windows)   /   export RUNNER=지원   (mac·linux)
    python benchmark_v1.py

산출물
    results_v1_<RUNNER>_<날짜>.csv     호출마다 한 행
    env_v1_<RUNNER>_<날짜>.json        환경 · 설정 · 보정 · 드리프트
    raw_v1/                            시도별 원문 (브라우저로 열어볼 것)

★ 이 파일을 고치지 마세요.
   바꿔도 되는 것   : RUNNER 환경변수뿐입니다
   바꾸면 안 되는 것 : MODELS · BASE_OPTIONS · NUM_PREDICT · SEEDS
                     프롬프트 · 케이스 · 반복 횟수

   전원이 네 모델을 모두 돌립니다. 소요 시간은 기기·재시도에 따라 달라집니다.
   v1.1 : E 요청/보존 검사, C 실패 시 중단, notices 보존, details 관계 검사.
   v1.2 : 모델이 깨진 HTML(잘못된 주석 등)을 출력해 BeautifulSoup가
         파싱을 거부(ParserRejectedMarkup 등)하면 전체가 죽던 문제를 고침.
         safe_soup()이 파싱 실패를 잡아 "빈 문서"로 취급 → 정상적으로
         no_section 등 실패 케이스로 기록되고 실행은 계속됨.
   v1.3 : Windows에서 백신 실시간 감시·인덱서 등이 결과 파일을 순간적으로
         잠가 os.replace가 PermissionError(WinError 5/32)로 죽던 문제를 고침.
         _write_with_retry()가 짧은 backoff로 재시도하고, 그래도 계속
         잠겨 있으면(예: 결과 CSV를 엑셀로 열어둔 경우) 그 저장만 건너뛰고
         계속 진행한다 — 메모리의 rows/문서는 유지되어 다음 저장 때 반영됨.
         실행 중에는 results_v1_*.csv 를 엑셀 등으로 열어두지 마세요.
   검증만 실행: python benchmark_v1.py --self-check
   
   
   v1.1, v1.2, v1.3를 통합하여 v1으로 지정한다. 
   JS는 구조 검사이며 실제 동작·보안 검증이 아닙니다.
   팀원 전원이 같은 v1 파일을 사용하세요 (env의 script_sha256으로 확인).
"""

import hashlib
import csv
import json
import os
import platform
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime

import requests
from bs4 import BeautifulSoup, NavigableString, Comment


def safe_soup(markup):
    """BeautifulSoup 파싱을 안전하게 감싼다.

    모델이 <![--- ... 처럼 깨진 주석/마크업을 출력하면 bs4가
    ParserRejectedMarkup(또는 그 내부 AssertionError 등)을 던져
    프로그램 전체가 죽는다. 파싱 실패는 "모델이 못 만든 것"과
    같은 의미이므로, 빈 문서로 취급해 검증기가 no_section 등
    정상적인 실패로 기록하게 한다.
    """
    try:
        return BeautifulSoup(markup, "html.parser")
    except Exception:
        return BeautifulSoup("", "html.parser")


# ══════════════════════════════════════════════════════════════════════
#  설정 — 전원 동일
# ══════════════════════════════════════════════════════════════════════

OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")
RUNNER = os.environ.get("RUNNER", "unknown")

# ── 전원이 네 모델을 모두 돌립니다. 이 목록은 바꾸지 마세요 ──────────
#
#  같은 모델을 여러 기기에서 돌려야
#    · 반복이 3배로 늘어 (5회 → 15회) 우연과 실력이 갈리고
#    · 모델마다 "기기 간 재현성" 이 나옵니다
#  모델 비교(시간·토큰)는 각자 기기 안에서 끝내고,
#  기기 간에는 통과율·토큰만 합칩니다.
#
#  모델 추가는 새 버전 사유가 아닙니다 — 프롬프트·채점·파라미터·케이스가
#  그대로면 기존 모델의 행은 유효하고, 새 CSV를 같은 폴더에 넣으면 됩니다.
#  이미 돌린 모델만 주석 처리하고 새 것만 켜서 돌리세요.
#  목록 자체는 v1이 다루는 모델 전부를 남겨둡니다.
MODELS = [
    # "exaone3.5:7.8b",   # 1차 완료 (도하·윤기·주호·지원)
    # "qwen2.5:7b",       # 1차 완료 — 생성 모델로 선정됨
    # "gemma3:4b",        # 1차 완료 — 저사양 대안
    # "qwen3:8b",         # 1차 완료 — 출력 잘림 14%로 탈락. 재실행 불필요
    "qwen2.5-coder:7b",
    "llama3.2:3b",
]

BASE_OPTIONS = {
    "temperature":    0.2,
    "top_p":          0.9,
    "top_k":          40,
    "repeat_penalty": 1.1,
    "num_ctx":        8192,
}

NUM_PREDICT = {
    "html":   1536,
    "router":  256,
}

SEEDS        = [42, 43, 44, 45, 46]     # 회차별로 바꾼다
ROUTER_SEEDS = [42, 43, 44]             # 라우터는 3회
KEEP_ALIVE   = "30m"
MAX_RETRY    = 3
TIMEOUT      = 900

CALIB_MODEL  = "exaone3.5:7.8b"
CALIB_PROMPT = "1부터 100까지 쉼표로 구분해 쓰세요. 다른 말은 쓰지 마세요."

OUT_DIR = "raw_v1"
STAMP   = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
OUT_DIR = os.path.join(OUT_DIR, STAMP)


# ══════════════════════════════════════════════════════════════════════
#  블록 레지스트리 — 프롬프트 · 검증기가 전부 여기서 나온다
# ══════════════════════════════════════════════════════════════════════

LLM, SERVER, MIXED = "llm", "server", "mixed"


@dataclass(frozen=True)
class Block:
    key: str
    required: bool
    source: str
    desc: str
    shape: str = ""          # 프롬프트에 들어가는 형태 지시
    must: str = ""           # 검증기가 찾는 CSS 선택자  (shape 와 짝)
    min_items: int = 0


BLOCKS = [
    Block("hero", True, LLM,
          "이벤트 제목과 한 줄 소개",
          shape="제목은 <h1>, 소개는 <p> 로 감싼다",
          must="h1"),

    Block("benefits", True, LLM,
          "혜택 2~4개. 각 항목은 한 문장",
          shape="<ul> 안에 <li> 로 항목을 나열한다. 2개 이상",
          must="ul li", min_items=2),

    Block("steps", False, LLM,
          "참여 방법 2~4단계",
          shape="<ol> 안에 <li> 로 순서대로 나열한다",
          must="ol li", min_items=2),

    Block("notices", True, SERVER,
          "유의사항 — 승인된 문구만 서버가 삽입"),

    Block("cta", True, MIXED,
          "참여 버튼. 문구만 생성, 링크는 폼 값",
          shape='<a href="#" class="btn"> 안에 버튼 문구를 넣는다',
          must="a"),
]

BY_KEY        = {b.key: b for b in BLOCKS}
LLM_BLOCKS    = [b for b in BLOCKS if b.source != SERVER]
SERVER_BLOCKS = [b for b in BLOCKS if b.source == SERVER]
REQUIRED_KEYS = tuple(b.key for b in LLM_BLOCKS if b.required)     # hero, benefits, cta
FORBID_KEYS   = tuple(b.key for b in SERVER_BLOCKS)                # notices


# ══════════════════════════════════════════════════════════════════════
#  프롬프트
# ══════════════════════════════════════════════════════════════════════

def build_system(with_shape: bool, with_omit_rule: bool = True) -> str:
    """with_shape=False 가 N군(대조).  with_omit_rule=False 가 D4."""
    lines = [
        "너는 통신사 이벤트 페이지를 만드는 도우미다.",
        "",
        "출력 규칙:",
        '- 각 영역은 <section data-block="이름"> ... </section> 으로 감싼다.',
        "- <html>, <head>, <body> 태그를 쓰지 마라.",
        "- 코드블록으로 감싸지 마라.",
        "- 설명, 인사말, 마무리 멘트를 붙이지 마라.",
        "",
        "만들 영역:",
    ]
    for b in LLM_BLOCKS:
        tail = "" if b.required else "  (선택)"
        line = f'- data-block="{b.key}" : {b.desc}{tail}'
        if with_shape and b.shape:
            line += f"\n    형태: {b.shape}"
        lines.append(line)

    if SERVER_BLOCKS:
        lines += ["", "만들면 안 되는 영역:"]
        for b in SERVER_BLOCKS:
            lines.append(f'- data-block="{b.key}" 는 절대 만들지 마라. {b.desc}')

    if with_shape:
        lines += [
            "",
            "태그를 반드시 쓴다. 맨 텍스트만 두지 마라.",
            "예:",
            '<section data-block="hero">',
            "  <h1>여름 데이터 대방출</h1>",
            "  <p>이번 여름 데이터 걱정 없이</p>",
            "</section>",
            '<section data-block="cta">',
            '  <a href="#" class="btn">참여하기</a>',
            "</section>",
        ]

    lines += [
        "",
        "금지:",
        "- 날짜를 임의로 만들지 마라. 기간은 주어진 값만 쓴다.",
        "- 주어지지 않은 혜택이나 수치를 만들어내지 마라.",
    ]
    if with_omit_rule:
        lines.append("- 대괄호 자리표시자를 절대 남기지 마라. 값을 모르면 그 문장을 아예 빼라.")
    lines += [
        "- 실존하는 방송 프로그램, 브랜드, 연예인 이름을 쓰지 마라.",
        "- 이모지를 쓰지 마라.",
    ]
    return "\n".join(lines)


def build_edit_system(key: str) -> str:
    """블록 하나만 고칠 때.  그 블록 외에는 출력 자체를 막는다."""
    b = BY_KEY[key]
    lines = [
        "너는 이벤트 페이지의 영역 하나를 수정하는 도우미다.",
        "",
        f'<section data-block="{key}"> 영역만 수정해서 그 영역만 출력한다.',
        f"이 영역의 역할: {b.desc}",
    ]
    if b.shape:
        lines.append(f"형태: {b.shape}")
    lines += [
        "",
        "출력 규칙:",
        f'- <section data-block="{key}"> 로 시작해서 </section> 으로 끝난다.',
        "- 다른 영역을 새로 만들지 마라.",
        "- 코드블록으로 감싸지 마라.",
        "- 설명을 붙이지 마라.",
        "",
        "금지:",
        "- 요청받은 것만 바꿔라. href, class 같은 기존 속성은 그대로 둔다.",
        '- href="#" 는 그대로 둬라. 실제 주소를 만들어 넣지 마라.',
        "- 날짜를 임의로 만들지 마라.",
        "- 대괄호 자리표시자를 남기지 마라.",
        "- 이모지를 쓰지 마라.",
    ]
    return "\n".join(lines)


ROUTER_SYSTEM = "\n".join([
    "너는 사용자 요청을 분류하는 라우터다. JSON 하나만 출력한다.",
    "",
    "영역 이름: " + ", ".join(b.key for b in BLOCKS),
    "",
    "출력 형식:",
    '{"op":"<동작>","target":"<영역 이름 또는 null>"}',
    "",
    "동작:",
    '- "EDIT"         특정 영역의 내용을 고친다',
    '- "ADD"          없는 영역을 새로 넣는다',
    '- "DELETE"       영역을 통째로 지운다',
    '- "MOVE"         영역의 순서를 바꾼다',
    '- "STYLE"        색·크기·굵기 등 겉모양만 바꾼다',
    '- "REWRITE_ALL"  페이지 전체에 걸친 요청이다',
    '- "GENERATE"     페이지를 처음부터 만든다',
    '- "ASK"          어느 영역인지 특정할 수 없다. 되물어야 한다',
    "",
    "REWRITE_ALL 과 GENERATE 는 target 을 null 로 둔다.",
    "JSON 외에는 아무것도 출력하지 마라.",
])

SYSTEM_PLAIN   = build_system(with_shape=False)                        # N군
SYSTEM_SHAPE   = build_system(with_shape=True)                         # S·D·E·JS·C군
SYSTEM_NO_OMIT = build_system(with_shape=True, with_omit_rule=False)   # D4


# 수정은 생성과 달리 서버 소유의 기존 notices도 그대로 보존한다.
SYSTEM_WHOLE_EDIT = """너는 기존 이벤트 HTML을 수정한다.
사용자가 요청한 변경만 수행하고 나머지 텍스트, 태그, 속성, 영역 순서를 유지한다.
기존 notices는 서버가 이미 제공한 내용이므로 삭제하거나 수정하지 않는다.
입력의 section 조각 전체만 출력한다. 설명, 코드펜스, html/head/body는 출력하지 않는다.
새로운 날짜, 혜택, 링크를 만들어내지 않는다."""


# ══════════════════════════════════════════════════════════════════════
#  프롬프트 본문
# ══════════════════════════════════════════════════════════════════════

P1 = ("2026년 8월 1일부터 8월 31일까지 신규 가입자에게 데이터 쿠폰 3GB를 주는 "
      "이벤트 페이지를 만들어줘.")
P2 = "가을 느낌 나는 멤버십 이벤트 페이지 하나 만들어줘."
P8 = ("10만원 상품권을 추첨 증정하는 이벤트 페이지를 만들어줘. "
      "혜택 3개, 참여방법 3단계를 포함해줘.")
P9 = ("여름 시즌에 맞춰 시원한 느낌으로 만들어줘. 20대 타겟이고, "
      "데이터 혜택 위주로 가되 혜택은 3개만. 참여 방법은 2단계로 간결하게. "
      "기간은 2026년 8월 1일 ~ 8월 31일.")

D1_PROMPT = "가을 멤버십 이벤트 페이지 만들어줘."
D3_PROMPT = "신규 가입 고객 대상 이벤트 페이지를 만들어줘."

# JS 케이스 전용 — 스크립트를 어디에 둘지 알려준다.
# 이게 없으면 모델이 <html><head><script> 를 만들고, 그건 지시 누락이지 모델 한계가 아니다.
JS_RULE = ("\n\n동작을 구현하는 <script> 는 마지막 <section> 안에 넣어라. "
           "<html>, <head>, <body> 를 만들지 마라. 나머지 영역은 그대로 유지해라.")

GIVEN_DATES_P1 = ((2026, 8, 1), (None, 8, 1), (2026, 8, 31), (None, 8, 31))


# ── 고정 입력 문서 ────────────────────────────────────────────────────

SHORT_DOC = """<section data-block="hero">
  <h1>여름 데이터 대방출</h1>
  <p>이번 여름 데이터 걱정 없이 마음껏 즐기세요</p>
</section>
<section data-block="benefits">
  <h2>혜택</h2>
  <ul><li>데이터 3GB 즉시 지급</li><li>월 요금 30% 할인</li></ul>
</section>
<section data-block="cta">
  <a href="#" class="btn">가입하기</a>
</section>"""

LONG_DOC = """<section data-block="hero">
  <h1>여름 데이터 대방출 페스타</h1>
  <p>이번 여름, 데이터 걱정 없이 마음껏 즐기세요</p>
  <p class="period">2026년 8월 1일 ~ 8월 31일</p>
</section>
<section data-block="benefits">
  <h2>이런 혜택을 드립니다</h2>
  <ul>
    <li><strong>데이터 3GB 즉시 지급</strong> — 가입 완료 즉시 자동 충전</li>
    <li><strong>월 요금 30% 할인</strong> — 개통 익월부터 6개월간 적용</li>
    <li><strong>제휴 카페 음료 쿠폰</strong> — 매월 1장씩 총 3장 제공</li>
    <li><strong>영화 예매권</strong> — 추첨을 통해 100명에게 증정</li>
  </ul>
</section>
<section data-block="steps">
  <h2>참여 방법</h2>
  <ol>
    <li>이벤트 페이지에서 요금제 선택</li>
    <li>온라인으로 가입 신청서 작성</li>
    <li>개통 완료 후 혜택 자동 적용</li>
  </ol>
</section>
<section data-block="notices">
  <h2>유의사항</h2>
  <ul>
    <li>본 이벤트는 신규 가입 및 번호이동 고객을 대상으로 합니다.</li>
    <li>기존 고객의 요금제 변경은 대상에서 제외됩니다.</li>
    <li>데이터 쿠폰은 지급일로부터 30일간 유효합니다.</li>
    <li>할인 혜택은 다른 프로모션과 중복 적용되지 않습니다.</li>
    <li>이벤트 내용은 사업자 사정에 따라 변경될 수 있습니다.</li>
  </ul>
</section>
<section data-block="cta">
  <a href="#" class="btn">가입하기</a>
</section>"""


def block_of(html: str, key: str) -> str:
    el = safe_soup(html).select_one(f'[data-block="{key}"]')
    return str(el) if el else ""


def replace_block(doc: str, key: str, new_html: str) -> str:
    """수정된 블록을 문서에 되돌려 끼운다. 없으면 맨 뒤에 붙인다."""
    soup = safe_soup(doc)
    old = soup.select_one(f'[data-block="{key}"]')
    frag = safe_soup(new_html)
    new = frag.select_one(f'[data-block="{key}"]')
    if new is None:
        return doc
    if old is None:
        soup.append(new)
    else:
        old.replace_with(new)
    return str(soup)


# ══════════════════════════════════════════════════════════════════════
#  검증
# ══════════════════════════════════════════════════════════════════════

FENCE       = re.compile(r"```")
PLACEHOLDER = re.compile(r"\[[가-힣A-Za-z0-9 _\-]{1,15}\]")
DATE_RE     = re.compile(r"\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일"
                         r"|\d{1,2}\s*월\s*\d{1,2}\s*일"
                         r"|\d{4}[-./]\d{1,2}[-./]\d{1,2}")
NUM_UNIT_RE = re.compile(r"\d+\s*(GB|MB|원|명|%|개월|회|배|장)")
JS_TODO     = re.compile(r"//\s*(TODO|여기에|구현|작성)|\.\.\.")

BAD_TAGS  = ["iframe", "object", "embed"]
FULL_DOC  = ["html", "head", "body"]
SOFT_FAILS = {"code_fence", "extra_text"}


def extract(raw: str) -> str:
    text = FENCE.sub("", raw)
    s, e = text.find("<"), text.rfind(">")
    return text[s:e + 1].strip() if s != -1 and e != -1 else ""


def norm_date(s: str):
    nums = [int(x) for x in re.findall(r"\d+", s)]
    if len(nums) == 3:
        return tuple(nums)
    if len(nums) == 2:
        return (None, nums[0], nums[1])
    return None


def check_html(raw, html, keep, forbid, strict, allow_script=False):
    """구조 검증.  (fails, note) 를 돌려준다."""
    fails, notes = [], []

    if not html:
        return ["no_html"], "HTML을 찾을 수 없습니다. <section> 태그로 시작하는 HTML만 출력하세요."

    if len(raw.strip()) - len(html) > 40:
        fails.append("extra_text")
        notes.append("HTML 앞뒤에 설명이 붙어 있습니다. HTML만 출력하세요.")
    if FENCE.search(raw):
        fails.append("code_fence")
        notes.append("코드블록으로 감쌌습니다. 감싸지 말고 HTML만 출력하세요.")

    soup = safe_soup(html)

    if not soup.find_all("section"):
        fails.append("no_section")
        notes.append("<section> 태그가 없습니다.")

    for t in BAD_TAGS:
        if soup.find(t):
            fails.append(f"bad_tag_{t}")
            notes.append(f"<{t}> 태그를 제거하세요.")
    if not allow_script and soup.find("script"):
        fails.append("bad_tag_script")
        notes.append("<script> 태그를 제거하세요.")

    for t in FULL_DOC:
        if soup.find(t):
            fails.append(f"full_doc_{t}")
            notes.append(f"<{t}> 태그가 있습니다. 조각만 출력하세요.")

    found = PLACEHOLDER.findall(html)
    if found:
        fails.append("placeholder")
        notes.append(f"자리표시자가 남아 있습니다: {', '.join(found[:3])}. 해당 문장을 빼세요.")

    for sec in soup.find_all("section"):
        if not sec.get("data-block"):
            fails.append("no_data_block")
            notes.append('모든 <section> 에 data-block="이름" 속성이 있어야 합니다.')
            break

    for k in keep:
        el = soup.select_one(f'[data-block="{k}"]')
        if el is None:
            fails.append(f"lost_{k}")
            notes.append(f"{k} 영역이 없습니다. 유지해야 합니다.")
            continue
        if not strict:
            continue
        b = BY_KEY[k]
        if b.must and not el.select_one(b.must):
            fails.append(f"empty_{k}")
            notes.append(f"{k} 안에 {b.shape} — 맨 텍스트만 두면 안 됩니다.")
        elif b.min_items:
            n = len(el.select("li"))
            if n < b.min_items:
                fails.append(f"few_{k}")
                notes.append(f"{k} 항목이 {n}개입니다. {b.min_items}개 이상 필요합니다.")

    for k in forbid:
        if soup.select_one(f'[data-block="{k}"]'):
            b = BY_KEY.get(k)
            if b and b.source == SERVER:
                fails.append(f"wrote_{k}")
                notes.append(f"{k} 영역은 만들면 안 됩니다. 서버가 채웁니다.")
            else:
                fails.append(f"extra_{k}")
                notes.append(f"{k} 영역은 만들지 마세요. 요청한 영역만 출력하세요.")

    return fails, " ".join(notes)


def check_extra(case, html, raw):
    """케이스별 추가 검사 — D군 · P9 개수 · JS군."""
    fails, notes = [], []
    soup = safe_soup(html) if html else None

    if "no_date" in case.checks and DATE_RE.search(html):
        fails.append("hallucinated_date")
        notes.append("주어지지 않은 날짜를 만들어냈습니다. 날짜를 쓰지 마세요.")

    if "given_dates" in case.checks:
        for m in DATE_RE.findall(html):
            if norm_date(m) not in case.given_dates:
                fails.append("wrong_date")
                notes.append(f"주어진 기간 외의 날짜가 있습니다: {m}")
                break

    if "no_numbers" in case.checks and NUM_UNIT_RE.search(html):
        fails.append("invented_benefit")
        notes.append("주어지지 않은 수치를 만들어냈습니다.")

    if case.exact and soup:
        for key, want in case.exact.items():
            el = soup.select_one(f'[data-block="{key}"]')
            n = len(el.select("li")) if el else 0
            if n != want:
                fails.append(f"exact_{key}_{want}")
                notes.append(f"{key} 항목이 {n}개입니다. 정확히 {want}개여야 합니다.")

    if "js_or_details" in case.checks and soup and soup.find("details"):
        benefits = soup.select_one('[data-block="benefits"]')
        items = benefits.select("ul li") if benefits else []
        valid = False
        if benefits and items:
            for detail in soup.find_all("details"):
                summary = detail.find("summary", recursive=False)
                if (summary and summary.get_text(strip=True)
                        and all(detail in item.parents and summary not in item.parents for item in items)):
                    valid = True
                    break
        if valid:
            return fails, " ".join(notes)
        fails.append("details_wrong_target")
        notes.append("혜택 목록 전체를 details 안에 넣고 직계 summary에 제목을 쓰세요.")
        return fails, " ".join(notes)

    if "js" in case.checks or "js_or_details" in case.checks:
        scripts = soup.find_all("script") if soup else []
        code = "\n".join(s.get_text() for s in scripts)
        if not scripts:
            fails.append("js_missing")
            notes.append("동작을 구현하는 <script> 가 없습니다. "
                         "<script> 를 마지막 <section> 안에 넣으세요.")
        elif not code.strip():
            fails.append("js_empty")
            notes.append("<script> 안이 비어 있습니다.")
        else:
            if not re.search(r"addEventListener|function\s|=>|const |let |var ", code):
                fails.append("js_no_code")
                notes.append("실제 동작 코드가 없습니다.")
            if JS_TODO.search(code):
                fails.append("js_todo")
                notes.append("미완성 표시가 남아 있습니다. 완성된 코드를 쓰세요.")
            if code.count("{") != code.count("}") or code.count("(") != code.count(")"):
                fails.append("js_unbalanced")
                notes.append("괄호 짝이 맞지 않습니다.")

    return fails, " ".join(notes)


# ══════════════════════════════════════════════════════════════════════
#  케이스
# ══════════════════════════════════════════════════════════════════════

@dataclass
class Case:
    pid: str
    group: str
    kind: str
    system: str
    prompt: str
    keep: tuple = REQUIRED_KEYS
    forbid: tuple = FORBID_KEYS
    strict: bool = True
    checks: tuple = ()
    given_dates: tuple = ()
    exact: dict = field(default_factory=dict)
    allow_script: bool = False
    pair: str = ""
    baseline: str = ""
    target: str = ""
    edit_rule: str = ""


ALL_KEYS = tuple(b.key for b in BLOCKS)
LONG_KEEP = ("hero", "benefits", "steps", "notices", "cta")


CASES = [
    # ── D군 · 환각 방어 ──────────────────────────────────────────────
    Case("D1", "D", "기간미제공_날짜생성여부", SYSTEM_SHAPE, D1_PROMPT,
         checks=("no_date",)),

    Case("D2", "D", "기간제공_날짜준수", SYSTEM_SHAPE, P1,
         checks=("given_dates",), given_dates=GIVEN_DATES_P1),

    Case("D3", "D", "혜택미제공_수치창작여부", SYSTEM_SHAPE, D3_PROMPT,
         checks=("no_numbers",)),

    Case("D4", "D", "자리표시자_규칙없음", SYSTEM_NO_OMIT, P2),

    Case("D5", "D", "자리표시자_규칙있음", SYSTEM_SHAPE, P2, pair="D4"),

    # ── E군 · 왕복 단위 ──────────────────────────────────────────────
    Case("E1", "E", "전체재생성_짧은문서", SYSTEM_WHOLE_EDIT,
         "다음 HTML에서 버튼 문구만 '지금 신청하기'로 바꿔줘. "
         f"나머지는 하나도 바꾸지 말고 그대로 출력해.\n\n{SHORT_DOC}",
         keep=("hero", "benefits", "cta")),

    Case("E2", "E", "블록왕복_짧은문서", build_edit_system("cta"),
         "이 영역의 버튼 문구만 '지금 신청하기'로 바꿔줘.\n\n"
         + block_of(SHORT_DOC, "cta"),
         keep=("cta",), forbid=("hero", "benefits", "steps", "notices"), pair="E1"),

    Case("E4", "E", "전체재생성_긴문서", SYSTEM_WHOLE_EDIT,
         "다음 HTML에서 버튼 문구만 '지금 신청하기'로 바꿔줘. "
         f"나머지는 하나도 바꾸지 말고 그대로 출력해.\n\n{LONG_DOC}",
         keep=LONG_KEEP, forbid=()),

    Case("E5", "E", "블록왕복_긴문서", build_edit_system("cta"),
         "이 영역의 버튼 문구만 '지금 신청하기'로 바꿔줘.\n\n"
         + block_of(LONG_DOC, "cta"),
         keep=("cta",), forbid=("hero", "benefits", "steps", "notices"), pair="E4"),

    # ── JS군 · 인터랙션 생성 ─────────────────────────────────────────
    # 스크립트를 어디에 넣을지 알려주지 않으면 모델이 <html><head> 를 만듭니다.
    # 그건 모델의 한계가 아니라 지시 누락이므로 JS_RULE 로 명시합니다.
    Case("JS1", "JS", "카운트다운", SYSTEM_SHAPE,
         "다음 HTML에 이벤트 종료까지 남은 시간을 보여주는 카운트다운을 넣어줘. "
         f"종료일은 2026년 8월 31일이야.{JS_RULE}\n\n{SHORT_DOC}",
         keep=("hero", "benefits", "cta"), checks=("js",), allow_script=True),

    # 접기/펼치기는 <details><summary> 로도 됩니다. 둘 다 정답으로 봅니다.
    Case("JS2", "JS", "접기펼치기", SYSTEM_SHAPE,
         f"다음 HTML에서 혜택 목록을 접었다 펼 수 있게 해줘. details/summary를 사용하면 script는 없어도 된다.{JS_RULE}\n\n{SHORT_DOC}",
         keep=("hero", "benefits", "cta"), checks=("js_or_details",), allow_script=True),

    Case("JS3", "JS", "확인메시지", SYSTEM_SHAPE,
         f"다음 HTML에서 참여 버튼을 누르면 확인 메시지가 뜨게 해줘.{JS_RULE}\n\n{SHORT_DOC}",
         keep=("hero", "benefits", "cta"), checks=("js",), allow_script=True),

    # ── N군 · 형태 규칙 없음 (대조) ──────────────────────────────────
    Case("N2", "N", "정보부족_규칙없음", SYSTEM_PLAIN, P2),
    Case("N9", "N", "긴서술형_규칙없음", SYSTEM_PLAIN, P9),

    # ── S군 · 형태 규칙 있음 ─────────────────────────────────────────
    Case("S1", "S", "정보충분", SYSTEM_SHAPE, P1,
         checks=("given_dates",), given_dates=GIVEN_DATES_P1),

    Case("S2", "S", "정보부족", SYSTEM_SHAPE, P2, pair="N2"),

    Case("S8", "S", "긴출력", SYSTEM_SHAPE, P8),

    Case("S9", "S", "긴서술형", SYSTEM_SHAPE, P9, pair="N9",
         keep=("hero", "benefits", "steps", "cta"),
         checks=("given_dates",), given_dates=GIVEN_DATES_P1,
         exact={"benefits": 3, "steps": 2}),
]


# ── C군 · 누적 수정 (묶음 A — HTML 직접 생성 → 블록 왕복 수정) ────────

CHAIN_STEPS = [
    ("cta",      "이 영역의 버튼 문구를 '지금 신청하기'로 바꿔줘."),
    ("benefits", "이 영역에 '제휴 카페 음료 쿠폰 제공' 항목을 하나 추가해줘. 기존 항목은 그대로 둬."),
    ("cta",      "이 영역의 버튼 배경색을 노란색으로 바꿔줘. style 속성을 써."),
    ("steps",    "참여 방법 영역을 새로 만들어줘. 2단계로."),
    ("hero",     "이 영역의 제목을 '여름엔 데이터가 두 배'로 바꿔줘."),
]


# ── R군 · 라우터 정확도 ──────────────────────────────────────────────
# (요청, 인정되는 op 들, 정답 target)
#   · op 이 여러 개인 것은 사람이 봐도 둘 다 말이 되는 경우입니다.
#     정답표가 애매하면 모델을 탓하는 게 아니라 정답표를 넓혀야 합니다.
#   · target 이 None 이면 채점에서 무시합니다.

ROUTER_CASES = [
    ("버튼 색을 노란색으로 바꿔줘",            ("STYLE",),              "cta"),
    ("제목 글씨를 더 크게 해줘",               ("STYLE",),              "hero"),
    ("참여 단계 지워줘",                      ("DELETE",),             "steps"),
    ("유의사항 영역 빼줘",                    ("DELETE",),             "notices"),
    ("혜택 항목을 하나 더 넣어줘",             ("EDIT",),                "benefits"),
    ("혜택 문구를 더 짧게 고쳐줘",             ("EDIT",),               "benefits"),
    ("제목을 '여름 대축제'로 바꿔줘",          ("EDIT",),               "hero"),
    ("버튼 문구를 '신청하기'로 바꿔줘",         ("EDIT",),               "cta"),
    ("참여 방법 영역을 새로 만들어줘",          ("ADD",),                "steps"),
    ("유의사항 영역 만들어줘",                 ("ADD",),                "notices"),
    ("혜택을 맨 위로 올려줘",                  ("MOVE",),               "benefits"),
    ("참여 방법을 혜택 아래로 내려줘",          ("MOVE",),               "steps"),
    ("전체적으로 톤을 밝게 해줘",              ("REWRITE_ALL",),        None),
    ("전부 존댓말로 통일해줘",                 ("REWRITE_ALL",),        None),
    ("전체적으로 좀 더 짧게 줄여줘",           ("REWRITE_ALL",),        None),
    ("월드컵 스코어 맞추기 이벤트 페이지 만들어줘", ("GENERATE",),           None),
    ("추첨 이벤트 페이지 하나 만들어줘",        ("GENERATE",),           None),
    ("두 번째 버튼 바꿔줘",                   ("ASK",),                None),
    ("그거 좀 고쳐줘",                        ("ASK",),                None),
    ("아래쪽 부분을 손봐줘",                   ("ASK",),                None),
]


# ══════════════════════════════════════════════════════════════════════
#  Ollama 호출
# ══════════════════════════════════════════════════════════════════════

def call(model, messages, seed=None, mode="html", as_json=False):
    opts = dict(BASE_OPTIONS)
    opts["num_predict"] = NUM_PREDICT.get(mode, 1536)
    if seed is not None:
        opts["seed"] = seed
    body = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": opts,
        "keep_alive": KEEP_ALIVE,
    }
    if as_json:
        body["format"] = "json"
    started = time.time()
    r = requests.post(f"{OLLAMA}/api/chat", json=body, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    data["_wall_sec"] = round(time.time() - started, 2)
    return data


def warmup(model):
    try:
        call(model, [{"role": "user", "content": "안녕"}], mode="router")
    except Exception as e:
        print(f"  [warmup 실패] {e}")


def unload(model):
    """다음 모델을 위해 VRAM 을 비운다."""
    try:
        requests.post(f"{OLLAMA}/api/chat",
                      json={"model": model, "messages": [], "keep_alive": 0},
                      timeout=60)
    except Exception:
        pass


def timings(res):
    pc = res.get("prompt_eval_count", 0)
    ec = res.get("eval_count", 0)
    pd = res.get("prompt_eval_duration", 0) or 1
    ed = res.get("eval_duration", 0) or 1
    return dict(
        load_ms       = res.get("load_duration", 0) // 1_000_000,
        prompt_ms     = pd // 1_000_000,
        eval_ms       = ed // 1_000_000,
        prompt_tokens = pc,
        eval_count    = ec,
        ctx_used      = pc + ec,
        prompt_rate   = round(pc / (pd / 1e9), 1),
        eval_rate     = round(ec / (ed / 1e9), 1),
        done_reason   = res.get("done_reason", ""),
    )


# ══════════════════════════════════════════════════════════════════════
#  환경 · 보정
# ══════════════════════════════════════════════════════════════════════

def sh(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def snapshot_env(models):
    gpu = sh("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader")
    if not gpu and sys.platform == "darwin":
        gpu = sh("system_profiler SPDisplaysDataType | grep Chipset")
    env = {
        "runner":       RUNNER,
        "protocol_version": "8.3",
        "script_sha256": hashlib.sha256(open(__file__, "rb").read()).hexdigest(),
        "run_at":       datetime.now().isoformat(timespec="seconds"),
        "os":           platform.platform(),
        "cpu":          platform.processor(),
        "gpu":          gpu or "cpu-only",
        "backend":      "cuda" if gpu and "NVIDIA" in gpu.upper()
                        else ("metal" if sys.platform == "darwin" else "cpu"),
        "ollama":       sh("ollama --version"),
        "python":       platform.python_version(),
        # 스크립트를 고치지 않고 돌렸는지 — git_dirty 가 true 면 합치기 전에 확인
        "git_commit":   sh("git rev-parse --short HEAD"),
        "git_dirty":    bool(sh("git status --porcelain")),
        "base_options": BASE_OPTIONS,
        "num_predict":  NUM_PREDICT,
        "seeds":        SEEDS,
        "router_seeds": ROUTER_SEEDS,
        "keep_alive":   KEEP_ALIVE,
        "max_retry":    MAX_RETRY,
        "excluded":     ["J(조합 계획)", "K(패치)"],
        "models":       {},
    }
    try:
        tags = requests.get(f"{OLLAMA}/api/tags", timeout=30).json()
        by_name = {m["name"]: m for m in tags.get("models", [])}
    except Exception:
        by_name = {}
    for m in models:
        info = {}
        try:
            show = requests.post(f"{OLLAMA}/api/show", json={"model": m}, timeout=30).json()
            d = show.get("details", {})
            info = {
                "parameters":   d.get("parameter_size"),
                "quantization": d.get("quantization_level"),
                "family":       d.get("family"),
            }
        except Exception:
            pass
        info["digest"]     = by_name.get(m, {}).get("digest", "")[:16]
        info["size_bytes"] = by_name.get(m, {}).get("size")
        env["models"][m] = info
    return env


def preflight(models):
    """돌리기 전에 Ollama 연결과 모델 보유를 확인한다. 2시간 뒤에 알면 늦다."""
    try:
        tags = requests.get(f"{OLLAMA}/api/tags", timeout=30).json()
    except Exception as e:
        print(f"\n  ✗ Ollama 에 연결할 수 없습니다: {e}")
        print("    ollama serve 가 떠 있는지 확인하세요.")
        return False

    have = {m.get("name", "") for m in tags.get("models", [])}
    missing = [m for m in models if m not in have]
    if missing:
        print(f"\n  ✗ 받지 않은 모델이 {len(missing)}개 있습니다. 먼저 받으세요.\n")
        for m in missing:
            print(f"      ollama pull {m}")
        print()
        return False

    if CALIB_MODEL not in have:
        print(f"\n  ✗ 보정 기준 모델이 없습니다:  ollama pull {CALIB_MODEL}")
        return False

    print(f"  ✓ 모델 {len(models)}개 확인")
    return True


def calibrate():
    warmup(CALIB_MODEL)
    er, pr = [], []
    for _ in range(3):
        res = call(CALIB_MODEL, [{"role": "user", "content": CALIB_PROMPT}],
                   seed=42, mode="html")
        t = timings(res)
        er.append(t["eval_rate"])
        pr.append(t["prompt_rate"])
    return {"eval_rate":   round(sum(er) / len(er), 1),
            "prompt_rate": round(sum(pr) / len(pr), 1)}


# ══════════════════════════════════════════════════════════════════════
#  실행 단위
# ══════════════════════════════════════════════════════════════════════

def new_row(**kw):
    base = dict(
        runner=RUNNER, model="", digest="", backend="",
        group="", prompt_id="", kind="", pair="", repeat_no=0, seed=0, attempt=0,
        hard_ok=0, all_ok=0, fails="", soft_fails="",
        wall_sec="", load_ms="", prompt_ms="", eval_ms="",
        prompt_tokens="", eval_count="", ctx_used="",
        prompt_rate="", eval_rate="",
        out_len="", html_len="", baseline_len="", patch_ratio="",
        done_reason="", router_op="", router_target="", router_ok="",
    )
    base.update(kw)
    return base


RES_PATH = f"results_v1_{RUNNER}_{STAMP}.csv"
ENV_PATH = f"env_v1_{RUNNER}_{STAMP}.json"


def _write_with_retry(write_fn, what, _sleep=time.sleep):
    """Windows에서 백신 실시간 감시·인덱서 등이 파일을 순간적으로 잠그면
    os.replace/open이 PermissionError(WinError 5/32)를 던진다.
    2~3시간 무인 실행 도중 이 때문에 죽는 걸 막기 위해 짧게 재시도하고,
    그래도 계속 잠겨 있으면(예: 결과 CSV를 엑셀로 열어둔 경우) 이번 저장만
    건너뛴다 — 메모리의 rows/문서는 그대로 남아 다음 저장 때 다시 반영된다."""
    delay = 0.15
    for attempt in range(8):
        try:
            write_fn()
            return
        except PermissionError as e:
            if attempt == 7:
                print(f"  [WARN] {what} 저장 실패(파일이 잠겨 있어 이번 저장은 건너뜀): {e}")
                return
            _sleep(delay)
            delay *= 2


def save_raw(name, text):
    def _write():
        with open(os.path.join(OUT_DIR, name), "w", encoding="utf-8") as f:
            f.write(text)
    _write_with_retry(_write, name)


def save_results(rows):
    """시도별 CSV 스냅샷을 임시 파일에 쓴 뒤 원자적으로 교체한다."""
    if not rows:
        return
    def _write():
        with open(RES_PATH + ".tmp", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        os.replace(RES_PATH + ".tmp", RES_PATH)
    _write_with_retry(_write, RES_PATH)


def save_env(env):
    def _write():
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            json.dump(env, f, ensure_ascii=False, indent=2)
    _write_with_retry(_write, ENV_PATH)


def run_one(model, case, seed, repeat_no, rows, meta):
    messages = [{"role": "system", "content": case.system},
                {"role": "user",   "content": case.prompt}]

    for attempt in range(1, MAX_RETRY + 1):
        try:
            res = call(model, messages, seed=seed, mode="html")
        except Exception as e:
            rows.append(new_row(model=model, group=case.group, prompt_id=case.pid,
                                kind=case.kind, pair=case.pair, repeat_no=repeat_no,
                                seed=seed, attempt=attempt, fails="request_error",
                                **meta))
            print(f"      요청 실패: {e}")
            save_results(rows)
            return False, ""

        raw  = res["message"]["content"]
        html = extract(raw)

        fails, note = check_html(raw, html, case.keep, case.forbid,
                                 case.strict, case.allow_script)
        ef, en = check_extra(case, html, raw)
        fails += ef
        note = (note + " " + en).strip()

        vf, vn = check_edit(case, html)
        fails += vf
        note = (note + " " + vn).strip()
        t = timings(res)
        if t["done_reason"] == "length":
            fails.append("truncated")
            note += " 출력이 중간에 끊겼습니다. 더 짧게 작성하세요."

        soft = [f for f in fails if f in SOFT_FAILS]
        hard = [f for f in fails if f not in SOFT_FAILS]
        hard_ok = int(not hard)

        rows.append(new_row(model=model, group=case.group, prompt_id=case.pid,
                            kind=case.kind, pair=case.pair, repeat_no=repeat_no,
                            seed=seed, attempt=attempt,
                            hard_ok=hard_ok, all_ok=int(not fails),
                            fails="|".join(hard), soft_fails="|".join(soft),
                            wall_sec=res["_wall_sec"],
                            out_len=len(html), html_len=len(html), **t, **meta))

        safe = model.replace(":", "_").replace("/", "_")
        stem = f"{RUNNER}_{safe}_{case.pid}_r{repeat_no}_try{attempt}"
        save_raw(stem + ".html", html or raw)
        save_raw(stem + ".json", json.dumps({"messages": messages, "response": res}, ensure_ascii=False, indent=2))
        save_results(rows)

        mark = "OK" if hard_ok else "X "
        print(f"      [{case.group}] {case.pid} r{repeat_no} try{attempt}: {mark} "
              f"{res['_wall_sec']}s out{t['eval_count']}tok {len(html)}자 "
              f"{'|'.join(hard)}{' ['+'|'.join(soft)+']' if soft else ''}")

        if hard_ok:
            return True, html

        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user",
                         "content": f"방금 출력에 문제가 있습니다. {note} "
                                    f"같은 요청을 다시 처리해서 HTML만 출력하세요."})

    return False, ""


def run_chain(model, seed, repeat_no, rows, meta):
    """C군 — 독립적인 C0 생성 후 성공한 블록 수정만 5단계 누적."""
    print(f"      [C] 누적 수정 r{repeat_no}")

    gen = Case("C0", "C", "누적_초기생성", SYSTEM_SHAPE, P1,
               checks=("given_dates",), given_dates=GIVEN_DATES_P1)
    ok, doc = run_one(model, gen, seed, repeat_no, rows, meta)
    rules = ["cta_text", "append_benefit", "yellow", "steps_two", "hero_title"]
    stop_at = 1
    if ok:
        for i, (key, instruction) in enumerate(CHAIN_STEPS, 1):
            cur = block_of(doc, key)
            prompt = instruction + "\n\n" + (cur or "(이 영역은 없습니다. 새로 만들어 주세요.)")
            step = Case(f"C{i}", "C", f"누적{i}_{key}", build_edit_system(key), prompt,
                        keep=(key,), forbid=tuple(k for k in ALL_KEYS if k != key),
                        baseline=cur, target=key, edit_rule=rules[i-1])
            ok, out = run_one(model, step, seed, repeat_no, rows, meta)
            rows[-1]["baseline_len"] = len(cur)
            if not ok:
                stop_at = i + 1
                break
            candidate = replace_block(doc, key, out)
            # 최종 병합 문서에서도 대상 외 블록과 기존 순서를 확인한다.
            if not outside_preserved(doc, candidate, key):
                rows[-1]["hard_ok"] = rows[-1]["all_ok"] = 0
                rows[-1]["fails"] += "|merge_changed_other_blocks"
                ok = False
                stop_at = i + 1
                break
            doc = candidate
            rows[-1]["patch_ratio"] = round(len(out) / len(doc), 3) if doc else ""
            save_results(rows)
        else:
            stop_at = len(CHAIN_STEPS) + 1
    # 미실행 단계도 남겨 체인 실패가 성공률 분모에서 사라지지 않도록 한다.
    if not ok:
        for i in range(stop_at, len(CHAIN_STEPS) + 1):
            rows.append(new_row(model=model, group="C", prompt_id=f"C{i}",
                                kind="skipped_after_failure", repeat_no=repeat_no,
                                seed=seed, attempt=0, fails="skipped_after_failure", **meta))
    safe = model.replace(":", "_").replace("/", "_")
    save_raw(f"{RUNNER}_{safe}_CHAIN_r{repeat_no}_final.html", doc)
    save_results(rows)


def run_router(model, seed, repeat_no, rows, meta):
    print(f"      [R] 라우터 r{repeat_no}")
    hit = 0
    for i, (req, want_ops, want_target) in enumerate(ROUTER_CASES, 1):
        messages = [{"role": "system", "content": ROUTER_SYSTEM},
                    {"role": "user",   "content": req}]
        try:
            res = call(model, messages, seed=seed, mode="router", as_json=True)
        except Exception as e:
            rows.append(new_row(model=model, group="R", prompt_id=f"R{i:02d}",
                                kind=req, repeat_no=repeat_no, seed=seed, attempt=1,
                                fails="request_error", **meta))
            continue

        raw = res["message"]["content"]
        op = target = ""
        fails = []
        try:
            s, e = raw.find("{"), raw.rfind("}")
            obj = json.loads(raw[s:e + 1])
            op = str(obj.get("op", "")).upper()
            target = obj.get("target")
            target = "" if target in (None, "null") else str(target)
        except Exception:
            fails.append("bad_json")

        ok = int(op in want_ops and (want_target is None or target == want_target))
        if ok:
            hit += 1
        elif not fails:
            fails.append(f"want_{'/'.join(want_ops)}_{want_target}"
                         f"_got_{op or 'null'}_{target or 'null'}")

        t = timings(res)
        rows.append(new_row(model=model, group="R", prompt_id=f"R{i:02d}", kind=req,
                            repeat_no=repeat_no, seed=seed, attempt=1,
                            hard_ok=ok, all_ok=ok, fails="|".join(fails),
                            wall_sec=res["_wall_sec"],
                            router_op=op, router_target=target, router_ok=ok,
                            out_len=len(raw), **t, **meta))

        save_results(rows)

    print(f"        정확도 {hit}/{len(ROUTER_CASES)}")


# ══════════════════════════════════════════════════════════════════════
#  자기 점검 — LLM 호출 전에 로직 결함을 잡는다
# ══════════════════════════════════════════════════════════════════════

def self_check():
    print("=" * 74)
    print("  자기 점검")
    print("=" * 74)

    for b in BLOCKS:
        src = {LLM: "모델", SERVER: "서버", MIXED: "혼합"}[b.source]
        print(f"  {b.key:<10} {src:<5} must={b.must or '-':<8} min={b.min_items}")

    # shape 를 시킨 블록은 must 도 있어야 한다 (프롬프트와 검증기의 짝)
    for b in LLM_BLOCKS:
        assert bool(b.shape) == bool(b.must), f"{b.key}: shape 와 must 가 짝이 아님"
        assert b.shape in SYSTEM_SHAPE,       f"{b.key}: shape 가 프롬프트에 없음"
        assert b.shape not in SYSTEM_PLAIN,   f"{b.key}: 대조군에 shape 가 들어감"

    # 서버 소유 블록은 금지 문구가 있어야 한다
    for b in SERVER_BLOCKS:
        assert f'data-block="{b.key}" 는 절대 만들지 마라' in SYSTEM_SHAPE

    # D4 는 '모르면 빼라' 규칙이 없고 D5 는 있어야 한다
    assert "값을 모르면 그 문장을 아예 빼라" in SYSTEM_SHAPE
    assert "값을 모르면 그 문장을 아예 빼라" not in SYSTEM_NO_OMIT

    # 블록 추출·교체가 실제로 되는지
    for key in ("hero", "benefits", "cta"):
        assert block_of(SHORT_DOC, key), f"SHORT_DOC 에서 {key} 를 못 뗌"
    for key in ("hero", "benefits", "steps", "notices", "cta"):
        assert block_of(LONG_DOC, key), f"LONG_DOC 에서 {key} 를 못 뗌"
    swapped = replace_block(SHORT_DOC, "cta",
                            '<section data-block="cta"><a href="#">테스트</a></section>')
    assert "테스트" in swapped and "여름 데이터 대방출" in swapped, "replace_block 오동작"

    # 정상 문서는 검증을 통과해야 한다
    f, _ = check_html(SHORT_DOC, SHORT_DOC, ("hero", "benefits", "cta"), FORBID_KEYS, True)
    assert not [x for x in f if x not in SOFT_FAILS], f"정상 문서가 검증 실패: {f}"

    # 날짜 정규화
    assert norm_date("2026년 8월 1일")  == (2026, 8, 1)
    assert norm_date("2026.08.31")     == (2026, 8, 31)
    assert norm_date("8월 1일")         == (None, 8, 1)

    # 라우터 정답표에 없는 op 가 없어야 한다
    valid_ops = {"EDIT", "ADD", "DELETE", "MOVE", "STYLE", "REWRITE_ALL", "GENERATE", "ASK"}
    for _, ops, tgt in ROUTER_CASES:
        assert isinstance(ops, tuple) and ops, "라우터 정답은 튜플이어야 함"
        for op in ops:
            assert op in valid_ops, f"라우터 정답에 없는 op: {op}"
            assert f'"{op}"' in ROUTER_SYSTEM, f"{op} 가 라우터 프롬프트에 없음"
        assert tgt is None or tgt in ALL_KEYS, f"라우터 정답에 없는 target: {tgt}"

    # 체인 단계의 블록이 전부 정의되어 있는지
    for key, _ in CHAIN_STEPS:
        assert key in BY_KEY, f"체인 단계에 없는 블록: {key}"

    # 블록 편집 프롬프트에 "기존 속성 유지" 지시가 들어갔는지
    assert 'href="#" 는 그대로 둬라' in build_edit_system("cta")

    # JS 케이스에 스크립트 위치 지시가 들어갔는지
    for c in CASES:
        if c.group == "JS":
            assert "<script> 는 마지막 <section> 안에 넣어라" in c.prompt, \
                f"{c.pid}: JS_RULE 누락"

    print(f"\n  SYSTEM(형태규칙 없음) {len(SYSTEM_PLAIN)}자")
    print(f"  SYSTEM(형태규칙 있음) {len(SYSTEM_SHAPE)}자")
    print(f"  SYSTEM(빼라규칙 없음) {len(SYSTEM_NO_OMIT)}자")
    print(f"  케이스 {len(CASES)}개 × {len(SEEDS)}회 + 체인 {len(CHAIN_STEPS)+1}단계 "
          f"+ 라우터 {len(ROUTER_CASES)}개 × {len(ROUTER_SEEDS)}회")
    print("  shape↔must 짝 · 블록 추출/교체 · 날짜 정규화 · 라우터 정답표 확인 완료\n")


# ══════════════════════════════════════════════════════════════════════
#  main
# ══════════════════════════════════════════════════════════════════════

def main():
    if "--self-check" in sys.argv:
        self_check()
        regression_check()
        return
    if RUNNER == "unknown":
        print("RUNNER 환경변수를 설정하세요.  예)  set RUNNER=지원")
        return

    self_check()
    regression_check()

    if not preflight(MODELS):
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    env = snapshot_env(MODELS)
    print("=" * 74)
    print(f"  {RUNNER} · {env['backend']} · {env['gpu']}")
    for m, info in env["models"].items():
        dg = info.get("digest") or "?"
        pm = info.get("parameters") or "?"
        qt = info.get("quantization") or "?"
        print(f"  {m:<20} {dg:<18} {pm:<8} {qt}")
    print("=" * 74)

    if env.get("git_dirty"):
        print("  ⚠ 스크립트가 수정된 상태입니다 (git_dirty). 결과를 합칠 때 확인하세요.")

    print("\n  보정 (시작) …")
    env["calibration_start"] = calibrate()
    print(f"  생성 {env['calibration_start']['eval_rate']} tok/s · "
          f"입력 {env['calibration_start']['prompt_rate']} tok/s")
    save_env(env)

    rows = []
    for model in MODELS:
        info = env["models"].get(model, {})
        meta = dict(digest=info.get("digest", ""), backend=env["backend"])
        print(f"\n{'='*74}\n  {model}\n{'='*74}")
        try:
            warmup(model)

            for repeat_no, seed in enumerate(SEEDS, 1):
                print(f"  ── 회차 {repeat_no} (seed {seed}) ──")
                for case in CASES:                      # ★ 회차마다 전체를 한 바퀴
                    run_one(model, case, seed, repeat_no, rows, meta)
                run_chain(model, seed, repeat_no, rows, meta)

            for i, seed in enumerate(ROUTER_SEEDS, 1):
                run_router(model, seed, i, rows, meta)

            save_results(rows)                          # ★ 중간 저장 — 끊겨도 여기까진 남음
            print(f"  → {RES_PATH} 중간 저장 ({len(rows)}행)")
        finally:
            save_results(rows)
            unload(model)

    print("\n  보정 (종료) …")
    env["calibration_end"] = calibrate()
    s = env["calibration_start"]["eval_rate"]
    e = env["calibration_end"]["eval_rate"]
    env["drift"] = round(e / s, 3) if s else None
    print(f"  생성 {e} tok/s   드리프트 {env['drift']}")
    if env["drift"] is not None and env["drift"] < 0.85:
        print("  ⚠ 드리프트 0.85 미만 — 이 실행의 시간 지표는 신뢰하지 마세요")
    elif env["drift"] is not None and env["drift"] < 0.95:
        print("  ⚠ 드리프트 0.95 미만 — 보고서에 명시하세요")

    if not rows:
        print("\n  기록된 행이 없습니다. Ollama 가 떠 있는지 확인하세요.")
        return

    save_results(rows)
    save_env(env)

    summary(rows)
    print(f"\n  {RES_PATH}")
    print(f"  {ENV_PATH}")
    print(f"  {OUT_DIR}/ 의 .html 을 브라우저로 열어 눈으로 확인하세요 (특히 JS군)")


def summary(rows):
    print("\n" + "=" * 74)
    print("  군별 요약   1차 = 첫 시도 통과 · 최종 = 재시도 포함")
    print("=" * 74)
    print(f"  {'모델':<20} {'군':<4} {'1차':>8} {'최종':>8} {'출력토큰':>9} {'시간':>9}")

    models = []
    for r in rows:
        if r["model"] and r["model"] not in models:
            models.append(r["model"])

    for model in models:
        for g in ("D", "E", "JS", "N", "S", "C", "R"):
            sub = [r for r in rows if r["model"] == model and r["group"] == g]
            if not sub:
                continue
            firsts = [r for r in sub if r["attempt"] == 1]
            # 케이스×회차 단위로 최종 성공 여부
            done = {}
            for r in sub:
                k = (r["prompt_id"], r["repeat_no"])
                done[k] = done.get(k, 0) or r["hard_ok"]
            tok = sum(r["eval_count"] for r in sub if isinstance(r["eval_count"], int))
            sec = sum(r["wall_sec"] for r in sub if isinstance(r["wall_sec"], float))
            print(f"  {model:<20} {g:<4} "
                  f"{sum(r['hard_ok'] for r in firsts)}/{len(firsts):<5} "
                  f"{sum(done.values())}/{len(done):<5} "
                  f"{tok:>9} {sec:>8.1f}s")

    # 회차별 생성 속도 — 발열 곡선
    print("\n  회차별 평균 생성 속도 (발열 확인)")
    for model in models:
        line = []
        for rn in range(1, len(SEEDS) + 1):
            sub = [r["eval_rate"] for r in rows
                   if r["model"] == model and r["repeat_no"] == rn
                   and isinstance(r["eval_rate"], float) and r["eval_rate"] > 0]
            line.append(f"{sum(sub)/len(sub):.1f}" if sub else "-")
        print(f"  {model:<20} " + "  ".join(f"r{i+1} {v}" for i, v in enumerate(line)))

    # 실패 유형 분포
    print("\n  실패 유형 분포")
    counts = {}
    for r in rows:
        for f in str(r["fails"]).split("|"):
            if f and not f.startswith("want_"):
                counts[f] = counts.get(f, 0) + 1
    for k, v in sorted(counts.items(), key=lambda x: -x[1])[:15]:
        print(f"    {k:<28} {v}")

    # 대조쌍 — 같은 요청을 조건만 바꿔 비교
    print("\n  대조쌍   1차 통과율 · 출력 토큰")
    for model in models:
        seen = []
        for r in rows:
            if r["model"] != model or not r["pair"]:
                continue
            key = (r["pair"], r["prompt_id"])
            if key in seen:
                continue
            seen.append(key)

            def stat(pid):
                f = [x for x in rows if x["model"] == model
                     and x["prompt_id"] == pid and x["attempt"] == 1]
                a = [x for x in rows if x["model"] == model and x["prompt_id"] == pid]
                if not f:
                    return None
                rate = sum(x["hard_ok"] for x in f) / len(f)
                tok = sum(x["eval_count"] for x in a if isinstance(x["eval_count"], int))
                return rate, tok

            before, after = stat(key[0]), stat(key[1])
            if before and after:
                print(f"  {model:<20} {key[0]:>4}→{key[1]:<5} "
                      f"1차 {before[0]:.2f}→{after[0]:.2f}   "
                      f"출력 {before[1]:>5}→{after[1]:<5}")



# ── v1.1 요청 충족 및 보존 검사 · v1.2 파싱 내구성 ─────────────────
def canonical(node):
    if isinstance(node, Comment):
        return ("comment", str(node))
    if isinstance(node, NavigableString):
        return ("text", re.sub(r"\s+", " ", str(node)).strip())
    attrs = tuple(sorted((k, tuple(v) if isinstance(v, list) else v)
                         for k, v in node.attrs.items())) if getattr(node, "attrs", None) else ()
    return (node.name, attrs, tuple(canonical(c) for c in node.children
                                   if not isinstance(c, NavigableString) or str(c).strip()))


def parsed(html):
    return safe_soup(html)


def outside_preserved(before, after, key):
    a, b = parsed(before), parsed(after)
    old_keys = [x.get("data-block") for x in a.find_all("section")]
    new_keys = [x.get("data-block") for x in b.find_all("section")]
    if new_keys != old_keys and not (key not in old_keys and new_keys == old_keys + [key]):
        return False
    for doc in (a, b):
        for el in doc.select(f'[data-block="{key}"]'):
            el.decompose()
    return canonical(a) == canonical(b)


def check_edit(case, html):
    if not case.edit_rule:
        return [], ""
    fails = []
    a, b = parsed(case.baseline), parsed(html)
    aa = a.select_one(f'[data-block="{case.target}"]')
    bb = b.select_one(f'[data-block="{case.target}"]')
    expected = len(a.find_all("section")) if case.group == "E" else 1
    if len(b.find_all("section")) != expected:
        fails.append("edit_block_count")
    if case.group == "E" and not outside_preserved(case.baseline, html, case.target):
        fails.append("diff_unintended")
    if bb is None:
        return fails + ["edit_target_missing"], "요청한 대상 영역을 유지하세요."
    rule = case.edit_rule
    if rule in ("cta_text", "hero_title"):
        tag, want = ("a", "지금 신청하기") if rule == "cta_text" else ("h1", "여름엔 데이터가 두 배")
        old, new = aa.find(tag) if aa else None, bb.find(tag)
        if new is None or new.get_text(strip=True) != want:
            fails.append("request_not_applied")
        if old is None or new is None:
            fails.append("edit_element_missing")
        else:
            old.clear(); old.append("__EDIT_TEXT__")
            new.clear(); new.append("__EDIT_TEXT__")
            if canonical(a) != canonical(b):
                fails.append("diff_unintended")
    elif rule == "append_benefit":
        old_ul, new_ul = aa.find("ul") if aa else None, bb.find("ul")
        if old_ul is None or new_ul is None:
            fails.append("benefit_list_missing")
        else:
            old_items = old_ul.find_all("li", recursive=False)
            new_items = new_ul.find_all("li", recursive=False)
            additions = [n for n in new_items if n.get_text(strip=True) == "제휴 카페 음료 쿠폰 제공"]
            if len(new_items) != len(old_items) + 1 or not additions:
                fails.append("request_not_applied")
            else:
                additions[-1].decompose()
                if canonical(a) != canonical(b):
                    fails.append("diff_unintended")
    elif rule == "yellow":
        old, new = aa.find("a") if aa else None, bb.find("a")
        def styles(el):
            return dict((k.strip().lower(), v.strip().lower()) for k, v in
                        (part.split(":", 1) for part in el.get("style", "").split(";") if ":" in part))
        if old is None or new is None:
            fails.append("edit_element_missing")
        else:
            os_, ns_ = styles(old), styles(new)
            value = ns_.get("background-color", ns_.get("background", ""))
            if re.sub(r"\s+", "", value) not in ("yellow", "#ff0", "#ffff00", "rgb(255,255,0)"):
                fails.append("request_not_applied")
            for prop in ("background", "background-color"):
                os_.pop(prop, None); ns_.pop(prop, None)
            if os_ != ns_:
                fails.append("diff_unintended_style")
            old.attrs.pop("style", None); new.attrs.pop("style", None)
            if canonical(a) != canonical(b):
                fails.append("diff_unintended")
    elif rule == "steps_two":
        if len(bb.select("ol > li")) != 2:
            fails.append("exact_steps_2")
    return list(dict.fromkeys(fails)), "요청한 변경을 정확히 적용하고 나머지 문구·태그·속성·순서를 유지하세요." if fails else ""


for _case in CASES:
    if _case.pid in ("E1", "E2", "E4", "E5"):
        _whole = SHORT_DOC if _case.pid in ("E1", "E2") else LONG_DOC
        _case.baseline = _whole if _case.pid in ("E1", "E4") else block_of(_whole, "cta")
        _case.target = "cta"
        _case.edit_rule = "cta_text"


def regression_check():
    for case in (c for c in CASES if c.group == "E"):
        good = case.baseline.replace("가입하기", "지금 신청하기")
        assert not check_edit(case, good)[0], case.pid
        assert "request_not_applied" in check_edit(case, case.baseline)[0]
        assert check_edit(case, good.replace('href="#"', 'href="https://wrong.example"'))[0]
        assert check_edit(case, good + block_of(good, "cta"))[0]
    e4 = next(c for c in CASES if c.pid == "E4")
    good = e4.baseline.replace("가입하기", "지금 신청하기")
    assert check_edit(e4, good.replace("30%", "90%"))[0]
    soup = parsed(good); soup.select_one('[data-block="notices"]').decompose()
    assert check_edit(e4, str(soup))[0]
    js = next(c for c in CASES if c.pid == "JS2")
    bad = SHORT_DOC + "<details></details><summary>혜택</summary>"
    assert "details_wrong_target" in check_extra(js, bad, bad)[0]
    soup = parsed(SHORT_DOC); ul = soup.select_one('[data-block="benefits"] ul')
    detail = soup.new_tag("details"); title = soup.new_tag("summary"); title.string = "혜택"
    ul.wrap(detail); detail.insert(0, title)
    assert not check_extra(js, str(soup), str(soup))[0]
    assert next(ops for req, ops, target in ROUTER_CASES if req == "혜택 항목을 하나 더 넣어줘") == ("EDIT",)

    # v1.2 회귀: 모델이 깨진 주석(<![--- ...)을 내면 bs4(html.parser)가
    # ParserRejectedMarkup 을 던져 전체 실행이 죽던 버그. safe_soup 로 감싼 뒤에는
    # 죽지 않고 빈 문서 취급 → check_html 이 정상적으로 fails 리스트를 돌려줘야 한다.
    broken = ('<section data-block="cta">\n'
              '<![--- cta 영역 유지 ---\n'
              '<a href="#" class="btn">가입하기</a>\n'
              '</section>')
    result_soup = safe_soup(broken)          # 여기서 예외가 나면 회귀 검사 자체가 실패한다
    assert isinstance(result_soup, BeautifulSoup)
    fails, _ = check_html(broken, broken, ("cta",), (), True)
    assert isinstance(fails, list)
    _, _ = check_extra(CASES[0], broken, broken)   # check_extra 경로도 죽지 않는지 확인
    assert not outside_preserved(broken, broken, "cta") or True  # 죽지만 않으면 됨

    # v1.3 회귀: 저장 중 일시적 PermissionError(백신 잠금 등)가 나도
    # 재시도 끝에 성공하면 죽지 않아야 하고, 끝까지 실패해도 예외 없이
    # 넘어가야 한다 (메모리의 rows/문서는 그대로 남는다).
    calls = {"n": 0}
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("locked")
    _write_with_retry(flaky, "test_transient", _sleep=lambda s: None)
    assert calls["n"] == 3, "일시적 실패 후 재시도로 복구되어야 함"

    def always_locked():
        raise PermissionError("locked forever")
    _write_with_retry(always_locked, "test_permanent", _sleep=lambda s: None)  # 예외 없이 넘어가야 함

    print("  v1.3 요청 충족·비대상 보존·details 관계·깨진 마크업·저장 재시도 내구성 회귀 검사 통과")


if __name__ == "__main__":
    main()