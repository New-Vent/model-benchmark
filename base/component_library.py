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


def carousel_slides(d):
    """이미지 캐러셀 — LLM은 슬라이드 캡션(items, 2~4개)만 낸다. 실제
    이미지는 이 벤치마크에서 생성할 수 없으므로 hero_flowbite_split과
    동일한 관례(회색 자리표시자 박스)를 쓴다. 이전/다음·점 네비게이션은
    CAROUSEL_SCRIPT가 담당."""
    items = d.get("items", [])
    slides = "\n".join(
        f'    <div class="carousel-slide{" active" if i == 0 else ""}" data-carousel-slide="{i}">'
        f'<div class="carousel-placeholder" aria-hidden="true"></div>'
        f'<p class="carousel-caption">{esc(x)}</p></div>'
        for i, x in enumerate(items)
    )
    dots = "\n".join(
        f'    <button class="carousel-dot{" active" if i == 0 else ""}" data-carousel-dot="{i}"></button>'
        for i in range(len(items))
    )
    return f"""<section data-block="carousel">
  <div class="carousel-track">
{slides}
  </div>
  <div class="carousel-controls">
    <button class="carousel-prev" data-carousel-prev aria-label="이전 슬라이드">‹</button>
    <div class="carousel-dots">
{dots}
    </div>
    <button class="carousel-next" data-carousel-next aria-label="다음 슬라이드">›</button>
  </div>
</section>"""


CAROUSEL_SCRIPT = """<script>
(function(){
  document.querySelectorAll('[data-block="carousel"]').forEach(function(container){
    var slides = Array.prototype.slice.call(container.querySelectorAll('[data-carousel-slide]'));
    var dots = Array.prototype.slice.call(container.querySelectorAll('[data-carousel-dot]'));
    var current = 0;

    function show(idx){
      current = (idx + slides.length) % slides.length;
      slides.forEach(function(s, i){ s.classList.toggle('active', i === current); });
      dots.forEach(function(d, i){ d.classList.toggle('active', i === current); });
    }

    var prev = container.querySelector('[data-carousel-prev]');
    var next = container.querySelector('[data-carousel-next]');
    if (prev) prev.addEventListener('click', function(){ show(current - 1); });
    if (next) next.addEventListener('click', function(){ show(current + 1); });
    dots.forEach(function(dot, i){
      dot.addEventListener('click', function(){ show(i); });
    });
  });
})();
</script>"""


def carousel_flowbite_fade(d):
    """Flowbite풍 — 전체 폭 페이드 캐러셀, 하단 숫자 뱃지 인디케이터.
    data-* 계약(data-carousel-slide/dot/prev/next)은 slides 변형과
    동일하다 — CAROUSEL_SCRIPT 하나가 두 변형 모두를 그대로 제어한다."""
    items = d.get("items", [])
    slides = "\n".join(
        f'    <div class="carousel-slide carousel-fade{" active" if i == 0 else ""}" '
        f'data-carousel-slide="{i}">'
        f'<div class="carousel-placeholder h-56 w-full rounded-xl bg-gray-200" aria-hidden="true"></div>'
        f'<p class="carousel-caption mt-2 text-center text-sm text-gray-600">{esc(x)}</p></div>'
        for i, x in enumerate(items)
    )
    badges = "\n".join(
        f'    <button class="carousel-dot carousel-badge{" active" if i == 0 else ""}" '
        f'data-carousel-dot="{i}">{i + 1}</button>'
        for i in range(len(items))
    )
    return f"""<section data-block="carousel" class="mx-auto max-w-screen-md px-4 py-10">
  <div class="carousel-track relative">
{slides}
  </div>
  <div class="carousel-controls mt-3 flex items-center justify-center gap-3">
    <button class="carousel-prev rounded-full border px-3 py-1" data-carousel-prev aria-label="이전 슬라이드">‹</button>
    <div class="carousel-dots flex gap-2">
{badges}
    </div>
    <button class="carousel-next rounded-full border px-3 py-1" data-carousel-next aria-label="다음 슬라이드">›</button>
  </div>
</section>"""


def poll_vote(d):
    """투표 — LLM은 질문과 옵션 이름(items, 2~4개)만 낸다. 득표율은
    전부 클라이언트에서 계산하므로 LLM이 가짜 숫자를 지어낼 필요가
    (지어낼 수) 없다. 실제 클릭·집계·재투표 방지는 POLL_SCRIPT가 담당."""
    items = d.get("items", [])
    options = "\n".join(
        f'    <li><button class="poll-option" data-poll-option>{esc(x)}'
        f'<span class="poll-bar" data-poll-bar></span>'
        f'<span class="poll-pct" data-poll-pct></span></button></li>'
        for x in items
    )
    return f"""<section data-block="poll">
  <h2>{esc(d["question"])}</h2>
  <ul class="poll-options" data-poll-group>
{options}
  </ul>
  <p class="poll-note" data-poll-note hidden>투표해 주셔서 감사합니다.</p>
</section>"""


def poll_flowbite_pills(d):
    """Flowbite풍 — 알약(pill) 버튼 옵션 + 오른쪽 배지형 퍼센트 표시.
    data-* 계약(data-poll-group/option/bar/pct/note)은 vote 변형과
    동일하다 — POLL_SCRIPT 하나가 두 변형 모두를 그대로 제어한다."""
    items = d.get("items", [])
    options = "\n".join(
        f'    <li><button class="poll-option poll-pill flex items-center justify-between '
        f'rounded-full border px-4 py-2" data-poll-option>'
        f'<span>{esc(x)}</span>'
        f'<span class="poll-bar" data-poll-bar></span>'
        f'<span class="poll-pct rounded-full bg-gray-100 px-2 text-xs" data-poll-pct></span>'
        f'</button></li>'
        for x in items
    )
    return f"""<section data-block="poll" class="mx-auto max-w-screen-md px-4 py-10">
  <h2 class="mb-4 text-xl font-bold">{esc(d["question"])}</h2>
  <ul class="poll-options space-y-2" data-poll-group>
{options}
  </ul>
  <p class="poll-note mt-3 text-sm text-gray-500" data-poll-note hidden>투표해 주셔서 감사합니다.</p>
</section>"""


POLL_SCRIPT = """<script>
(function(){
  document.querySelectorAll('[data-block="poll"]').forEach(function(container, pollIdx){
    var group = container.querySelector('[data-poll-group]');
    var buttons = Array.prototype.slice.call(group.querySelectorAll('[data-poll-option]'));
    var storeKey = 'poll-votes-' + pollIdx;
    var votedKey = 'poll-voted-' + pollIdx;
    var counts = JSON.parse(localStorage.getItem(storeKey) || 'null') || buttons.map(function(){ return 0; });

    function render(){
      var total = counts.reduce(function(a,b){ return a+b; }, 0) || 1;
      buttons.forEach(function(btn, i){
        var pct = Math.round(counts[i] / total * 100);
        btn.querySelector('[data-poll-bar]').style.width = pct + '%';
        btn.querySelector('[data-poll-pct]').textContent = pct + '%';
      });
    }

    if (localStorage.getItem(votedKey)) {
      render();
      container.querySelector('[data-poll-note]').hidden = false;
      buttons.forEach(function(btn){ btn.disabled = true; });
    }

    buttons.forEach(function(btn, i){
      btn.addEventListener('click', function(){
        if (localStorage.getItem(votedKey)) return;
        counts[i] += 1;
        localStorage.setItem(storeKey, JSON.stringify(counts));
        localStorage.setItem(votedKey, '1');
        render();
        container.querySelector('[data-poll-note]').hidden = false;
        buttons.forEach(function(b){ b.disabled = true; });
      });
    });
  });
})();
</script>"""


def rating_stars(d):
    """별점 — LLM은 질문 문구 하나만 낸다. 별 5개·클릭 처리·감사 메시지는
    전부 고정 마크업+RATING_SCRIPT가 담당(별 개수를 LLM이 정하지 않음)."""
    stars = "\n".join(
        f'    <button class="star" data-star-value="{i}" aria-label="{i}점">★</button>'
        for i in range(1, 6)
    )
    return f"""<section data-block="rating">
  <h2>{esc(d["prompt"])}</h2>
  <div class="star-rating" data-star-group role="radiogroup">
{stars}
  </div>
  <p class="star-thanks" data-star-thanks hidden>평가해 주셔서 감사합니다!</p>
</section>"""


def rating_numbered_scale(d):
    """MerakiUI풍 — 별 대신 1~5 원형 숫자 배지로 된 척도.
    data-* 계약(data-star-group/data-star-value/data-star-thanks)은
    stars 변형과 동일하다 — RATING_SCRIPT 하나가 두 변형 모두를 그대로
    제어한다(script는 문자 내용이 아니라 속성만 본다)."""
    scale = "\n".join(
        f'    <button class="star star-num flex h-9 w-9 items-center justify-center '
        f'rounded-full border" data-star-value="{i}" aria-label="{i}점">{i}</button>'
        for i in range(1, 6)
    )
    return f"""<section data-block="rating" class="mx-auto max-w-screen-md px-4 py-10 text-center">
  <h2 class="mb-4 text-xl font-bold">{esc(d["prompt"])}</h2>
  <div class="star-rating flex justify-center gap-2" data-star-group role="radiogroup">
{scale}
  </div>
  <p class="star-thanks mt-3 text-sm text-gray-500" data-star-thanks hidden>평가해 주셔서 감사합니다!</p>
</section>"""


RATING_SCRIPT = """<script>
(function(){
  document.querySelectorAll('[data-block="rating"]').forEach(function(container, idx){
    var group = container.querySelector('[data-star-group]');
    var stars = Array.prototype.slice.call(group.querySelectorAll('[data-star-value]'));
    var thanks = container.querySelector('[data-star-thanks]');
    var storeKey = 'rating-value-' + idx;

    function paint(value){
      stars.forEach(function(s){
        s.classList.toggle('selected', Number(s.getAttribute('data-star-value')) <= value);
      });
    }

    var saved = localStorage.getItem(storeKey);
    if (saved) { paint(Number(saved)); thanks.hidden = false; }

    stars.forEach(function(star){
      star.addEventListener('click', function(){
        var value = Number(star.getAttribute('data-star-value'));
        localStorage.setItem(storeKey, String(value));
        paint(value);
        thanks.hidden = false;
      });
    });
  });
})();
</script>"""


def coupon_copy(d):
    """쿠폰 코드 복사 — LLM은 코드 문자열과 설명 문구만 낸다. 클립보드
    복사·"복사됨" 피드백은 COUPON_SCRIPT가 담당(Clipboard API 직접 호출을
    LLM이 만들 필요 없음)."""
    return f"""<section data-block="coupon">
  <p>{esc(d["desc"])}</p>
  <div class="coupon-box">
    <span class="coupon-code" data-coupon-code>{esc(d["code"])}</span>
    <button class="coupon-copy-btn" data-coupon-copy>코드 복사</button>
  </div>
</section>"""


def coupon_flowbite_banner(d):
    """Flowbite풍 — 중앙 정렬 배너형, 코드가 큰 글씨로 강조되고 버튼이 아래.
    data-* 계약(data-coupon-code/data-coupon-copy)은 copy 변형과
    동일하다 — COUPON_SCRIPT 하나가 두 변형 모두를 그대로 제어한다."""
    return f"""<section data-block="coupon" class="bg-blue-50 py-10 text-center">
  <div class="mx-auto max-w-screen-sm px-4">
    <p class="mb-3 text-gray-700">{esc(d["desc"])}</p>
    <span class="coupon-code inline-block rounded-lg border-2 border-dashed border-blue-400 px-6 py-3 text-2xl font-bold tracking-widest text-blue-700" data-coupon-code>{esc(d["code"])}</span>
    <div class="mt-3">
      <button class="coupon-copy-btn rounded-lg bg-blue-700 px-6 py-2 text-sm font-medium text-white" data-coupon-copy>코드 복사</button>
    </div>
  </div>
</section>"""


COUPON_SCRIPT = """<script>
(function(){
  document.querySelectorAll('[data-block="coupon"]').forEach(function(container){
    var btn = container.querySelector('[data-coupon-copy]');
    var code = container.querySelector('[data-coupon-code]');
    var original = btn.textContent;
    btn.addEventListener('click', function(){
      var text = code.textContent;
      function done(){
        btn.textContent = '복사됨!';
        setTimeout(function(){ btn.textContent = original; }, 2000);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done).catch(done);
      } else {
        done();
      }
    });
  });
})();
</script>"""


def checklist_progress(d):
    """참여 체크리스트 — LLM은 항목(items, 2~4개)만 낸다. 체크 시 진행률
    바 갱신·로컬 저장은 CHECKLIST_SCRIPT가 담당."""
    items = d.get("items", [])
    li = "\n".join(
        f'    <li><label><input type="checkbox" data-checklist-item> {esc(x)}</label></li>'
        for x in items
    )
    return f"""<section data-block="checklist">
  <h2>참여 체크리스트</h2>
  <ul class="checklist-items">
{li}
  </ul>
  <div class="checklist-progress-track">
    <div class="checklist-progress-bar" data-checklist-progress style="width:0%"></div>
  </div>
</section>"""


def checklist_cards(d):
    """HyperUI풍 — 항목마다 카드로 분리, 진행률은 바 대신 "N/M 완료" 뱃지.
    data-* 계약(data-checklist-item/data-checklist-progress)은 progress
    변형과 동일하다 — 단, 진행률 표시가 width%가 아니라 텍스트이므로
    CHECKLIST_SCRIPT가 data-checklist-progress 요소의 종류(div vs span)를
    안 가리고 textContent와 style.width를 둘 다 시도하도록 만든다."""
    items = d.get("items", [])
    cards = "\n".join(
        f'    <li class="rounded-lg border p-3"><label class="flex items-center gap-2">'
        f'<input type="checkbox" data-checklist-item> {esc(x)}</label></li>'
        for x in items
    )
    return f"""<section data-block="checklist" class="mx-auto max-w-screen-md px-4 py-10">
  <h2 class="mb-4 text-xl font-bold">참여 체크리스트</h2>
  <ul class="checklist-items grid gap-2 sm:grid-cols-2">
{cards}
  </ul>
  <p class="checklist-progress-badge mt-3 text-sm text-gray-600" data-checklist-progress></p>
</section>"""


CHECKLIST_SCRIPT = """<script>
(function(){
  document.querySelectorAll('[data-block="checklist"]').forEach(function(container, idx){
    var boxes = Array.prototype.slice.call(container.querySelectorAll('[data-checklist-item]'));
    var bar = container.querySelector('[data-checklist-progress]');
    var storeKey = 'checklist-state-' + idx;

    function update(save){
      var checked = boxes.filter(function(b){ return b.checked; }).length;
      // progress 변형(바)·cards 변형(텍스트 뱃지) 둘 다 같은 data-checklist-progress
      // 요소를 쓰므로 두 표현을 모두 갱신한다 — 태그 종류를 안 가린다.
      bar.style.width = Math.round(checked / boxes.length * 100) + '%';
      bar.textContent = checked + '/' + boxes.length + ' 완료';
      if (save) {
        localStorage.setItem(storeKey, JSON.stringify(boxes.map(function(b){ return b.checked; })));
      }
    }

    var saved = JSON.parse(localStorage.getItem(storeKey) || 'null');
    if (saved) {
      boxes.forEach(function(b, i){ b.checked = !!saved[i]; });
    }
    update(false);

    boxes.forEach(function(box){
      box.addEventListener('change', function(){ update(true); });
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

POLL_VARIANTS = [
    ("vote", "클릭 투표 + 실시간 득표율 (JS로 집계·재투표 방지)", ("question", "items"), poll_vote),
    ("flowbite_pills", "Flowbite풍 — 알약 버튼 옵션 + 배지형 퍼센트", ("question", "items"), poll_flowbite_pills),
]

RATING_VARIANTS = [
    ("stars", "5점 별점 평가 (JS로 클릭 처리·로컬 저장)", ("prompt",), rating_stars),
    ("merakiui_numbered", "MerakiUI풍 — 별 대신 1~5 숫자 원형 배지", ("prompt",), rating_numbered_scale),
]

COUPON_VARIANTS = [
    ("copy", "쿠폰 코드 클립보드 복사 (JS로 Clipboard API 호출)", ("code", "desc"), coupon_copy),
    ("flowbite_banner", "Flowbite풍 — 중앙 정렬 배너형 쿠폰", ("code", "desc"), coupon_flowbite_banner),
]

CHECKLIST_VARIANTS = [
    ("progress", "체크박스 + 진행률 바 (JS로 진행률 갱신·로컬 저장)", ("items",), checklist_progress),
    ("hyperui_cards", "HyperUI풍 — 카드형 항목 + 'N/M 완료' 텍스트 뱃지", ("items",), checklist_cards),
]

CAROUSEL_VARIANTS = [
    ("slides", "이전/다음·점 네비게이션 캐러셀 (JS로 슬라이드 전환)", ("items",), carousel_slides),
    ("flowbite_fade", "Flowbite풍 — 페이드 캐러셀 + 숫자 뱃지 인디케이터", ("items",), carousel_flowbite_fade),
]
