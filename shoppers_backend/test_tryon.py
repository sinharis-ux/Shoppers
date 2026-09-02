import os
import django
import sys
import base64

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shoppers_ecommerce.settings")
django.setup()

from api.models import AmazonProduct, AvatarSession
from api.virtual_tryon_service import virtual_tryon

def test_tryon():
    try:
        # User's avatar session ID
        session_id = "7d06ebc9-627c-4aea-8c35-a52473e3c57d"
        session = AvatarSession.objects.get(session_id=session_id)
        person_temp_path = getattr(session, 'latest_tryon_path', getattr(session, 'avatar_path', None))
        
        # Product ID
        product_id = "B0FCFMV852"
        product = AmazonProduct.objects.get(asin=product_id)
        
        garment_temp_path = os.path.join("media", 'temp', f'garment_test_{product_id}.jpg')
        
        import requests
        product_response = requests.get(product.image_url, timeout=30)
        product_response.raise_for_status()
        
        with open(garment_temp_path, 'wb') as f:
            f.write(product_response.content)
            
        print(f"Person image: {person_temp_path}")
        print(f"Garment image: {garment_temp_path}")
        
        garment_description = f"top, {product.title}, upper body clothing"
        
        is_full_body = getattr(session, 'is_full_body', False)
        
        tryon_output_path = virtual_tryon(
            person_temp_path,
            garment_temp_path,
            garment_description,
            is_full_body=is_full_body,
            explicit_category='top'
        )
        print("Success!", tryon_output_path)
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_tryon()
