# HireForge — AI Resume Builder with ATS Score & Interview Prep

> Built by [danimaster.com](https://danimaster.com) · Live at [jobs.bizlocal.ca](https://jobs.bizlocal.ca) · MIT License

**HireForge** is a free, open-source, self-hosted AI job application toolkit. Build ATS-optimized resumes, write tailored cover letters, practice interviews with AI scoring, auto-apply to jobs, and track every application — all in one place, with your data fully private on your own server.

---

## Features

### Resume & CV
- **ATS Resume Builder** — Generate ATS-optimized resumes with AI-enhanced bullet points tailored to specific job descriptions
- **Resume Generation from Job Posts** — Upload a job description file or paste a LinkedIn/Indeed job URL, and the AI automatically creates a customized resume optimized for that specific role
- **ATS Match Score** — Instantly see how well your resume matches a job posting before applying
- **Multi-Profile Management** — Manage multiple resumes, industries, and career profiles from one dashboard

### Cover Letter & Applications
- **AI Cover Letter Generator** — Generate personalized cover letters instantly from a job file, company description, or LinkedIn job posting URL
- **Smart Apply** — One-click generation of a tailored resume and cover letter directly from a LinkedIn or job posting URL
- **Auto Apply System** — Automatically apply to selected jobs using your customized resume, cover letter, and profile preferences
- **Job Application Tracker** — Track applications across all hiring stages: Applied, Interviewing, and Offer

### Interview Preparation
- **Interview Preparation** — Practice with AI-generated interview questions and receive scored feedback in both English and French
- **Voice Recording & AI Analysis** — Record your interview answers directly inside the platform. The AI listens and analyzes your answers — checking grammar, sentence structure, communication clarity, confidence, and pronunciation — then provides improvement suggestions and lets you retry to improve

### Privacy & Hosting
- **Self-hosted & Private** — Your data stays fully private and hosted on your own server
- **Local LLM Support** — Run the AI models on your own laptop (via Ollama) while the app stays online. See [Local LLM Setup](#local-llm-setup-ollama) below

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | SvelteKit, TypeScript, TailwindCSS, shadcn-svelte |
| Backend | Python (FastAPI), SQLite, Alembic |
| AI / LLM | LiteLLM — supports OpenAI, OpenRouter, Anthropic, Ollama (local), and any OpenAI-compatible endpoint |
| Deployment | Docker Compose |

---

## Quick Start

### Prerequisites
- Docker + Docker Compose
- One of: OpenAI API key, OpenRouter API key, or Ollama installed locally

### 1. Clone

```bash
git clone https://github.com/profitelai/hireforge.git
cd hireforge
```

### 2. Configure

```bash
# Backend
cp backend/.env.example backend/.env

# Frontend
cp frontend/.env.example frontend/.env
```

Edit `backend/.env` and add your API key(s):

```env
# Choose one or more providers
OPENAI_API_KEY=sk-...
OPENROUTER_API_KEY=sk-or-...

# Database (SQLite, default is fine)
DATABASE_URL=sqlite:///./hireforge.db
```

### 3. Run

```bash
docker compose up -d
```

App is available at **http://localhost:3000**

---

## Local LLM Setup (Ollama)

HireForge is built to work with **local LLMs via [Ollama](https://ollama.com)**. This means you can keep the app hosted online (on a server or VPS) while the AI model runs entirely on your own laptop or machine — no cloud API costs, no data sent to third parties.

### How it works



The server calls the Ollama API on your machine. Your resume data and prompts never leave your local network for AI processing.

### Setup

1. **Install Ollama** on your laptop: [ollama.com](https://ollama.com)

2. **Pull a model:**
   ```bash
   ollama pull llama3.2        # fast, good quality
   ollama pull qwen3.5         # strong multilingual support
   ollama pull llama4          # most capable
   ```

3. **Expose Ollama to your network** (if HireForge runs on a remote server):
   ```bash
   OLLAMA_HOST=0.0.0.0 ollama serve
   ```
   Or use a tunnel tool like [ngrok](https://ngrok.com):
   ```bash
   ngrok http 11434
   ```

4. **Configure in HireForge:**
   - Open HireForge → Settings → AI Provider
   - Select **Ollama** as provider
   - Set the Ollama URL to your machine's IP or ngrok URL (e.g. `http://192.168.1.x:11434` or `https://your-ngrok-url.ngrok-free.dev`)
   - Select your model (llama3.2, qwen3.5, etc.)
   - No API key required

### Supported local models

| Model | Size | Best for |
|---|---|---|
| llama3.2 | 2–8B | Fast, general use |
| llama3.1 | 8B | Balanced quality |
| llama4 | 17B+ | Best quality |
| qwen3.5 | 8B | Strong multilingual (EN/FR) |
| glm-4.7-flash | 7B | Fast Chinese/English |

> **Note:** Voice features (TTS + Whisper transcription) require an OpenAI API key regardless of which LLM you use for generation.

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Description | Required |
|---|---|---|
| `DATABASE_URL` | SQLite path (default: `sqlite:///./hireforge.db`) | No |
| `OPENAI_API_KEY` | OpenAI key — required for voice/TTS features | For voice |
| `OPENROUTER_API_KEY` | OpenRouter key (access to 200+ models) | Optional |
| `OLLAMA_API_BASE` | Ollama base URL override (default: `http://localhost:11434`) | No |
| `HIREFORGE_SCRIPTS_DIR` | Path to LinkedIn automation scripts | Optional |

### Frontend (`frontend/.env`)

| Variable | Description | Default |
|---|---|---|
| `VITE_API_BASE_URL` | Backend API URL | `http://localhost:8000/api` |

---

## Project Structure

```
hireforge/
├── frontend/          # SvelteKit app
│   └── src/
│       ├── routes/    # Pages: /, /generate, /interview, /tracker, etc.
│       └── lib/       # API client, components, utilities
├── backend/           # FastAPI app
│   └── app/
│       ├── routes/    # API endpoints
│       ├── services/  # LLM, interview, CV logic
│       └── models.py  # Database models
├── docker-compose.yml
└── .env.example
```

---

## Contributing

Pull requests are welcome. For major changes, open an issue first to discuss what you'd like to change.

1. Fork the repo
2. Create your feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -m 'Add my feature'`
4. Push: `git push origin feature/my-feature`
5. Open a Pull Request

---

## License

MIT License — Copyright (c) 2026 [danimaster.com](https://danimaster.com) — Profitel AI

See [LICENSE](LICENSE) for full text.

---

Built with care by [danimaster.com](https://danimaster.com)
