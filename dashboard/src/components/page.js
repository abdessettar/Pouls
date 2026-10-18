/** Page header and small layout pieces shared by every page. */
import {html} from "npm:htl";
import {date, range} from "./format.js";

/**
 * The header row: eyebrow, title, subtitle, and a stamp with the date the data runs to.
 * meta: the object from data/meta.json.
 */
export function pageHeader({eyebrow, title, subtitle, meta}) {
  return html`<div class="page-head">
    <div>
      ${eyebrow ? html`<p class="eyebrow">${eyebrow}</p>` : ""}
      <h1>${title}</h1>
      ${subtitle ? html`<p class="subtitle">${subtitle}</p>` : ""}
    </div>
    ${meta ? html`<span class="stamp"><span class="dot"></span>Data through <b>${date(meta.data_through)}</b></span>` : ""}
  </div>`;
}

/** "28 days: 8 Apr – 5 May 2025" */
export const windowText = (w) => range(w.start, w.end);

/** A card with a title, an optional generated insight line, the body and a source note. */
export function card({title, insight, note, body, source}) {
  return html`<div class="card">
    ${title ? html`<div class="card-head"><h3 class="card-title">${title}</h3>${note ? html`<span class="card-note">${note}</span>` : ""}</div>` : ""}
    ${insight ? html`<p class="insight">${insight}</p>` : ""}
    ${body}
    ${source ? html`<p class="source">${source}</p>` : ""}
  </div>`;
}

/** Placeholder card for content arriving in a later milestone. */
export const placeholder = (text) => html`<div class="placeholder">${text}</div>`;
