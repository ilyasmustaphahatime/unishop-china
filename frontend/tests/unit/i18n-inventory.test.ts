import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import ts from 'typescript';
import { expect, it } from 'vitest';
import { supportedLanguages } from '../../src/i18n/languages';
import { namespaces } from '../../src/i18n/resources';

it('validates all 28 UTF-8 JSON files and rejects duplicate/malformed keys', () => {
  for (const locale of supportedLanguages) for (const ns of namespaces) {
    const file = path.resolve('src/i18n/locales', locale, ns + '.json');
    const bytes = fs.readFileSync(file);
    const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    const values = JSON.parse(text);
    expect(Object.values(values).every((value) => typeof value === 'string' && value.trim())).toBe(true);
    const ast = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.JSON);
    const keys: string[] = [];
    function inspect(node: ts.Node) {
      if (ts.isPropertyAssignment(node)) keys.push(node.name.getText(ast));
      ts.forEachChild(node, inspect);
    }
    inspect(ast);
    expect(new Set(keys).size).toBe(keys.length);
    expect(text).not.toContain('\uFFFD');
    expect(text).not.toMatch(/[\t ]+$/m);
  }
});

it('has no application-controlled JSX English text outside reviewed brand/diagnostic exceptions', () => {
  const inventory = JSON.parse(execFileSync(process.execPath, ['scripts/inventory-i18n.mjs'], { encoding: 'utf8' }));
  const remaining: string[] = [];
  // AST check supplements manual dynamic-message review; not arbitrary text grep.
  for (const file of inventory.reachableModules.filter((file: string) => file.endsWith('.tsx'))) {
    const source = ts.createSourceFile(file, fs.readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true);
    function inspect(node: ts.Node) {
      if (ts.isJsxText(node)) {
        const value = node.text.trim().replace(/\s+/g, ' ');
        if (/[A-Za-z]/.test(value) && !['UniShop China', 'phone_verified=true'].includes(value)) remaining.push(file + ': ' + value);
      }
      if (ts.isJsxAttribute(node) && ['aria-label', 'placeholder', 'title', 'label', 'hint', 'description'].includes(node.name.getText(source)) && node.initializer && ts.isStringLiteral(node.initializer) && /[A-Za-z]/.test(node.initializer.text)) {
        remaining.push(file + ': ' + node.initializer.text);
      }
      ts.forEachChild(node, inspect);
    }
    inspect(source);
  }
  expect(remaining).toEqual([]);
});

it('keeps locale presentation independent of auth, HTTP, query clients and remote loaders', () => {
  for (const file of ['index.ts', 'controller.ts', 'persistence.ts', 'useAppTranslation.ts']) {
    const source = fs.readFileSync(path.resolve('src/i18n', file), 'utf8');
    expect(source).not.toMatch(/from ['"].*(authStore|apiClient|queryClient|features\/auth)/);
    expect(source).not.toMatch(/fetch\(|axios|http-backend|language-detector|dangerouslySetInnerHTML/);
  }
});
