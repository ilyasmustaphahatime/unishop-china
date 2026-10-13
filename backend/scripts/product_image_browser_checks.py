"""Real Chrome UI checks in an isolated profile; no personal browser data or TLS bypass."""
from io import BytesIO
from pathlib import Path
import json
import subprocess
import time

import httpx
from PIL import Image
from websockets.sync.client import connect

CHROME=Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


class BrowserEnvironmentBlocked(RuntimeError):
    pass


class Page:
    def __init__(self,socket):
        self.socket,self.serial=socket,0
        self.events=[]

    def call(self,method,params=None):
        self.serial+=1
        request_id=self.serial
        self.socket.send(json.dumps({"id":request_id,"method":method,"params":params or {}}))
        while True:
            response=json.loads(self.socket.recv(timeout=15))
            event=response.get("method")
            if event in {"Fetch.requestPaused","Network.loadingFinished","Network.loadingFailed"}:
                params=response.get("params",{})
                # Retain only scheduling metadata, never request headers/cookies/body.
                safe={key:params[key] for key in ("requestId","networkId","responseStatusCode","canceled") if key in params}
                if event=="Fetch.requestPaused":
                    safe["url"]=params.get("request",{}).get("url")
                self.events.append({"method":event,"params":safe})
            if response.get("id")==request_id:
                if "error" in response:
                    raise RuntimeError("Browser protocol operation failed.")
                return response.get("result",{})

    def event(self,method,predicate,label):
        for _ in range(150):
            for index,event in enumerate(self.events):
                if event["method"]==method and predicate(event["params"]):
                    return self.events.pop(index)["params"]
            self.evaluate("0")  # Drain notifications through a harmless protocol round-trip.
            time.sleep(0.1)
        raise AssertionError("Browser event wait failed: "+label)

    def evaluate(self,expression):
        result=self.call("Runtime.evaluate",{"expression":expression,"returnByValue":True,"awaitPromise":True})
        if "exceptionDetails" in result:
            raise RuntimeError("Browser evaluation failed.")
        return result.get("result",{}).get("value")

    def wait(self,expression,label):
        for _ in range(150):
            if self.evaluate(expression):
                return
            time.sleep(0.1)
        raise AssertionError("Browser wait failed: "+label)

    def value(self,selector,value):
        self.evaluate("""(()=>{const element=document.querySelector(%s);
          const prototype=element.tagName==='SELECT'?HTMLSelectElement.prototype:
            element.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
          Object.getOwnPropertyDescriptor(prototype,'value').set.call(element,%s);
          element.dispatchEvent(new Event('input',{bubbles:true}));
          element.dispatchEvent(new Event('change',{bubbles:true}));})()"""%(json.dumps(selector),json.dumps(value)))

    def click(self,text,*,tag="button"):
        expression="Array.from(document.querySelectorAll("+json.dumps(tag)+")).find(e=>e.textContent.trim()==="+json.dumps(text)+" && !e.disabled)"
        self.wait("Boolean("+expression+")","control-ready")
        self.evaluate("("+expression+").click()")

    def link(self,path):
        self.wait("Boolean(document.querySelector('a[href="+json.dumps(path)+"]'))","navigation-ready")
        self.evaluate("document.querySelector('a[href="+json.dumps(path)+"]').click()")

    def file(self,path):
        self.wait("Boolean(document.querySelector('#product-image-file') && !document.querySelector('#product-image-file').disabled)","file-ready")
        document=self.call("DOM.getDocument")
        node=self.call("DOM.querySelector",{"nodeId":document["root"]["nodeId"],"selector":"#product-image-file"})
        self.call("DOM.setFileInputFiles",{"nodeId":node["nodeId"],"files":[str(path)]})


def run_browser_checks(frontend,backend,email,password,other_email,other_password,category,root,check):
    if not CHROME.is_file():
        raise BrowserEnvironmentBlocked("Chrome executable unavailable.")
    root=root.resolve()
    profile=root/"profile"
    process=subprocess.Popen([str(CHROME),"--headless=new","--disable-background-networking",
        "--remote-debugging-address=127.0.0.1","--remote-debugging-port=0","--user-data-dir="+str(profile),"about:blank"],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    stage="startup"
    try:
        for _ in range(80):
            if (profile/"DevToolsActivePort").is_file():
                port=int((profile/"DevToolsActivePort").read_text().splitlines()[0])
                break
            time.sleep(0.1)
        else:
            raise BrowserEnvironmentBlocked("Headless runtime unavailable.")
        with httpx.Client(trust_env=False,timeout=5) as protocol:
            tab=protocol.put(f"http://127.0.0.1:{port}/json/new?about:blank").json()
        with connect(tab["webSocketDebuggerUrl"],proxy=None,max_size=4*1024*1024,open_timeout=5) as socket:
            page=Page(socket)
            page.call("Page.enable")
            page.call("Network.enable")
            page.call("Emulation.setDeviceMetricsOverride",{"width":1280,"height":900,"deviceScaleFactor":1,"mobile":False})
            page.call("Page.addScriptToEvaluateOnNewDocument",{"source":"""(()=>{
              window.__imageAudit={created:0,revoked:0};
              const create=URL.createObjectURL.bind(URL),revoke=URL.revokeObjectURL.bind(URL);
              URL.createObjectURL=(blob)=>{window.__imageAudit.created++;return create(blob);};
              URL.revokeObjectURL=(url)=>{window.__imageAudit.revoked++;return revoke(url);};})();"""})
            stage="seller-login"
            page.call("Page.navigate",{"url":frontend+"/login"})
            page.wait("Boolean(document.querySelector('#identifier'))",stage)
            page.value("#identifier",email)
            page.value("#password",password)
            page.click("Sign in")
            page.wait("location.pathname!='/login' && Boolean(document.querySelector('a[href=\"/sell/new\"]'))",stage)
            check(True,"browser-seller-login")
            page.link("/sell/new")
            page.wait("Boolean(document.querySelector('#product-title'))","create-ready")
            page.wait("Boolean(document.querySelector('#product-category option[value="+json.dumps(category)+"]'))","catalog-ready")
            page.value("#product-title","Synthetic browser image listing")
            page.value("#product-description","Only synthetic images for real browser verification.")
            page.value("#product-price","19.99")
            page.value("#product-city","qingdao")
            page.value("#product-category",category)
            page.click("Create draft")
            page.wait("/^\\/seller\\/listings\\/item-[0-9a-f]{24}\\/edit$/.test(location.pathname)","draft-created")
            slug=page.evaluate("location.pathname.split('/')[3]")
            check(True,"browser-create-draft")
            public="/api/v1/products/"+slug
            photo=root/"input.png"
            for index,color in enumerate(((120,20,20),(20,20,120),(20,120,20),(120,120,20)),1):
                with Image.new("RGB",(16,12),color) as image:
                    output=BytesIO()
                    image.save(output,format="PNG")
                    photo.write_bytes(output.getvalue())
                stage="upload-"+str(index)
                page.file(photo)
                page.click("Upload image")
                page.wait("document.querySelectorAll('section[aria-label=\"Product images\"] ol li').length=="+str(index),stage)
                page.wait("Array.from(document.querySelectorAll('section[aria-label=\"Product images\"] img')).length=="+str(index)+
                    " && Array.from(document.querySelectorAll('section[aria-label=\"Product images\"] img')).every(e=>e.complete&&e.naturalWidth>0)",stage)
                check(True,"browser-upload-and-authenticated-preview-"+str(index))
            page.evaluate("window.__firstPreview=document.querySelector('section[aria-label=\"Product images\"] img').src")
            page.click("Move right")
            page.wait("document.querySelector('section[aria-label=\"Product images\"] img').src!==window.__firstPreview","cover-changed")
            check(True,"browser-reorder-cover")
            page.click("Publish")
            page.wait("Boolean(Array.from(document.querySelectorAll('button')).find(e=>e.textContent.trim()==='Pause'))","published")
            page.click("Public page",tag="a")
            page.wait("document.querySelectorAll('[aria-label=\"Product gallery\"] img').length==4 && "
              "Array.from(document.querySelectorAll('[aria-label=\"Product gallery\"] img')).every(e=>e.complete&&e.naturalWidth>0)","public-gallery")
            check(True,"browser-public-gallery")
            with httpx.Client(base_url=backend,trust_env=False) as anonymous:
                metadata=anonymous.get(public).json()["images"]
                check(len(metadata)==4,"browser-public-metadata")
                image_url=metadata[0]["url"]
                check(anonymous.get(image_url).status_code==200,"browser-public-bytes")
                page.call("Page.navigate",{"url":frontend+"/seller/listings/"+slug+"/edit"})
                page.wait("Boolean(Array.from(document.querySelectorAll('button')).find(e=>e.textContent.trim()==='Pause'))","manage-restored")
                check(True,"browser-refresh-cookie-bootstrap")
                page.click("Pause")
                page.wait("Boolean(Array.from(document.querySelectorAll('button')).find(e=>e.textContent.trim()==='Publish'))","paused")
                check(anonymous.get(image_url).status_code==404,"browser-pause-hides-image")
                page.click("Publish")
                page.wait("Boolean(Array.from(document.querySelectorAll('button')).find(e=>e.textContent.trim()==='Pause'))","republished")
                check(anonymous.get(image_url).status_code==200,"browser-republish-restores-image")
                page.click("Delete image 1")
                page.wait("document.querySelectorAll('section[aria-label=\"Product images\"] ol li').length==3","deleted")
                check(anonymous.get(image_url).status_code==404,"browser-deleted-cover-hidden")
                stage="archive"
                page.click("Archive permanently")
                page.wait("!document.querySelector('#product-image-file') && Boolean(Array.from(document.querySelectorAll('button')).find(e=>e.textContent.trim()==='Delete image 1'))","archived")
                check(anonymous.get(public).status_code==404,"browser-archive-hides-parent")
            check(not page.evaluate("Boolean(Array.from(document.querySelectorAll('button')).find(e=>e.textContent.trim()==='Move right'))"),"browser-archive-no-reorder")
            page.click("Delete image 1")
            page.wait("document.querySelectorAll('section[aria-label=\"Product images\"] ol li').length===2","archived-cleanup")
            check(True,"browser-archived-owner-delete")
            page.wait("Boolean(document.querySelector('img[src^=\"blob:\"]')?.complete && document.querySelector('img[src^=\"blob:\"]')?.naturalWidth)","remaining-private-preview")
            # Real UI remount refetches two owner previews. Hold one already-
            # authorized 200 response while the other is genuinely displayed.
            # Releasing it only after logout AND account B login exercises the
            # actual browser/axios session fence, not a mocked API promise.
            stage="late-private-response"
            held_url=backend+"/api/v1/seller/products/"+slug+"/images/"+metadata[-1]["ref"]
            page.call("Fetch.enable",{"patterns":[{"urlPattern":held_url,"requestStage":"Response"}]})
            page.link("/seller/listings")
            page.wait("location.pathname==='/seller/listings' && !document.querySelector('section[aria-label=\"Product images\"]')","private-view-unmounted")
            page.evaluate("history.back()")
            page.wait("location.pathname==="+json.dumps("/seller/listings/"+slug+"/edit")+
                      " && document.querySelectorAll('section[aria-label=\"Product images\"] ol li').length===2","private-view-remounted")
            held=page.event("Fetch.requestPaused",lambda event:event.get("url")==held_url,"private-response-paused")
            page.wait("Array.from(document.querySelectorAll('img[src^=\"blob:\"]')).some(e=>e.complete&&e.naturalWidth>0)","live-preview-with-held-response")
            check(held.get("responseStatusCode")==200 and bool(held.get("networkId")) and
                  not any(event["method"] in {"Network.loadingFinished","Network.loadingFailed"} and
                          event["params"].get("requestId")==held["networkId"] for event in page.events),
                  "browser-private-response-paused-with-live-preview")
            page.call("Emulation.setDeviceMetricsOverride",{"width":390,"height":844,"deviceScaleFactor":1,"mobile":True})
            check(page.evaluate("document.documentElement.scrollWidth<=window.innerWidth"),"browser-mobile-no-horizontal-overflow")
            check(page.evaluate("Boolean(document.querySelector('img[src^=\"blob:\"]')) && window.__imageAudit.created>window.__imageAudit.revoked"),"browser-live-private-preview-before-logout")
            page.click("Sign out")
            page.wait("location.pathname==='/login' && Boolean(document.querySelector('#identifier'))","signed-out")
            check(page.evaluate("document.querySelectorAll('img[src^=\"blob:\"]').length===0"),"browser-logout-private-preview-removed")
            check(page.evaluate("window.__imageAudit.revoked>=window.__imageAudit.created"),"browser-object-urls-revoked")
            check(page.evaluate("localStorage.length===0 && sessionStorage.length===0"),"browser-no-persistent-private-state")
            created_at_logout=page.evaluate("window.__imageAudit.created")
            stage="second-account"
            page.value("#identifier",other_email)
            page.value("#password",other_password)
            page.click("Sign in")
            page.wait("location.pathname!='/login'","second-login")
            page.call("Fetch.continueRequest",{"requestId":held["requestId"]})
            terminal=page.event("Network.loadingFinished",lambda event:event.get("requestId")==held["networkId"],"late-private-response-completed")
            check(terminal["requestId"]==held["networkId"],"browser-private-response-completes-after-account-switch")
            # Let promise handlers and React paint after the actual network completion.
            clean=page.evaluate("new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve(document.querySelectorAll('img[src^=\"blob:\"]').length===0 && window.__imageAudit.created==="+str(created_at_logout)+" && window.__imageAudit.revoked>=window.__imageAudit.created))))")
            check(clean,"browser-late-private-response-cannot-restore-preview")
            page.call("Fetch.disable")
            page.call("Page.navigate",{"url":frontend+"/seller/listings/"+slug+"/edit"})
            page.wait("document.body.textContent.includes('This listing is not available.')","cross-owner-denied")
            check(page.evaluate("document.querySelectorAll('img[src^=\"blob:\"]').length===0"),"browser-second-account-no-private-images")
            check(page.evaluate("!location.href.includes('token=') && !location.href.includes('product-media') && !location.href.includes('storage_key')"),"browser-address-bar-privacy")
            print(json.dumps({"browser":"PASS","engine":"Chrome headless","synthetic_profile":True}))
    except Exception as error:
        detail = str(error) if isinstance(error, AssertionError) else type(error).__name__
        print(json.dumps({"browser":"FAIL","stage":stage,"check":detail}))
        raise
    finally:
        if process.poll() is None:
            subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            process.wait(timeout=10)
