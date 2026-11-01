# Hosting for free, and keeping your data

All data lives in ONE folder: `STUDIO_HOME` (default: the app folder). It holds `studio.db`, `growth/`,
`projects/<video id>/`, `reports/`, `logs/`. Delete it by hand, or use the **Data** page (per video, per channel,
or everything; each asks you to type `DELETE`). Secrets (`.env`, `client_secret.json`, `token.json`) are git-ignored
and never included in exports or backups.

## Honest comparison (checked 2026-11-01; limits change, verify before relying on them)

| Option | Cost | RAM/CPU for ffmpeg | Disk survives restart? | Notes |
|---|---|---|---|---|
| **Your own PC** | free | your machine | **yes, always** | Best for rendering. Reach it from your phone with a free Cloudflare Tunnel. Off when the PC is off. |
| **Hugging Face Spaces** (free CPU) | free | about 16 GB RAM, 2 vCPU | **no** (disk wiped on restart; persistent storage is a paid add-on); sleeps after inactivity | Most RAM of any free host. Use backup (below). Make the Space **private**. |
| Oracle Cloud Always Free VM | free, card needed for signup | Arm: up to 2 OCPU / 12 GB (Oracle reportedly cut it from 4/24; enforcement unclear), 200 GB disk | **yes** (real disk) | Real server, but signup is picky, capacity is often unavailable, idle instances can be reclaimed. |
| Streamlit Community Cloud | free | about 1 GB RAM | no | OOM-kills video builds. Fine for scripts/topics only. |
| Render free | free | 512 MB, sleeps after 15 min | no | Too small for rendering. |
| Railway / Fly.io | trial credit / card needed | small | volumes cost | Not free long term. |

**Recommendation.** Run on your own PC for production rendering (nothing to configure; data stays in the folder).
For an always-reachable hosted copy, use **Hugging Face Spaces + backup to a private GitHub repo** (best free RAM,
backup is free and needs no card). **Fallback:** an Oracle Always Free VM with the Dockerfile (disk persists), or
the PC with a tunnel.

## A. Own PC (default, nothing lost on restart or reboot)
`run_app.bat` (Windows) or `streamlit run app.py`. Data stays in the app folder. To keep it elsewhere set
`STUDIO_HOME=D:\studio-data` (copy `.env` and `client_secret.json` there). Optional extra copy to a Google Drive /
Dropbox synced folder: in `.env` set `STORAGE_BACKEND=folder` and `BACKUP_FOLDER=C:\Users\you\Drive\studio-backup`.

## B. Hugging Face Spaces (free) with GitHub backup
1. Create a **private** GitHub repo, e.g. `studio-backup` (leave it empty, add a README so it has a default branch).
2. GitHub -> Settings -> Developer settings -> Fine-grained tokens: limit to that one repo, permission
   **Contents: Read and write**. Copy the token.
3. huggingface.co -> New Space -> SDK **Docker**, visibility **Private**, hardware CPU basic (free).
4. Push this repo's files to the Space (`git remote add space https://huggingface.co/spaces/<you>/<name>`;
   `git push space main`). The Space needs `app_port: 7860` in a README front matter:
   ```
   ---
   title: Studio
   sdk: docker
   app_port: 7860
   ---
   ```
5. Space -> Settings -> **Secrets** (secrets, not variables): `APP_PASSWORD`, `STORAGE_BACKEND=github`,
   `GITHUB_BACKUP_REPO=<you>/studio-backup`, `GITHUB_BACKUP_TOKEN=<token>`, plus `PIXABAY_API_KEY` if you have one.
   For YouTube upload: on your PC sign in once, then paste the full content of `token.json` into secret
   `YOUTUBE_TOKEN_JSON` (and `client_secret.json` into `GOOGLE_CLIENT_SECRET_JSON`). They are written to disk at
   start-up only, never committed or backed up.
6. Open the Space. The **Data** page shows the backend and last status. Data auto-saves after every action; after a
   restart the app restores from the repo when the disk is empty. The app refuses to back up to a public repo.

Limits: backup is a zip of database, scripts and plans (no mp4/mp3); GitHub caps it near 90 MB. Download finished
videos from step 4 before the Space sleeps. Alternative backend for bigger data: `STORAGE_BACKEND=s3` with
`S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_ENDPOINT_URL` (Cloudflare R2 / Backblaze B2 free tiers;
needs `pip install boto3`, already in the Dockerfile).

## C. Oracle Cloud Always Free VM (fallback, disk persists)
Create an Always Free Ampere A1 Ubuntu VM, open port 8501 in the security list, then:
`sudo apt install ffmpeg python3-venv git`, clone the repo, `pip install -r requirements.txt streamlit`,
`STUDIO_HOME=/home/ubuntu/studio-data APP_PASSWORD=... streamlit run app.py --server.address 0.0.0.0` (use systemd
to keep it running). Data lives on the VM disk; enable the folder or S3 backup for a second copy.

## Secrets rules
Never put keys in git. Local: `.env`. Hosted: the host's Secrets screen. Exports and backups exclude
`token.json`/`client_secret.json`/`.env` by design.
