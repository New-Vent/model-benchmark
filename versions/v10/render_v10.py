"""
render_v10.py — 저장된 블록 조각을 **열어볼 수 있는 페이지**로 만든다. 0원.
==============================================================================

## 왜 필요한가

v8~v10 이 남긴 건 `.txt` 블록 조각과 `.csv` 실패 코드뿐이다.
**완성된 페이지가 하나도 없어서 지금껏 결과를 눈으로 본 적이 없다.**

v10 의 D 군은 "디자인이 깨지는가" 를 재는 축인데, 재는 방법은 이렇다.

    class_changed_root          클래스 문자열 비교
    item_count(.benefit-card)   선택자로 개수 세기

전부 **대리 지표**다. 화면을 본 적이 없으니 두 방향으로 다 틀릴 수 있다.

    검사 통과 · 화면 깨짐    .benefit-card 는 살아있는데 안쪽이 바뀐 경우
    검사 실패 · 화면 멀쩡    어제 실제로 났다 — 오탐 4건으로 12/27 까지 떨어졌고
                             원문을 눈으로 봤으면 5분에 알았을 것들이었다

## 무엇을 하나

    raw_v10/<stamp>/D_D1_r1_a1.txt        블록 조각 (지금 있는 것)
        ↓ sanitize_edited → merge(원본 문서)
    rendered_v10/<모델>/D1_r1.html        열리는 페이지 (만드는 것)

`event.css` 는 외부 `<link>` 라 상대경로만 고쳐주면 브라우저에서 바로 열린다.
템플릿의 `<script>` 는 인라인이라 건드릴 게 없다.

★ **페이지 자체는 손대지 않는다.** 어느 블록을 고쳤는지 표시하려고 테두리를
  그리면 레이아웃 문제를 가릴 수 있다. 표시는 `index.html` 쪽에만 둔다.

## 실행

    python render_v10.py                  # 1차(a1)만 — 기본
    python render_v10.py --all-attempts   # 재시도까지 (피드백이 오염돼 있음)
"""

import argparse
import glob
import html as _html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cases_v10 as CS        # noqa: E402
import checks_v10 as C        # noqa: E402
import rescore_v10 as RS      # noqa: E402
import templates_v10 as T     # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(HERE, "raw_v10")
OUT_DIR = os.path.join(HERE, "rendered_v10")
CSS_SRC = os.path.join(T.TEMPLATE_DIR, "event.css")


def full_doc(n: int) -> str:
    """템플릿 n 의 **문서 전체**. block_html() 은 블록만 주므로 여기서 따로 읽는다."""
    paths = sorted(glob.glob(os.path.join(T.TEMPLATE_DIR, f"template_{n}_*.html")))
    return open(paths[0], encoding="utf-8").read()


# ★ 꺾쇠를 쓰면 안 된다. BeautifulSoup 이 텍스트 노드를 직렬화할 때
#   `<!--...-->` 를 `&lt;!--...--&gt;` 로 이스케이프해서 치환이 또 실패한다.
#   (첫 시도에서 77개 전부 스타일이 빠졌다.) 맨 토큰이어야 한다.
_CSS_MARK = "NEWVENT_CSS_PLACEHOLDER_4f21"


def fix_css(doc: str, out_path: str) -> str:
    """`<link rel=stylesheet>` 를 **인라인 `<style>`** 로 바꾼다.

    ★ 상대경로로 바꾸는 것부터 해봤는데 안 된다. 뷰어에 따라 로컬 파일의
      형제 리소스를 안 읽어주고(`file:` 샌드박스·스냅샷 렌더), 그러면
      **스타일 없는 날것**이 뜬다. 디자인을 보려고 만든 파일이 디자인 없이
      열리는 셈이라, 파일 하나로 완결되게 박아 넣는다.

    ★ 문자열 치환으로 하면 안 된다 (실측으로 밟았다)
      `merge()` 가 BeautifulSoup 으로 문서를 다시 직렬화하면서 링크가
      `<link href="./event.css" rel="stylesheet"/>` 로 **속성 순서가 바뀌고
      자기닫힘**이 된다. 원본 문자열과 안 맞아 치환이 조용히 실패하고,
      원본 5종만 스타일이 먹고 결과 72개는 날것으로 뜬다.
      그래서 **태그를 찾아서** 바꾼다.

    ★ 자리표시자를 거치는 이유
      `<style>` 안에 CSS 를 BeautifulSoup 으로 직접 넣으면 `>` 같은 문자가
      이스케이프될 수 있다. 주석 하나로 자리만 잡고 마지막에 끼워 넣는다.
    """
    soup = C._soup(doc)
    link = soup.select_one('link[rel="stylesheet"]')
    if link is None:
        return doc
    link.replace_with(soup.new_string(_CSS_MARK))
    css = open(CSS_SRC, encoding="utf-8").read()
    return str(soup).replace(_CSS_MARK, f"<style>\n{css}\n</style>")


def render_one(case, raw: str, out_path: str) -> str:
    """블록 조각을 원본 문서에 끼워 넣어 완성 페이지로."""
    block = C.sanitize_edited(C.extract(raw))
    doc = C.merge(full_doc(case.tpl), case.target, block)
    doc = fix_css(doc, out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)
    return block


def render_originals():
    """대조용 원본 5종 — 손대지 않은 템플릿."""
    for n, name in T.NAMES.items():
        out = os.path.join(OUT_DIR, "_원본", f"template_{n}_{name}.html")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(fix_css(full_doc(n), out))


ROW = """    <tr class="{cls}">
      <td>{pid}</td><td>{group}</td><td>{tpl}/{block}</td>
      <td>{mark}</td><td class="f">{fails}</td>
      <td><a href="{href}" target="_blank">결과</a></td>
      <td><a href="{orig}" target="_blank">원본</a></td>
      <td class="q">{ask}</td>
    </tr>"""

STYLE = """
 body{font:14px/1.6 -apple-system,sans-serif;margin:2rem;max-width:1100px}
 h2{margin-top:2.5rem;border-bottom:2px solid #333;padding-bottom:.3rem}
 table{border-collapse:collapse;width:100%;margin-top:.8rem}
 td,th{border:1px solid #ddd;padding:.4rem .6rem;text-align:left}
 th{background:#f5f5f5}
 tr.fail{background:#fff3f3}
 td.f{font:12px ui-monospace,monospace;color:#c00;max-width:340px}
 td.q{font-size:12px;color:#a60}
 .note{background:#f9f9f9;border-left:3px solid #999;padding:.7rem 1rem;margin:1rem 0}
"""


def write_index(per_model, null_pass):
    rows = []
    for name, items in per_model.items():
        n_ok = sum(1 for i in items if i["ok"])
        rows.append(f"  <h2>{_html.escape(name)} — 1차 {n_ok}/{len(items)}</h2>")
        rows.append("  <table><tr><th>케이스</th><th>군</th><th>템플릿/블록</th>"
                    "<th>판정</th><th>실패 코드</th><th></th><th></th>"
                    "<th>눈으로 볼 것</th></tr>")
        for i in items:
            rows.append(ROW.format(
                cls="" if i["ok"] else "fail",
                pid=i["pid"], group=i["group"], tpl=i["tpl"], block=i["block"],
                mark="✓" if i["ok"] else "✗",
                fails=_html.escape(i["fails"]),
                href=i["href"], orig=i["orig"],
                ask=("검사가 통과시킨 게 화면에서도 맞나"
                     if i["ok"] and i["pid"] in null_pass else
                     "" if i["ok"] else "검사가 잡은 게 화면에서도 보이나")))
        rows.append("  </table>")

    body = "\n".join(rows)
    note = (f"<div class=note><b>무변경으로도 통과하는 케이스: "
            f"{', '.join(sorted(null_pass))}</b><br>"
            f"이 케이스의 ✓ 는 '잘했다' 가 아니라 '안 부쉈다' 는 뜻입니다.</div>")
    out = os.path.join(OUT_DIR, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"<!DOCTYPE html><html lang=ko><head><meta charset=UTF-8>"
                f"<title>v10 렌더 결과</title><style>{STYLE}</style></head><body>"
                f"<h1>v10 — 저장된 원문을 페이지로 (1차)</h1>{note}{body}"
                f"</body></html>")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all-attempts", action="store_true")
    args = ap.parse_args()

    render_originals()
    null_pass = {c.pid for c in CS.CASES if not RS.backend_score(c, c.before)}

    per_model, total = {}, 0
    for stamp in sorted(os.listdir(RAW_DIR)):
        d = os.path.join(RAW_DIR, stamp)
        if not os.path.isdir(d):
            continue
        name = RS.SHORT.get(RS.model_of(stamp), stamp)
        items = []
        for path in sorted(glob.glob(os.path.join(d, "*.txt"))):
            m = RS.RAW_NAME.match(os.path.basename(path))
            if not m:
                continue
            att = int(m["att"])
            if not args.all_attempts and att != 1:
                continue
            case = RS.BY_PID.get(m["pid"])
            if case is None:
                continue

            stem = f"{case.pid}_r{m['rep']}" + (f"_a{att}" if args.all_attempts else "")
            out = os.path.join(OUT_DIR, name, f"{stem}.html")
            block = render_one(case, open(path, encoding="utf-8").read(), out)
            total += 1

            fails = RS.backend_score(case, block)
            orig = os.path.join(OUT_DIR, "_원본",
                                f"template_{case.tpl}_{T.NAMES[case.tpl]}.html")
            items.append(dict(
                pid=case.pid, group=case.group, tpl=T.NAMES[case.tpl],
                block=case.block, ok=not fails,
                fails="|".join(k for k, _ in fails),
                href=os.path.relpath(out, OUT_DIR),
                orig=os.path.relpath(orig, OUT_DIR)))
        if items:
            per_model[name] = items

    idx = write_index(per_model, null_pass)
    print(f"  페이지 {total}개 + 원본 {len(T.NAMES)}개 · 호출 0회 · 비용 0원")
    for name, items in per_model.items():
        print(f"    {name:10} {sum(1 for i in items if i['ok'])}/{len(items)}")
    print(f"\n  열어보기: {idx}")


if __name__ == "__main__":
    main()
