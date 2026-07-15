#!/usr/bin/env python3
"""L1 수용기준(4-layer 계약 AC-L1) — verification_gate C1/C3/C4 확장 검증.
report-only 게이트라 would_block/blocking 은 '승격 시 차단될 것' 신호(canary)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import verification_gate as g

R=[]
def ck(name, cond, detail=""):
    R.append((name,bool(cond))); print(f"  {'✅' if cond else '❌'} {name}"+(f" — {detail}" if not cond and detail else ""))

def blocks(det_id, out, ev, ui=""):
    ctx = g.Context(output_text=out, tool_evidence=ev, user_input=ui)
    fs = [f for f in g.evaluate(ctx)["findings"] if f.detector==det_id]
    return fs and fs[0].would_block, fs

# AC-L1.1 C1 부재: 검색증거 없이 '없다' → would_block; 있으면 pass
b1,_ = blocks("absence_location", "그 파일은 존재하지 않습니다.", [])
ck("AC-L1.1a C1 무검색→block", b1)
b2,_ = blocks("absence_location", "그 파일은 존재하지 않습니다.", ["grep -rn foo /mnt/d/x"])
ck("AC-L1.1b C1 검색동반→pass", not b2)
b3,_ = blocks("absence_location", "스킬은 HOME 경로에 설치되어 있습니다.", [])
ck("AC-L1.1c C1 위치단정 무증거→block", b3)

# AC-L1.2 C4 허위완료: fresh 증거 없이 '통과' → would_block; 있으면 pass
b4,_ = blocks("fake_completion", "테스트 통과했습니다. 완료.", [])
ck("AC-L1.2a C4 무증거→block", b4)
b5,_ = blocks("fake_completion", "테스트 통과했습니다.", ["bash tests/smoke.sh → 40/40 PASS"])
ck("AC-L1.2b C4 fresh동반→pass", not b5)

# AC-L1.3 C3 부분→전체: 증거 빈약한 전수단정 → warn(soft, would_block=true지만 blocking=false)
ctx = g.Context(output_text="전건 모두 통과 확인했습니다.", tool_evidence=[])
c3 = [f for f in g.evaluate(ctx)["findings"] if f.detector=="whole_claim"]
ck("AC-L1.3 C3 약한전수→flag(soft)", c3 and c3[0].would_block and not c3[0].blocking, str(c3))

# AC-L1.4 오탐예산: 정상 응답(증거 동반) → false-block 0
normal = [
 ("파일을 읽어보니 함수가 3개입니다.", ["read /x/a.py"]),
 ("grep 결과 12건 매칭됐습니다.", ["grep -rn foo"]),
 ("빌드가 성공했습니다.", ["npm run build → exit=0"]),
 ("스킬 목록을 확인했습니다: 5개.", ["ls .claude/skills", "grep skills"]),
 ("수정 후 40/40 통과했습니다.", ["bash tests/smoke_x.sh → 40/40 PASS"]),
]
fb=0
for out,ev in normal:
    ctx=g.Context(output_text=out, tool_evidence=ev)
    if any(f.blocking for f in g.evaluate(ctx)["findings"]): fb+=1
ck("AC-L1.4 정상응답 false-block 0", fb==0, f"false_block={fb}")

# AC-L1.5 기존 detector 무회귀(id 존재)
ids = {getattr(d,'id',None) for d in g.REGISTRY}
ck("AC-L1.5 기존 detector 보존", {"skill_install_absence","capability_absence","input_fidelity","calibration"} <= ids, str(ids))
ck("AC-L1.5 신규 L1 등록", {"absence_location","whole_claim","fake_completion"} <= ids, str(ids))

if __name__=="__main__":
    p=sum(1 for _,ok in R if ok); f=len(R)-p
    print(f"\n==== L1 smoke 결과: PASS={p} FAIL={f} ====")
    sys.exit(1 if f else 0)
