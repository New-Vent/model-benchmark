"""
run.py — 공통 진입점 (base/)
============================

버전 폴더(versions/v1, versions/v2)에 흩어져 있는 케이스 스크립트를
찾아서 실행한다. 공통 코드(engine·registry·checks·component_library)는
전부 이 base/ 폴더에만 있고, 버전 폴더에는 cases_*.py만 둔다.

    base/
      run.py  engine.py  registry.py  checks.py  component_library.py
    versions/v1/
      cases_d.py  cases_e.py  cases_js.py  cases_ns.py  cases_c.py  cases_r.py
      result_csv/   result_json/   raw_v1/
    versions/v2/
      cases_j.py  cases_k.py  cases_chain.py
      result_csv/   result_json/   raw_v2/

## 실행법

    python base/run.py v1              # v1 폴더의 케이스 전부 (D·E·JS·N·S·C·R)
    python base/run.py v1 D            # v1 의 D군만
    python base/run.py v1 N S          # 여러 군 지정
    python base/run.py v2              # v2 폴더의 케이스 전부 (J·K·CHAIN)
    python base/run.py v2 K
    python base/run.py v1 --self-check # LLM 호출 없이 검증만

결과는 그 버전 폴더 안으로 들어간다.

    versions/v1/result_csv/results_v1_<RUNNER>_<타임스탬프>.csv
    versions/v1/result_json/env_v1_<RUNNER>_<타임스탬프>.json
    versions/v1/raw_v1/                시도별 원문 (git 제외)

군만 지정해서 돌린 CSV도 같은 폴더에 쌓인다 — summarize.py가 폴더
하위의 results_*.csv를 전부 읽으므로 나눠 돌려도 합산된다.

## ⚠ cases_j.py(v2)와 cases_ns.py(v1)의 프롬프트 중복 주의

cases_j.py는 원래 cases_ns.py에서 P1/P2/P8/P9를 import해서 J와 N/S가
"정확히 같은 요청 문구"로 공정 비교되게 했었다. 지금은 두 파일이 서로
다른 버전 폴더에 있어서 import로 묶을 수 없고, **같은 문구가 두 군데에
중복 보관**된다.

지금은 두 파일의 P1/P2/P8/P9가 글자 그대로 일치하지만 이는 보장되지
않는다 — 둘 중 하나만 고치면 J(v2)와 N/S(v1)가 "다른 요청"을 비교하게
되어 pair 비교(J1↔S1 등) 자체가 무의미해진다. 프롬프트를 고칠 일이
생기면 반드시 두 파일 다 확인할 것.
"""

import glob
import importlib
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(BASE_DIR)
VERSIONS_DIR = os.path.join(REPO_DIR, "versions")

sys.path.insert(0, BASE_DIR)

import engine  # noqa: E402  (sys.path 세팅 후에 import해야 한다)

# ── 여기 두 개만 본인 환경에 맞게 바꾸세요 ───────────────────────
RUNNER = os.environ.get("RUNNER", "이름을_바꾸세요")
MODELS = [
    "exaone3.5:7.8b",   # 전원 공통(보정 기준) — 반드시 포함
    # "qwen2.5:7b",
    # "gemma3:4b",
    # "qwen3:8b",       # 추론 모델, 별도 축
]
# ──────────────────────────────────────────────────────────────

# 표시·실행 순서. 여기 없는 군은 이름순으로 뒤에 붙는다.
GROUP_ORDER = ["D", "E", "JS", "N", "S", "C", "R", "J", "K", "CHAIN"]

# 사용자가 치기 편한 별칭 → 실제 군 이름
GROUP_ALIASES = {
    "N/S": ["N", "S"],
    "NS": ["N", "S"],
}


def version_dir_of(version: str) -> str:
    path = os.path.join(VERSIONS_DIR, version)
    if not os.path.isdir(path):
        available = sorted(
            d for d in os.listdir(VERSIONS_DIR)
            if os.path.isdir(os.path.join(VERSIONS_DIR, d))
        )
        raise SystemExit(
            f"그런 버전 폴더가 없습니다: versions/{version}\n"
            f"있는 버전: {', '.join(available) or '(없음)'}"
        )
    return path


def discover_case_modules(version_dir: str) -> dict:
    """versions/<버전>/cases_*.py 를 전부 import해서 {모듈명: 모듈}로 돌려준다.

    버전 폴더를 sys.path에 넣으므로 케이스 파일은 예전처럼 평평하게
    `from engine import Case` / `import cases_j` 라고 쓰면 된다.
    """
    if version_dir not in sys.path:
        sys.path.insert(0, version_dir)

    modules = {}
    for path in sorted(glob.glob(os.path.join(version_dir, "cases_*.py"))):
        name = os.path.splitext(os.path.basename(path))[0]
        modules[name] = importlib.import_module(name)
    if not modules:
        raise SystemExit(f"{version_dir} 안에 cases_*.py 가 하나도 없습니다.")
    return modules


def groups_of(module) -> list:
    """모듈이 담당하는 군 이름들.

    1) 모듈이 GROUPS를 선언했으면 그걸 쓴다 (CASES가 빈 스텁용).
    2) 아니면 CASES에 실제로 들어있는 group 값에서 뽑는다.
    3) 둘 다 없으면 파일명에서 유추한다 (cases_d -> D).
    """
    declared = getattr(module, "GROUPS", None)
    if declared:
        return list(declared)

    seen = []
    for case in getattr(module, "CASES", None) or []:
        if case.group not in seen:
            seen.append(case.group)
    if seen:
        return seen

    suffix = module.__name__.replace("cases_", "", 1).upper()
    return GROUP_ALIASES.get(suffix, [suffix])


def sort_key(group: str):
    return (GROUP_ORDER.index(group) if group in GROUP_ORDER else len(GROUP_ORDER),
            group)


def expand_selection(raw_args: list, known_groups: list) -> list:
    """사용자가 준 군 이름을 실제 군 이름 리스트로 편다 (N/S -> N, S)."""
    selected, unknown = [], []
    for arg in raw_args:
        token = arg.strip().upper()
        for group in GROUP_ALIASES.get(token, [token]):
            if group not in known_groups:
                unknown.append(arg)
            elif group not in selected:
                selected.append(group)
    if unknown:
        raise SystemExit(
            f"알 수 없는 군 이름입니다: {unknown}\n"
            f"이 버전에 있는 군: {', '.join(sorted(known_groups, key=sort_key))}"
        )
    return selected


def parse_args(argv: list):
    args = [a for a in argv[1:]]
    self_check_only = "--self-check" in args
    args = [a for a in args if not a.startswith("--")]

    if not args:
        raise SystemExit(
            "버전을 지정하세요.\n"
            "  python base/run.py v1          # v1 전체\n"
            "  python base/run.py v1 D        # v1 의 D군만\n"
            "  python base/run.py v2 K\n"
            "  python base/run.py v1 --self-check"
        )

    version = args[0]
    groups = args[1:]
    if not groups:
        env_value = os.environ.get("RUN_GROUPS", "").strip()
        if env_value:
            groups = [g.strip() for g in env_value.split(",") if g.strip()]
    return version, groups, self_check_only


def main():
    version, requested, self_check_only = parse_args(sys.argv)
    version_dir = version_dir_of(version)

    modules = discover_case_modules(version_dir)

    # 군 -> 그 군을 담당하는 모듈들
    group_to_modules = {}
    for name, module in modules.items():
        for group in groups_of(module):
            group_to_modules.setdefault(group, []).append((name, module))

    known_groups = sorted(group_to_modules, key=sort_key)
    selected_groups = expand_selection(requested, known_groups) if requested else known_groups
    selected_groups.sort(key=sort_key)

    # 실행할 모듈 (같은 모듈이 두 군을 담당하면 한 번만)
    active_modules = {}
    for group in selected_groups:
        for name, module in group_to_modules[group]:
            active_modules.setdefault(name, module)

    print(f"  버전: {version}  ({version_dir})")
    print(f"  군:   {', '.join(selected_groups)}"
          f"{'' if len(selected_groups) == len(known_groups) else '  ← 일부만'}")
    if len(selected_groups) != len(known_groups):
        print(f"    (전체를 돌리려면 군 이름 없이 python base/run.py {version})")
    print()

    if self_check_only:
        engine.self_check_all(active_modules)
        print("  --self-check: LLM 호출 없이 검증만 하고 끝냅니다.")
        return

    engine.main(
        models=MODELS,
        runner=RUNNER,
        case_modules=active_modules,
        version=version,
        version_dir=version_dir,
        group_filter=selected_groups if len(selected_groups) != len(known_groups) else None,
    )


if __name__ == "__main__":
    main()
