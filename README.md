
AI Tutor

Lightweight AI tutoring project combining a Python backend and a small Next.js auth demo.

## Overview

This repository contains a minimal AI Tutor prototype. It includes:

- A Python backend and app entry points: [app.py](app.py) and [enhanced_app.py](enhanced_app.py).
- A Next.js demo auth frontend in the `clerk_login` folder demonstrating Clerk integration.
- Database migration files under `migrations/` (Alembic).
- An `instance/` directory for runtime configuration.

## Requirements

- Python 3.9+ (or compatible)
- Node (for the Next.js app in `clerk_login`)
- `pnpm` is used in the `clerk_login` workspace but `npm`/`yarn` also work

Install Python dependencies:

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# or Windows cmd
.\.venv\Scripts\activate.bat

pip install -r requirements.txt
```

## Running the Python app

Basic run (development):

```bash
# Run the simple app
python app.py

# Or run the enhanced app (contains improvements / additional features)
python enhanced_app.py
```

Notes:

- The apps may expect configuration or environment variables (DB URL, secret keys). Place runtime configuration in the `instance/` directory or set environment variables before running.
- Migrations are managed with Alembic. To upgrade the DB schema:

```bash
alembic -c migrations/alembic.ini upgrade head
```

## Clerk / Next.js frontend (clerk_login)

The `clerk_login` folder holds a Next.js app demonstrating Clerk auth middleware and pages.

Quick start for the frontend:

```bash
cd clerk_login
pnpm install   # or `npm install` / `yarn`
pnpm dev       # or `npm run dev`
```

Configure Clerk environment variables (e.g., keys) in that app's environment before starting.

## Project structure (high level)

- [app.py](app.py) — main Python entrypoint (simple setup)
- [enhanced_app.py](enhanced_app.py) — enhanced backend variant
- `clerk_login/` — Next.js demo with Clerk middleware
- `migrations/` — Alembic DB migration scripts
- `instance/` — runtime configuration (local settings, secrets)

## Contributing

If you plan to extend this project:

- Add setup instructions for any new services you introduce.
- Document required environment variables and sample `.env` or config in `instance/`.

## License

This repository does not include an explicit license file. Add a `LICENSE` if you want to clarify usage rights.

---

If you want, I can: add a more detailed list of environment variables, create a sample `.env.template`, or wire up a simple `Makefile` / `run` script. Tell me which you'd prefer.
