// Static coverage audit: list Japanese UI strings in index.html / app.js that i18n.tr() cannot translate (en).
const fs = require('fs');
const vm = require('vm');
const dir = process.argv[2];
const sb = { console, localStorage: { getItem: () => 'en', setItem() {} }, document: { documentElement: {} }, CustomEvent: function () {}, Node: {}, NodeFilter: {}, MutationObserver: function () { this.observe = () => {}; } };
sb.window = sb; sb.confirm = () => true; sb.alert = () => {}; sb.dispatchEvent = () => {};
vm.createContext(sb);
vm.runInContext(fs.readFileSync(dir + '/i18n_phrases.js', 'utf8'), sb);
vm.runInContext(fs.readFileSync(dir + '/i18n_phrases_backend.js', 'utf8'), sb);
vm.runInContext(fs.readFileSync(dir + '/i18n.js', 'utf8'), sb);
const i18n = sb.i18n; i18n.currentLang = 'en';
const dict = i18n.dict.ja;
const JA = /[\u3040-\u30ff\u4e00-\u9fff]/;
const miss = new Set();
function test(t) {
  t = t.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim();
  if (!t || !JA.test(t)) return;
  if (i18n.tr(t) !== t) return;
  miss.add(t);
}
// HTML
let html = fs.readFileSync(dir + '/index.html', 'utf8').replace(/<script[\s\S]*?<\/script>|<!--[\s\S]*?-->|<style[\s\S]*?<\/style>/g, '');
// drop elements translated by data-i18n / data-i18n-html (their inner content)
html = html.replace(/<([a-z0-9]+)\b[^>]*data-i18n(?:-html)?="[^"]+"[^>]*>[\s\S]*?<\/\1>/g, '');
(html.match(/>([^<>]+)</g) || []).forEach(m => test(m.slice(1, -1)));
// attributes
const attrs = html.match(/\b(placeholder|title)="[^"]*"/g) || [];
attrs.forEach(a => test(a.replace(/^[a-z]+="/, '').replace(/"$/, '')));
// JS
const js = fs.readFileSync(dir + '/app.js', 'utf8');
const lits = js.match(/`(?:[^`\\]|\\[\s\S])*`|"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'/g) || [];
lits.forEach(l => {
  if (!JA.test(l)) return;
  let s = l.slice(1, -1).replace(/\\n/g, '\n').replace(/\$\{[^}]*\}/g, '1');
  if (!/<[a-z]/i.test(s)) { test(s); return; }
  s.split(/<[^>]*>/).forEach(test);
});
// ignore things only inside comments / copy-text templates intentionally untranslated
const ignore = [/^【社内AIナレッジポータル 初期ログイン/];
const out = [...miss].filter(t => !ignore.some(r => r.test(t)));
console.log(out.join('\n'));
console.error('untranslated:', out.length);
