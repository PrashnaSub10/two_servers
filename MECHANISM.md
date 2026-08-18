# Secure Two-Server File Transfer: Detailed Mechanism

This document explains the complete design and behavior of the two-server Docker Compose setup in a granular way.

## 1. Goal of the system

The project is built to demonstrate a secure file-transfer flow across two isolated servers:

- Server A: public-facing, receives files from the user
- Server B: private, does not expose its port to the outside world
- Server A can reach Server B internally on a private Docker bridge network
- Files are encrypted before movement
- Files are decrypted on the receiving server
- The decrypted files are then stored in a Git repository and pushed to GitHub

The system is intended to demonstrate a realistic pattern where the public-facing node does not directly expose the private data storage node.

---

## 2. Network design

The system uses Docker networking instead of exposing both servers directly to the host.

### Network subnet

The private network is configured as:

- subnet: 10.42.0.0/28
- gateway: 10.42.0.1

This is a small private subnet with very limited IP space, which keeps the environment isolated.

### IP allocation

- Server A: 10.42.0.2
- Server B: 10.42.0.3

### Host reachability

The host machine can reach Server A because it is published on a host port:

- localhost:8083 -> Server A:8080

The host machine cannot reach Server B because no host port is mapped. That is the main isolation rule.

### Internal Docker communication

Server A can talk to Server B using Docker DNS name resolution:

- http://server-b:8080/receive

This works because both services are attached to the same Docker network.

### Why this matters

This architecture creates the required flow:

- host -> Server A: allowed
- host -> Server B: denied
- Server A -> Server B: allowed

This is exactly the “can’t reach B from outside, but A can reach B” requirement.

---

## 3. Docker Compose structure

The Compose file defines two services:

### Server A service

- Built from the `server-a` folder
- Runs the Flask app that accepts uploaded files
- Publishes port 8080 to host port 8083
- Depends on Server B

### Server B service

- Built from the `server-b` folder
- Runs the Flask app that receives encrypted payloads
- Not mapped to the host
- Uses a bind mount to a local repository folder

### Network section

The Compose file creates a custom bridge network named `private-net` and assigns static IPs to the containers.

This is important because the private addressing is predictable and stable in the Docker network.

---

## 4. Environment variables and secrets

The environment file contains the runtime values used by both services.

### Shared key

```env
SHARED_KEY=your-random-secret
```

This is used as the encryption key seed. The code derives a SHA-256 hash from it and uses that as the actual AES key.

### GitHub configuration

```env
GITHUB_OWNER=prashanna
GITHUB_REPO=secure-file-transfer-demo
GITHUB_BRANCH=main
GITHUB_TOKEN=ghp_...
GIT_USER_NAME="Secure File Transfer Bot"
GIT_USER_EMAIL="secure-bot@example.com"
```

These values are used by Server B to initialize a local Git repository and push to GitHub.

### Ports

```env
SERVER_A_HOST_PORT=8083
SERVER_B_HOST_PORT=8082
```

Even though Server B is private, the host port variables are still kept for clarity and flexibility.

In the final architecture, only Server A should be published to the host. Server B remains private.

---

## 5. Server A: upload and encrypt phase

Server A exposes an upload endpoint:

- method: POST
- route: /upload
- expects multipart form data with the field `file`

### Step-by-step process

#### Step 1: file received from user

When the user sends a file using:

```bash
curl -F "file=@example.txt" http://localhost:8083/upload
```

Flask receives the file in the request.

#### Step 2: save the original file temporarily

The file is written to a temporary directory on the container filesystem.

This is a local staging area before encryption.

#### Step 3: read the file as bytes

The file content is read as raw bytes before encryption.

#### Step 4: generate nonce

A random nonce is generated using:

```python
os.urandom(12)
```

This nonce is required by AES-GCM. It must be unique for each message.

#### Step 5: encrypt with AES-GCM

The application uses the cryptography package and AES-GCM mode.

The encryption flow is:

- derive a SHA-256 key from `SHARED_KEY`
- create AES-GCM object
- encrypt plaintext + nonce

This produces ciphertext.

#### Step 6: encode payload for transfer

The encrypted data and nonce are base64 encoded so they can be transmitted as JSON.

The JSON payload contains:

- filename
- nonce
- ciphertext
- timestamp

#### Step 7: send to Server B

Server A sends the JSON payload to:

```text
http://server-b:8080/receive
```

This request stays inside the Docker network and is never exposed to the host.

---

## 6. Why AES-GCM is used

AES-GCM is a modern authenticated encryption standard.

It provides:

- confidentiality: the file contents remain encrypted
- integrity: it detects tampering
- strong security for file-transfer demonstrations

The important part is that the same key is shared between Server A and Server B, which allows decryption on the receiving side.

---

## 7. Server B: receive and decrypt phase

Server B exposes a receive endpoint:

- method: POST
- route: /receive

### Step-by-step process

#### Step 1: receive JSON payload

Server B reads the incoming JSON payload and expects:

- filename
- nonce
- ciphertext

#### Step 2: base64 decode

The base64 values are decoded back to binary.

#### Step 3: decrypt with the same key

Server B applies the same key derivation logic and decrypts the AES-GCM data using the nonce and ciphertext.

The result is the original file content in plaintext.

#### Step 4: save decrypted file to repository folder

The file is written to the repository path, such as:

```text
/data/repo/<filename>
```

The code writes the file directly to the repo folder so the data is present for Git operations.

#### Step 5: stage file in Git

The file is added to Git using:

```bash
git add <filename>
```

This tells Git that the file should be tracked or updated.

#### Step 6: commit and push

If a GitHub token is configured, the script attempts:

```bash
git commit -m "Add <filename>"
git push origin main
```

This pushes the file to the configured GitHub repository.

---

## 8. Replacement behavior

The requirement says:

- do not delete files in Server B
- replace files if same-name files are transferred from Server A

The app accomplishes this by writing the received file into its target path and tracking it in Git.

### Why this is safe

- Existing unrelated files remain untouched
- If a file with the same name arrives again, it is overwritten in the repo path
- Git then stages the replacement as an updated version

This avoids deleting the entire repository and preserves other files.

---

## 9. GitHub push logic

Server B uses Git to create a repository if it does not exist yet.

### Initialization sequence

If `.git` does not exist, it runs:

```bash
git init -b main
```

Then it sets:

- user.name
- user.email

If a token is provided, it also adds a remote:

```bash
git remote add origin https://TOKEN@github.com/OWNER/REPO.git
```

Then it pushes the file.

### This is only for learning

This push logic is educational and small-scale. It is not a production-grade GitHub automation system.

---

## 10. Why Server B should not be reachable from host

This is a security boundary.

### Public-facing node

Server A is the public point of entry. It accepts file uploads and is exposed to the host.

### Private node

Server B stores the decrypted files and pushes to GitHub. It is not exposed because it contains the internal data flow and the repository state.

### Real-world security pattern

This design mimics a common architecture:

- front-end or upload service is publicly reachable
- data processing or storage node stays private
- only the trusted internal system connects to it

This reduces the attack surface and keeps sensitive data away from direct public network exposure.

---

## 11. How to verify the design manually

### Test 1: verify Server A is reachable from host

```bash
curl http://localhost:8083/health
```

Expected:

```json
{"server":"A","status":"ok"}
```

### Test 2: verify Server B is not reachable from host

```bash
curl http://localhost:8082/health
```

Expected: connection refused or timeout

### Test 3: verify Server A can reach Server B internally

```bash
docker exec -it secure-file-a python -c "import urllib.request; print(urllib.request.urlopen('http://server-b:8080/health').read().decode())"
```

Expected:

```json
{"status":"ok","server":"B"}
```

### Test 4: upload and verify end-to-end flow

```bash
echo "hello from secure transfer" > sample.txt
curl -F "file=@sample.txt" http://localhost:8083/upload
```

Then check the repo folder on the host or inside the container:

```bash
ls -la server-b/repo
```

The file should exist in plaintext in the repository path after decryption.

---

## 12. Full flow summary

At a high level, the process is:

1. User uploads file to Server A
2. Server A encrypts the file with AES-GCM
3. Server A sends the encrypted payload to Server B over private Docker network
4. Server B decrypts the payload
5. Server B stores the plaintext file in the Git repository folder
6. Server B stages and commits the file
7. Server B pushes the file to GitHub
8. Same-name files are overwritten without deleting unrelated files

---

## 13. Final learning outcome

This project demonstrates several important DevOps and security ideas:

- private networking with Docker
- isolated network segmentation
- encrypted file transfer
- secure internal-only service model
- Git-based delivery to a remote repository
- operational learning about trust boundaries and deployment design

It is a simple yet effective example of how two services can collaborate securely while keeping one server out of direct reach from the outside world.
