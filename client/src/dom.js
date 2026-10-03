// Tiny DOM helpers: escape text for templates, and find things by id.

export const $ = (id) => document.getElementById(id);

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

export function badge(source) {
  const label = { llm: "model", cache: "cache", fallback: "fallback" }[source] || source;
  return `<span class="badge ${esc(source)}" title="Line came from: ${esc(label)}">${esc(label)}</span>`;
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
