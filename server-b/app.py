import base64
import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask import Flask, jsonify, request
from github import Github


app = Flask(__name__)

KEY = os.environ.get("SHARED_KEY", "0123456789abcdef0123456789abcdef").encode()
SECRET_KEY = hashlib.sha256(KEY).digest()
AES = AESGCM(SECRET_KEY)
REPO_PATH = Path(os.environ.get("REPO_PATH", "/data/repo"))
REPO_PATH.mkdir(parents=True, exist_ok=True)

GITHUB_OWNER = os.environ.get("GITHUB_OWNER", "prashanna")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "secure-file-transfer-demo")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GIT_USER_NAME = os.environ.get("GIT_USER_NAME", "Secure File Transfer Bot")
GIT_USER_EMAIL = os.environ.get("GIT_USER_EMAIL", "secure-bot@example.com")


def ensure_repo():
    if not (REPO_PATH / ".git").exists():
        subprocess.run(["git", "init", "-b", GITHUB_BRANCH], cwd=str(REPO_PATH), check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", GIT_USER_NAME], cwd=str(REPO_PATH), check=True)
        subprocess.run(["git", "config", "user.email", GIT_USER_EMAIL], cwd=str(REPO_PATH), check=True)

    remotes = subprocess.run(["git", "remote", "-v"], cwd=str(REPO_PATH), capture_output=True, text=True)
    if "origin" not in remotes.stdout and GITHUB_TOKEN:
        remote_url = f"https://{GITHUB_TOKEN}@github.com/{GITHUB_OWNER}/{GITHUB_REPO}.git"
        subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=str(REPO_PATH), check=True)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "server": "B"})


@app.route("/receive", methods=["POST"])
def receive_file():
    payload = request.get_json(silent=True) or {}
    filename = payload.get("filename")
    nonce = payload.get("nonce")
    ciphertext = payload.get("ciphertext")

    if not filename or not nonce or not ciphertext:
        return jsonify({"error": "missing encrypted payload"}), 400

    ensure_repo()

    nonce_bytes = base64.b64decode(nonce)
    ciphertext_bytes = base64.b64decode(ciphertext)
    plaintext = AES.decrypt(nonce_bytes, ciphertext_bytes, None)

    target_path = REPO_PATH / filename
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with open(target_path, "wb") as f:
        f.write(plaintext)

    # Replace same-name files, but do not delete unrelated files already in repo.
    # This is effectively the same as using os.replace for the incoming file.
    # We keep the existing repository tree and only overwrite the target file.
    subprocess.run(["git", "add", filename], cwd=str(REPO_PATH), check=True, capture_output=True, text=True)

    if GITHUB_TOKEN:
        try:
            subprocess.run(["git", "status", "--short"], cwd=str(REPO_PATH), check=True, capture_output=True, text=True)
            subprocess.run(["git", "commit", "-m", f"Add {filename}"], cwd=str(REPO_PATH), check=True, capture_output=True, text=True)
            subprocess.run(["git", "push", "origin", GITHUB_BRANCH], cwd=str(REPO_PATH), check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            return jsonify({
                "status": "decrypted_but_push_failed",
                "filename": filename,
                "details": exc.stderr.strip() or exc.stdout.strip(),
            }), 202

    return jsonify({
        "status": "decrypted_and_stored",
        "filename": filename,
        "repo_path": str(target_path),
        "github_push": bool(GITHUB_TOKEN),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
