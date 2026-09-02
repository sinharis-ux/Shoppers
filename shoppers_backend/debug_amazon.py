import requests
import json

def test_amazon_api():
    url = "https://real-time-amazon-data.p.rapidapi.com/search"
    headers = {
        "x-rapidapi-key": "6e04be09f0msh25586b8de303f34p1b0451jsn773a26c23f59",
        "x-rapidapi-host": "real-time-amazon-data.p.rapidapi.com"
    }
    
    # Using the suspected problematic params (from amazon_service.py)
    params = {
        "query": "gucci bag",
        "page": "1",
        "country": "US",
        "sort_by": "RELEVANCE",
        # "product_condition": "ALL"  <-- Commented out, just like in amazon_service.py
    }

    try:
        print(f"Testing URL: {url}")
        print(f"Params: {params}")
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        print(f"Status Code: {response.status_code}")
        
        try:
            data = response.json()
        except:
            print(f"Raw Response: {response.text}")
            return

        # Check for error in response body explicitly
        if data.get('status') == 'error':
             print(f"API Error Message: {data.get('message')}")

        products = data.get('data', {}).get('products', [])
        
        if products:
            print(f"SUCCESS: Found {len(products)} products.")
            print("First Product Sample:")
            print(json.dumps(products[0], indent=2))
        else:
            print("FAILURE: No products found.")
            print("Full API Response:")
            print(json.dumps(data, indent=2))
            
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_amazon_api()
