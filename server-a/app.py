import base64
import hashlib
import os
from datetime import datetime

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask import Flask, jsonify, request
import requests


app = Flask(__name__)

KEY = os.environ.get("SHARED_KEY", "0123456789abcdef0123456789abcdef").encode()
SECRET_KEY = hashlib.sha256(KEY).digest()
AES = AESGCM(SECRET_KEY)
SERVER_B_URL = os.environ.get("SERVER_B_URL", "http://server-b:8080/receive")
UPLOAD_FOLDER = "/tmp/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "server": "A"})


@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    uploaded = request.files["file"]
    if uploaded.filename == "":
        return jsonify({"error": "No selected file"}), 400

    original_name = uploaded.filename
    file_path = os.path.join(UPLOAD_FOLDER, original_name)
    uploaded.save(file_path)

    with open(file_path, "rb") as f:
        plaintext = f.read()

    nonce = os.urandom(12)
    ciphertext = AES.encrypt(nonce, plaintext, None)
    payload = {
        "filename": original_name,
        "nonce": base64.b64encode(nonce).decode("utf-8"),
        "ciphertext": base64.b64encode(ciphertext).decode("utf-8"),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    response = requests.post(SERVER_B_URL, json=payload, timeout=30)
    response.raise_for_status()

    return jsonify({
        "status": "encrypted_and_transferred",
        "filename": original_name,
        "server_b_status": response.json(),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
