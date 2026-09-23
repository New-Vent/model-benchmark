"""
registry_v11.py — 백엔드 `com.newvent.registry` 미러
====================================================

v8은 v1~v7과 달리 **벤치마크 고유 규격을 쓰지 않는다.** 실제 백엔드가 쓰는
블록 정의를 그대로 옮겨서, 여기서 통과한 것이 서비스에서도 통과하게 만든다.

원본 (backend/src/main/java/com/newvent/registry/)
    Block.java   블록 5종 + shape/must/minItems/source
    Slot.java    슬롯 2종 — 서버가 폼 값으로 채우는 자리

★ 왜 template/*.html 을 안 쓰는가
    v4~v7은 디자이너 템플릿 5종을 baseline 으로 썼다. 그런데 백엔드가 실제로
    모델에게 시키는 형태는 `Block.shape` 이다 — 예를 들어 cta 는
    `<a href="#" class="btn">` 이고, 템플릿은 `<button class="cta-btn">` 이다.
    둘은 다른 물건이라 섞으면 또 v4 때처럼 채점이 틀어진다.
    v8 의 기준은 **백엔드 레지스트리 하나뿐이다.**

★ 이 파일을 고칠 일이 생기면 Block.java 도 같이 고쳐야 한다.
    `self_check()` 가 Java 원본과 어긋나는지까지는 자동으로 못 본다 —
    둘 다 사람이 맞춰야 한다. (백엔드 PR 과 v8 이 갈라지는 걸 막는 유일한 장치)
"""

from dataclasses import dataclass

# ── Source — 누가 내용을 만드는가 (Block.Source)
LLM = "LLM"        # 모델이 전부 만든다
SERVER = "SERVER"  # 서버가 채운다. 모델은 만들면 안 된다
MIXED = "MIXED"    # 값은 폼·서버, 문장만 모델


@dataclass(frozen=True)
class Block:
    key: str
    required: bool
    source: str
    desc: str
    shape: str | None   # 모델에게 시키는 말
    must: str | None    # 그게 지켜졌는지 보는 CSS 선택자
    min_items: int

    def selector(self) -> str:
        return f'[data-block="{self.key}"]'

    def can_edit(self) -> bool:
        return self.source != SERVER

    def can_delete(self) -> bool:
        return not self.required

    def can_create(self) -> bool:
        return self.source != SERVER and not self.required


# ★ PERIOD 는 블록이 아니라 슬롯이다 (아래 SLOTS).
BLOCKS = [
    Block("hero", True, MIXED,
          "이벤트 제목과 한 줄 소개. 기간은 서버가 넣는다",
          "제목은 <h1>, 소개는 <p> 로 감싼다",
          "h1", 0),

    Block("benefits", True, MIXED,
          "혜택 — 항목은 폼 값, 문장만 다듬는다",
          "<ul> 안에 <li> 로 항목을 나열한다. 2개 이상",
          "ul li, .benefit-card", 2),

    Block("steps", False, LLM,
          "참여 방법 2~4단계",
          "<ol> 안에 <li> 로 순서대로 나열한다",
          "ol li, .step-card", 2),

    Block("notices", True, SERVER,
          "유의사항 — 승인된 문구만 서버가 삽입",
          None, None, 0),

    Block("cta", True, MIXED,
          "참여 버튼. 문구만 생성, 링크는 폼 값",
          '<a href="#" class="btn"> 안에 버튼 문구를 넣는다',
          "a, button", 0),
]

BY_KEY = {b.key: b for b in BLOCKS}


def of(key: str) -> Block:
    if key not in BY_KEY:
        raise ValueError(f"없는 블록: {key}")
    return BY_KEY[key]


def llm_blocks() -> list:
    """모델이 만드는 블록 (SERVER 제외)"""
    return [b for b in BLOCKS if b.source != SERVER]


def server_blocks() -> list:
    """서버가 채우는 블록 — 모델 출력을 무시하고 덮어쓴다"""
    return [b for b in BLOCKS if b.source == SERVER]


# ── 슬롯 — 서버가 폼 값으로 채우는 자리. 블록이 아니다.
#
#   블록(data-block)  문단 단위.  LLM 이 만들고, 채팅으로 고칠 수 있다
#   슬롯(data-slot)   값 하나.    서버만 채우고, 채팅 대상이 아니다
#
# ★ 생성과 수정에서 규칙이 정반대다 (백엔드 PR 의 ①번 수정 사유)
#     생성: 모델이 슬롯을 만들면 안 된다   — 서버의 쓰기 지점을 모델이 정하면 안 되니까
#     수정: 원본에 있던 슬롯을 지켜야 한다 — 지우면 서버가 값을 못 넣으니까
@dataclass(frozen=True)
class Slot:
    key: str
    desc: str

    def selector(self) -> str:
        return f'[data-slot="{self.key}"]'


SLOTS = [
    Slot("period", "이벤트 기간"),      # 폼의 start_at ~ end_at
    Slot("cta-link", "참여 링크"),      # <a> 면 href, <button> 이면 data-href
]

SLOT_KEYS = {s.key for s in SLOTS}


def assert_consistent():
    """Block.assertConsistent() 이식 — shape 와 must 는 짝이어야 한다."""
    for b in BLOCKS:
        has_shape = bool(b.shape and b.shape.strip())
        has_must = bool(b.must and b.must.strip())
        assert has_shape == has_must, (
            f"{b.key}: shape 와 must 는 짝이어야 합니다 "
            f"(shape={has_shape}, must={has_must})")
        assert not (b.source == SERVER and has_shape), (
            f"{b.key}: SERVER 블록에 shape 를 주면 안 됩니다. 모델이 만들게 됩니다.")
        assert not (b.min_items > 0 and not has_must), (
            f"{b.key}: min_items 를 세려면 must 가 필요합니다.")


def self_check():
    assert_consistent()
    assert [b.key for b in BLOCKS] == ["hero", "benefits", "steps", "notices", "cta"]
    assert [b.key for b in llm_blocks()] == ["hero", "benefits", "steps", "cta"]
    assert [b.key for b in server_blocks()] == ["notices"]
    # ★ must 는 v9 보다 넓다 — "시키는 말은 하나, 받아주는 모양은 여럿".
    #   템플릿 5종은 cta 를 <button> 으로, benefits 를 .benefit-card 로 만든다.
    #   좁게 두면 실제 마크업이 전부 empty_* 로 떨어진다(v4 에서 겪음).
    assert of("cta").must == "a, button"
    assert of("benefits").must == "ul li, .benefit-card"
    assert of("steps").must == "ol li, .step-card"
    assert of("benefits").min_items == 2
    assert not of("steps").required and of("steps").can_delete()
    assert not of("notices").can_edit()
    assert SLOT_KEYS == {"period", "cta-link"}
    print("  [registry_v11] self_check 통과")


if __name__ == "__main__":
    self_check()
