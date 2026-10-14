// Review aid, not proof of complete coverage: static text in reachable UI modules.
import fs from 'node:fs';
import path from 'node:path';
import ts from 'typescript';
import process from 'node:process';
import console from 'node:console';

const root = path.resolve('src');
const seen = new Set();
const inventory = [];
const ignoredAttributes = new Set(['className', 'id', 'htmlFor', 'name', 'type', 'role', 'autoComplete', 'to', 'href', 'src', 'value']);
function resolve(from, specifier) {
  if (!specifier.startsWith('.')) return null;
  const stem = path.resolve(path.dirname(from), specifier);
  return [stem, stem + '.tsx', stem + '.ts', path.join(stem, 'index.ts')].find((p) => /\.tsx?$/.test(p) && fs.existsSync(p));
}
function inspect(file) {
  if (path.relative(root, file).replaceAll('\\', '/').startsWith('i18n/')) return;
  if (seen.has(file)) return;
  seen.add(file);
  const source = ts.createSourceFile(file, fs.readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true);
  const imports = [];
  function walk(node) {
    if (ts.isStringLiteral(node)) {
      const dependency = resolve(file, node.text);
      if (dependency) imports.push(dependency);
    }
    if (ts.isJsxText(node) || ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
      const text = node.text.replace(/\s+/g, ' ').trim();
      const attribute = ts.isJsxAttribute(node.parent) ? node.parent.name.getText(source) : null;
      if (text && !ignoredAttributes.has(attribute) && /[A-Za-z]/.test(text) && /\s/.test(text) && !/^(\.\.?\/|https?:|\/api\/)/.test(text)) {
        inventory.push({ file: path.relative(process.cwd(), file).replaceAll('\\', '/'), line: source.getLineAndCharacterOfPosition(node.getStart()).line + 1, text });
      }
    }
    ts.forEachChild(node, walk);
  }
  walk(source);
  imports.forEach(inspect);
}
inspect(path.join(root, 'main.tsx'));
console.log(JSON.stringify({ reachableModules: [...seen].map((p) => path.relative(process.cwd(), p).replaceAll('\\', '/')).sort(), candidates: inventory }, null, 2));
