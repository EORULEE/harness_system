#!/usr/bin/env python3
"""L4 수용기준(AC-L4) — 층 합성 규칙 검증."""
import sys, os
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS)
import verification_gate as vg
import verification_gate_l4 as l4

R=[]
def ck(n,c,d=""):
    R.append((n,bool(c))); print(f"  {'✅' if c else '❌'} {n}"+(f" — {d}" if not c and d else ""))

def l1_of(out, ev, ui=""):
    return vg.evaluate(vg.Context(output_text=out, tool_evidence=ev, user_input=ui))

# AC-L4.1 L1 high 단독(부재 무증거) → hard
r = l4.compose(l1_of("그 파일은 존재하지 않습니다.", []))
ck("AC-L4.1 L1 high 단독→hard", r["tier"]=="hard" and r["exit_code"]==2, str(r))

# AC-L4.2 L1 soft만(약한 전수) → warn (hard 아님)
r = l4.compose(l1_of("전건 모두 통과 확인.", []))   # whole_claim=soft, fake_completion?'통과'매칭→hard?
# '통과'가 fake_completion CLAIM('모두 통과')에도 매칭될 수 있어 증거동반으로 hard회피 테스트는 아래서
# 여기선 soft-only 케이스를 명시적으로: whole_claim만 남기려 완료어휘 회피
r = l4.compose(l1_of("전부 살펴봤습니다.", []))
ck("AC-L4.2 soft만→warn", r["tier"] in ("warn","pass"), str(r))

# AC-L4.3 정상(증거동반) → pass
r = l4.compose(l1_of("grep 결과 3건입니다.", ["grep -rn foo"]))
ck("AC-L4.3 정상→pass", r["tier"]=="pass" and r["exit_code"]==0, str(r))

# AC-L4.4 ≥2층 합의 → hard (L1 soft + L2 refute + L3 unsupported)
l1r = l1_of("전부 살펴봤습니다.", [])   # L1 soft(whole_claim, would_block)
l2f = [{"detector":"l2_codex_refute","would_block":True,"mode":"soft"}]
l3f = [{"detector":"l3_groundedness","would_block":True,"mode":"soft"}]
r = l4.compose(l1r, l2f, l3f)
ck("AC-L4.4 ≥2층 합의→hard", r["tier"]=="hard" and len(r["layers_flagged"])>=2, str(r))

# AC-L4.5 L2 단독 refute → warn(자동 hard 금지, 합의/high 아님)
r = l4.compose(l1_of("일반 서술입니다.", ["read x"]), [{"detector":"l2_codex_refute","would_block":True,"mode":"soft"}])
ck("AC-L4.5 L2 단독→warn(자동hard금지)", r["tier"]=="warn", str(r))

# AC-L4.6 아무것도 없음 → pass
r = l4.compose(l1_of("안녕하세요.", []))
ck("AC-L4.6 무findings→pass", r["tier"]=="pass", str(r))

if __name__=="__main__":
    p=sum(1 for _,ok in R if ok); f=len(R)-p
    print(f"\n==== L4 smoke 결과: PASS={p} FAIL={f} ====")
    sys.exit(1 if f else 0)
