import os
import time
import requests

BASE_URL = "http://127.0.0.1:8000"
# Ensure WORKSPACE_ID matches an existing document _id in enterprise_copilot_db.workspaces
WORKSPACE_ID = "6a9a4cf6688bb9d432e4b840" 
NEWJSONS_FOLDER = r"D:\MANTHAN\2nd year\PROJECTS\ragpronew\newjsons"

EMAIL = "admin@example.com"
PASSWORD = "adminpassword123"


def get_fresh_token() -> str:
    """Logs in dynamically to fetch an active JWT access token."""
    login_url = f"{BASE_URL}/api/auth/login"
    try:
        res = requests.post(login_url, data={"username": EMAIL, "password": PASSWORD}, timeout=10)
        if res.status_code == 200:
            return res.json().get("access_token")
    except requests.exceptions.RequestException:
        pass

    signup_url = f"{BASE_URL}/api/auth/signup"
    requests.post(signup_url, json={"email": EMAIL, "password": PASSWORD}, timeout=10)

    res = requests.post(login_url, data={"username": EMAIL, "password": PASSWORD}, timeout=10)
    return res.json().get("access_token")


def main():
    if not os.path.exists(NEWJSONS_FOLDER):
        print(f"❌ Folder not found: {NEWJSONS_FOLDER}")
        return

    json_files = [f for f in os.listdir(NEWJSONS_FOLDER) if f.endswith(".json")]
    if not json_files:
        print(f"❌ No .json files found in {NEWJSONS_FOLDER}")
        return

    print("🔑 Authenticating and fetching fresh access token...")
    token = get_fresh_token()
    headers = {"Authorization": f"Bearer {token}"}

    upload_url = f"{BASE_URL}/api/workspaces/{WORKSPACE_ID}/documents/upload-transcript"
    succeeded, failed = 0, 0

    print(f"📦 Found {len(json_files)} transcript files to upload.\n")

    for idx, filename in enumerate(json_files, 1):
        filepath = os.path.join(NEWJSONS_FOLDER, filename)
        print(f"⬆️  [{idx}/{len(json_files)}] Uploading: {filename} ...", end=" ", flush=True)

        with open(filepath, "rb") as f:
            files = {"file": (filename, f, "application/json")}
            try:
                res = requests.post(upload_url, headers=headers, files=files, timeout=300)
            except requests.exceptions.RequestException as e:
                print(f"❌ Connection error: {e}")
                failed += 1
                continue

        if res.status_code == 200:
            data = res.json()
            print(f"✅ {data.get('chunks_indexed', 0)} chunks indexed")
            succeeded += 1
        elif res.status_code == 429:
            print("⚠️ Rate limit hit (429). Pausing 12 seconds before retry...")
            time.sleep(12)
            with open(filepath, "rb") as f:
                files = {"file": (filename, f, "application/json")}
                res = requests.post(upload_url, headers=headers, files=files, timeout=300)
                if res.status_code == 200:
                    print(f"✅ Retry succeeded! {res.json().get('chunks_indexed', 0)} chunks indexed")
                    succeeded += 1
                else:
                    print(f"❌ Failed after retry: {res.status_code} - {res.text}")
                    failed += 1
        else:
            print(f"❌ {res.status_code}: {res.text}")
            failed += 1

        # Pause 6 seconds between requests to satisfy gateway rate limit quotas smoothly
        time.sleep(6)

    print(f"\n🎉 Process finished. {succeeded} succeeded, {failed} failed.")


if __name__ == "__main__":
    main()