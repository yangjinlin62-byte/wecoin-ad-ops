"use strict";

/**
 * 极简 CDP 客户端，基于 Node 24 内置的 WebSocket。
 * 只实现本项目需要的能力：request/response + event 订阅。
 */
class CDP {
  constructor(wsUrl, label) {
    this.wsUrl = wsUrl;
    this.label = label || "target";
    this.ws = null;
    this.nextId = 0;
    this.pending = new Map();
    this.handlers = new Map();
    this.closed = false;
  }

  connect(timeoutMs = 15000) {
    return new Promise((resolve, reject) => {
      let settled = false;
      const ws = new WebSocket(this.wsUrl);
      this.ws = ws;

      const timer = setTimeout(() => {
        if (settled) return;
        settled = true;
        try { ws.close(); } catch (_) {}
        reject(new Error("CDP connect timeout: " + this.wsUrl));
      }, timeoutMs);

      ws.addEventListener("open", () => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve(this);
      });

      ws.addEventListener("error", (ev) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        reject(new Error("CDP connect error: " + (ev && ev.message ? ev.message : this.wsUrl)));
      });

      ws.addEventListener("message", (ev) => {
        let msg;
        try {
          const raw = typeof ev.data === "string" ? ev.data : Buffer.from(ev.data).toString("utf8");
          msg = JSON.parse(raw);
        } catch (_) {
          return;
        }
        this._onMessage(msg);
      });

      ws.addEventListener("close", () => {
        this.closed = true;
        for (const [, p] of this.pending) {
          clearTimeout(p.timer);
          p.reject(new Error("CDP closed: " + this.label));
        }
        this.pending.clear();
        this._emit("__close", {});
      });
    });
  }

  _onMessage(msg) {
    if (msg.id && this.pending.has(msg.id)) {
      const p = this.pending.get(msg.id);
      this.pending.delete(msg.id);
      clearTimeout(p.timer);
      if (msg.error) p.reject(new Error(msg.error.message || "CDP error"));
      else p.resolve(msg.result || {});
      return;
    }
    if (msg.method) this._emit(msg.method, msg.params || {});
  }

  on(method, handler) {
    if (!this.handlers.has(method)) this.handlers.set(method, []);
    this.handlers.get(method).push(handler);
    return this;
  }

  _emit(method, params) {
    const list = this.handlers.get(method);
    if (!list) return;
    for (const fn of list) {
      try { fn(params); } catch (e) { /* 不让单个处理器打断整个会话 */ }
    }
  }

  send(method, params = {}, timeoutMs = 20000) {
    if (!this.ws || this.closed || this.ws.readyState !== 1) {
      return Promise.reject(new Error("CDP not open: " + method));
    }
    const id = ++this.nextId;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error("CDP timeout: " + method));
      }, timeoutMs);
      this.pending.set(id, { resolve, reject, timer });
      try {
        this.ws.send(JSON.stringify({ id, method, params }));
      } catch (e) {
        clearTimeout(timer);
        this.pending.delete(id);
        reject(e);
      }
    });
  }

  close() {
    try { if (this.ws) this.ws.close(); } catch (_) {}
  }
}

module.exports = { CDP };
