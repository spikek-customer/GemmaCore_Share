// Node-based behavioral check for i18n engine (used by tests/test_i18n.py)
const fs = require('fs');
const vm = require('vm');
const dir = process.argv[2];
const store = {};
const sandbox = {
  console,
  localStorage: { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } },
  document: { documentElement: {}, querySelectorAll: () => [], getElementById: () => null, body: null, title: '' },
  CustomEvent: function (n, o) { this.type = n; this.detail = o && o.detail; },
  Node: { TEXT_NODE: 3, ELEMENT_NODE: 1 },
  NodeFilter: { SHOW_TEXT: 4 },
  MutationObserver: function () { this.observe = () => {}; },
};
sandbox.window = sandbox;
sandbox.window.dispatchEvent = () => {};
sandbox.window.confirm = () => true;
sandbox.window.alert = () => {};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(dir + '/i18n_phrases.js', 'utf8'), sandbox);
vm.runInContext(fs.readFileSync(dir + '/i18n_phrases_backend.js', 'utf8'), sandbox);
vm.runInContext(fs.readFileSync(dir + '/i18n.js', 'utf8'), sandbox);
const i18n = sandbox.window.i18n;
const out = { errors: [] };

const ja = Object.keys(i18n.dict.ja);
['en', 'zh-TW'].forEach(l => {
  const missing = ja.filter(k => !(k in i18n.dict[l]));
  const empty = Object.keys(i18n.dict[l]).filter(k => !String(i18n.dict[l][k]).trim());
  if (missing.length) out.errors.push(`missing in ${l}: ${missing.join(',')}`);
  if (empty.length) out.errors.push(`empty in ${l}: ${empty.join(',')}`);
});
out.keyCount = ja.length;

const ph = sandbox.window.I18N_PHRASES;
Object.keys(ph).forEach(k => {
  if (!Array.isArray(ph[k]) || ph[k].length !== 2 || !ph[k][0].trim() || !ph[k][1].trim()) out.errors.push(`bad phrase: ${k}`);
});
out.phraseCount = Object.keys(ph).length;

i18n.currentLang = 'en';
const checks = [
  ['キャンセル', 'Cancel'],
  ['  削除 🗑️ ', '  Delete 🗑️ '],
  ['🔒 ロック中 (4分30秒)', '🔒 Locked (4m 30s)'],
  ['取込エラー: boom', 'Import error: boom'],
  ['Untranslated Taro Yamada', 'Untranslated Taro Yamada'],
];
checks.forEach(([i, o]) => { const r = i18n.tr(i); if (r !== o) out.errors.push(`en tr(${i}) = ${r} expected ${o}`); });
i18n.currentLang = 'zh-TW';
if (i18n.tr('キャンセル') !== '取消') out.errors.push('zh tr failed');
if (i18n.t('toast_auth_success', { name: 'A' }).indexOf('A') < 0) out.errors.push('param substitution failed');
i18n.currentLang = 'ja';
if (i18n.tr('キャンセル') !== 'キャンセル') out.errors.push('ja passthrough failed');
console.log(JSON.stringify(out));
