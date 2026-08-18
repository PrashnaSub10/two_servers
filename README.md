# Secure two-server file transfer demo

This project demonstrates a small private-network file flow that matches the requirement:

- Server A is reachable from the host, but server B is not exposed to the host.
- Server A can reach server B internally over a private /28 Docker bridge network.
- Files are encrypted on server A before they are sent.
- Server B decrypts the file and writes it into a Git repository.
- If the same filename arrives again, the file is replaced instead of deleted.

## Network design

The Docker network is configured as a private /28 subnet:

- Subnet: 10.42.0.0/28
- Server A: 10.42.0.2
- Server B: 10.42.0.3

Host access:

- Server A is exposed on the host as http://localhost:8081
- Server B is not port-mapped, so it is not reachable from the host directly

Internal access:

- Server A -> http://server-b:8080/receive
- Server B -> no host port, only inside Docker network

## Required flow

1. Upload a file to server A.
2. Server A encrypts the file with AES-256-GCM.
3. Server A sends the encrypted blob to server B.
4. Server B decrypts the blob and saves it into a Git repo checkout.
5. Server B stages the file, commits it, and pushes it to GitHub.

## How to run

1. Copy the example environment file:

   ```bash
   cp .env.example .env
   ```

2. Edit .env and set your values:

   ```dotenv
   SHARED_KEY=your-32-byte-or-longer-secret
   GITHUB_OWNER=prashanna
   GITHUB_REPO=secure-file-transfer-demo
   GITHUB_BRANCH=main
   GITHUB_TOKEN=ghp_xxx
   GIT_USER_NAME="Secure File Transfer Bot"
   GIT_USER_EMAIL="secure-bot@example.com"
   ```

   Use the GitHub owner name you want to push as. For the two-part learning setup, keep the same repo name and change only the owner between `prashanna` and `basant`.

3. Build and start the stack:

   ```bash
   docker compose up --build
   ```

4. Upload a test file:

   ```bash
   curl -F "file=@example.txt" http://localhost:8081/upload
   ```

5. Verify the result:

   ```bash
   ls -la server-b/repo
   ```

6. Check the repository on GitHub when the push succeeds.

## Important notes

- The project keeps server B private on the Docker network. This is why the host can reach A but not B.
- Server B uses `os.replace` when a file with the same name exists, which overwrites only that file while leaving unrelated files intact.
- The GitHub remote is configured through environment variables. For public repos a token is optional; for private repos, provide a PAT or deploy token.

## File structure

```text
.
├── .env.example
├── .gitignore
├── docker-compose.yml
├── README.md
├── server-a/
│   ├── app.py
│   ├── Dockerfile
│   └── requirements.txt
├── server-b/
│   ├── app.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── repo/
└── .env
```

## Why this matches the requirement

- Private subnet: custom Docker bridge network with 10.42.0.0/28
- Host visibility: only server A is published to localhost
- One-way trust: server A can reach server B internally
- Encryption: AES-256-GCM on server A
- Transfer: HTTP from A to B over the private network
- Decrypt + publish: server B writes to repo and pushes to GitHub
- Replacement behavior: `os.replace` overwrites same-name files without deleting other files
