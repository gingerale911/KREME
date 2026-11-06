import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';

const require = createRequire(import.meta.url);
const source = readFileSync(new URL('../src/components/CarStatusPanel.tsx', import.meta.url), 'utf8').replace('import "./CarStatusPanel.css";', '');
let { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX } });
outputText = outputText.replaceAll('"react/jsx-runtime"', JSON.stringify(pathToFileURL(require.resolve('react/jsx-runtime')).href));
const { default: Panel } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);
const freshness = { telemetry: { state: 'fresh' }, damage: { state: 'fresh' } };
function render(damage, wear = [0,0,0,0], online = true) {
  return renderToStaticMarkup(React.createElement(Panel, { online, freshness, player: {
    tyres: { wearPct: wear, damagePct: damage }, damage: { floorDamage: damage[0], rearWingDamage: damage[1] }
  } }));
}
function fill(html, attr, value) { return html.match(new RegExp(`${attr}="${value}"[^>]*fill="([^"]+)"`))?.[1]; }
test('tyres use damage in RL RR FL FR packet order independently of wear', () => {
  const html = render([100,50,0,25]);
  assert.match(fill(html, 'data-tyre', 'RL'), /^hsl\(0 /);
  assert.match(fill(html, 'data-tyre', 'FL'), /^hsl\(120 /);
  assert.notEqual(fill(html, 'data-tyre', 'RL'), fill(html, 'data-tyre', 'RR'));
  assert.equal(fill(render([0,0,0,0], [100,100,100,100]), 'data-tyre', 'FL'), fill(html, 'data-tyre', 'FL'));
});
test('floor and rear wing react independently and unavailable data is grey', () => {
  const html = render([100,0,0,0]);
  assert.notEqual(fill(html, 'data-part', 'floorDamage'), fill(html, 'data-part', 'rearWingDamage'));
  assert.notEqual(fill(render([0,100,0,0]), 'data-part', 'rearWingDamage'), fill(html, 'data-part', 'rearWingDamage'));
  assert.equal(fill(render([100,100,100,100], undefined, false), 'data-part', 'floorDamage'), '#728091');
});
