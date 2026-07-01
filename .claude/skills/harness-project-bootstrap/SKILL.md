---
name: harness-project-bootstrap
description: "LEEER 새 프로젝트의 표준 구조(README·PROJECT.yaml·Data/Code/Experiments/Report/Wiki/_claude)를 결정적으로 생성. 같은 입력→동일 구조(Linux/WSL/Windows), 2회 실행은 덮어쓰기·중복 없음(idempotent). 기본 dry-run, --apply 는 사용자 승인 후. 기존 프로젝트 migration 미사용. '새 LEEER 프로젝트 만들어' 시 명시 호출."
disable-model-invocation: true
allowed-tools: [Bash, Read]
argument-hint: "--project-id <id> --title <t> --root <dir> [--machine-profile euru] [--owner <o>]"
---

# harness-project-bootstrap — LEEER 프로젝트 결정적 생성 (명시 호출 전용)

> 새 프로젝트 **구조만** 결정적으로 생성. 구조 SoT = `docs/leeer-storage-design.md §2` + `leeer-llm-wiki-guide.md §8` + `leeer-experiment-registry-design.md §6` + `_templates/`. 새 폴더 체계 임의 생성 금지.
> 엔진 = `scripts/leeer_project_bootstrap.py`. 검증 = `tests/smoke_leeer_project_bootstrap.sh`(10 assert). 최종권위 = stop-guard·hookify.

## 언제
- **새 LEEER 프로젝트 1개** 표준 골격 생성. (기존 프로젝트 **migration·재구성에는 사용 안 함** — 그건 storage-audit + 사람 승인.)

## 절차 (반자동 — 승인 게이트)
1. **먼저 dry-run**(기본): `python3 scripts/leeer_project_bootstrap.py --project-id <id> --title "<t>" --root <dir> [--machine-profile <p>] [--owner <o>]`
   → CREATE/EXISTS/CONFLICT 표 + `=== MANIFEST ===`(상대경로+sha256) 계획을 **사용자에게 제시**. 쓰기 0.
2. **사용자 승인 후에만** 동일 명령에 **`--apply`** 추가 실행.
3. apply 후 **검증**: `bash tests/smoke_leeer_project_bootstrap.sh`(10/10) + 생성된 `<root>/<id>/_claude/bootstrap-manifest.json`·`tree.txt` 확인.

## 안전 불변(엔진이 강제)
- 기본 dry-run · `--apply` 없이는 **쓰기 0**.
- 기존 파일 **이동·삭제·rename·덮어쓰기 금지**. 기존≠생성예정 → **CONFLICT(exit 3, HOLD)**, 미기록.
- **원본 데이터 미생성/미복사** — raw 는 `Data/manifests/data_manifest.csv` + 디렉토리 골격만.
- 머신 절대경로 **하드코딩 없음**(`--root` 인자 + `00_REGISTRY/mount_map·storage_map` registry 상대). PROJECT.yaml 경로는 루트 상대.
- secret/token 생성·기록 안 함 · 출력·manifest 순서 결정적(정렬).

## PROJECT.yaml (`schema_version: leeer-project/v1`)
`project_id·title·status·owner·created_at·storage_profile·paths{data,code,experiments,report,wiki}·nas_path·keep_out`.

## 비고
- 생성 후 사용자가 PROJECT.yaml(title/owner 등)을 편집하면, 재실행 시 그 파일은 **CONFLICT→보존**(덮어쓰지 않음)이 정상.
- 실제 연구 프로젝트 생성은 사용자 승인 + 올바른 `--root`(예: NAS staging `_output/leeer-apply/` 또는 머신 projects 루트)에서만.
