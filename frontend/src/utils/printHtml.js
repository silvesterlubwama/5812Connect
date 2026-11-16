/**
 * Print a server-rendered HTML document without tripping popup blockers.
 * Fetching is async, so a `window.open` afterwards is no longer inside the
 * user gesture and gets blocked — we render into a hidden iframe instead.
 */
export function printHtmlDocument(html, { autoPrint = true } = {}) {
  const frame = document.createElement('iframe');
  frame.setAttribute('aria-hidden', 'true');
  // Off-screen, NOT visibility:hidden. A hidden iframe is skipped by Chrome's
  // layout for printing and comes out as a blank page — "nothing printed"
  // (iter421). Parked off to the left it still lays out properly.
  frame.style.cssText = 'position:fixed;left:-10000px;top:0;width:120mm;height:200mm;border:0;';
  document.body.appendChild(frame);
  let printed = false;
  const fire = () => {
    if (printed || !frame.contentWindow) return;
    printed = true;
    try {
      frame.contentWindow.focus();
      frame.contentWindow.print();
    } catch (e) {
      console.warn('[printHtml] print failed', e);
    }
    setTimeout(() => frame.remove(), 60000);
  };
  frame.onload = () => { if (autoPrint) fire(); };
  const doc = frame.contentWindow.document;
  doc.open();
  doc.write(html);
  doc.close();
  // Some browsers don't fire onload for document.write'd frames.
  if (autoPrint) setTimeout(fire, 500);
  return frame;
}

/** Fetch an authenticated HTML endpoint and send it straight to the printer. */
export async function fetchAndPrint(url, token) {
  const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) throw new Error(res.statusText || `HTTP ${res.status}`);
  const html = await res.text();
  printHtmlDocument(html);
}
