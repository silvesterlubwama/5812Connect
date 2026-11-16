# iter421 — Till printer dialog + receipt print layout (frontend only). Run via browser_automation.
await page.set_viewport_size({"width": 1920, "height": 1080})
page.on("console", lambda m: print("CONSOLE:", m.text) if m.type in ("error",) else None)
HOOK = """() => {
  window.__prints = []; window.__printCalls = 0;
  new MutationObserver(ms => ms.forEach(m => m.addedNodes.forEach(n => {
    if (n.tagName === 'IFRAME') {
      try { n.contentWindow.print = () => { window.__printCalls++; }; } catch(e) {}
      setTimeout(() => { try { n.contentWindow.print = () => { window.__printCalls++; };
        window.__prints.push({style: n.style.cssText, html: n.contentDocument.documentElement.outerHTML}); } catch(e) { window.__prints.push({err: String(e)}); } }, 120);
    }
  }))).observe(document.body, {childList: true});
}"""
try:
    await page.fill('[data-testid="login-identifier-input"]', 'admin@5812uganda.org')
    await page.fill('[data-testid="login-password-input"]', 'Admin@5812')
    await page.click('[data-testid="login-submit-button"]')
    await page.wait_for_timeout(4000)
    print("after login url:", page.url)
    await page.evaluate("() => localStorage.removeItem('5812:till-printer')")
    await page.goto("https://multi-tenant-scope.preview.emergentagent.com/5812global/sales")
    await page.wait_for_selector('[data-testid="till-printer-btn"]', timeout=20000)
    print("PASS: POS loaded, printer btn present:", await page.inner_text('[data-testid="till-printer-btn"]'))
    await page.evaluate(HOOK)
    await page.click('[data-testid="till-printer-btn"]')
    await page.wait_for_timeout(800)
    for c in ["usb", "bluetooth", "network", "none"]:
        print(c, "visible:", await page.is_visible(f'[data-testid="till-conn-{c}"]'))
    # default paper = auto with resolved text
    print("paper select:", await page.inner_text('[data-testid="till-paper-select"]'))
    if await page.is_visible('[data-testid="till-paper-resolved"]'):
        print("PASS resolved:", await page.inner_text('[data-testid="till-paper-resolved"]'))
    else:
        print("FAIL: till-paper-resolved not shown")
    # none: silent help
    await page.click('[data-testid="till-conn-none"]')
    await page.wait_for_timeout(300)
    print("silent help visible:", await page.is_visible('[data-testid="till-silent-help"]'))
    await page.click('[data-testid="till-silent-help-toggle"]')
    await page.wait_for_timeout(300)
    print("silent help has kiosk-printing:", '--kiosk-printing' in await page.inner_text('[data-testid="till-silent-help"]'))
    print("test btn disabled (none)?", await page.is_disabled('[data-testid="till-test-btn"]'))
    print("drawer btn disabled (none)?", await page.is_disabled('[data-testid="till-open-drawer-btn"]'))
    await page.screenshot(path=".screenshots/till_none.jpeg", quality=40, full_page=False)
    await page.click('[data-testid="till-test-btn"]')
    await page.wait_for_timeout(1500)
    toasts = await page.evaluate("() => Array.from(document.querySelectorAll('[data-sonner-toast]')).map(t=>t.innerText)")
    print("toasts after browser test:", toasts)
    prints = await page.evaluate("() => ({calls: window.__printCalls, prints: window.__prints.map(p => ({style: p.style, err: p.err, html: (p.html||'').slice(0,1500)}))})")
    print("print capture:", prints)
    # usb: baud select
    await page.click('[data-testid="till-conn-usb"]')
    await page.wait_for_timeout(300)
    print("baud select visible:", await page.is_visible('[data-testid="till-baud-select"]'))
    if await page.is_visible('[data-testid="till-baud-select"]'):
        await page.click('[data-testid="till-baud-select"]')
        await page.wait_for_timeout(300)
        opts = await page.evaluate("() => Array.from(document.querySelectorAll('[role=option]')).map(o=>o.innerText)")
        print("baud options:", opts)
        await page.get_by_role("option", name="19200 baud").click(force=True)
        await page.wait_for_timeout(300)
        print("saved cfg:", await page.evaluate("() => Object.entries(localStorage).filter(([k])=>/till/i.test(k))"))
    # network: warning + failing test
    await page.click('[data-testid="till-conn-network"]')
    await page.wait_for_timeout(300)
    print("network warning visible:", await page.is_visible('[data-testid="till-network-warning"]'))
    await page.fill('[data-testid="till-network-host"]', '192.168.1.250') if await page.is_visible('[data-testid="till-network-host"]') else print("no host input testid")
    await page.wait_for_timeout(300)
    await page.click('[data-testid="till-test-btn"]')
    await page.wait_for_timeout(9000)
    toasts = await page.evaluate("() => Array.from(document.querySelectorAll('[data-sonner-toast]')).map(t=>t.innerText)")
    print("toasts after network test:", toasts)
    if await page.is_visible('[data-testid="till-test-reason"]'):
        print("PASS reason box:", await page.inner_text('[data-testid="till-test-reason"]'))
    else:
        print("FAIL: no till-test-reason")
    await page.screenshot(path=".screenshots/till_network.jpeg", quality=40, full_page=False)
    # second test press should still really try (cooldown cleared)
    import time
    t0 = time.time()
    await page.click('[data-testid="till-test-btn"]')
    await page.wait_for_selector('[data-testid="till-test-btn"]:not([disabled])', timeout=20000)
    await page.wait_for_timeout(200)
    print("2nd network test duration s:", round(time.time()-t0, 1))
    # paper select 58mm
    await page.click('[data-testid="till-paper-select"]')
    await page.wait_for_timeout(300)
    opts = await page.evaluate("() => Array.from(document.querySelectorAll('[role=option]')).map(o=>o.innerText)")
    print("paper options:", opts)
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(300)
    # reset to none
    await page.click('[data-testid="till-conn-none"]')
    print("final cfg:", await page.evaluate("() => Object.entries(localStorage).filter(([k])=>/till/i.test(k))"))
except Exception as e:
    print("ERROR:", e)
    await page.screenshot(path=".screenshots/err.jpeg", quality=40, full_page=False)
