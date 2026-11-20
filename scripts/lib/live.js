"use strict";

const { CDP } = require("../recorder/cdp");

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

class Live {
  constructor(port, label) {
    this.port = port;
    this.label = label || String(port);
    this.cdp = null;
    this.page = null;
    this.origin = "";
    this.query = "";
    this.headers = null;
    this.lastRequestAt = 0;
  }

  async connect() {
    const list = await (await fetch(`http://127.0.0.1:${this.port}/json/list`)).json();
    const page = list.find((t) => t.type === "page" && t.url.includes("channels.weixin.qq.com")) || list.find((t) => t.type === "page");
    if (!page) throw new Error(`no page on ${this.port}`);
    this.page = page;
    this.cdp = new CDP(page.webSocketDebuggerUrl, `live-${this.label}`);
    await this.cdp.connect();
    await this.cdp.send("Page.enable").catch(() => {});
    await this.cdp.send("Network.enable").catch(() => {});

    this.cdp.on("Network.requestWillBeSent", (p) => {
      const r = p.request || {};
      if (!/\/promote\/api\/web\/transfer\//.test(r.url || "")) return;
      try {
        const u = new URL(r.url);
        this.origin = u.origin;
        this.query = u.search ? u.search.slice(1) : "";
      } catch (_) {}
    });

    this.cdp.on("Network.requestWillBeSentExtraInfo", (p) => {
      if (!this.origin) return;
      const h = p.headers || {};
      const get = (k) => {
        const key = Object.keys(h).find((x) => x.toLowerCase() === k.toLowerCase());
        return key ? h[key] : undefined;
      };
      const uab = get("uab-session-id");
      const finger = get("finger-print-device-id");
      if (!uab || !finger) return;
      this.headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "finger-print-device-id": finger,
        "promote-biz-id": get("promote-biz-id") || "0",
        "uab-session-id": uab,
      };
      this.lastRequestAt = Date.now();
    });

    return this;
  }

  async ensureHeaders(timeoutMs = 30000) {
    if (this.headers && this.origin) return;
    await this.cdp.send("Page.reload", { ignoreCache: false }).catch(() => {});
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      if (this.headers && this.origin) return;
      await sleep(500);
    }
    throw new Error(`headers not captured on ${this.port}`);
  }

  async evaluate(expression, timeoutMs = 30000) {
    const r = await this.cdp.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true }, timeoutMs);
    return r && r.result ? r.result.value : null;
  }

  async api(apiPath, body = {}) {
    await this.ensureHeaders();
    const url = `${this.origin}/promote/api/web/transfer/${apiPath}?${this.query}`;
    const expr =
      "(async()=>{try{const r=await fetch(" +
      JSON.stringify(url) +
      ",{method:'POST',headers:" +
      JSON.stringify(this.headers) +
      ",body:" +
      JSON.stringify(JSON.stringify(body)) +
      ",credentials:'include'});return JSON.stringify({status:r.status,text:await r.text()})}catch(e){return JSON.stringify({error:String(e)})}})()";
    const raw = await this.evaluate(expr, 30000);
    if (!raw) throw new Error(`empty response ${this.port}`);
    const p = JSON.parse(raw);
    if (p.error) throw new Error(p.error);
    if (p.status !== 201) throw new Error(`HTTP ${p.status} ${String(p.text).slice(0, 200)}`);
    return JSON.parse(p.text);
  }

  async text() {
    return this.evaluate("(document.body && document.body.innerText || '').slice(0,3000)");
  }

  close() {
    if (this.cdp) this.cdp.close();
  }
}

module.exports = { Live };
