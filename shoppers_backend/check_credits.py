import requests

# ==========================================
# PASTE YOUR NANO BANANA PRO API KEY HERE
# ==========================================
API_KEY = "ef60b196b500300bb0723264fcd45331"

def check_credits():
    if not API_KEY or API_KEY == "YOUR_API_KEY_HERE":
        print("❌ ERROR: Please set your API key in the script.")
        return

    url = "https://api.nanobananaapi.ai/api/v1/common/credit"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    print("🔍 Fetching Nano Banana credit balance...")
    try:
        response = requests.get(url, headers=headers, timeout=20)
        if response.status_code == 200:
            result = response.json()
            if result.get("code") == 200:
                credits = result.get("data")
                print(f"💳 Current Balance: {credits} credits")
                if credits < 10.0:
                    print("⚠️ Warning: Your credit balance is very low. Image generation tasks may fail or require top-up.")
            else:
                print(f"❌ API returned an error: {result.get('msg')}")
        else:
            print(f"❌ HTTP Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"❌ Connection Error: {e}")

if __name__ == "__main__":
    check_credits()
