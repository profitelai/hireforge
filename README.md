# HireForge — AI Resume Builder with ATS Score & Interview Prep

**HireForge** is a free, open-source, self-hosted AI job application toolkit. Build ATS-optimized resumes, write tailored cover letters, practice interviews with AI scoring, and track all your applications in one place.

🌐 **Live demo:** [jobs.bizlocal.ca](https://jobs.bizlocal.ca)

---

## Features

- **ATS Resume Builder** — Generate ATS-optimized CVs with AI-enhanced bullet points tailored to any job description
- **ATS Score** — See how well your resume matches a job posting before you apply
- **AI Cover Letter Generator** — Paste a job URL and get a tailored cover letter in seconds
- **Smart Apply** — One-click tailored CV + cover letter from a job URL
- **Interview Preparation** — Practice with AI-generated questions and get scored feedback (EN & FR)
- **Job Application Tracker** — Track applications across Pipeline stages (Applied, Interviewing, Offer)
- **Multi-profile** — Manage multiple resumes and career profiles
- **Self-hosted & private** — Your data never leaves your server

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | SvelteKit, TypeScript, TailwindCSS |
| Backend | Python (FastAPI), SQLite |
| AI | OpenAI / OpenRouter (configurable) |
| Deployment | Docker Compose |

---

## Quick Start

### Prerequisites
- Docker + Docker Compose
- An OpenAI or OpenRouter API key

### 1. Clone

```bash
git clone https://github.com/profitelai/hireforge.git
cd hireforge
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Run

```bash
docker compose up -d
```

App is available at `http://localhost:3000`

---

## Environment Variables

| Variable | Description | Required |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API key for CV generation and interview AI | Yes |
| `OPENROUTER_API_KEY` | OpenRouter key (alternative to OpenAI) | Optional |

---

## Contributing

Pull requests are welcome. For major changes, open an issue first to discuss what you would like to change.

1. Fork the repo
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

MIT — see [LICENSE](LICENSE)

---

Built by [Profitel AI](https://github.com/profitelai)
