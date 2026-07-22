"""MatForge shared config — key management + the omega (Fable-5) HTTP call.
Used by forge_fal.py (vision prompts), forge_max.py (chat help + key settings).

Key resolution order: process env -> _keys.json (written by the Settings panel)
-> Windows env var -> hardcoded _falkey.py/_omegakey.py fallback.
"""
import json
import os

_REPO = os.path.dirname(os.path.abspath(__file__))
_KEYS_PATH = os.path.join(_REPO, "_keys.json")

OMEGA_DEFAULT_BASE = "https://omega.kesarcloud.in/v1"
OMEGA_DEFAULT_MODEL = "claude-fable-5"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MatForge/1.0"


def _load():
    try:
        with open(_KEYS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_fal_key():
    k = os.environ.get("FAL_KEY")
    if k:
        return k
    d = _load()
    if d.get("fal_key"):
        return d["fal_key"]
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as h:
            v = winreg.QueryValueEx(h, "FAL_KEY")[0]
            if v:
                return v
    except Exception:
        pass
    try:
        import _falkey
        return _falkey.FAL_KEY
    except Exception:
        return None


def get_omega():
    """Return (key, base_url, model)."""
    d = _load()
    key = d.get("omega_key") or ""
    base = d.get("omega_base") or ""
    model = d.get("omega_model") or ""
    if not key or not base:
        try:
            import _omegakey
            key = key or _omegakey.OMEGA_KEY
            base = base or _omegakey.OMEGA_BASE
            model = model or _omegakey.OMEGA_MODEL
        except Exception:
            pass
    return key, (base or OMEGA_DEFAULT_BASE), (model or OMEGA_DEFAULT_MODEL)


def save_keys(fal_key=None, omega_key=None, omega_model=None):
    d = _load()
    if fal_key is not None:
        d["fal_key"] = str(fal_key).strip()
    if omega_key is not None:
        d["omega_key"] = str(omega_key).strip()
    if omega_model:
        d["omega_model"] = str(omega_model).strip()
    with open(_KEYS_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    return True


def _mask(s):
    if not s:
        return ""
    return (s[:6] + "…" + s[-4:]) if len(s) > 12 else "set"


def get_keys_status():
    """Masked view for the Settings panel (never returns full secrets)."""
    fk = get_fal_key() or ""
    ok, _, model = get_omega()
    return {"fal": _mask(fk), "omega": _mask(ok), "omega_model": model,
            "fal_set": bool(fk), "omega_set": bool(ok)}


def omega_message(content, max_tokens=400, system=None, timeout=30):
    """One Anthropic-style call to the omega gateway. `content` is a list of
    message content blocks. Returns the assistant text, or raises."""
    import urllib.request

    key, base, model = get_omega()
    if not key:
        raise RuntimeError("no omega key set")
    body = {"model": model, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": content}]}
    if system:
        body["system"] = system

    def _call(m):
        b = dict(body, model=m)
        req = urllib.request.Request(
            base.rstrip("/") + "/messages",
            data=json.dumps(b).encode(), method="POST")
        req.add_header("Authorization", "Bearer " + key)
        req.add_header("anthropic-version", "2023-06-01")
        req.add_header("content-type", "application/json")
        req.add_header("User-Agent", _UA)   # gateway Cloudflare 1010s default UA
        with urllib.request.urlopen(req, timeout=timeout) as r:
            resp = json.load(r)
        return "".join(p.get("text", "") for p in resp.get("content", [])
                       if p.get("type") == "text").strip()

    try:
        return _call(model)
    except Exception:
        if model != OMEGA_DEFAULT_MODEL:
            raise
        return _call("claude-opus-4-8")     # fallback model on the gateway
