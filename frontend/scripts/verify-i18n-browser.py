"""Phase 11A real Chrome gate using the existing synthetic MySQL HTTP harness.

Run with backend/.venv/Scripts/python.exe from the backend directory. No app,
database, auth or storage implementation is replaced. The harness cleans only
its random synthetic namespace and compares all 16 development table hashes.
"""
from pathlib import Path
import base64
import json
import subprocess
import sys
import tempfile
import time

import httpx
from PIL import Image
from websockets.sync.client import connect

FRONTEND = Path(__file__).resolve().parents[1]
BACKEND = FRONTEND.parent / "backend"
sys.path.insert(0, str(BACKEND))

# The existing backend harness is imported only after its fixed repository path is set.
from scripts.product_image_browser_checks import CHROME, Page, BrowserEnvironmentBlocked  # noqa: E402

LOCALES = ("en", "zh-CN", "ar", "fr")
SELECT = "select:has(option[value='zh-CN'])"
COPY = {locale: {ns: json.loads((FRONTEND / "src/i18n/locales" / locale / (ns + ".json")).read_text(encoding="utf-8"))
                  for ns in ("common", "auth", "products", "verification", "validation")}
        for locale in LOCALES}


class LocalePage(Page):
    def evaluate(self, expression):
        result = self.call("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in result:
            details = result["exceptionDetails"]
            print(json.dumps({"safe_browser_exception": {"class": details.get("exception", {}).get("className"),
                "line": details.get("lineNumber"), "column": details.get("columnNumber")}}))
            raise RuntimeError("Browser evaluation failed.")
        return result.get("result", {}).get("value")


def run_browser_checks(frontend, backend, email, password, other_email, other_password, category, root, check):
    if not CHROME.is_file():
        raise BrowserEnvironmentBlocked("Chrome executable unavailable.")
    profile = root.resolve() / "profile"
    visual = Path(tempfile.mkdtemp(prefix="unishop-i18n-visual-"))
    process = subprocess.Popen([str(CHROME), "--headless=new", "--disable-background-networking",
        "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0", "--user-data-dir=" + str(profile), "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    stage = "startup"
    timings = []
    try:
        for _ in range(80):
            if (profile / "DevToolsActivePort").is_file():
                port = int((profile / "DevToolsActivePort").read_text().splitlines()[0])
                break
            time.sleep(0.1)
        else:
            raise BrowserEnvironmentBlocked("Headless Chrome unavailable.")
        with httpx.Client(trust_env=False, timeout=5) as protocol:
            tab = protocol.put(f"http://127.0.0.1:{port}/json/new?about:blank").json()
        with connect(tab["webSocketDebuggerUrl"], proxy=None, max_size=4 * 1024 * 1024, open_timeout=5) as socket:
            page = LocalePage(socket)
            page.call("Page.enable")
            page.call("Network.enable")
            page.call("Page.addScriptToEvaluateOnNewDocument", {"source": """(()=>{
              window.__i18nAudit={created:0,revoked:0,requests:0,firstVisibleLocale:null,identity:Math.random().toString(36)};
              const create=URL.createObjectURL.bind(URL),revoke=URL.revokeObjectURL.bind(URL);
              URL.createObjectURL=(blob)=>{window.__i18nAudit.created++;return create(blob)};
              URL.revokeObjectURL=(url)=>{window.__i18nAudit.revoked++;return revoke(url)};
              const open=XMLHttpRequest.prototype.open;
              XMLHttpRequest.prototype.open=function(...args){window.__i18nAudit.requests++;return open.apply(this,args)};
              const observe=new MutationObserver(()=>{if(document.querySelector('#root')?.childElementCount && !window.__i18nAudit.firstVisibleLocale)
                window.__i18nAudit.firstVisibleLocale=document.documentElement.lang;});
              observe.observe(document,{childList:true,subtree:true});
            })();"""})

            def viewport(width):
                page.call("Emulation.setDeviceMetricsOverride", {"width": width, "height": 900, "deviceScaleFactor": 1, "mobile": width < 500})

            def locale(value):
                nonlocal stage
                stage = "switch-" + value
                started = time.perf_counter()
                page.value(SELECT, value)
                direction = "rtl" if value == "ar" else "ltr"
                page.wait("document.documentElement.lang===" + json.dumps(value) + " && document.documentElement.dir===" + json.dumps(direction)
                          + " && document.querySelector(" + json.dumps(SELECT) + ").value===" + json.dumps(value), "locale-ready")
                page.evaluate("new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))")
                timings.append(round((time.perf_counter() - started) * 1000, 2))

            def button(ns, key, value):
                page.click(COPY[value][ns][key])

            def reload_login():
                identity = page.evaluate("window.__i18nAudit.identity")
                page.call("Page.reload")
                page.wait("window.__i18nAudit?.identity!==" + json.dumps(identity) + " && Boolean(document.querySelector('#identifier'))", "new-login-document")

            stage = "four-language-login-layouts"
            viewport(1280)
            login_url = frontend + "/login?keep=yes#locale-test"
            page.call("Page.navigate", {"url": login_url})
            page.wait("Boolean(document.querySelector('#identifier'))", "login-ready")
            check(page.evaluate("document.documentElement.lang==='en' && localStorage.getItem('unishop.locale')===null"), "i18n-first-visit-English")
            page.evaluate("window.__originalDocument=document; window.__originalIdentifier=document.querySelector('#identifier'); true")
            for width in (1280, 390):
                viewport(width)
                for value in LOCALES:
                    locale(value)
                    check(page.evaluate("document.documentElement.scrollWidth<=window.innerWidth"), f"i18n-{value}-{width}-no-overflow")
                    check(page.evaluate("document.title===" + json.dumps(COPY[value]["common"]["documentTitle"])), f"i18n-{value}-document-title-{width}")
                    check(page.evaluate("document.querySelector('h1').textContent===" + json.dumps(COPY[value]["auth"]["loginTitle"])), f"i18n-{value}-login-heading-{width}")
                    check(page.evaluate("document===window.__originalDocument && document.querySelector('#identifier')===window.__originalIdentifier && location.search==='?keep=yes' && location.hash==='#locale-test'"), f"i18n-{value}-route-and-mount-{width}")
                    # Screenshots contain only the empty login screen, never credentials/private media.
                    screenshot = page.call("Page.captureScreenshot", {"format": "png"})["data"]
                    (visual / f"{value}-{width}.png").write_bytes(base64.b64decode(screenshot))
            stage = "persistence-and-keyboard"
            for value in LOCALES:
                locale(value)
                reload_login()
                check(page.evaluate("document.documentElement.lang===" + json.dumps(value) + " && window.__i18nAudit.firstVisibleLocale===" + json.dumps(value)), "i18n-refresh-no-flash-" + value)
            page.evaluate("document.querySelector(" + json.dumps(SELECT) + ").focus()")
            for key, code in (("Home", "Home"), ("ArrowDown", "ArrowDown")):
                page.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": key, "code": code})
                page.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": key, "code": code})
            page.wait("document.documentElement.lang==='zh-CN'", "native-keyboard-selection")
            check(page.evaluate("document.activeElement===document.querySelector(" + json.dumps(SELECT) + ")"), "i18n-native-keyboard-focus")
            page.evaluate("(()=>{const e=document.querySelector(" + json.dumps(SELECT) + ");for(const l of ['ar','fr','zh-CN']){e.value=l;e.dispatchEvent(new Event('change',{bubbles:true}));}})()")
            page.wait("document.documentElement.lang==='zh-CN' && localStorage.getItem('unishop.locale')==='zh-CN'", "rapid-latest-selection")
            check(True, "i18n-rapid-latest-selection")
            page.evaluate("localStorage.setItem('unishop.locale','../ar')")
            reload_login()
            check(page.evaluate("document.documentElement.lang==='en' && document.documentElement.dir==='ltr'"), "i18n-invalid-preference-fallback")
            blocked = page.call("Page.addScriptToEvaluateOnNewDocument", {"source": """(()=>{
              const get=Storage.prototype.getItem,set=Storage.prototype.setItem;
              Storage.prototype.getItem=function(key){if(key==='unishop.locale')throw new Error('blocked');return get.call(this,key)};
              Storage.prototype.setItem=function(key,value){if(key==='unishop.locale')throw new Error('blocked');return set.call(this,key,value)};
            })();"""})["identifier"]
            reload_login()
            check(page.evaluate("document.documentElement.lang==='en'"), "i18n-blocked-storage-default")
            locale("fr")
            check(page.evaluate("document.documentElement.lang==='fr'"), "i18n-blocked-storage-switch")
            page.call("Page.removeScriptToEvaluateOnNewDocument", {"identifier": blocked})
            reload_login()
            locale("en")
            stage = "login-form-preservation"
            page.value("#identifier", email)
            page.value("#password", password)
            page.evaluate("window.__loginInputs=[document.querySelector('#identifier'),document.querySelector('#password')]; window.__loginRequests=window.__i18nAudit.requests")
            for value in LOCALES:
                locale(value)
                check(page.evaluate("document.querySelector('#identifier')===window.__loginInputs[0] && document.querySelector('#password')===window.__loginInputs[1] && document.querySelector('#identifier').value===" + json.dumps(email)
                    + " && document.querySelector('#password').value===" + json.dumps(password) + " && window.__i18nAudit.requests===window.__loginRequests"), "i18n-login-values-and-no-auth-request-" + value)
            locale("en")
            button("common", "signIn", "en")
            page.wait("Boolean(document.querySelector('a[href=\"/sell/new\"]'))", "seller-login")
            page.link("/sell/new")
            page.wait("Boolean(document.querySelector('#product-category option[value=" + json.dumps(category) + "]'))", "catalog-ready")
            title = "Synthetic <img src=x> مكتب 书桌"
            description = "Original synthetic description <script>not executable</script> وصف أصلي."
            page.value("#product-title", title)
            page.value("#product-description", description)
            page.value("#product-price", "19.99")
            page.value("#product-city", "qingdao")
            page.value("#product-category", category)
            page.evaluate("window.__titleInput=document.querySelector('#product-title'); window.__formRequests=window.__i18nAudit.requests")
            for value in LOCALES:
                locale(value)
                check(page.evaluate("document.querySelector('#product-title')===window.__titleInput && document.querySelector('#product-title').value===" + json.dumps(title)
                    + " && document.querySelector('#product-description').value===" + json.dumps(description)
                    + " && document.querySelector('#product-price').value==='19.99' && document.querySelector('#product-city').value==='qingdao' && document.querySelector('#product-category').value===" + json.dumps(category)
                    + " && window.__i18nAudit.requests===window.__formRequests"), "i18n-product-values-and-no-requests-" + value)
                check(page.evaluate("document.documentElement.scrollWidth<=window.innerWidth"), "i18n-product-mobile-layout-" + value)
            locale("en")
            button("products", "createDraft", "en")
            page.wait("/^\\/seller\\/listings\\/item-[0-9a-f]{24}\\/edit$/.test(location.pathname)", "draft-created")
            slug = page.evaluate("location.pathname.split('/')[3]")
            photo = root / "synthetic.png"
            with Image.new("RGB", (16, 12), (120, 30, 40)) as image:
                image.save(photo, format="PNG")
            page.file(photo)
            button("products", "uploadImage", "en")
            page.wait("document.querySelector('img[src^=\"blob:\"]')?.naturalWidth>0", "private-preview-loaded")
            page.file(photo)
            page.evaluate("window.__privateImage=document.querySelector('img[src^=\"blob:\"]');window.__beforeLocale={...window.__i18nAudit};")
            for value in LOCALES:
                locale(value)
                check(page.evaluate("document.querySelector('img[src^=\"blob:\"]')===window.__privateImage && window.__i18nAudit.created===window.__beforeLocale.created && window.__i18nAudit.revoked===window.__beforeLocale.revoked && window.__i18nAudit.requests===window.__beforeLocale.requests && document.querySelector('#product-image-file').files.length===1"), "i18n-private-preview-and-selected-file-stable-" + value)
            locale("ar")
            button("products", "uploadImage", "ar")
            page.wait("document.querySelectorAll('img[src^=\"blob:\"]').length===2 && Array.from(document.querySelectorAll('img[src^=\"blob:\"]')).every(i=>i.naturalWidth>0)", "second-private-image")
            def owner_order():
                return page.evaluate("import('/src/features/productImages/api.ts').then(m=>m.getMyProductImages(" + json.dumps(slug) + ").then(images=>images.map(i=>i.ref)))")

            original_order = owner_order()
            page.evaluate("window.__oldCover=document.querySelector('img[src^=\"blob:\"]').src")
            button("products", "moveLater", "ar")
            page.wait("document.querySelector('img[src^=\"blob:\"]').src!==window.__oldCover", "RTL-reorder")
            check(owner_order() == list(reversed(original_order)), "i18n-RTL-image-reorder-matches-label")
            button("products", "publish", "ar")
            page.wait("Boolean(document.querySelector('a[href=\"/p/" + slug + "\"]'))", "published")
            page.link("/p/" + slug)
            page.wait("document.querySelectorAll('article img').length===2 && Array.from(document.querySelectorAll('article img')).every(i=>i.naturalWidth>0)", "public-images-loaded")
            for width in (1280, 390):
                viewport(width)
                for value in LOCALES:
                    locale(value)
                    check(page.evaluate("document.querySelector('h1').textContent===" + json.dumps(title) + " && document.querySelector('h1').dir==='auto' && !document.querySelector('article script') && document.querySelectorAll('article img').length===2 && document.documentElement.scrollWidth<=innerWidth"), f"i18n-public-original-content-safe-{value}-{width}")
            with httpx.Client(base_url=backend, trust_env=False) as anonymous:
                public = anonymous.get("/api/v1/products/" + slug).json()
                check(public["title"] == title and public["description"] == description and public["price"] == "19.99" and public["currency"] == "CNY", "i18n-server-original-content-and-decimal")
                check(not {"storage_key", "seller_user_id", "id"}.intersection(public) and len(public["images"]) == 2, "i18n-public-contract-privacy")
            page.evaluate("history.back()")
            page.wait("location.pathname===" + json.dumps("/seller/listings/" + slug + "/edit"), "return-to-owner-shell")
            page.link("/seller/listings")
            page.wait("Boolean(document.querySelector('time[datetime]'))", "owner-list-UTC-clock")
            for value, intl in (("en", "en-US"), ("zh-CN", "zh-CN"), ("ar", "ar-MA"), ("fr", "fr-FR")):
                locale(value)
                expression = r"""(()=>{const element=document.querySelector('time'),raw=element.dateTime;
                  const timestamp=/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(raw)?raw+'Z':raw;
                  const date=new Intl.DateTimeFormat(INTL,{year:'numeric',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',second:'2-digit',timeZone:'UTC',timeZoneName:'short'}).format(new Date(timestamp));
                  return element.textContent===COPY.replace('{{date}}',date);})()"""
                expression = expression.replace("INTL", json.dumps(intl)).replace("COPY", json.dumps(COPY[value]["products"]["updated"]))
                check(page.evaluate(expression), "i18n-owner-list-preserves-UTC-clock-" + value)
            locale("ar")
            page.call("Page.navigate", {"url": frontend + "/seller/listings/" + slug + "/edit"})
            page.wait("document.querySelectorAll('img[src^=\"blob:\"]').length===2 && Array.from(document.querySelectorAll('img[src^=\"blob:\"]')).every(i=>i.naturalWidth>0)", "private-restored")
            check(page.evaluate("document.documentElement.lang==='ar'"), "i18n-auth-refresh-Arabic-persistence")
            stage = "held-private-response"
            held_url = backend + "/api/v1/seller/products/" + slug + "/images/" + public["images"][-1]["ref"]
            page.call("Fetch.enable", {"patterns": [{"urlPattern": held_url, "requestStage": "Response"}]})
            page.link("/seller/listings")
            page.wait("location.pathname==='/seller/listings' && !document.querySelector('section[aria-label] ol')", "private-view-unmounted")
            page.evaluate("history.back()")
            page.wait("location.pathname===" + json.dumps("/seller/listings/" + slug + "/edit")
                      + " && document.querySelectorAll('section[aria-label] ol li').length===2", "owner-images-remounted")
            held = page.event("Fetch.requestPaused", lambda event: event.get("url") == held_url, "private-response-paused")
            page.wait("Array.from(document.querySelectorAll('img[src^=\"blob:\"]')).some(e=>e.complete&&e.naturalWidth>0)", "other-private-preview-live")
            check(held.get("responseStatusCode") == 200 and bool(held.get("networkId")) and
                  not any(event["method"] in {"Network.loadingFinished", "Network.loadingFailed"} and
                          event["params"].get("requestId") == held["networkId"] for event in page.events),
                  "i18n-private-response-held-while-other-preview-visible")
            locale("fr")
            locale("ar")
            check(page.evaluate("Array.from(document.querySelectorAll('img[src^=\"blob:\"]')).some(e=>e.complete&&e.naturalWidth>0)"),
                  "i18n-held-response-does-not-hide-other-private-preview")
            button("common", "signOut", "ar")
            page.wait("location.pathname==='/login' && Boolean(document.querySelector('#identifier'))", "logout")
            check(page.evaluate("document.querySelectorAll('img[src^=\"blob:\"]').length===0 && window.__i18nAudit.revoked>=window.__i18nAudit.created && localStorage.length===1 && localStorage.getItem('unishop.locale')==='ar' && sessionStorage.length===0"), "i18n-logout-revokes-private-previews-preserves-only-locale")
            created_at_logout = page.evaluate("window.__i18nAudit.created")
            page.value("#identifier", other_email)
            page.value("#password", other_password)
            button("common", "signIn", "ar")
            page.wait("location.pathname!='/login'", "other-account-login")
            page.call("Fetch.continueRequest", {"requestId": held["requestId"]})
            completed = page.event("Network.loadingFinished", lambda event: event.get("requestId") == held["networkId"], "late-private-response-completed")
            check(completed["requestId"] == held["networkId"], "i18n-held-private-response-completes-after-account-switch")
            check(page.evaluate("new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve(document.documentElement.lang==='ar' && document.querySelectorAll('img[src^=\"blob:\"]').length===0 && window.__i18nAudit.created===" + str(created_at_logout) + "))))"),
                  "i18n-no-Seller-A-preview-or-new-Blob-after-late-response")
            page.call("Fetch.disable")
            page.call("Page.navigate", {"url": frontend + "/seller/listings/" + slug + "/edit"})
            page.wait("document.body.textContent.includes(" + json.dumps(COPY["ar"]["products"]["unavailable"]) + ")", "cross-owner-denied")
            check(page.evaluate("document.documentElement.lang==='ar' && document.querySelectorAll('img[src^=\"blob:\"]').length===0 && localStorage.length===1 && !location.href.includes('token=') && !location.href.includes('storage_key')"), "i18n-account-switch-private-image-isolation")
            print(json.dumps({"i18n_browser": "PASS", "engine": "real Chrome headless", "visual_artifacts": str(visual), "switch_roundtrip_ms_min": min(timings), "switch_roundtrip_ms_max": max(timings)}))
    except Exception as error:
        print(json.dumps({"i18n_browser": "FAIL", "stage": stage, "error_type": type(error).__name__, "safe_check": str(error) if isinstance(error, AssertionError) else None, "visual_artifacts": str(visual)}))
        raise
    finally:
        if process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            process.wait(timeout=10)


if __name__ == "__main__":
    import scripts.product_image_browser_checks as original_browser
    from scripts.audit_security_http import main
    original_browser.run_browser_checks = run_browser_checks
    sys.argv = [sys.argv[0], "--browser"]
    raise SystemExit(main())
