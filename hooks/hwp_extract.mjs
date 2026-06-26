#!/usr/bin/env node
// hwp_extract.mjs — rhwp(@rhwp/core) WASM 기반 .hwp/.hwpx 읽기·편집·저장
// 요구: Node 16+ (rhwp WASM multi-value return 사용 — Node 12 불가)
//
// 사용:
//   node hwp_extract.mjs extract <file>                          → 전체 본문 stdout
//   node hwp_extract.mjs search  <file> <query> [case]           → 검색 결과 JSON
//   node hwp_extract.mjs replace <in> <out> <query> <new> [case] → 치환 후 저장
//   node hwp_extract.mjs insert  <in> <out> <sec> <para> <off> <text> → 삽입 후 저장
//   node hwp_extract.mjs <file>                                  → extract (하위호환)
//
// 저장 포맷: <out> 확장자로 결정 (.hwp→exportHwp, .hwpx→exportHwpx)
// ⚠️ 편집(replace/insert) 보존: .hwpx 만 보존됨. .hwp 바이너리 저장은
//    편집을 잃음(rhwp 한계, 2026-05-28 검증). 편집본은 반드시 .hwpx 로 저장.

import { readFileSync, writeFileSync, existsSync } from 'fs';
import { createRequire } from 'module';
import { fileURLToPath } from 'url';
import { dirname, join, extname } from 'path';

const require = createRequire(import.meta.url);

function resolveCore() {
  const here = dirname(fileURLToPath(import.meta.url));
  const candidates = [
    process.env.RHWP_CORE_PATH,
    join(here, 'vendor', 'rhwp', 'rhwp.js'),
    join(here, '..', 'vendor', 'rhwp', 'rhwp.js'),
  ].filter(Boolean);
  for (const c of candidates) {
    if (existsSync(c)) return c;
  }
  try { return require.resolve('@rhwp/core'); } catch (e) { return null; }
}

async function loadDoc(corePath, filePath) {
  const wasmPath = corePath.replace(/rhwp\.js$/, 'rhwp_bg.wasm');
  const mod = await import(corePath);
  const init = mod.default;
  const { HwpDocument } = mod;
  await init({ module_or_path: readFileSync(wasmPath) });
  const data = readFileSync(filePath);
  return { doc: new HwpDocument(new Uint8Array(data)), HwpDocument };
}

function extractText(doc) {
  const out = [];
  const secCount = doc.getSectionCount();
  for (let s = 0; s < secCount; s++) {
    const paraCount = doc.getParagraphCount(s);
    for (let p = 0; p < paraCount; p++) {
      const len = doc.getParagraphLength(s, p);
      if (len <= 0) { out.push(''); continue; }
      let t = doc.getTextRange(s, p, 0, len);
      if (t && t.startsWith('{') && t.includes('"text"')) {
        try { const parsed = JSON.parse(t); t = (parsed && parsed.text) ? parsed.text : ''; } catch (e) { /* plain */ }
      }
      out.push(t || '');
    }
  }
  return out.join('\n');
}

function warnFidelity() {
  // 2026-05-28 실측: rhwp 편집+export는 그림 참조 누락 + 중첩표 평탄화 + 표크기 손실.
  // .hwpx/.hwp 둘 다 영향. 충실도 유지 편집은 pyhwpx(한컴 COM, Windows) 사용.
  process.stderr.write(
    '⚠️ 충실도 경고: rhwp 편집은 텍스트만 안전합니다. '
    + '그림·중첩표·표 크기는 손실됩니다(rhwp v0.7.13 한계). '
    + '원본 충실도가 필요하면 pyhwpx(한컴 COM, Windows)를 쓰세요.\n'
  );
}

function saveDoc(doc, outPath) {
  const ext = extname(outPath).toLowerCase();
  let bytes;
  if (ext === '.hwp') {
    // ⚠️ 검증됨(2026-05-28): exportHwp()는 편집(replace/insert)을 아예 반영 못함
    // ("recovered" 모드 = 원본 복구). 편집 저장은 .hwpx 만 (단 그림/표 손실은 별개).
    process.stderr.write(
      '⚠️ .hwp 저장은 편집을 전혀 반영하지 못합니다(원본 복구 모드). 편집본은 .hwpx 로 저장하세요.\n'
    );
    bytes = doc.exportHwp();
  } else if (ext === '.hwpx') {
    bytes = doc.exportHwpx();
  } else {
    throw new Error(`출력 확장자는 .hwp 또는 .hwpx 여야 함: ${outPath}`);
  }
  writeFileSync(outPath, Buffer.from(bytes));
  return bytes.length;
}

async function main() {
  const argv = process.argv.slice(2);
  if (argv.length === 0) {
    process.stderr.write('usage: extract|search|replace|insert ... (README 참조)\n');
    process.exit(2);
  }

  const corePath = resolveCore();
  if (!corePath) {
    process.stderr.write('[rhwp 미설치] vendor/rhwp/ 또는 npm @rhwp/core 필요. RHWP_CORE_PATH 지정 가능\n');
    process.exit(3);
  }

  const KNOWN = ['extract', 'search', 'replace', 'insert'];
  // 하위호환: 첫 인자가 명령이 아니면 extract 로 간주
  let cmd, rest;
  if (KNOWN.includes(argv[0])) {
    cmd = argv[0]; rest = argv.slice(1);
  } else {
    cmd = 'extract'; rest = argv;
  }

  if (cmd === 'extract') {
    const { doc } = await loadDoc(corePath, rest[0]);
    process.stdout.write(extractText(doc));
    return;
  }

  if (cmd === 'search') {
    const [file, query, caseSens] = rest;
    const { doc } = await loadDoc(corePath, file);
    const res = doc.searchAllText(query, caseSens === 'true', true);
    process.stdout.write(res);
    return;
  }

  if (cmd === 'replace') {
    const [inFile, outFile, query, newText, caseSens] = rest;
    if (!outFile || query === undefined || newText === undefined) {
      process.stderr.write('usage: replace <in> <out> <query> <new> [case]\n');
      process.exit(2);
    }
    warnFidelity();
    const { doc } = await loadDoc(corePath, inFile);
    const res = doc.replaceAll(query, newText, caseSens === 'true');
    const size = saveDoc(doc, outFile);
    process.stdout.write(JSON.stringify({ ok: true, replace_result: res, out: outFile, bytes: size }));
    return;
  }

  if (cmd === 'insert') {
    const [inFile, outFile, sec, para, off, text] = rest;
    if (text === undefined) {
      process.stderr.write('usage: insert <in> <out> <sec> <para> <off> <text>\n');
      process.exit(2);
    }
    warnFidelity();
    const { doc } = await loadDoc(corePath, inFile);
    const res = doc.insertText(Number(sec), Number(para), Number(off), text);
    const size = saveDoc(doc, outFile);
    process.stdout.write(JSON.stringify({ ok: true, insert_result: res, out: outFile, bytes: size }));
    return;
  }
}

main().catch(e => {
  process.stderr.write(`[rhwp 실패] ${e.message}\n`);
  process.exit(1);
});
