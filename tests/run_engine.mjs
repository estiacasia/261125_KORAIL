// JS 엔진으로 render_cases.json 전 케이스를 렌더링해 비교한다.
//   node tests/run_engine.mjs           → 불일치 보고, 실패 시 종료 코드 1
//   node tests/run_engine.mjs --json    → 결과 배열을 JSON으로 출력
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);
const E = require(path.join(root, 'app/static/js/engine.js'));
const catalog = JSON.parse(readFileSync(path.join(root, 'data/seed_catalog.json'), 'utf8'));
const cases = JSON.parse(readFileSync(path.join(root, 'tests/fixtures/render_cases.json'), 'utf8'));

const KEYS = ['subject', 'body', 'subjectHtml', 'bodyHtml'];
const results = cases.map(c => {
  const r = E.render(catalog, c.state, c.sig, { month: c.month, hot: c.hot });
  return { name: c.name, ...Object.fromEntries(KEYS.map(k => [k, r[k]])) };
});

if (process.argv.includes('--json')) {
  process.stdout.write(JSON.stringify(results));
} else {
  let bad = 0;
  results.forEach((r, i) => {
    for (const k of KEYS) {
      if (r[k] !== cases[i].expected[k]) {
        bad++;
        console.log(`✗ ${r.name} [${k}]\n  JS : ${JSON.stringify(r[k])}\n  exp: ${JSON.stringify(cases[i].expected[k])}`);
        break;
      }
    }
  });
  console.log(`${results.length - bad}/${results.length} cases match`);
  process.exit(bad ? 1 : 0);
}
