import os
import time
import json
import subprocess
import tempfile
import requests
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

load_dotenv()

TOKEN   = os.getenv("USER_ACCESS_TOKEN")
PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
IG_ID   = os.getenv("INSTAGRAM_ID")  # opcional: o script confirma/atualiza
API_V   = os.getenv("API_VERSION", "v23.0")

CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUD_KEY  = os.getenv("CLOUDINARY_API_KEY")
CLOUD_SEC  = os.getenv("CLOUDINARY_API_SECRET")

def die(msg):
    print(f"❌ {msg}")
    raise SystemExit(1)

def get_json(url, params=None, method="GET"):
    if params is None:
        params = {}
    params["access_token"] = TOKEN
    r = requests.request(method, url, params=params, timeout=120)
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    if r.status_code >= 400:
        print(f"  → {r.status_code} {data}")
        die(f"Falha em {url}")
    return data

def confirm_ig_id():
    global IG_ID
    url = f"https://graph.facebook.com/{API_V}/{PAGE_ID}"
    data = get_json(url, params={"fields": "connected_instagram_account{id,username},name,can_post"})
    ig = data.get("connected_instagram_account")
    if not ig:
        die("Página não tem conta do Instagram conectada. Vá na Página > Configurações > Instagram e conecte.")
    ig_id = ig.get("id")
    ig_user = ig.get("username")
    print(f"✅ IG conectado: {ig_user} (id {ig_id})")
    if IG_ID and IG_ID != ig_id:
        print(f"ℹ️  INSTAGRAM_ID no .env ({IG_ID}) difere do conectado ({ig_id}). Usarei {ig_id} neste teste.")
    IG_ID = ig_id

def make_video_10s(out_path):
    # 10s, 1080x1920, com áudio silencioso (aac) — Reels costuma exigir áudio
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=10",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-shortest",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "25",
        "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "128k",
        out_path
    ]
    print("🎬 Gerando MP4 10s…")
    subprocess.run(cmd, check=True)
    print(f"✅ Vídeo: {out_path}")

def upload_cloudinary(path):
    print("☁️  Enviando ao Cloudinary…")
    cloudinary.config(
        cloud_name=CLOUD_NAME,
        api_key=CLOUD_KEY,
        api_secret=CLOUD_SEC
    )
    res = cloudinary.uploader.upload(path, resource_type="video")
    url = res.get("secure_url")
    if not url:
        die(f"Cloudinary não retornou secure_url: {res}")
    print(f"✅ Cloudinary OK: {url}")
    return url

def create_ig_container(video_url, caption):
    url = f"https://graph.facebook.com/{API_V}/{IG_ID}/media"
    params = {
        "media_type": "REELS",       # chave para Reels
        "video_url": video_url,
        "caption": caption,
        "share_to_feed": "true"      # opcional: aparece no feed
    }
    data = get_json(url, params=params, method="POST")
    creation_id = data.get("id")
    if not creation_id:
        die(f"Sem creation_id: {data}")
    print(f"🧩 creation_id: {creation_id}")
    return creation_id

def wait_until_finished(creation_id, timeout=180):
    url = f"https://graph.facebook.com/{API_V}/{creation_id}"
    t0 = time.time()
    while True:
        data = get_json(url, params={"fields": "status_code"})
        status = data.get("status_code")
        print(f"⏳ status_code={status}")
        if status in ("FINISHED", "EXPIRED", "ERROR"):
            return status
        if time.time() - t0 > timeout:
            return "TIMEOUT"
        time.sleep(5)

def publish_ig(creation_id):
    url = f"https://graph.facebook.com/{API_V}/{IG_ID}/media_publish"
    data = get_json(url, params={"creation_id": creation_id}, method="POST")
    media_id = data.get("id")
    if not media_id:
        die(f"Sem media_id no publish: {data}")
    print(f"🎉 Reel publicado! media_id={media_id}")
    print(f"Obs: Você verá no painel de status em out/status.html o resultado do último ciclo.")

