#!/usr/bin/env node
/**
 * math_to_svg.js — Batch LaTeX-to-SVG renderer using MathJax
 *
 * Reads a JSON array from stdin:
 *   [{"id": "0", "latex": "x^2", "display": false}, ...]
 *
 * Writes a JSON object to stdout:
 *   {"0": "<svg ...>...</svg>", "1": "<svg ...>...</svg>", ...}
 */

const { mathjax } = require('mathjax-full/js/mathjax.js');
const { TeX } = require('mathjax-full/js/input/tex.js');
const { SVG } = require('mathjax-full/js/output/svg.js');
const { liteAdaptor } = require('mathjax-full/js/adaptors/liteAdaptor.js');
const { RegisterHTMLHandler } = require('mathjax-full/js/handlers/html.js');
const { AllPackages } = require('mathjax-full/js/input/tex/AllPackages.js');

const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);

const tex = new TeX({
  packages: AllPackages,
  inlineMath: [['$', '$'], ['\\(', '\\)']],
  displayMath: [['$$', '$$'], ['\\[', '\\]']],
});

const svg = new SVG({
  fontCache: 'none',   // inline all glyphs for self-contained SVGs
});

const html = mathjax.document('', { InputJax: tex, OutputJax: svg });

function renderOne(latex, display) {
  const node = html.convert(latex, { display });
  let svgStr = adaptor.innerHTML(node);
  // Remove the outer mjx-container wrapper if present
  // MathJax wraps in <mjx-container ...><svg ...>...</svg></mjx-container>
  // We want just the <svg> element
  const svgMatch = svgStr.match(/<svg[\s\S]*<\/svg>/);
  if (svgMatch) {
    svgStr = svgMatch[0];
  }
  return svgStr;
}

// Read all stdin
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (chunk) => { input += chunk; });
process.stdin.on('end', () => {
  try {
    const items = JSON.parse(input);
    const results = {};
    for (const item of items) {
      try {
        results[item.id] = renderOne(item.latex, !!item.display);
      } catch (e) {
        // On failure, return an error marker
        results[item.id] = `<span class="math-error" title="${e.message}">[math error]</span>`;
      }
    }
    process.stdout.write(JSON.stringify(results));
  } catch (e) {
    process.stderr.write('Error parsing input: ' + e.message + '\n');
    process.exit(1);
  }
});
