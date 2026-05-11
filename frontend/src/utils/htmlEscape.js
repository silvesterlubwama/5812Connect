/**
 * escapeHtml — safely encode user-controlled data before embedding into HTML strings.
 * Use this for ANY string that flows into a print-window's document.write() / outerHTML.
 *
 * Why: those print pipelines build HTML via template literals — without escaping, a malicious
 * product name like `<script>alert(1)</script>` or `" onerror=alert(1)` would execute.
 */
export function escapeHtml(value) {
  if (value == null) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/\//g, '&#x2F;');
}

/** Quick alias for use inside template literals. */
export const e = escapeHtml;
