"""
Bulk-uploads every transcript JSON in newjsons/ into one workspace, using the
new /documents/upload-transcript endpoint.

Usage:
    1. Log in first and grab your access token (via /docs, POST /api/auth/login)
    2. Create (or pick) a workspace and grab its workspace_id
    3. Fill in the three variables below
    4. Run: python bulk_upload_transcripts.py
"""

import os
import requests

# ---- Fill these in ----
BASE_URL = "http://127.0.0.1:8000"
ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI2YTk0M2FmNjEwZDk2ZTlmZGQ2YjY3OTIiLCJleHAiOjE3ODg1ODMzMjN9.Rap2lBbLhOD2RLN0AG4b3th6AX6RQlJfdtLWkRkXrWo"
WORKSPACE_ID = "6a9a4cf6688bb9d432e4b840"
NEWJSONS_FOLDER =r"D:\MANTHAN\2nd year\PROJECTS\ragpronew\newjsons"  # relative to wherever you run this script from
# ------------------------

# ------------------------

def main():
    if not os.path.exists(NEWJSONS_FOLDER):
        print(f"❌ Folder not found: {NEWJSONS_FOLDER}")
        return

    json_files = [f for f in os.listdir(NEWJSONS_FOLDER) if f.endswith(".json")]
    if not json_files:
        print(f"❌ No .json files found in {NEWJSONS_FOLDER}")
        return

    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}

    # Check what's already been uploaded to this workspace, so re-running
    # this script after a partial failure doesn't create duplicate chunks
    # for files that already succeeded.
    list_url = f"{BASE_URL}/api/workspaces/{WORKSPACE_ID}/documents"
    already_uploaded = set()
    try:
        res = requests.get(list_url, headers=headers, timeout=30)
        if res.status_code == 200:
            already_uploaded = {d["filename"] for d in res.json().get("documents", [])}
            print(f"ℹ️  {len(already_uploaded)} file(s) already uploaded to this workspace — will skip those.\n")
    except requests.exceptions.RequestException as e:
        print(f"⚠️  Couldn't check existing documents ({e}) — proceeding without skip-check.\n")

    print(f"📦 Found {len(json_files)} transcript files total.\n")

    url = f"{BASE_URL}/api/workspaces/{WORKSPACE_ID}/documents/upload-transcript"

    succeeded = 0
    failed = 0
    skipped = 0

    for filename in json_files:
        if filename in already_uploaded:
            print(f"⏩ Skipping (already uploaded): {filename}")
            skipped += 1
            continue

        filepath = os.path.join(NEWJSONS_FOLDER, filename)
        print(f"⬆️  Uploading: {filename} ...", end=" ")

        with open(filepath, "rb") as f:
            files = {"file": (filename, f, "application/json")}
            try:
                res = requests.post(url, headers=headers, files=files, timeout=300)
            except requests.exceptions.RequestException as e:
                print(f"❌ Connection error: {e}")
                failed += 1
                continue

        if res.status_code == 200:
            data = res.json()
            print(f"✅ {data['chunks_indexed']} chunks indexed")
            succeeded += 1
        else:
            print(f"❌ {res.status_code}: {res.text}")
            failed += 1

    print(f"\n🎉 Done. {succeeded} succeeded, {failed} failed, {skipped} skipped (already uploaded).")


if __name__ == "__main__":
    main()
