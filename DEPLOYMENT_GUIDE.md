# 🚀 Free Cloud Deployment Guide

This guide explains how to deploy the **Enterprise Knowledge Copilot** to the cloud with 100% free tiers:
- **Database**: MongoDB Atlas (Free M0 Cluster)
- **Backend API**: Render.com (Free Web Service)
- **Frontend App**: Vercel (Free Hobby Tier)
- **LLM**: Groq Cloud API (Free LPU Tier)

---

## Architecture Overview

```
                      ┌───────────────────────┐
                      │   Vercel (Frontend)   │
                      │  React 18 + Vite SPA  │
                      └──────────┬────────────┘
                                 │ HTTPS / SSE
                                 ▼
                      ┌───────────────────────┐
                      │    Render (Backend)   │
                      │     FastAPI Python    │
                      └─────┬───────────┬─────┘
                            │           │
                 ChromaDB / │           │ Cloud Inference
            ONNX Embeddings │           ▼
                            │    ┌──────────────┐
                            │    │  Groq Cloud  │
                            │    │ (LPU / 120B) │
                            │    └──────────────┘
                            ▼
               ┌────────────────────────┐
               │     MongoDB Atlas      │
               │   Cloud Free Cluster   │
               └────────────────────────┘
```

---

## Step 1: Set Up MongoDB Atlas (Database)

1. Go to [mongodb.com/cloud/atlas](https://www.mongodb.com/cloud/atlas) and sign up / log in.
2. Click **Create a Deployment** → Choose **M0 (Free)**.
3. Choose a region near you (e.g. AWS Mumbai / Frankfurt / us-east-1) → Click **Create**.
4. **Security Setup**:
   - **Database User**: Create a username (e.g., `admin`) and a password. Copy the password!
   - **Network Access**: Add IP Address `0.0.0.0/0` (Allow Access from Anywhere) so Render can connect.
5. Click **Connect** → **Drivers** (Python).
6. Copy your connection string:
   ```text
   mongodb+srv://admin:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```
   *(Replace `<password>` with your actual password)*.

---

## Step 2: Deploy Backend on Render

1. Push your latest code to your GitHub repository:
   ```bash
   git add .
   git commit -m "feat: ready for cloud deployment"
   git push origin main
   ```

2. Go to [render.com](https://render.com) and log in with GitHub.
3. Click **New +** → **Web Service**.
4. Select your `enterprise-knowledge-copilot` repository.
5. Fill in the settings:
   - **Name**: `enterprise-copilot-backend` (or your choice)
   - **Root Directory**: `backend`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: `Free`

6. Under **Environment Variables**, add the following:

   | Key | Value | Notes |
   |---|---|---|
   | `SECRET_KEY` | `python -c "import secrets; print(secrets.token_hex(32))"` | Any 64-char random hex string |
   | `MONGO_URI` | `mongodb+srv://admin:...` | Your Atlas string from Step 1 |
   | `DB_NAME` | `enterprise_copilot_db` | Database name |
   | `LLM_PROVIDER` | `groq` | Cloud LLM provider |
   | `GROQ_API_KEY` | `gsk_...` | Your Groq API key |
   | `GROQ_MODEL` | `openai/gpt-oss-120b` | High-accuracy fast model |
   | `EMBEDDING_PROVIDER` | `default` | Uses self-contained ONNX embeddings (no Ollama needed) |

7. Click **Create Web Service**.
   - Render will build and deploy your backend.
   - Once live, copy your backend URL (e.g. `https://enterprise-copilot-backend.onrender.com`).
   - Test it by visiting `https://enterprise-copilot-backend.onrender.com/docs` — you should see the Swagger UI!

---

## Step 3: Deploy Frontend on Vercel

1. Go to [vercel.com](https://vercel.com) and log in with GitHub.
2. Click **Add New...** → **Project**.
3. Import your `enterprise-knowledge-copilot` repository.
4. Configure Project:
   - **Framework Preset**: `Vite`
   - **Root Directory**: Click Edit → select `frontend`
   - **Build Command**: `npm run build` (auto-detected)
   - **Output Directory**: `dist` (auto-detected)

5. Under **Environment Variables**, add:

   | Name | Value |
   |---|---|
   | `VITE_API_URL` | `https://enterprise-copilot-backend.onrender.com` *(your Render URL from Step 2)* |

6. Click **Deploy**.
   - In ~45 seconds, your app will be live with a URL like `https://enterprise-copilot-frontend.vercel.app`!

---

## Step 4: Verification Checklist

- [ ] Open your Vercel URL in your browser.
- [ ] Sign up a new account (or log in).
- [ ] Create a Workspace and test document upload.
- [ ] Ask a question and verify real-time SSE streaming answer powered by Groq.
- [ ] Copy the live Vercel URL to your resume / GitHub README! 🎉
