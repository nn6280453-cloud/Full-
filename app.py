import os
import time
import base64
import threading
from pathlib import Path

from flask import Flask, request, jsonify, render_template_string
import requests
from dotenv import load_dotenv

load_dotenv()

from neonize.client import NewClient
from neonize.events import ConnectedEv, DisconnectedEv

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

IMGBB_KEY = os.getenv("IMGBB_API_KEY")
SESSION_ROOT = Path(os.getenv("SESSION_ROOT", "./sessions"))
SESSION_ROOT.mkdir(parents=True, exist_ok=True)

SESSIONS = {}
LOCK = threading.Lock()


def clean_phone(p):
    n = "".join(c for c in str(p) if c.isdigit())
    if n.startswith("0"):
        n = n[1:]
    return n


def bind_phone(phone):
    with LOCK:
        s = SESSIONS.get(phone)
        if s and s.get("connected"):
            return {"already": True}

    session_dir = SESSION_ROOT / phone
    session_dir.mkdir(parents=True, exist_ok=True)

    client = NewClient(str(session_dir / "session.db"))

    @client.event(ConnectedEv)
    def _on_connected(_client, _event):
        if phone in SESSIONS:
            SESSIONS[phone]["connected"] = True
            SESSIONS[phone]["code"] = None
        print(f"[K] {phone} connected", flush=True)

    @client.event(DisconnectedEv)
    def _on_disconnected(_client, _event):
        if phone in SESSIONS:
            SESSIONS[phone]["connected"] = False
        print(f"[K] {phone} disconnected", flush=True)

    SESSIONS[phone] = {
        "client": client,
        "code": None,
        "connected": False,
        "created": time.time(),
    }

    # Neonize 0.5.x: pass pairphone to connect() — it returns the pairing code
    code = None
    try:
        code = client.connect(pairphone=phone)
    except Exception as e:
        print(f"[K] connect(pairphone) failed: {e}", flush=True)

    if not code:
        # fallback for versions where connect() returns None
        time.sleep(2)
        try:
            code = client.PairPhone(phone, show_push_notification=True)
        except Exception as e:
            raise RuntimeError(f"pairing failed: {e}")

    SESSIONS[phone]["code"] = code
    print(f"[K] pairing code for {phone}: {code}", flush=True)
    return {"code": code}


def set_full_dp(phone, image_url):
    s = SESSIONS.get(phone)
    if not s:
        raise RuntimeError("session not found")
    if not s.get("connected"):
        raise RuntimeError("session not connected")

    img_bytes = requests.get(image_url, timeout=30).content
    s["client"].set_profile_photo(img_bytes)
    return True


HTML_PAGE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nima Full DP</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@600;700&display=swap" rel="stylesheet">
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Inter',system-ui,sans-serif;background:radial-gradient(ellipse at top,#131829 0%,#08090d 60%);color:#e8ecf4;min-height:100vh;padding:32px 16px 64px;line-height:1.5}
  .wrap{max-width:560px;margin:0 auto}
  .brand{display:flex;align-items:center;gap:12px;margin-bottom:8px}
  .logo{width:42px;height:42px;border-radius:11px;background:linear-gradient(135deg,#7c5cff,#22d3ee);display:flex;align-items:center;justify-content:center;font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:18px;color:#08090d}
  h1{font-family:'Space Grotesk',sans-serif;font-size:26px;font-weight:700;letter-spacing:-.5px}
  .tag{color:#7c8699;font-size:13.5px;margin-bottom:28px}
  .badge{display:inline-block;font-size:11px;font-weight:600;background:rgba(124,92,255,.15);color:#a99bff;padding:3px 9px;border-radius:6px;margin-left:6px;text-transform:uppercase;letter-spacing:.5px}
  .card{background:#0f1219;border:1px solid #1c2130;border-radius:16px;padding:22px;margin-bottom:14px}
  .step-label{display:flex;align-items:center;gap:10px;font-size:12px;color:#7c8699;text-transform:uppercase;letter-spacing:.7px;font-weight:600;margin-bottom:14px}
  .step-num{width:22px;height:22px;border-radius:50%;background:#7c5cff;color:#fff;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700}
  input[type=file]{width:100%;padding:11px;background:#08090d;border:1px dashed #2a3245;border-radius:10px;color:#7c8699;font-size:13px;font-family:inherit;cursor:pointer}
  input[type=file]::file-selector-button{background:#7c5cff;color:#fff;border:0;padding:6px 12px;border-radius:6px;font-family:inherit;font-weight:600;font-size:12.5px;cursor:pointer;margin-right:10px}
  input[type=tel]{width:100%;padding:13px;background:#08090d;border:1px solid #2a3245;border-radius:10px;color:#e8ecf4;font-size:15px;font-family:inherit;outline:none}
  input[type=tel]:focus{border-color:#7c5cff}
  input[type=tel]::placeholder{color:#4a5266}
  button{width:100%;padding:13px;margin-top:12px;background:linear-gradient(135deg,#7c5cff,#6a4ce0);border:0;border-radius:10px;color:#fff;font-family:inherit;font-size:14.5px;font-weight:600;cursor:pointer;letter-spacing:.2px}
  button:disabled{opacity:.45;cursor:not-allowed}
  .code{font-family:'Space Grotesk',monospace;font-size:34px;font-weight:700;letter-spacing:8px;text-align:center;padding:22px;background:#08090d;border-radius:12px;margin:14px 0;color:#22d3ee;border:1px solid #1c2130}
  .st{font-size:13px;padding:11px 14px;border-radius:9px;margin-top:11px;font-weight:500}
  .st.ok{background:rgba(34,197,94,.1);color:#4ade80;border:1px solid rgba(34,197,94,.25)}
  .st.err{background:rgba(239,68,68,.1);color:#f87171;border:1px solid rgba(239,68,68,.25)}
  .st.info{background:rgba(124,92,255,.1);color:#a99bff;border:1px solid rgba(124,92,255,.25)}
  .hide{display:none}
  .preview{margin-top:14px;border-radius:12px;overflow:hidden;border:1px solid #1c2130;background:#08090d}
  .preview img{width:100%;display:block;max-height:280px;object-fit:contain}
  .foot{text-align:center;color:#4a5266;font-size:12px;margin-top:32px;line-height:1.7}
</style>
</head>
<body>
<div class="wrap">
  <div class="brand">
    <div class="logo">N</div>
    <h1>Nima Full DP<span class="badge">no crop</span></h1>
  </div>
  <p class="tag">Set your WhatsApp profile picture at full size — nothing cut off.</p>

  <div class="card">
    <div class="step-label"><span class="step-num">1</span> Upload your image</div>
    <input type="file" id="imgInput" accept="image/*">
    <div id="preview" class="preview hide"><img id="previewImg"></div>
    <button id="btnUpload">Upload</button>
    <div id="upSt" class="st hide"></div>
  </div>

  <div class="card">
    <div class="step-label"><span class="step-num">2</span> Connect your WhatsApp</div>
    <input type="tel" id="phoneInput" placeholder="9477XXXXXXX (with country code)">
    <button id="btnBind">Get pairing code</button>
    <div id="codeBox" class="code hide"></div>
    <div id="bindSt" class="st hide"></div>
  </div>

  <div class="card">
    <div class="step-label"><span class="step-num">3</span> Apply full DP</div>
    <button id="btnApply">Set profile picture</button>
    <div id="applySt" class="st hide"></div>
  </div>

  <p class="foot">Sessions are temporary. Nothing stored longer than needed.</p>
</div>

<script>
const S = { url: null, phone: null };
const $ = id => document.getElementById(id);
const st = (el, msg, kind) => { el.textContent = msg; el.className = 'st ' + kind; el.classList.remove('hide'); };

$('imgInput').onchange = () => {
  const f = $('imgInput').files[0];
  if (!f) return;
  $('previewImg').src = URL.createObjectURL(f);
  $('preview').classList.remove('hide');
};

$('btnUpload').onclick = async () => {
  const f = $('imgInput').files[0];
  if (!f) return st($('upSt'), 'choose a file first', 'err');
  $('btnUpload').disabled = true;
  $('btnUpload').textContent = 'Uploading...';
  const fd = new FormData();
  fd.append('image', f);
  try {
    const r = await fetch('/api/upload', { method: 'POST', body: fd });
    const j = await r.json();
    if (!j.ok) throw new Error(j.error);
    S.url = j.url;
    st($('upSt'), 'Image ready', 'ok');
  } catch (e) {
    st($('upSt'), e.message, 'err');
  }
  $('btnUpload').disabled = false;
  $('btnUpload').textContent = 'Upload';
};

$('btnBind').onclick = async () => {
  const p = $('phoneInput').value.trim();
  if (!p) return st($('bindSt'), 'enter your number', 'err');
  S.phone = p;
  $('btnBind').disabled = true;
  $('btnBind').textContent = 'Generating...';
  try {
    const r = await fetch('/api/bind', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: p })
    });
    const j = await r.json();
    if (!j.ok) throw new Error(j.error);
    if (j.already) {
      st($('bindSt'), 'Already connected', 'ok');
    } else {
      $('codeBox').textContent = j.code;
      $('codeBox').classList.remove('hide');
      st($('bindSt'), 'WhatsApp > Linked Devices > Link with phone number > enter this code', 'info');
    }
  } catch (e) {
    st($('bindSt'), e.message, 'err');
  }
  $('btnBind').disabled = false;
  $('btnBind').textContent = 'Get pairing code';
};

$('btnApply').onclick = async () => {
  if (!S.phone || !S.url) return st($('applySt'), 'complete steps 1 and 2 first', 'err');
  $('btnApply').disabled = true;
  $('btnApply').textContent = 'Applying...';
  try {
    const r = await fetch('/api/set', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: S.phone, imageUrl: S.url })
    });
    const j = await r.json();
    if (!j.ok) throw new Error(j.error);
    st($('applySt'), 'Full DP applied - check your WhatsApp', 'ok');
  } catch (e) {
    st($('applySt'), e.message, 'err');
  }
  $('btnApply').disabled = false;
  $('btnApply').textContent = 'Set profile picture';
};
</script>
</body>
</html>
"""


@app.route("/")
def home():
    return render_template_string(HTML_PAGE)


@app.route("/api/upload", methods=["POST"])
def api_upload():
    try:
        f = request.files.get("image")
        if not f:
            return jsonify(ok=False, error="no file")
        if not IMGBB_KEY:
            return jsonify(ok=False, error="IMGBB_API_KEY missing")
        b64 = base64.b64encode(f.read()).decode()
        r = requests.post(
            f"https://api.imgbb.com/1/upload?key={IMGBB_KEY}",
            data={"image": b64},
            timeout=30,
        ).json()
        if not r.get("success"):
            raise RuntimeError("imgbb upload failed")
        return jsonify(ok=True, url=r["data"]["url"])
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/api/bind", methods=["POST"])
def api_bind():
    try:
        data = request.get_json() or {}
        phone = clean_phone(data.get("phone", ""))
        if len(phone) < 8:
            return jsonify(ok=False, error="invalid phone")
        result = bind_phone(phone)
        return jsonify(ok=True, **result)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/api/set", methods=["POST"])
def api_set():
    try:
        data = request.get_json() or {}
        phone = clean_phone(data.get("phone", ""))
        image_url = data.get("imageUrl")
        if not phone or not image_url:
            return jsonify(ok=False, error="phone + imageUrl required")
        set_full_dp(phone, image_url)
        return jsonify(ok=True, message="Full DP applied")
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/api/status/<phone>")
def api_status(phone):
    p = clean_phone(phone)
    s = SESSIONS.get(p)
    if not s:
        return jsonify(ok=True, connected=False)
    return jsonify(ok=True, connected=s.get("connected", False))


if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    app.run(host="0.0.0.0", port=port, threaded=True)
