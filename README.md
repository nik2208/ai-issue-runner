# AI Issue Runner (Decentralized)

An autonomous, decentralized AI runner inspired by PleaseAI (`shunt` & `work-please`) and self-hosted CI/CD runners, designed to solve GitHub/GitLab issues and execute complex engineering tasks under a strict **Guarded Agentic Loop**.

---

## 🌟 Key Features

1. **Guarded Agentic Loop (`LoopGuard`)**:
   - The agent cannot prematurely terminate a task simply by claiming "I'm done".
   - Completion attempts trigger real-time **Acceptance Criteria** verification (`pytest`, linters, type-checks, file assertions).
   - If tests fail, exit is blocked, and rich diagnostic feedback (stderr/stdout) is injected into the agent's context to force self-correction until all criteria pass.

2. **Agnostic AI Providers & Interactive OAuth**:
   - Native drivers for **Google Gemini** (OAuth PKCE & API keys), **Anthropic Claude**, **OpenAI / Codex**, and **Ollama**.
   - Embedded Web UI on `http://127.0.0.1:4242` with one-click Google OAuth login and real-time terminal streaming.
   - CLI Link Interceptor to capture browser login URLs from CLI subprocesses.

3. **Pluggable Agent Harnesses**:
   - **`NativeHarness`**: Built-in, high-performance ReAct tool loop (`read_file`, `write_file`, `replace_file_content`, `run_bash`, `grep_search`, `finish_task`) with token history compaction.
   - **`AgyHarness`**: Official adapter for Google Antigravity SDK (`google-antigravity`).
   - **`OpenCodeHarness` & `PiHarness`**: Subprocess bridge adapters for OpenCode and Pi-agent.

4. **Dual Deployment Topologies**:
   - **Ephemeral Mode (GitHub Actions)**: Container runs directly on GitHub-hosted runners (`ubuntu-latest`) billed by execution minute. Zero VPS hosting cost!
   - **Persistent Mode (VPS Daemon)**: Long-running daemon listening for GitHub webhook events (`POST /api/webhook/github`) with HMAC validation.

---

## 🚀 Deployment Modes

### 1. Ephemeral Mode (GitHub Actions Compute)

In this mode, GitHub spins up a fresh runner per issue and runs the Docker image directly from GitHub Container Registry (`ghcr.io/nik2208/ai-issue-runner:latest`).

#### Workflow Setup:
1. **Publish Container to GHCR**:
   - Copy `templates/github-workflows/docker-publish.yml` into `.github/workflows/docker-publish.yml`.
   - On every push to `main`, GitHub Actions builds and publishes the multi-arch container to `ghcr.io/nik2208/ai-issue-runner:latest`.
2. **Export Auth Secret**:
   ```bash
   ai-runner login google   # or set API key
   ai-runner auth export    # prints base64 credential bundle
   ```
   Save the output as a GitHub Repository Secret named `AI_RUNNER_AUTH`.
3. **Enable Issue Runner Workflow**:
   - Copy `templates/github-workflows/ai-issue-runner.yml` into `.github/workflows/ai-issue-runner.yml`.
   - When an issue is opened or labeled with `ai-run`, GitHub Actions automatically:
     - Pulls `ghcr.io/nik2208/ai-issue-runner:latest`.
     - Imports credentials and executes the Guarded Loop.
     - Verifies all acceptance criteria pass.
     - Opens a Pull Request with the verified solution.

---

### 2. Persistent Mode (VPS / Self-Hosted Watcher)

Run the daemon continuously on your own server or homelab:

```bash
# Start daemon with Web Dashboard on port 4242
ai-runner start --host 0.0.0.0 --port 4242

# Or via Docker:
docker run -d \
  -p 4242:4242 \
  -v ~/.ai-runner:/root/.ai-runner \
  ghcr.io/nik2208/ai-issue-runner:latest
```

Configure a GitHub Webhook pointing to `http://your-server:4242/api/webhook/github` (Event: `issues`, `issue_comment`).

---

## 💻 Local CLI Usage

```bash
# 1. Install locally
pip install -e .

# 2. Check runner & provider status
ai-runner status

# 3. Authenticate with an AI provider
ai-runner login google
# or for API key:
ai-runner login anthropic

# 4. Run a plan with Acceptance Criteria
ai-runner run --plan example_plan.yaml --harness native

# 5. Run full automated test suite (29 tests)
pytest tests/ -v
```

---

## 📦 Container Registry

The container image is available at:
`ghcr.io/nik2208/ai-issue-runner:latest`

```bash
docker pull ghcr.io/nik2208/ai-issue-runner:latest
docker run --rm ghcr.io/nik2208/ai-issue-runner:latest --help
```
