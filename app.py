import os, time, base64, threading
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string
import requests
from neonize.client import NewClient
from neonize.events import ConnectedEv

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

IMGBB_KEY = os.getenv("IMGBB_API_KEY")
SESSION_ROOT = Path(os.getenv("SESSION_ROOT", "./sessions"))
SESSION_ROOT.mkdir(parents=True, exist_ok=True)

SESSIONS = {}   # phone -> {"client", "code", "connected"}
LOCK = threading.Lock()


def clean(p):
    n = "".join(c for c in str(p) if c.isdigit())
    return n[1:] if n.startswith("0") else n


def bind(phone):
    with LOCK:
        s = SESSIONS.get(phone)
        if s and s["connected"]:
            return {"already": True}

    d = SESSION_ROOT / phone
    d.mkdir(parents=True, exist_ok=True)

    client = NewClient(str(d / "session.db"))

    @client.event(ConnectedEv)
    def _on_conn(_c, _e):
        SESSIONS[phone]["connected"] = True
        SESSIONS[phone]["code"] = None

    code = client.PairPhone(phone, show_push_notification=True)
    SESSIONS[phone] = {"client": client, "code": code, "connected": False}
    return {"code": code}


def set_dp(phone, url):
    s = SESSIONS.get(phone)
    if not s or not s["connected"]:
        raise RuntimeError("not connected")
    img = requests.get(url, timeout=30).content
    s["client"].set_profile_photo(img)


HTML = """
<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nima Full DP</title>
<style>
body{font-family:system-ui;background:#0b0f19;color:#e6e9ef;padding:24px;max-width:520px;margin:auto}
h1{font-size:22px;margin:0 0 4px}p{color:#8b93a7;font-size:13px;margin:0 0 24px}
.card{background:#141a28;border:1px solid #232b3d;border-radius:14px;padding:20px;margin-bottom:14px}
label{font-size:12px;color:#8b93a7;text-transform:uppercase;letter-spacing:.5px;display:block;margin-bottom:10px}
input{width:100%;padding:12px;background:#0b0f19;border:1px solid #232b3d;border-radius:8px;color:#fff;font-size:14px;box-sizing:border-box}
button{width:100%;padding:13px;background:#3b82f6;border:0;border-radius:8px;color:#fff;font-size:15px;font-weight:600;cursor:pointer;margin-top:12px}
button:disabled{opacity:.5}
.code{font-family:monospace;font-size:32px;letter-spacing:6px;text-align:center;padding:18px;background:#0b0f19;border-radius:8px;margin:12px 0;color:#22d3ee}
.st{font-size:13px;padding:10px;border-radius:8px;margin-top:10px}
.ok{background:#0f2a1a;color:#4ade80;border:1px solid #1e4a2e}
.err{background:#2a1010;color:#f87171;border:1px solid #4a1e1e}
.hide{display:none}
</style></head><body>
<h1>Nima Full DP</h1><p>full image, no crop</p>

<div class="card"><label>1 — upload image</label>
<input type="file" id="img" accept="image/*">
<button id="up">Upload</button><div id="upSt" class="st hide"></div></div>

<div class="card"><label>2 — phone (with country code)</label>
<input type="tel" id="ph" placeholder="9477XXXXXXX">
<button id="bd">Get pairing code</button>
<div id="code" class="code hide"></div><div id="bdSt" class="st hide"></div></div>

<div class="card"><label>3 — apply DP</label>
<button id="ap">Set profile picture</button><div id="apSt" class="st hide"></div></div>

<script>
const S={url:null,phone:null},$=id=>document.getElementById(id);
const st=(el,m,k)=>{el.textContent=m;el.className='st '+k;el.classList.remove('hide')};

$('up').onclick=async()=>{
  const f=$('img').files[0]; if(!f)return;
  $('up').disabled=true;
  const fd=new FormData(); fd.append('image',f);
  try{
    const j=await(await fetch('/api/upload',{method:'POST',body:fd})).json();
    if(!j.ok)throw new Error(j.error);
    S.url=j.url; st($('upSt'),'image ready','ok');
  }catch(e){st($('upSt'),e.message,'err')}
  $('up').disabled=false;
};

$('bd').onclick=async()=>{
  const p=$('ph').value.trim(); if(!p)return;
  S.phone=p; $('bd').disabled=true;
  try{
    const j=await(await fetch('/api/bind',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone:p})})).json();
    if(!j.ok)throw new Error(j.error);
    if(j.already){st($('bdSt'),'already connected','ok')}
    else{$('code').textContent=j.code;$('code').classList.remove('hide');
         st($('bdSt'),'WhatsApp → Linked Devices → Link with phone number','ok')}
  }catch(e){st($('bdSt'),e.message,'err')}
  $('bd').disabled=false;
};

$('ap').onclick=async()=>{
  if(!S.phone||!S.url)return st($('apSt'),'do steps 1 & 2 first','err');
  $('ap').disabled=true;
  try{
    const j=await(await fetch('/api/set',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone:S.phone,imageUrl:S.url})})).json();
    if(!j.ok)throw new Error(j.error);
    st($('apSt'),'Full DP applied','ok');
  }catch(e){st($('apSt'),e.message,'err')}
  $('ap').disabled=false;
};
</script></body></html>
"""


@app.route("/")
def home():
    return render_template_string(HTML)


@app.route("/api/upload", methods=["POST"])
def upload():
    try:
        f = request.files.get("image")
        if not f:
            return jsonify(ok=False, error="no file")
        b64 = base64.b64encode(f.read()).decode()
        r = requests.post(
            f"https://api.imgbb.com/1/upload?key={IMGBB_KEY}",
            data={"image": b64}, timeout=30
        ).json()
        if not r.get("success"):
            raise RuntimeError("upload failed")
        return jsonify(ok=True, url=r["data"]["url"])
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/api/bind", methods=["POST"])
def api_bind():
    try:
        phone = clean((request.json or {}).get("phone", ""))
        if len(phone) < 8:
            return jsonify(ok=False, error="bad phone")
        return jsonify(ok=True, **bind(phone))
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/api/set", methods=["POST"])
def api_set():
    try:
        d = request.json or {}
        phone = clean(d.get("phone", ""))
        url = d.get("imageUrl")
        if not phone or not url:
            return jsonify(ok=False, error="phone + imageUrl required")
        set_dp(phone, url)
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 3000)))
