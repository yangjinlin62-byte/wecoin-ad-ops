"use strict";

const fs = require("fs");
const path = require("path");
const { CDP } = require("../recorder/cdp");

const ROOT = path.join(__dirname, "..", "..");
const taskFile = process.argv[2];
const port = Number(process.argv[3] || 9445);
const outName = process.argv[4] || "cashier-inject.jpg";
const j = JSON.parse(fs.readFileSync(taskFile, "utf8"));
const token = (((j.data || {}).result || {}).pcSdkInfo);
if (!token) throw new Error("no pcSdkInfo");

(async () => {
  const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const page = list.find((t) => t.type === "page" && t.url.includes("channels.weixin.qq.com"));
  const c = new CDP(page.webSocketDebuggerUrl, "cashier");
  await c.connect();
  await c.send("Page.bringToFront");

  const url = "https://webeans.my-qcloud.com/sdk/#/consume/qrcode?" + token + "&theme=light";
  const expr = `(function(){
    try{var old=document.getElementById('__pay_iframe'); if(old) old.remove();}catch(e){}
    window.__payResult=null;
    window.addEventListener('message', function(e){ try{ if(e.data && (e.data.type||e.data.event)) window.__payResult=JSON.stringify(e.data).slice(0,500); }catch(_){} });
    var f=document.createElement('iframe');
    f.id='__pay_iframe';
    f.src=${JSON.stringify(url)};
    f.setAttribute('allowtransparency','true');
    f.style.cssText='position:fixed;top:0;left:0;width:100%;height:100%;border:none;z-index:999999;background:#fff;';
    document.body.appendChild(f);
    return 'injected ' + ${JSON.stringify(url.length)};
  })()`;
  const r = await c.send("Runtime.evaluate", { expression: expr, returnByValue: true });
  console.log(r.result && r.result.value);
  await new Promise((res) => setTimeout(res, 5000));

  const s = await c.send("Page.captureScreenshot", { format: "jpeg", quality: 85, fromSurface: true });
  const out = path.join(ROOT, "data", "ops", outName);
  fs.writeFileSync(out, Buffer.from(s.data, "base64"));
  console.log("screenshot", out);

  const state = await c.send("Runtime.evaluate", {
    expression: `JSON.stringify({result:window.__payResult, iframes:Array.from(document.querySelectorAll('iframe')).map(function(f){return {src:f.src, w:f.clientWidth, h:f.clientHeight}})})`,
    returnByValue: true,
  });
  console.log(state.result && state.result.value);
  c.close();
})();
