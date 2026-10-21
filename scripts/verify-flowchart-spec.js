#!/usr/bin/env node
"use strict";
/*
 * verify-flowchart-spec.js — three-layer audit pipeline for data-driven
 * native-SVG flowchart HTML files (flowchart-spec).
 *
 * Usage:  node scripts/verify-flowchart-spec.js <flowchart.html> [...]
 *
 * Layers:
 *   1. Syntax check   — every <script> block must parse (new Function).
 *   2. Smoke render   — execute scripts against a DOM stub; assert each SVG
 *                       gets a viewBox and child elements (catches runtime
 *                       errors syntax checks miss, e.g. undeclared vars).
 *   3. Geometry audit — from window.__fcGeo (built-time exported), re-assert:
 *                       endpoints on anchors (≤3px), no unknown routes,
 *                       no missing group members, no node-piercing.
 *   Extra: tag balance (void whitelist) + anchor integrity (href="#x" ↔ id).
 */
const fs = require("fs");
const path = require("path");
const VPAT = [];
const voidEls = new Set(["area","base","br","col","embed","hr","img","input","link","meta","param","source","track","wbr"]);
function vEl(tag, attrs, kids) {
  const el = {
    _tag: tag.toLowerCase(), _kids: [], _attrs: {},
    setAttribute(k, v) { this._attrs[k] = String(v); if (k === "id") (el.ids = el.ids || []).push(String(v)); },
    getAttribute(k) { return k in this._attrs ? this._attrs[k] : null; },
    appendChild(c) { if (c) this._kids.push(c); return c; },
    addEventListener() {}, setPointerCapture() {}, releasePointerCapture() {},
    classList: { add() {}, remove() {} },
    textContent: "", innerHTML: "",
  };
  return el;
}
function makeEl(tag) {
  tag = tag.toLowerCase();
  if (tag === "svg" || tag === "g" || tag === "defs" || tag === "path" || tag === "marker" ||
      tag === "rect" || tag === "polygon" || tag === "line" || tag === "text" || tag === "title" ||
      tag === "circle" || tag === "polyline" || tag === "tspan") {
    return vEl(tag);
  }
  if (tag === "script") { const s = vEl("script"); s.style = {}; return s; }
  const e = vEl(tag);
  e.clientHeight = 800; e.clientWidth = 1200;
  e.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1200, height: 800 });
  e.style = {};
  return e;
}
function makeWin() {
  const ids = {};
  const byTag = { svg: [] };
  const win = {
    clientWidth: 1200, innerWidth: 1200, innerHeight: 800,
    addEventListener() {}, removeEventListener() {},
    __svgRoot: null,
    createElement(t) { const e = makeEl(t); (byTag[t] = byTag[t] || []).push(e); return e; },
    createElementNS(ns, t) { const e = makeEl(t); if (t === "svg") byTag.svg.push(e); return e; },
    getElementById(id) {
      if (ids[id]) return ids[id];
      /* an element whose id ends in "-svg" is the SVG root in our markup */
      var isSvg = /-svg$/.test(id);
      const el = isSvg ? makeEl("svg") : makeEl("div");
      if (isSvg) (byTag.svg = byTag.svg || []).push(el);
      el._id = id; ids[id] = el;
      el.querySelector = () => null;
      el.addEventListener = () => {};
      el.appendChild = (c) => { if (c) el._kids.push(c); };
      return el;
    },
  };
  win.document = {
    createElement: win.createElement,
    createElementNS: win.createElementNS,
    getElementById: win.getElementById,
  };
  win.__byTag = byTag;
  return win;
}
function runSmokeTest(html) {
  const win = makeWin();
  win.window = win;
  const scripts = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].map((m) => m[1]);
  const code = scripts.join("\n;\n");
  /* Layer 1: syntax */
  try { new Function(code); } catch (e) {
    console.error("LAYER 1 FAIL — syntax error in <script>:", e.message);
    process.exit(1);
  }
  /* Layer 2: execution */
  try {
    const fn = new Function(
      "window", "document", "navigator", "console",
      code + '\nreturn {svg: window.__byTag && window.__byTag.svg, built: window.__fcBuilt};'
    );
    const api = fn(win, win.document, { userAgent: "node" }, console);
    const svgs = api.svg || [];
    if (svgs.length === 0) {
      console.error("LAYER 2 FAIL — no <svg> element created at runtime");
      process.exit(1);
    }
    for (const s of svgs) {
      const vb = s._attrs.viewBox || s.getAttribute && s.getAttribute("viewBox");
      const nKids = (s._kids || []).length;
      if (!vb) { console.error("LAYER 2 FAIL — svg missing viewBox"); process.exit(1); }
      if (nKids === 0) { console.error("LAYER 2 FAIL — svg has no child elements"); process.exit(1); }
      console.log("LAYER 2 OK  — rendered svg: viewBox=%s children=%d", vb, nKids);
    }
    if (!win.__fcGeo || !win.__fcBuilt) {
      console.error("LAYER 2 FAIL — window.__fcGeo / __fcBuilt not registered");
      process.exit(1);
    }
    console.log("LAYER 2 OK  — built:", JSON.stringify(win.__fcBuilt));
    return win;
  } catch (e) {
    console.error("LAYER 2 FAIL — runtime error:", e.stack || e.message);
    process.exit(1);
  }
}
function geometryAudit(win) {
  const g = win.__fcGeo;
  const issues = [];
  const routeSet = new Set(["v", "h", "h2", "elbow", "hdown", "sdown", "gdown", "lup"]);
  const nodes = g.nodes;
  for (const e of g.edges) {
    if (!routeSet.has(e.route)) issues.push(`${e.id}: unknown route '${e.route}'`);
    const p0 = e.pts[0], p1 = e.pts[e.pts.length - 1];
    const d0 = Math.hypot(p0[0] - e.anchorFrom[0], p0[1] - e.anchorFrom[1]);
    const d1 = Math.hypot(p1[0] - e.anchorTo[0], p1[1] - e.anchorTo[1]);
    if (d0 > 3) issues.push(`${e.id}: source endpoint off anchor by ${d0.toFixed(2)}px`);
    if (d1 > 3) issues.push(`${e.id}: target endpoint off anchor by ${d1.toFixed(2)}px`);
  }
  /* occlusion: sample segments against node boxes */
  for (const e of g.edges) {
    for (let i = 0; i < e.pts.length - 1; i++) {
      const a = e.pts[i], b = e.pts[i + 1];
      const skip = new Set([e.from, e.to]);
      for (const nid of Object.keys(nodes)) {
        if (skip.has(nid)) continue;
        const bb = nodes[nid].box, infl = 4;
        const x0 = bb.x - infl, x1 = bb.x + bb.w + infl, y0 = bb.y - infl, y1 = bb.y + bb.h + infl;
        let pierced = false;
        for (let s = 0; s <= 48; s++) {
          const t = s / 48, px = a[0] + (b[0] - a[0]) * t, py = a[1] + (b[1] - a[1]) * t;
          if (Math.hypot(px - a[0], py - a[1]) < 8) continue;
          if (Math.hypot(px - b[0], py - b[1]) < 8) continue;
          if (px > x0 && px < x1 && py > y0 && py < y1) { pierced = true; break; }
        }
        if (pierced) { issues.push(`${e.id}: pierces node ${nid}`); break; }
      }
    }
  }
  for (const grp of g.groups) {
    for (const m of grp.members) if (!nodes[m]) issues.push(`${grp.id}: missing member ${m}`);
  }
  if (issues.length) {
    console.error("LAYER 3 FAIL — " + issues.length + " geometry issue(s):");
    issues.slice(0, 20).forEach((s) => console.error("   - " + s));
    return false;
  }
  console.log(`LAYER 3 OK  — ${g.edges.length} edges · ${Object.keys(nodes).length} nodes · 0 occlusions`);
  return true;
}
function staticChecks(html) {
  let ok = true;
  const open = [...html.matchAll(/<([a-zA-Z][a-zA-Z0-9]*)((?:"[^"]*")|\b[a-zA-Z0-9-]+="[^"]*")*\s*(\/?)>/g)];
  const stack = [];
  for (const m of open) {
    const tag = m[1].toLowerCase(), selfClosed = m[3] === "/";
    if (voidEls.has(tag) || selfClosed) continue;
    stack.push(tag);
  }
  const closes = [...html.matchAll(/<\/([a-zA-Z][a-zA-Z0-9]*)>/g)].map((m) => m[1].toLowerCase())
    .filter((t) => !voidEls.has(t));
  /* loose balance: open count vs close count per tag */
  const counts = {};
  for (const t of open) if (!voidEls.has(t[1])) counts[t[1]] = (counts[t[1]] || 0) + 1;
  const closeCounts = {};
  for (const t of closes) closeCounts[t] = (closeCounts[t] || 0) + 1;
  for (const tag of new Set([...Object.keys(counts), ...Object.keys(closeCounts)])) {
    const o = counts[tag] || 0, c = closeCounts[tag] || 0;
    if (o !== c) {
      /* SVG inline self-closing forms are fine */
      if (voidEls.has(tag)) continue;
      console.error(`STATIC FAIL — tag <${tag}> balance: open=${o} close=${c}`);
      ok = false;
    }
  }
  /* anchor integrity: href="#x" must have id="x" */
  const idSet = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1]));
  const refs = [...html.matchAll(/href="#([^"]+)"/g)].map((m) => m[1]);
  for (const r of refs) if (!idSet.has(r)) { console.error(`STATIC FAIL — dangling anchor #${r}`); ok = false; }
  if (ok) console.log("STATIC OK  — tag balance + anchor integrity");
  return ok;
}
function main() {
  const files = process.argv.slice(2);
  if (files.length === 0) {
    console.error("usage: node verify-flowchart-spec.js <flowchart.html> [...]");
    process.exit(2);
  }
  let allOk = true;
  for (const f of files) {
    console.log("=== " + path.resolve(f) + " ===");
    const html = fs.readFileSync(f, "utf8");
    if (!staticChecks(html)) allOk = false;
    const win = runSmokeTest(html);
    if (!geometryAudit(win)) allOk = false;
  }
  console.log(allOk ? "ALL LAYERS PASS" : "PIPELINE FAILED");
  process.exit(allOk ? 0 : 1);
}
main();
