"""
Re-uploads all 21 lecture transcripts from newjsons/ into MongoDB Atlas Vector Search.

This must be run AFTER deploying the new MongoDB-backed ingestion.py to Render.

Usage:
    python reupload_lectures.py

The script skips lectures already uploaded (checks MongoDB document records).
"""
import os
import time
import requests
from jose import jwt

# ---------- Config ----------
RENDER_URL = "https://enterprise-knowledge-copilot-fj0z.onrender.com"
SECRET_KEY = "9d4e5f2b8a7c6e1d3f0a4b8c7d9e2a1b5c8d7e4f1a2b3c4d5e6f7a8b9c0d1e2f"
USER_ID = "6ac90f35018b8b7cc6e3ee1e"
WORKSPACE_ID = "6a9a4cf6688bb9d432e4b840"
FOLDER = r"D:\MANTHAN\2nd year\PROJECTS\ragpronew\newjsons"
# ----------------------------


def main():
    token = jwt.encode({"sub": USER_ID}, SECRET_KEY, algorithm="HS256")
    headers = {"Authorization": f"Bearer {token}"}

    # Wake up Render if it's sleeping
    print("=== Waking up Render (may take up to 60s) ===")
    for attempt in range(1, 6):
        try:
            r = requests.get(f"{RENDER_URL}/health", timeout=90)
            if r.status_code == 200:
                print(f"Server is alive: {r.json()}\n")
                break
        except Exception as e:
            print(f"  Attempt {attempt}: {e}")
            time.sleep(10)

    # Check which files are already uploaded
    already_uploaded = set()
    try:
        res = requests.get(
            f"{RENDER_URL}/api/workspaces/{WORKSPACE_ID}/documents",
            headers=headers,
            timeout=30
        )
        if res.status_code == 200:
            already_uploaded = {d["filename"] for d in res.json().get("documents", [])}
            print(f"ℹ️  {len(already_uploaded)} file(s) already in MongoDB — will skip those.\n")
    except Exception as e:
        print(f"⚠️  Could not check existing docs: {e}\n")

    # Scan folder
    entries = sorted(
        [e for e in os.scandir(FOLDER) if e.name.endswith(".json")],
        key=lambda x: x.name
    )
    if not entries:
        print(f"❌ No JSON files found in {FOLDER}")
        return

    print(f"📦 Found {len(entries)} transcript files total.\n")

    upload_url = f"{RENDER_URL}/api/workspaces/{WORKSPACE_ID}/documents/upload-transcript"
    succeeded = failed = skipped = 0

    for idx, entry in enumerate(entries, 1):
        safe_name = f"lecture_{idx:02d}.json"

        if safe_name in already_uploaded:
            print(f"⏩ [{idx:02d}/{len(entries)}] Skipping {safe_name} (already in MongoDB)")
            skipped += 1
            continue

        print(f"⬆️  [{idx:02d}/{len(entries)}] Uploading {safe_name} ...", end=" ", flush=True)

        for attempt in range(1, 6):
            try:
                with open(entry.path, "rb") as f:
                    res = requests.post(
                        upload_url,
                        headers=headers,
                        files={"file": (safe_name, f, "application/json")},
                        timeout=120
                    )

                if res.status_code == 200:
                    chunks = res.json().get("chunks_indexed", "?")
                    print(f"✅ {chunks} chunks indexed")
                    succeeded += 1
                    time.sleep(2)   # brief pause to avoid rate-limiting
                    break
                elif res.status_code == 429:
                    print(f"\n  ⏳ Rate limited. Waiting 65s...")
                    time.sleep(65)
                else:
                    print(f"\n  ❌ HTTP {res.status_code}: {res.text[:200]}")
                    if attempt < 5:
                        time.sleep(5)
                    else:
                        failed += 1
            except Exception as e:
                print(f"\n  ⚠️  Network error (attempt {attempt}/5): {e}")
                time.sleep(8)
        else:
            failed += 1

    print(f"\n🎉 Done. {succeeded} succeeded, {skipped} skipped, {failed} failed.")


if __name__ == "__main__":
    main()
