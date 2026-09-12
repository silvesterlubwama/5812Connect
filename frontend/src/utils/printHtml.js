/**
 * Print a server-rendered HTML document without tripping popup blockers.
 * Fetching is async, so a `window.open` afterwards is no longer inside the
 * user gesture and gets blocked — we render into a hidden iframe instead.
 */
export function printHtmlDocument(html, { autoPrint = true } = {}) {
  const frame = document.createElement('iframe');
  frame.setAttribute('aria-hidden', 'true');
  frame.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden;';
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
