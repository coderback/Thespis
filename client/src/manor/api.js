// The manor's engine API (docs/manor.md), under /manor on the same server as The Crypt Road.

export class ApiError extends Error {
  constructor(status, error, reason) {
    super(reason);
    this.status = status;
    this.error = error;
    this.reason = reason;
  }
}

export class ManorApi {
  constructor(base = new URL("../manor", location.href).pathname) {
    this.base = base.replace(/\/$/, "");
    this.session = null;
    this.kind = "http";
  }

  async req(method, path, body) {
    const headers = { "Content-Type": "application/json" };
    if (this.session) headers["X-Session"] = this.session;
    let res;
    try {
      res = await fetch(this.base + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    } catch {
      throw new ApiError(0, "network", "Can't reach the engine. Is it running?");
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new ApiError(res.status, data.error || "error", data.reason || `HTTP ${res.status}`);
    return data;
  }

  async newSession() {
    this.session = null;
    const out = await this.req("POST", "/session", {});
    this.session = out.session;
    return out;
  }

  state() { return this.req("GET", "/state"); }
  allowed() { return this.req("GET", "/allowed"); }
  act(body) { return this.req("POST", "/act", body); }
  say(body) { return this.req("POST", "/say", body); } // {target, text}: read as one of the buttons, or as nothing
  reset() { return this.req("POST", "/reset", {}); }
  reload() { return this.req("POST", "/reload", {}); }
  brain(mode) { return this.req("POST", "/dev/brain", { mode }); }
}
