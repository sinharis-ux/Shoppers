import time
import requests

# ==========================================
# PASTE YOUR NANO BANANA PRO API KEY HERE
# ==========================================
API_KEY = "ddbead66f37429a39d5fd7c67d1244ba"

BASE_URL = "https://api.nanobananaapi.ai/api/v1/nanobanana"

def test_nanobanana_api():
    if not API_KEY or API_KEY == "YOUR_API_KEY_HERE":
        print("❌ ERROR: Please replace 'YOUR_API_KEY_HERE' with your actual Nano Banana Pro API key.")
        return

    print("🚀 Starting Nano Banana API Connection Test...")
    print(f"Base URL: {BASE_URL}")
    print(f"API Key: {API_KEY[:8]}...{API_KEY[-8:] if len(API_KEY) > 16 else ''}")

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    # Step 1: Submit an image generation request (Text-to-Image)
    print("\n1️⃣ Sending image generation request...")
    prompt = "A high-fashion model wearing a premium jacket, professional studio lighting, 8k resolution"
    
    # Note: The API uses the specific typo "TEXTTOIAMGE"
    payload = {
        "prompt": prompt,
        "type": "TEXTTOIAMGE",
        "numImages": 1,
        "image_size": "1:1",
        "callBackUrl": "https://example.com/callback"
    }

    try:
        response = requests.post(f"{BASE_URL}/generate", json=payload, headers=headers, timeout=30)
        print(f"HTTP Status Code: {response.status_code}")
        
        try:
            result = response.json()
        except Exception:
            print("❌ Failed to parse response as JSON. Response body:")
            print(response.text)
            return

        if response.status_code != 200 or result.get('code') != 200:
            print("❌ API Error Response:")
            print(result)
            return

        task_id = result.get("data", {}).get("taskId")
        if not task_id:
            print("❌ Error: Response succeeded but no 'taskId' was found in the data.")
            print(result)
            return

        print(f"✅ Success! Task created successfully. Task ID: {task_id}")

    except Exception as e:
        print(f"❌ Connection/Request Error: {e}")
        return

    # Step 2: Poll status of the task
    print("\n2️⃣ Polling task status (waiting for image generation)...")
    start_time = time.time()
    timeout = 120  # wait up to 2 minutes
    poll_interval = 2.0  # check every 2 seconds

    while (time.time() - start_time) < timeout:
        elapsed = int(time.time() - start_time)
        try:
            status_response = requests.get(f"{BASE_URL}/record-info?taskId={task_id}", headers=headers, timeout=20)
            
            if status_response.status_code != 200:
                print(f"⚠️ Non-200 status during poll: {status_response.status_code}")
                time.sleep(poll_interval)
                continue

            status_result = status_response.json()
            if status_result.get('code') != 200:
                print(f"⚠️ Error during poll: {status_result.get('msg')}")
                time.sleep(poll_interval)
                continue

            data = status_result.get("data", {})
            success_flag = data.get("successFlag")

            if success_flag == 0:
                print(f"⏳ Generating... [Elapsed: {elapsed}s]")
                time.sleep(poll_interval)
            elif success_flag == 1:
                print(f"\n🎉 SUCCESS! Image generated successfully after {elapsed}s!")
                response_data = data.get("response", {})
                
                # Check different possible fields for image URL
                result_url = response_data.get("resultImageUrl")
                if not result_url:
                    result_urls = response_data.get("resultImageUrls") or response_data.get("images") or []
                    if result_urls:
                        result_url = result_urls[0] if isinstance(result_urls[0], str) else result_urls[0].get("url")
                
                if result_url:
                    print(f"🔗 Generated Image URL: {result_url}")
                    print("\n✨ Test Complete: Nano Banana API is WORKING perfectly! ✨")
                else:
                    print("⚠️ Success status returned, but no resultImageUrl was found.")
                    print("Full Response Data:", response_data)
                return
            elif success_flag == 2:
                print(f"\n❌ API Error: Task creation failed.")
                print(f"Message: {data.get('errorMessage', 'No error message details')}")
                return
            elif success_flag == 3:
                print(f"\n❌ API Error: Image generation failed.")
                print(f"Message: {data.get('errorMessage', 'No error message details')}")
                return
            else:
                print(f"⚠️ Unknown successFlag value: {success_flag}")
                time.sleep(poll_interval)

        except Exception as e:
            print(f"⚠️ Error while polling: {e}")
            time.sleep(poll_interval)

    print(f"\n⏳ Timeout: Task did not complete within {timeout} seconds.")

if __name__ == "__main__":
    test_nanobanana_api()
