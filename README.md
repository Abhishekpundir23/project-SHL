# Conversational SHL Assessment Recommender

Stateless FastAPI service that guides users from hiring intent to a grounded shortlist of SHL Individual Test Solutions.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Endpoints:

- `GET /health` -> `{"status": "ok"}`
- `POST /chat` -> strict response with `reply`, `recommendations`, and `end_of_conversation`

## Refresh the SHL catalog

```powershell
python scripts/ingest_shl_catalog.py
```

The ingestion script downloads the official assignment catalog JSON and normalizes it into `app/data/shl_catalog.json`. The app only recommends entries present in that normalized catalog.

## Run trace regression

```powershell
python tests/trace_regression.py
```

The regression script evaluates the 10 public traces from `D:\Download\GenAI_SampleConversations` when they are available.

## Deploy on Render

1. Push this repository to GitHub.
2. In Render, choose **New +** -> **Blueprint**.
3. Connect the GitHub repository.
4. Render will use `render.yaml`.
5. After deploy, test:

```text
https://YOUR-RENDER-SERVICE.onrender.com/health
https://YOUR-RENDER-SERVICE.onrender.com/docs
```

Submit the deployed base URL, for example `https://YOUR-RENDER-SERVICE.onrender.com`.
