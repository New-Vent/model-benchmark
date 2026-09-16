"""
component_library.py — 실제 UI 라이브러리 스타일을 참고한 컴포넌트 마크업 모음
====================================================================
출처 (전부 무료/오픈소스, 복사-붙여넣기 재사용을 공식 허용하는 라이브러리):
    - HyperUI   (https://hyperui.dev)   — MIT 라이선스, Tailwind CSS
    - Flowbite  (https://flowbite.com/blocks/) — 무료 Tailwind 블록
    - Preline   (https://preline.co)     — 오픈소스 Tailwind 컴포넌트
    - Meraki UI (https://merakiui.com)   — 무료 Tailwind 컴포넌트
    - Uiverse   (https://uiverse.io)     — 커뮤니티 공유 HTML/CSS 스니펫

주의: 각 사이트의 마크업을 그대로 긁어온 것이 아니라, 해당 사이트들이
공통적으로 쓰는 구조/유틸리티 클래스 패턴(카드형 그리드, 그라데이션 히어로,
글로우 버튼 등)을 참고해 model_test_v7.py의 Block/Variant 체계에 맞게
새로 작성했다. 각 함수 주석에 "어느 사이트 스타일을 참고했는지"만 표기한다.

이 파일의 함수들은 전부 (dict) -> str 형태이며, model_test_v7.py의
Variant(name, desc, fields, render) 네 번째 인자로 그대로 등록해서 쓴다.
필수 구조(hero=h1, benefits/steps=ul·ol+li, cta=a)는 스타일이 달라도
전부 동일하게 유지한다 — check_html의 must/min_items 검증이 스타일과
무관하게 항상 같은 기준으로 통과/실패를 판정해야 하기 때문이다.
"""

import html as htmllib


def esc(v):
    return htmllib.escape(str(v), quote=True)


# ══════════════════════════════════════════════════════════════
#  HERO 변형 — 필수 구조: <h1> 하나는 반드시 있어야 함 (must="h1")
# ══════════════════════════════════════════════════════════════

def hero_hyperui_centered(d):
    """HyperUI 스타일 — 가운데 정렬, 여백 넉넉한 단순 히어로."""
    sub = f'<p class="mx-auto mt-4 max-w-xl text-gray-500">{esc(d["sub"])}</p>' if d.get("sub") else ""
    return f"""<section data-block="hero" class="bg-white">
  <div class="mx-auto max-w-screen-xl px-4 py-16 text-center">
    <h1 class="text-3xl font-extrabold sm:text-5xl">{esc(d["title"])}</h1>
    {sub}
  </div>
</section>"""


def hero_flowbite_split(d):
    """Flowbite 스타일 — 좌우 분할(텍스트+이미지 자리) 히어로 배너."""
    sub = f'<p class="mb-6 max-w-lg text-lg font-normal text-gray-500 lg:text-xl">{esc(d["sub"])}</p>' if d.get("sub") else ""
    return f"""<section data-block="hero" class="bg-gray-50">
  <div class="mx-auto grid max-w-screen-xl px-4 py-8 lg:grid-cols-12 lg:gap-8 lg:py-16">
    <div class="mr-auto place-self-center lg:col-span-7">
      <h1 class="mb-4 max-w-2xl text-4xl font-extrabold leading-none tracking-tight md:text-5xl">{esc(d["title"])}</h1>
      {sub}
    </div>
    <div class="hidden lg:col-span-5 lg:mt-0 lg:flex" aria-hidden="true">
      <div class="h-64 w-full rounded-lg bg-gray-200"></div>
    </div>
  </div>
</section>"""


def hero_merakiui_badge(d):
    """Meraki UI 스타일 — 상단에 작은 뱃지를 붙인 히어로."""
    sub = f'<p class="mt-4 text-gray-600 dark:text-gray-300">{esc(d["sub"])}</p>' if d.get("sub") else ""
    return f"""<section data-block="hero" class="bg-white dark:bg-gray-900">
  <div class="mx-auto max-w-screen-md px-4 py-14 text-center">
    <span class="rounded-full bg-blue-100 px-3 py-1 text-xs font-semibold text-blue-700">EVENT</span>
    <h1 class="mt-3 text-3xl font-bold text-gray-800 dark:text-white md:text-4xl">{esc(d["title"])}</h1>
    {sub}
  </div>
</section>"""


# ══════════════════════════════════════════════════════════════
#  BENEFITS 변형 — 필수 구조: <ul><li> 2개 이상 (must="ul li", min_items=2)
# ══════════════════════════════════════════════════════════════

def benefits_hyperui_list(d):
    """HyperUI 스타일 — 단순 글머리 목록형 혜택 리스트."""
    li = "\n".join(f'    <li class="flex items-center gap-2 text-gray-700">'
                   f'<span class="text-green-600">✓</span> {esc(x)}</li>' for x in d["items"])
    return f"""<section data-block="benefits" class="mx-auto max-w-screen-xl px-4 py-10">
  <h2 class="mb-4 text-2xl font-bold">혜택</h2>
  <ul class="space-y-2">
{li}
  </ul>
</section>"""


def benefits_flowbite_cards(d):
    """Flowbite 스타일 — 그리드로 배치된 카드형 혜택 목록."""
    cards = "\n".join(
        f'    <li class="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">'
        f'<p class="font-semibold text-gray-900">{esc(x)}</p></li>' for x in d["items"])
    return f"""<section data-block="benefits" class="bg-gray-50 py-10">
  <div class="mx-auto max-w-screen-xl px-4">
    <h2 class="mb-6 text-2xl font-bold">혜택</h2>
    <ul class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
{cards}
    </ul>
  </div>
</section>"""


def benefits_merakiui_icons(d):
    """Meraki UI 스타일 — 아이콘 원형 뱃지 + 텍스트가 나열된 형태."""
    li = "\n".join(
        f'    <li class="flex items-start gap-3">'
        f'<span class="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs text-white">✓</span>'
        f'<span class="text-gray-700 dark:text-gray-200">{esc(x)}</span></li>' for x in d["items"])
    return f"""<section data-block="benefits" class="bg-white dark:bg-gray-900 py-10">
  <div class="mx-auto max-w-screen-md px-4">
    <h2 class="mb-6 text-2xl font-bold text-gray-800 dark:text-white">혜택</h2>
    <ul class="space-y-4">
{li}
    </ul>
  </div>
</section>"""


# ══════════════════════════════════════════════════════════════
#  STEPS 변형 — 필수 구조: <ol><li> 2개 이상 (must="ol li", min_items=2)
# ══════════════════════════════════════════════════════════════

def steps_hyperui_numbered(d):
    """HyperUI 스타일 — 원형 숫자 뱃지가 붙은 단순 단계 목록."""
    li = "\n".join(
        f'    <li class="flex items-center gap-3">'
        f'<span class="flex h-8 w-8 items-center justify-center rounded-full bg-gray-900 text-sm text-white">{i+1}</span>'
        f'<span>{esc(x)}</span></li>' for i, x in enumerate(d["items"]))
    return f"""<section data-block="steps" class="mx-auto max-w-screen-md px-4 py-10">
  <h2 class="mb-4 text-2xl font-bold">참여 방법</h2>
  <ol class="space-y-3">
{li}
  </ol>
</section>"""


def steps_preline_timeline(d):
    """Preline 스타일 — 세로 타임라인 형태의 단계 목록."""
    li = "\n".join(
        f'    <li class="relative border-l border-gray-200 pb-6 pl-6">'
        f'<span class="absolute -left-1.5 top-0 h-3 w-3 rounded-full bg-blue-600"></span>'
        f'<p class="font-medium text-gray-800">{esc(x)}</p></li>' for x in d["items"])
    return f"""<section data-block="steps" class="mx-auto max-w-screen-md px-4 py-10">
  <h2 class="mb-6 text-2xl font-bold">참여 방법</h2>
  <ol class="ml-2">
{li}
  </ol>
</section>"""


# ══════════════════════════════════════════════════════════════
#  CTA 변형 — 필수 구조: <a> 하나는 반드시 있어야 함 (must="a")
# ══════════════════════════════════════════════════════════════

def cta_hyperui_simple(d):
    """HyperUI 스타일 — 단순 텍스트 버튼 하나."""
    return f"""<section data-block="cta" class="mx-auto max-w-screen-xl px-4 py-10 text-center">
  <a href="#" class="inline-block rounded-lg bg-gray-900 px-8 py-3 text-sm font-medium text-white">{esc(d["label"])}</a>
</section>"""


def cta_flowbite_banner(d):
    """Flowbite 스타일 — 배경색이 채워진 배너형 CTA."""
    return f"""<section data-block="cta" class="bg-blue-700 py-10">
  <div class="mx-auto max-w-screen-md px-4 text-center">
    <a href="#" class="inline-block rounded-lg bg-white px-8 py-3 text-sm font-semibold text-blue-700 hover:bg-gray-100">{esc(d["label"])}</a>
  </div>
</section>"""


def cta_uiverse_glow(d):
    """Uiverse 스타일 — 그라데이션 + 은은한 글로우 효과를 가진 버튼."""
    return f"""<section data-block="cta" class="mx-auto max-w-screen-xl px-4 py-10 text-center">
  <a href="#" class="inline-block rounded-full bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500
             px-10 py-3 text-sm font-bold text-white shadow-lg shadow-purple-500/40
             transition hover:shadow-purple-500/60">{esc(d["label"])}</a>
</section>"""


# ══════════════════════════════════════════════════════════════
#  인터랙티브(JS) 변형 — "JS 인터랙티브" 트랙
#
#  원칙은 HTML/CSS와 완전히 동일하다: LLM은 실제 동작하는 JS 코드를
#  단 한 줄도 쓰지 않는다. LLM이 내는 건 "목표 날짜", "질문/답변"
#  같은 콘텐츠 값뿐이고, 그 값은 HTML data-* 속성으로만 노출된다.
#  실제 상호작용을 만드는 JS는 100% 고정된 스니펫(COUNTDOWN_SCRIPT,
#  FAQ_ACCORDION_SCRIPT)이며, model_test_v7.py의 assemble_page()가
#  "해당 타입의 블록이 하나라도 있으면" 그 스니펫을 한 번만 붙인다.
#  즉 JS는 여러 인스턴스가 있어도 항상 같은 코드 한 벌만 쓰이므로,
#  LLM이 몇 개를 만들든 문법이 깨질 방법 자체가 없다.
# ══════════════════════════════════════════════════════════════

import re as _re
COUNTDOWN_DATE = _re.compile(r"^\d{4}-\d{2}-\d{2}$")


def countdown_digital(d):
    """카운트다운 — target_date가 YYYY-MM-DD 형식이 아니면 렌더링
    자체를 건너뛴다(빈 문자열 반환 → render_plan이 자동 스킵)."""
    target = str(d.get("target_date", ""))
    if not COUNTDOWN_DATE.match(target):
        return ""
    return f"""<section data-block="countdown">
  <h2>{esc(d["title"])}</h2>
  <span data-countdown-target="{esc(target)}" class="countdown-value">계산 중...</span>
</section>"""


COUNTDOWN_SCRIPT = """<script>
(function(){
  document.querySelectorAll('[data-countdown-target]').forEach(function(el){
    var target = new Date(el.getAttribute('data-countdown-target') + 'T00:00:00').getTime();
    function tick(){
      var diff = target - Date.now();
      if (diff <= 0) { el.textContent = '마감되었습니다'; return; }
      var d = Math.floor(diff / 86400000);
      var h = Math.floor((diff % 86400000) / 3600000);
      var m = Math.floor((diff % 3600000) / 60000);
      el.textContent = d + '일 ' + h + '시간 ' + m + '분 남음';
      setTimeout(tick, 60000);
    }
    tick();
  });
})();
</script>"""


def faq_accordion(d):
    """FAQ 아코디언 — LLM은 질문/답변 텍스트만 items로 낸다.
    실제 펼침/접힘 동작은 브라우저 네이티브 <details>/<summary>가
    담당하므로(HTML만으로 동작), 이 컴포넌트는 JS 없이도 이미
    상호작용이 가능하다는 걸 보여주는 대조군 역할도 겸한다."""
    items = d.get("items", [])
    blocks = "\n".join(
        f'  <details class="faq-item">\n    <summary>{esc(q)}</summary>\n'
        f'    <p>{esc(a)}</p>\n  </details>'
        for q, a in (pair.split("|", 1) if "|" in pair else (pair, "") for pair in items)
    )
    return f"""<section data-block="faq">
  <h2>자주 묻는 질문</h2>
{blocks}
</section>"""


def tab_switcher(d):
    """탭 전환 — 순수 JS(상태 토글)가 실제로 필요한 컴포넌트.
    LLM은 탭 이름과 내용(items, "탭이름|내용" 형식)만 낸다."""
    items = d.get("items", [])
    tabs, panels = [], []
    for i, pair in enumerate(items):
        label, content = pair.split("|", 1) if "|" in pair else (pair, "")
        active = " active" if i == 0 else ""
        tabs.append(f'    <button class="tab-btn{active}" data-tab-index="{i}">{esc(label)}</button>')
        panels.append(f'    <div class="tab-panel{active}" data-tab-panel="{i}">{esc(content)}</div>')
    return f"""<section data-block="tabs">
  <div class="tab-buttons">
{chr(10).join(tabs)}
  </div>
  <div class="tab-panels">
{chr(10).join(panels)}
  </div>
</section>"""


TAB_SWITCHER_SCRIPT = """<script>
(function(){
  document.querySelectorAll('[data-block="tabs"]').forEach(function(container){
    var buttons = container.querySelectorAll('[data-tab-index]');
    var panels = container.querySelectorAll('[data-tab-panel]');
    buttons.forEach(function(btn){
      btn.addEventListener('click', function(){
        var idx = btn.getAttribute('data-tab-index');
        buttons.forEach(function(b){ b.classList.toggle('active', b === btn); });
        panels.forEach(function(p){
          p.classList.toggle('active', p.getAttribute('data-tab-panel') === idx);
        });
      });
    });
  });
})();
</script>"""


# ══════════════════════════════════════════════════════════════
#  각 함수를 model_test_v7.py의 BLOCKS 레지스트리에 그대로 꽂을 수 있도록
#  (variant_name, desc, fields, render_fn) 튜플 목록으로 노출한다.
# ══════════════════════════════════════════════════════════════

HERO_VARIANTS = [
    ("hyperui_centered", "HyperUI풍 — 가운데 정렬 단순 히어로", ("title", "sub"), hero_hyperui_centered),
    ("flowbite_split", "Flowbite풍 — 좌우 분할 배너 히어로", ("title", "sub"), hero_flowbite_split),
    ("merakiui_badge", "MerakiUI풍 — 상단 뱃지 + 중앙 정렬 히어로", ("title", "sub"), hero_merakiui_badge),
]

BENEFITS_VARIANTS = [
    ("hyperui_list", "HyperUI풍 — 체크표시 글머리 목록", ("items",), benefits_hyperui_list),
    ("flowbite_cards", "Flowbite풍 — 그리드 카드형 목록", ("items",), benefits_flowbite_cards),
    ("merakiui_icons", "MerakiUI풍 — 원형 아이콘 뱃지 목록", ("items",), benefits_merakiui_icons),
]

STEPS_VARIANTS = [
    ("hyperui_numbered", "HyperUI풍 — 숫자 원형 뱃지 단계", ("items",), steps_hyperui_numbered),
    ("preline_timeline", "Preline풍 — 세로 타임라인 단계", ("items",), steps_preline_timeline),
]

CTA_VARIANTS = [
    ("hyperui_simple", "HyperUI풍 — 단순 텍스트 버튼", ("label",), cta_hyperui_simple),
    ("flowbite_banner", "Flowbite풍 — 배경색 채운 배너 CTA", ("label",), cta_flowbite_banner),
    ("uiverse_glow", "Uiverse풍 — 그라데이션 글로우 버튼", ("label",), cta_uiverse_glow),
]

# JS 인터랙티브 트랙 — LLM은 콘텐츠 값만 내고, 실제 동작 JS는
# model_test_v7.py의 COUNTDOWN_SCRIPT/TAB_SWITCHER_SCRIPT(고정)가 담당.
COUNTDOWN_VARIANTS = [
    ("digital", "숫자 카운트다운 (JS로 실시간 갱신)", ("title", "target_date"), countdown_digital),
]

FAQ_VARIANTS = [
    ("native_details", "브라우저 네이티브 <details> 아코디언 (JS 불필요)", ("items",), faq_accordion),
]

TABS_VARIANTS = [
    ("js_switcher", "JS로 전환되는 탭 (순수 JS 상태 토글 필요)", ("items",), tab_switcher),
]
