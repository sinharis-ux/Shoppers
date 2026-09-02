import os
import time
import json
import base64
import uuid
import requests
import logging
from pathlib import Path
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from django.conf import settings

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser

# OpenAI import removed - using Nano Banana Pro for image generation
# Keeping langchain imports for other features (RAG, etc.)
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

from .models import AvatarSession, NordstromProduct, AmazonProduct
from .serializers import AvatarSessionSerializer, NordstromProductSerializer, AmazonProductSerializer
from .pagination import StandardResultsSetPagination

# Setup logger
logger = logging.getLogger(__name__)


def get_media_url():
    """Get MEDIA_URL without 'shoppers/' prefix"""
    media_url = settings.MEDIA_URL
    if media_url.startswith('shoppers/'):
        return media_url.replace('shoppers/', '', 1)
    return media_url


class CreateSessionView(APIView):
    """
    APIView to create a new avatar session
    """
    
    def post(self, request):
        """Create a new session for avatar generation"""
        try:
            # Create new session
            session = AvatarSession.objects.create()
            serializer = AvatarSessionSerializer(session)
            
            return Response({
                'status': 'success',
                'message': 'Session created successfully',
                'session': serializer.data
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Error creating session: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GetSessionView(APIView):
    """
    APIView to get session details
    """
    
    def get(self, request, session_id):
        """Get session details by session_id"""
        try:
            session = AvatarSession.objects.get(session_id=session_id)
            serializer = AvatarSessionSerializer(session)
            
            # Check if avatar file exists
            avatar_exists = False
            avatar_url = None
            if session.avatar_path and os.path.exists(session.avatar_path):
                avatar_exists = True
                # Create a URL path relative to media directory
                media_url = get_media_url()
                avatar_url = session.avatar_path.replace(settings.MEDIA_ROOT, media_url)
            
            response_data = {
                'status': 'success',
                'session': serializer.data,
                'avatar_exists': avatar_exists,
                'avatar_url': avatar_url
            }
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except AvatarSession.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Session not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Error retrieving session: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class ListProductsAPI(APIView):

    def get(self, request):
        """List all products with pagination"""
        products = NordstromProduct.objects.all().order_by('-scraped_at')

        paginator = StandardResultsSetPagination()
        result_page = paginator.paginate_queryset(products, request)

        serializer = NordstromProductSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)






import os
import json
import time
import base64
import requests
import numpy as np
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageFilter
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
# OpenAI import removed - using Nano Banana Pro for image generation

from .models import AvatarSession, NordstromProduct, AmazonProduct
from .amazon_service import fetch_amazon_products


class FetchAmazonDataAPI(APIView):
    """
    API to trigger fetching data from Amazon RapidAPI for Men, Women, and Children clothing.
    """
    def post(self, request):
        try:
            total_saved = 0
            
            # 1. Fetch Men's Cloths
            print("Fetching Men's products...")
            count_men = fetch_amazon_products("mens clothing", "Men")
            total_saved += count_men
            
            # 2. Fetch Women's Cloths
            print("Fetching Women's products...")
            count_women = fetch_amazon_products("womens clothing", "Women")
            total_saved += count_women
            
            # 3. Fetch Children's Cloths
            print("Fetching Children's products...")
            count_children = fetch_amazon_products("childrens clothing", "Children")
            total_saved += count_children
            
            return Response({
                "status": "success",
                "message": f"Successfully fetched and saved {total_saved} products.",
                "details": {
                    "Men": count_men,
                    "Women": count_women,
                    "Children": count_children
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AmazonProductListAPI(APIView):
    """
    API to list Amazon products.
    Supports filtering by category (Men, Women, Children).
    """
    def get(self, request):
        from django.db.models import Q
        
        category = request.query_params.get('category')
        search_query = request.query_params.get('search')
        
        products = AmazonProduct.objects.all().order_by('-fetched_at')
        
        if category:
            products = products.filter(category__iexact=category)
            
        if search_query:
            products = products.filter(
                Q(title__icontains=search_query) |
                Q(asin__icontains=search_query)
            )
            
        # Pagination
        paginator = StandardResultsSetPagination()
        result_page = paginator.paginate_queryset(products, request)
        
        serializer = AmazonProductSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)


class AmazonSearchProxyAPI(APIView):
    """
    Real-time Amazon Search Proxy.
    Searches RapidAPI -> Saves to DB -> Returns results.
    Allows users to search for ANYTHING (e.g. 'Guitar', 'Red Shoes') and effectively 'Try On' if applicable.
    """
    def get_cached_products(self, query, category, page, page_size=20):
        """Search already-saved Amazon products when live RapidAPI search is unavailable."""
        from django.db.models import Q

        try:
            page = max(int(page), 1)
        except (TypeError, ValueError):
            page = 1

        try:
            page_size = min(max(int(page_size), 1), 100)
        except (TypeError, ValueError):
            page_size = 20

        products = AmazonProduct.objects.all().order_by('-fetched_at')

        if category:
            products = products.filter(category__iexact=category)

        terms = [term.strip() for term in query.split() if term.strip()]
        if terms:
            search_filter = Q()
            for term in terms:
                search_filter |= Q(title__icontains=term) | Q(asin__icontains=term)
            products = products.filter(search_filter)

        start = (page - 1) * page_size
        end = start + page_size
        cached_page = products[start:end]
        serializer = AmazonProductSerializer(cached_page, many=True)
        return list(serializer.data)

    def get(self, request):
        from .amazon_service import AmazonAPIRequestError, search_amazon_products_raw
        
        query = request.query_params.get('query', '').strip()
        page = request.query_params.get('page', 1)
        category = request.query_params.get('category', '').strip()
        
        if not query:
            return Response({
                "status": "error",
                "message": "Query parameter is required."
            }, status=status.HTTP_400_BAD_REQUEST)
            
        # ------------------------------------------------------------------
        # CLOTHING VALIDATION
        # Validate if the query is related to clothing/fashion
        # ------------------------------------------------------------------
        def is_clothing_related(search_term):
            term = search_term.lower()
            print(f"DEBUG: Validating '{term}'")  # DEBUG LOG
            
            # 1. Explicit Whitelist (Strong Indicators)
            clothing_keywords = [
                'shirt', 'pant', 'jeans', 'dress', 'shoe', 'jacket', 'hoodie', 'top', 
                'skirt', 'short', 'coat', 'blazer', 'suit', 'sweater', 'cardigan', 
                'vest', 'gown', 'saree', 'kurta', 'tunic', 'frock', 'lehenga', 
                'blouse', 'trousers', 'legging', 'jogger', 'sweat', 'capri', 
                'jumpsuit', 'romper', 'bodysuit', 'lingerie', 'sleep', 'swim', 
                'active', 'sport', 'sandal', 'heel', 'flat', 'loafer', 'slipper', 
                'boot', 'sneaker', 'wear', 'outfit', 'cloth', 'fashion', 'apparel',
                'garment', 'attire', 'costume', 'uniform'
            ]
            
            # 2. Explicit Blacklist (Non-clothing items)
            forbidden_keywords = [
                'iphone', 'samsung', 'mobile', 'phone', 'laptop', 'computer', 'macbook',
                'tablet', 'ipad', 'watch', 'camera', 'lens', 'headphone', 'speaker',
                'earbud', 'audio', 'video', 'tv', 'television', 'monitor', 'keyboard',
                'mouse', 'charger', 'cable', 'battery', 'adapter', 'electronic',
                'gaming', 'console', 'xbox', 'playstation', 'nintendo', 'game',
                'toy', 'lego', 'action figure', 'doll', 'book', 'novel', 'paper',
                'pen', 'pencil', 'stationery', 'furniture', 'table', 'chair', 'sofa',
                'bed', 'pillow', 'kitchen', 'cook', 'appliance', 'fridge', 'oven',
                'tool', 'drill', 'hardware', 'car', 'bike', 'motor', 'part', 'tyre',
                'tire', 'oil', 'shampoo', 'soap', 'detergent', 'clean', 'food',
                'snack', 'drink', 'beverage', 'grocery', 'vitamin', 'supplement',
                # Accessories (Blacklisted as per client request for strict clothing)
                'bag', 'purse', 'wallet', 'handbag', 'backpack', 'luggage', 'suitcase',
                'belt', 'hat', 'cap', 'scarf', 'glove', 'sock', 'tie', 'accessories',
                'jewelry', 'ring', 'necklace', 'earring', 'bracelet'
            ]
            
            # Check Blacklist first
            for bad_word in forbidden_keywords:
                # Use word boundary check to avoid false positives (e.g. "shoe" in "horseshoe" - rare but possible)
                # Simple check: term includes bad_word
                if bad_word in term:
                    return False
            
            # Check Whitelist
            for good_word in clothing_keywords:
                if good_word in term:
                    return True
            
            # 3. Brand Heuristics (Optional - if term is just a brand name like "Gucci")
            # If no explicit keyword, but not blacklisted, we might allow it if it's not "generic"
            # But client wants strict "only clothing".
            
            # If we are unsure, we default to FALSE to be safe (client asked "only works for clothes")
            # Exception: If the query is just a brand like "Gucci" or "Nike", we should probably allow it?
            fashion_brands = [
                'gucci', 'prada', 'nike', 'adidas', 'puma', 'zara', 'h&m', 'uniqlo',
                'levis', 'calvin', 'klein', 'tommy', 'hilfiger', 'ralph', 'lauren',
                'versace', 'dior', 'chanel', 'hermes', 'burberry', 'balenciaga'
            ]
            for brand in fashion_brands:
                if brand in term:
                    return True

            return False

        if not is_clothing_related(query):
            return Response({
                "status": "error",
                "message": "It only supports cloths searching."
            }, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            # 1. Search Amazon Real-Time. If RapidAPI is rate-limited/down,
            # return cached DB products so the app still has usable results.
            try:
                products = search_amazon_products_raw(query, page=page, category=category)
                source = "rapidapi"
                rate_limited = False
                fallback_reason = None
            except AmazonAPIRequestError as e:
                cached_products = self.get_cached_products(
                    query,
                    category,
                    page,
                    page_size=request.query_params.get('page_size', 20)
                )
                return Response({
                    "status": "success",
                    "query": query,
                    "page": page,
                    "count": len(cached_products),
                    "saved_new": 0,
                    "source": "cache",
                    "rate_limited": e.status_code == 429,
                    "fallback_reason": str(e),
                    "message": "Live Amazon search unavailable. Showing cached products.",
                    "results": cached_products
                }, status=status.HTTP_200_OK)
            
            # 2. Save to DB (Background Sync)
            # We save them so they have IDs/ASINs that can be used for Virtual Try-On
            saved_count = 0
            if products:
                # Add a temporary category tag for search results
                # If explicitly asked for a category, save with that category
                # Otherwise, fallback to Search Result
                assigned_category = category if category in dict(AmazonProduct.CATEGORY_CHOICES).keys() else 'Search Result'
                for p in products:
                    p['category'] = assigned_category
                
                # Check for duplicates explicitly to report accurate 'saved_new' count
                fetched_asins = [p['asin'] for p in products]
                existing_asins = set(AmazonProduct.objects.filter(asin__in=fetched_asins).values_list('asin', flat=True))
                
                new_products = [p for p in products if p['asin'] not in existing_asins]
                
                if new_products:
                    product_objects = [AmazonProduct(**p) for p in new_products]
                    AmazonProduct.objects.bulk_create(product_objects, ignore_conflicts=True)
                    saved_count = len(product_objects)
                    print(f"DEBUG: Saved {saved_count} new products to DB.")
                else:
                    print("DEBUG: All products already exist in DB.")
            
            # 3. Return Results directly (faster than querying DB back)
            for p in products:
                p['product_id'] = p['asin']
                
            return Response({
                "status": "success",
                "query": query,
                "page": page,
                "count": len(products),
                "saved_new": saved_count,
                "source": source,
                "rate_limited": rate_limited,
                "fallback_reason": fallback_reason,
                "results": products
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ApplyProductDallE2EditAPI(APIView):
    """
    Virtual Try-On API (Legacy Endpoint)
    Now redirected to use CatVTON/OOTDiffusion for better results (preserving body).
    Maintains backward compatibility with DALL-E 2 API response format.
    """
    
    def save_avatar_locally(self, image_data, session_id, suffix="tryon"):
        """Save avatar image locally"""
        avatars_dir = os.path.join(settings.MEDIA_ROOT, 'avatars')
        Path(avatars_dir).mkdir(parents=True, exist_ok=True)
        
        filename = f"avatar_{suffix}_{session_id}.png"
        filepath = os.path.join(avatars_dir, filename)
        
        if isinstance(image_data, bytes):
            with open(filepath, 'wb') as f:
                f.write(image_data)
        else:
            image_data.save(filepath, 'PNG', quality=95)
        
        return filepath

    def post(self, request):
        from .virtual_tryon_service import virtual_tryon
        
        session_id = request.data.get("session_id")
        product_id = request.data.get("product_id")

        # Validation
        if not session_id:
            return Response({
                "status": "error",
                "message": "session_id is required."
            }, status=status.HTTP_400_BAD_REQUEST)
            
        if not product_id:
            return Response({
                "status": "error",
                "message": "product_id is required."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            session = AvatarSession.objects.get(session_id=session_id)
        except AvatarSession.DoesNotExist:
            return Response({
                "status": "error",
                "message": "Invalid session_id."
            }, status=status.HTTP_404_NOT_FOUND)

        if not session.avatar_path or not os.path.exists(session.avatar_path):
            return Response({
                "status": "error",
                "message": "No avatar found for this session."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            product = NordstromProduct.objects.get(product_id=product_id)
        except NordstromProduct.DoesNotExist:
            return Response({
                "status": "error",
                "message": "Product not found."
            }, status=status.HTTP_404_NOT_FOUND)

        if not product.image_url:
            return Response({
                "status": "error",
                "message": "Product has no image."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            print(f"\n{'='*70}")
            print(f"VIRTUAL TRY-ON (Redirected to CatVTON)")
            print(f"Session: {session_id}")
            print(f"Product: {product.title}")
            print(f"{'='*70}\n")
            
            start_time = time.time()
            
            person_path = session.avatar_path
            # OPTIMIZATION: Use external URL directly instead of downloading and re-uploading
            garment_path = product.image_url
            # 3. Virtual Try-On using CatVTON (Preserves Body)
            # Use a descriptive string for better category detection inside virtual_tryon
            garment_des = f"{product.title} {product.formatted_price} {product.brand}"
            
            print("Calling virtual_tryon service...")
            output_path = virtual_tryon(person_path, garment_path, garment_des)
            
            # 4. Read result
            with open(output_path, 'rb') as f:
                final_bytes = f.read()
            
            # 5. Save as session avatar (maintain legacy behavior of updating the avatar)
            # Unlike VirtualTryOnView, this old endpoint typically UPDATED the avatar.
            # We will respect that behavior if that's what the frontend expects.
            
            # Delete old avatar file if it exists and isn't the original
            if session.avatar_path and os.path.exists(session.avatar_path) and session.avatar_path != session.original_avatar_path:
                try:
                    os.remove(session.avatar_path)
                except:
                    pass

            save_path = self.save_avatar_locally(final_bytes, session_id, suffix="catvton")
            
            session.avatar_path = save_path
            session.save()
            
            # 6. Prepare Response (Mapping to match DALL-E 2 response format)
            relative_path = os.path.relpath(save_path, settings.MEDIA_ROOT)
            media_url = get_media_url()
            public_url = media_url + relative_path.replace("\\", "/")
            image_b64 = base64.b64encode(final_bytes).decode('utf-8')
            
            total_time = time.time() - start_time
            
            # Cleanup
            if not garment_path.startswith('http') and os.path.exists(garment_path):
                try:
                    os.remove(garment_path)
                except:
                    pass
            
            return Response({
                "status": "success",
                "session_id": str(session_id),
                "product_id": str(product_id),
                "product_name": product.title,
                "product_analysis": {
                    "category": "auto-detected",
                    "provider": "CatVTON"
                },
                "updated_avatar_url": public_url,
                "dalle_image_url": public_url, # Legacy field
                "image_base64": image_b64,     # Legacy field (often used by frontend)
                "prompt_used": "CatVTON (Image-based)",
                "provider": "CatVTON (Replaces DALL-E 2)",
                "model": "CatVTON",
                "processing_time_seconds": round(total_time, 2)
            }, status=status.HTTP_200_OK)

        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"\n❌ ERROR:\n{error_trace}\n")
            return Response({
                "status": "error",
                "message": f"Error processing request: {str(e)}",
                "trace": error_trace if settings.DEBUG else None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    def get_mask_coordinates(self, category, bottom_subtype, width, height):
        """
        Get precise mask coordinates based on product type
        
        Returns dict with x1, y1, x2, y2, and blur radius
        """
        coords = {}
        
        if category == 'bottom':
            if bottom_subtype in ['shorts', 'short']:
                # SHORTS: waist to mid-thigh only
                coords = {
                    'x1': int(width * 0.15),
                    'y1': int(height * 0.46),
                    'x2': int(width * 0.85),
                    'y2': int(height * 0.68),  # End at mid-thigh
                    'blur': 18
                }
                print(f"Using SHORTS mask: {coords}")
            elif bottom_subtype == 'skirt':
                # Skirt: waist to knee area
                coords = {
                    'x1': int(width * 0.15),
                    'y1': int(height * 0.46),
                    'x2': int(width * 0.85),
                    'y2': int(height * 0.75),
                    'blur': 22
                }
            elif bottom_subtype == 'leggings':
                # Leggings: waist to ankles
                coords = {
                    'x1': int(width * 0.18),
                    'y1': int(height * 0.46),
                    'x2': int(width * 0.82),
                    'y2': int(height * 0.92),
                    'blur': 30
                }
            else:
                # PANTS (default): waist to ankles
                coords = {
                    'x1': int(width * 0.18),
                    'y1': int(height * 0.46),
                    'x2': int(width * 0.82),
                    'y2': int(height * 0.90),
                    'blur': 30
                }
                print(f"Using PANTS mask: {coords}")
                
        elif category == 'top':
            # TOP: neck to waist
            coords = {
                'x1': int(width * 0.10),
                'y1': int(height * 0.16),
                'x2': int(width * 0.90),
                'y2': int(height * 0.50),
                'blur': 25
            }
            
        elif category == 'shoes':
            # SHOES: feet only
            coords = {
                'x1': int(width * 0.18),
                'y1': int(height * 0.86),
                'x2': int(width * 0.82),
                'y2': int(height * 0.99),
                'blur': 12
            }
            
        elif category == 'dress':
            # DRESS: neck to knees/ankles
            coords = {
                'x1': int(width * 0.10),
                'y1': int(height * 0.16),
                'x2': int(width * 0.90),
                'y2': int(height * 0.88),
                'blur': 30
            }
            
        else:
            # Default fallback
            coords = {
                'x1': int(width * 0.15),
                'y1': int(height * 0.20),
                'x2': int(width * 0.85),
                'y2': int(height * 0.80),
                'blur': 25
            }
        
        return coords

    def create_mask(self, width, height, coords):
        """
        Create DALL-E 2 compatible mask
        
        CRITICAL:
        - Transparent areas (alpha=0) = DALL-E will REGENERATE these areas
        - Opaque areas (alpha=255) = DALL-E will KEEP these areas unchanged
        """
        x1 = max(0, coords['x1'])
        y1 = max(0, coords['y1'])
        x2 = min(width, coords['x2'])
        y2 = min(height, coords['y2'])
        blur = coords.get('blur', 20)
        
        print(f"Creating mask: region ({x1},{y1}) to ({x2},{y2}), size {x2-x1}x{y2-y1}, blur {blur}")
        
        # Create alpha channel: 255 = keep, 0 = regenerate
        alpha_array = np.ones((height, width), dtype=np.uint8) * 255
        
        # Set edit region to 0 (transparent = regenerate)
        alpha_array[y1:y2, x1:x2] = 0
        
        # Convert to PIL Image
        alpha_image = Image.fromarray(alpha_array, mode='L')
        
        # Apply gaussian blur for smooth edges
        alpha_image = alpha_image.filter(ImageFilter.GaussianBlur(radius=blur))
        
        # Ensure center of edit region is fully transparent after blur
        alpha_array_blurred = np.array(alpha_image)
        margin = blur + 3
        inner_x1 = min(x1 + margin, x2)
        inner_y1 = min(y1 + margin, y2)
        inner_x2 = max(x2 - margin, x1)
        inner_y2 = max(y2 - margin, y1)
        
        if inner_x2 > inner_x1 and inner_y2 > inner_y1:
            alpha_array_blurred[inner_y1:inner_y2, inner_x1:inner_x2] = 0
        
        alpha_image = Image.fromarray(alpha_array_blurred, mode='L')
        
        # Create RGBA mask with this alpha channel
        mask = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        mask.putalpha(alpha_image)
        
        return mask

    def prepare_square_avatar(self, image):
        """
        Prepare avatar image for DALL-E 2 (1024x1024 square)
        Uses white background for padding
        """
        width, height = image.size
        max_dim = max(width, height)
        
        # Create white background
        square = Image.new('RGBA', (max_dim, max_dim), (255, 255, 255, 255))
        
        # Center the image
        offset = ((max_dim - width) // 2, (max_dim - height) // 2)
        
        if image.mode == 'RGBA':
            square.paste(image, offset, image)
        else:
            square.paste(image, offset)
        
        # Resize to 1024x1024
        if max_dim != 1024:
            square = square.resize((1024, 1024), Image.Resampling.LANCZOS)
        
        return square, offset, (width, height)

    def prepare_square_mask(self, mask_image):
        """
        Prepare mask for DALL-E 2 (1024x1024 square)
        
        CRITICAL: Preserves alpha channel correctly!
        - Padding areas must be OPAQUE (alpha=255) so they're preserved
        - Edit areas must stay TRANSPARENT (alpha=0) so they're regenerated
        """
        width, height = mask_image.size
        max_dim = max(width, height)
        offset = ((max_dim - width) // 2, (max_dim - height) // 2)
        
        # Extract alpha channel from mask
        if mask_image.mode == 'RGBA':
            alpha = mask_image.split()[3]
        else:
            alpha = mask_image.convert('L')
        
        # Create square alpha channel - padding is 255 (keep/opaque)
        square_alpha = Image.new('L', (max_dim, max_dim), 255)
        
        # Paste original alpha in center
        square_alpha.paste(alpha, offset)
        
        # Resize to 1024x1024
        if max_dim != 1024:
            square_alpha = square_alpha.resize((1024, 1024), Image.Resampling.LANCZOS)
        
        # Create final RGBA mask
        square_mask = Image.new('RGBA', (1024, 1024), (0, 0, 0, 0))
        square_mask.putalpha(square_alpha)
        
        return square_mask, offset, (width, height)

    def restore_original_size(self, edited_image, original_size, offset):
        """
        Restore edited image to original dimensions
        """
        orig_width, orig_height = original_size
        max_dim = max(orig_width, orig_height)
        
        if orig_width == orig_height:
            return edited_image.resize(original_size, Image.Resampling.LANCZOS)
        
        # Calculate scaling
        scale = 1024 / max_dim
        scaled_offset = (int(offset[0] * scale), int(offset[1] * scale))
        scaled_size = (int(orig_width * scale), int(orig_height * scale))
        
        # Crop out the original region
        cropped = edited_image.crop((
            scaled_offset[0],
            scaled_offset[1],
            scaled_offset[0] + scaled_size[0],
            scaled_offset[1] + scaled_size[1]
        ))
        
        # Resize to exact original size
        final = cropped.resize(original_size, Image.Resampling.LANCZOS)
        return final

    def create_prompt(self, product_info):
        """
        Create effective prompt for DALL-E 2 based on product analysis
        """
        category = product_info.get('category', 'bottom')
        bottom_subtype = product_info.get('bottom_subtype', 'pants')
        item_type = product_info.get('item_type', '')
        color = product_info.get('primary_color', 'black')
        secondary = product_info.get('secondary_colors', '')
        style = product_info.get('style', 'casual')
        features = product_info.get('features', '')
        brand = product_info.get('brand', '')
        
        # Build color description
        color_desc = color
        if secondary and secondary.lower() not in ['none', '']:
            color_desc = f"{color} with {secondary}"
        
        # Build item description
        if brand and brand.lower() not in ['none', '']:
            item_desc = f"{brand} {color_desc} {style}"
        else:
            item_desc = f"{color_desc} {style}"
        
        # Add features if present
        if features and features.lower() not in ['none', '']:
            item_desc += f" with {features}"
        
        # Category-specific prompts
        if category == 'bottom':
            if bottom_subtype in ['shorts', 'short']:
                prompt = f"""3D cartoon avatar wearing {item_desc} athletic shorts.
The shorts end ABOVE the knee, mid-thigh length.
Natural bare legs visible below the shorts.
Same cartoon avatar style, same pose, same skin tone.
White clean background. Full body view."""
            
            elif bottom_subtype == 'skirt':
                prompt = f"""3D cartoon avatar wearing {item_desc} skirt.
Same cartoon avatar style, same pose.
White clean background. Full body view."""
            
            else:  # pants, jeans, leggings
                prompt = f"""3D cartoon avatar wearing {item_desc} {bottom_subtype or 'pants'}.
Full length {bottom_subtype or 'pants'} reaching to the ankles.
Same cartoon avatar style, same pose.
White clean background. Full body view."""
        
        elif category == 'top':
            prompt = f"""3D cartoon avatar wearing {item_desc} {item_type or 'top'}.
Same cartoon avatar style, same pose.
White clean background. Full body view."""
        
        elif category == 'shoes':
            prompt = f"""3D cartoon avatar wearing {item_desc} {item_type or 'shoes'}.
Same cartoon avatar style, same pose.
White clean background. Full body view."""
        
        elif category == 'dress':
            prompt = f"""3D cartoon avatar wearing {item_desc} dress.
Same cartoon avatar style, same pose.
White clean background. Full body view."""
        
        else:
            prompt = f"""3D cartoon avatar wearing {item_desc}.
Same cartoon avatar style, same pose.
White clean background. Full body view."""
        
        return prompt.strip()

    def save_debug_mask(self, mask_image, session_id):
        """
        Save a visual debug version of the mask
        RED = edit/regenerate area
        GREEN = keep/preserve area
        """
        try:
            debug_dir = os.path.join(settings.MEDIA_ROOT, 'debug')
            os.makedirs(debug_dir, exist_ok=True)
            
            # Get alpha channel
            alpha = mask_image.split()[3]
            alpha_array = np.array(alpha)
            
            # Create RGB visualization
            height, width = alpha_array.shape
            visual = np.zeros((height, width, 3), dtype=np.uint8)
            
            # Red where transparent (edit), Green where opaque (keep)
            visual[alpha_array < 128] = [255, 0, 0]   # Red = edit
            visual[alpha_array >= 128] = [0, 255, 0]  # Green = keep
            
            visual_image = Image.fromarray(visual, mode='RGB')
            debug_path = os.path.join(debug_dir, f'mask_debug_{session_id}.png')
            visual_image.save(debug_path)
            
            # Calculate stats
            edit_pixels = np.sum(alpha_array < 128)
            total_pixels = alpha_array.size
            edit_percent = 100 * edit_pixels / total_pixels
            
            print(f"Debug mask saved: {debug_path}")
            print(f"Edit area: {edit_pixels:,} / {total_pixels:,} pixels ({edit_percent:.1f}%)")
            
            if edit_pixels == 0:
                print("⚠️ WARNING: No edit area! Mask is fully opaque - nothing will change!")
            elif edit_percent > 80:
                print("⚠️ WARNING: Edit area very large - most of image will be regenerated!")
            
            return debug_path
            
        except Exception as e:
            print(f"Could not save debug mask: {e}")
            return None

    def post(self, request):
        """
        Legacy endpoint for DALL-E 2 virtual try-on.
        Redirected to NanoBanana VirtualTryOnView for far superior results.
        """
        # Instantiate the new view and forward the request
        tryon_view = VirtualTryOnView()
        
        # Add a flag so the frontend knows it was redirected
        response = tryon_view.post(request)
        
        if hasattr(response, 'data') and isinstance(response.data, dict):
            # Ensure the frontend still gets the expected fields if possible
            response.data['provider'] = 'nanobanana_redirected_from_dalle2'
            response.data['legacy_redirect'] = True
            
            # Add backwards compatible fields that the old endpoint returned
            if 'tryon_url' in response.data:
                response.data['updated_avatar_url'] = response.data['tryon_url']
                response.data['dalle_image_url'] = response.data['tryon_url']
            
        return response


class VirtualTryOnView(APIView):
    """
    Virtual Try-On API using Hugging Face IDM-VTON
    Combines person image with garment image for virtual try-on
    """
    parser_classes = (MultiPartParser, FormParser)

    def analyze_product_for_tryon(self, product_b64, client):
        """
        Analyze the product image to determine category, type, color, etc.
        Optimized for virtual try-on with explicit category detection
        """
        prompt = """
Analyze this clothing product image carefully for virtual try-on.

Provide ONLY this JSON response:
{
    "category": "top|bottom|shoes|dress",
    "bottom_subtype": "shorts|pants|skirt|leggings|jeans|none",
    "item_type": "specific type (hoodie, t-shirt, jeans, sneakers, etc.)",
    "primary_color": "main color",
    "secondary_colors": "other colors if any",
    "style": "athletic|casual|formal|streetwear|etc",
    "features": "notable features (logo, stripes, pockets, etc.)",
    "brand": "brand name if visible, otherwise none"
}

CRITICAL: 
- If it's pants, jeans, shorts, skirt, or leggings, category MUST be "bottom"
- If it's a shirt, t-shirt, hoodie, blouse, or top, category MUST be "top"
- Be very accurate about category - this determines where the garment is applied on the person
"""
        
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{product_b64}"}
                        }
                    ]
                }],
                max_tokens=300,
                temperature=0
            )
            
            content = response.choices[0].message.content.strip()
            content = content.replace('```json', '').replace('```', '').strip()
            result = json.loads(content)
            
            print(f"Product Analysis: {json.dumps(result, indent=2)}")
            return result
            
        except Exception as e:
            print(f"Product analysis error: {e}")
            # Default to bottom if we can't determine (safer for pants)
            return {
                "category": "bottom",
                "bottom_subtype": "pants",
                "item_type": "pants",
                "primary_color": "black",
                "secondary_colors": "",
                "style": "casual",
                "features": "",
                "brand": "none"
            }

    def save_image_locally(self, image_data, session_id, product_id=None, suffix="tryon"):
        """Save try-on result locally in tryon folder and return the file path"""
        tryon_dir = os.path.join(settings.MEDIA_ROOT, 'tryon')
        Path(tryon_dir).mkdir(parents=True, exist_ok=True)
        import time
        timestamp = int(time.time() * 1000)
        
        if product_id:
            filename = f"tryon_{session_id}_{product_id}_{timestamp}.jpg"
        else:
            filename = f"tryon_{session_id}_{timestamp}.jpg"
        filepath = os.path.join(tryon_dir, filename)
        
        if isinstance(image_data, bytes):
            with open(filepath, 'wb') as f:
                f.write(image_data)
        else:
            image_data.save(filepath, 'JPEG', quality=95)  # Increased quality for better results
        
        return filepath

    def post(self, request):
        """
        Virtual try-on endpoint
        
        Required:
        - session_id: UUID of the session
        - product_id: ID of the product to try on
        
        Optional:
        - garment_description: Description of the garment (default: auto-generated from product)
        - apply_3d: Boolean to apply 3D effects (default: False)
        - include_base64: Boolean to include base64 image in response (default: False)
          Note: Setting this to true will make the response very large. Use avatar_url instead.
        """
        from .virtual_tryon_service import (
            apply_3d_effects,
            build_garment_intent,
            select_tryon_person_path,
            virtual_tryon,
        )
        
        # Validate session_id
        session_id = request.data.get('session_id')
        if not session_id:
            return Response({
                'status': 'error',
                'message': 'session_id is required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate product_id
        product_id = request.data.get('product_id')
        if not product_id:
            return Response({
                'status': 'error',
                'message': 'product_id is required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            session = AvatarSession.objects.get(session_id=session_id)
        except AvatarSession.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Invalid session_id. Session not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        # Validate avatar exists
        if not session.avatar_path or not os.path.exists(session.avatar_path):
            return Response({
                'status': 'error',
                'message': 'No avatar found for this session. Please generate an avatar first.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get parameters
        apply_3d = request.data.get('apply_3d', 'false').lower() == 'true'
        include_base64 = request.data.get('include_base64', 'false').lower() == 'true'


        try:
            explicit_category = request.data.get('garment_category', '').lower().strip()
            person_temp_path, input_image_source, used_compounding = select_tryon_person_path(
                session.avatar_path,
                getattr(session, 'latest_tryon_path', None),
                explicit_category,
            )

            if not person_temp_path:
                return Response({
                    'status': 'error',
                    'message': 'No avatar found for this session.'
                }, status=status.HTTP_400_BAD_REQUEST)

            if input_image_source == 'latest_tryon':
                print(f"📌 Using PREVIOUS try-on result as Image 1: {person_temp_path}")
            elif explicit_category in ['outfit', 'suit', 'co-ord', 'set', 'dress', 'full-body']:
                print(f"📌 Using BASE avatar as Image 1 (full outfit reset): {person_temp_path}")
            else:
                print(f"📌 Using BASE avatar as Image 1 (first top/bottom try-on): {person_temp_path}")
            
            # Prepare temp directory for product image
            temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp')
            os.makedirs(temp_dir, exist_ok=True)
            
            garment_temp_path = None
            product = None
            
            # 1. CHECK FOR UPLOADED FILE FIRST (Higher Priority)
            if 'garment_image' in request.FILES:
                garment_file = request.FILES['garment_image']
                garment_temp_path = os.path.join(temp_dir, f'upload_{session_id}_{int(time.time())}.jpg')
                with open(garment_temp_path, 'wb') as f:
                    for chunk in garment_file.chunks():
                        f.write(chunk)
                print(f"✓ Using uploaded garment image: {garment_temp_path}")

            # 2. IF NO UPLOAD, CHECK FOR PRODUCT ID
            elif product_id:
                try:
                    product = NordstromProduct.objects.get(product_id=product_id)
                except NordstromProduct.DoesNotExist:
                    # Fallback to Amazon Product
                    try:
                        product = AmazonProduct.objects.get(asin=product_id)
                    except AmazonProduct.DoesNotExist:
                        product = None

                if not product:
                    return Response({
                        'status': 'error',
                        'message': 'Product not found and no file uploaded.'
                    }, status=status.HTTP_404_NOT_FOUND)

                if not product.image_url:
                    return Response({
                        'status': 'error',
                        'message': 'Product has no image.'
                    }, status=status.HTTP_400_BAD_REQUEST)
                    
                # OPTIMIZATION: Use the external URL directly instead of downloading and re-uploading
                garment_temp_path = product.image_url
                print(f"Using product image URL: {garment_temp_path}")

            
            if not garment_temp_path or (not garment_temp_path.startswith('http') and not os.path.exists(garment_temp_path)):
                 return Response({
                    'status': 'error',
                    'message': 'No garment image provided (file upload or product_id required).'
                }, status=status.HTTP_400_BAD_REQUEST)

            print(f"Avatar path: {person_temp_path}")
            print(f"Product image saved to: {garment_temp_path}")

            # Analyze product to determine category and create proper description
            print("\n" + "="*60)
            print("Analyzing product for virtual try-on...")
            print("="*60)
            
            # CHECK FOR EXPLICIT CATEGORY FROM FRONTEND (TOP PRIORITY)
            # This allows frontend to specify category directly: 'top-wear' or 'bottom-wear'
            explicit_category = request.data.get('garment_category', '').lower().strip()
            
            provided_description = request.data.get('garment_description')
            product_title = getattr(product, 'title', '') if product else ''
            product_brand = getattr(product, 'brand', '') if product else ''
            product_url = getattr(product, 'image_url', garment_temp_path) if product else garment_temp_path

            if provided_description:
                garment_description = provided_description
            elif product_title:
                garment_description = f"{explicit_category or 'garment'}, {product_title}"
                if product_brand:
                    garment_description = f"{garment_description}, brand: {product_brand}"
            else:
                garment_description = f"{explicit_category or 'garment'}, uploaded garment image"

            garment_intent = build_garment_intent(explicit_category, garment_description)
            category = garment_intent['action']
            bottom_subtype = garment_intent['subtype'] if category == 'bottom' else None
            product_info = {
                'category': category,
                'bottom_subtype': bottom_subtype,
                'item_type': product_title[:50] if product_title else garment_intent['subtype'],
                'primary_color': '',
                'style': '',
                'brand': product_brand,
            }
            print(f"✓ Garment intent: {garment_intent}")

            # Get is_full_body from session to determine which model to use
            is_full_body = getattr(session, 'is_full_body', False)
            print(f"\n📊 Image Type: {'Full Body (Original)' if is_full_body else 'Selfie (Generated Avatar)'}")
            print(f"→ Using: Nano Banana Pro API")
            print(f"→ Category: {category or 'auto-detect from description'}")

            # Perform virtual try-on with appropriate model
            # Pass explicit category if available
            tryon_output_path = virtual_tryon(
                person_temp_path,
                garment_temp_path,
                garment_description,
                is_full_body=is_full_body,
                explicit_category=explicit_category or category
            )

            # Apply 3D effects if requested
            final_output_path = tryon_output_path
            if apply_3d:
                final_output_path = apply_3d_effects(tryon_output_path)

            # Read the final result
            with open(final_output_path, 'rb') as f:
                final_image_data = f.read()

            # Save to tryon directory (don't overwrite avatar)
            suffix = "tryon_3d" if apply_3d else "tryon"
            saved_path = self.save_image_locally(final_image_data, session_id, product_id=product_id, suffix=suffix)

            # Keep track of the latest tryon for compounding
            session.latest_tryon_path = saved_path
            session.save()

            # Don't update session.avatar_path - keep original avatar intact
            # The try-on result is saved separately in the tryon folder

            # Create response URLs
            relative_path = os.path.relpath(saved_path, settings.MEDIA_ROOT)
            media_url = get_media_url()
            tryon_url = media_url + relative_path.replace("\\", "/")
            
            # Get original avatar URL (if exists)
            avatar_url = None
            if session.avatar_path and os.path.exists(session.avatar_path):
                avatar_relative_path = os.path.relpath(session.avatar_path, settings.MEDIA_ROOT)
                avatar_url = media_url + avatar_relative_path.replace("\\", "/")
            
            # Only encode base64 if explicitly requested (to avoid large responses)
            response_data = {
                'status': 'success',
                'session_id': str(session_id),
                'product_id': str(product_id),
                'product_title': product_title,
                'product_url': product_url,
                'tryon_url': tryon_url,
                'avatar_url': avatar_url,  # Original avatar URL (unchanged)
                'garment_description': garment_description,
                'garment_intent': garment_intent,
                'input_image_source': input_image_source,
                'used_compounding': used_compounding,
                '3d_effects_applied': apply_3d,
                'saved_path': saved_path,
                'is_full_body': is_full_body,  # True if original full body, False if generated avatar
                'tryon_model': 'Nano Banana Pro'  # Using Nano Banana Pro API for virtual try-on
            }
            
            # Add product analysis if available
            if product_info:
                response_data['product_analysis'] = {
                    'category': category,
                    'bottom_subtype': bottom_subtype if category == 'bottom' else None,
                    'item_type': product_info.get('item_type', ''),
                    'color': product_info.get('primary_color', ''),
                    'style': product_info.get('style', ''),
                    'brand': product_info.get('brand', '')
                }
            
            if include_base64:
                image_base64 = base64.b64encode(final_image_data).decode('utf-8')
                response_data['image_base64'] = image_base64

            # Cleanup temp files (don't delete avatar_path, only temp product image)
            try:
                # Only remove garment_temp_path if it's a local file
                if garment_temp_path and not garment_temp_path.startswith('http') and os.path.exists(garment_temp_path):
                    os.remove(garment_temp_path)
                if final_output_path != tryon_output_path and os.path.exists(tryon_output_path):
                    os.remove(tryon_output_path)
            except Exception as e:
                print(f"Could not remove temp files: {e}")

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"\n❌ ERROR:\n{error_trace}\n")
            
            return Response({
                'status': 'error',
                'message': f'Error processing virtual try-on: {str(e)}',
                'trace': error_trace if settings.DEBUG else None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class GenerateAvatarAPI(APIView):
    """
    Generate/Process avatar for virtual try-on
    Generates a FULL BODY avatar including shoes
    """
    parser_classes = (MultiPartParser, FormParser)

    def save_image_locally(self, image_data, session_id, suffix="improved"):
        avatars_dir = os.path.join(settings.MEDIA_ROOT, 'avatars')
        Path(avatars_dir).mkdir(parents=True, exist_ok=True)

        # Use unique filename with timestamp to prevent frontend caching
        import time
        filename = f"avatar_{suffix}_{int(time.time() * 1000)}.png"
        filepath = os.path.join(avatars_dir, filename)

        with open(filepath, 'wb') as f:
            f.write(image_data)

        return filepath

    def post(self, request):
        from .avatar_improvement_service import preprocess_for_avatar

        include_base64 = request.data.get('include_base64', 'false').lower() == 'true'
        session_id = request.data.get('session_id')

        if not session_id:
            return Response(
                {'status': 'error', 'message': 'session_id is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            session = AvatarSession.objects.get(session_id=session_id)
        except AvatarSession.DoesNotExist:
            return Response(
                {'status': 'error', 'message': 'Invalid session_id.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------------------
        # INPUT IMAGE SELECTION (MULTI-VIEW SUPPORT)
        # ---------------------------------------------------------
        input_image_path = None
        reference_map = {}

        logger.error(f"\n{'='*60}")
        logger.error("🔍 DEBUG: Checking for images in request...")
        logger.error(f"   - request.FILES keys: {list(request.FILES.keys())}")
        logger.error(f"   - session.original_avatar_path: {session.original_avatar_path}")
        logger.error(f"{'='*60}\n")

        allowed = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
        reference_fields = [
            ('front', 'image_front'),
            ('side', 'image_side'),
            ('back', 'image_back'),
            ('face', 'image_face'),
            ('front', 'image'),  # Backward compatibility
        ]
        has_new_images = any(field in request.FILES for _, field in reference_fields)

        originals_dir = os.path.join(settings.MEDIA_ROOT, 'originals', str(session_id))
        os.makedirs(originals_dir, exist_ok=True)
        reference_meta_path = os.path.join(originals_dir, 'reference_images.json')

        def save_uploaded_image(image_file, label):
            if image_file.content_type not in allowed:
                raise ValueError('Invalid image type.')
            import time
            file_ext = os.path.splitext(image_file.name)[1] or '.jpg'
            filename = f"{label}_{int(time.time() * 1000)}{file_ext}"
            filepath = os.path.join(originals_dir, filename)
            with open(filepath, 'wb') as f:
                f.write(image_file.read())
            return filepath

        if has_new_images:
            logger.error("✅ NEW IMAGES RECEIVED - Processing upload...")

            # Clear old originals on new upload to avoid stale references
            try:
                for name in os.listdir(originals_dir):
                    old_path = os.path.join(originals_dir, name)
                    if os.path.isfile(old_path):
                        os.remove(old_path)
            except Exception as e:
                logger.error(f"⚠ Could not clean originals dir: {e}")

            try:
                for label, field in reference_fields:
                    if field in request.FILES and label not in reference_map:
                        reference_map[label] = save_uploaded_image(request.FILES[field], label)
            except ValueError as e:
                return Response(
                    {'status': 'error', 'message': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not reference_map:
                return Response(
                    {'status': 'error', 'message': 'No valid images provided.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Choose primary image (front preferred)
            input_image_path = reference_map.get('front') or next(iter(reference_map.values()))

            # Persist reference map for reuse
            try:
                with open(reference_meta_path, 'w') as f:
                    json.dump(reference_map, f)
            except Exception as e:
                logger.error(f"⚠ Could not save reference metadata: {e}")

            # Update session original reference
            session.original_avatar_path = input_image_path

            # Clear cached avatar to force regeneration with new images
            if session.avatar_path and os.path.exists(session.avatar_path):
                try:
                    os.remove(session.avatar_path)
                    logger.error(f"🗑 Deleted old avatar: {session.avatar_path}")
                except Exception:
                    pass
            if getattr(session, 'latest_tryon_path', None) and os.path.exists(session.latest_tryon_path):
                try:
                    os.remove(session.latest_tryon_path)
                    logger.error(f"🗑 Deleted old latest_tryon_path: {session.latest_tryon_path}")
                except Exception:
                    pass

            session.avatar_path = None
            session.latest_tryon_path = None
            session.save()

        else:
            # No new images, try to use stored references
            if os.path.exists(reference_meta_path):
                try:
                    with open(reference_meta_path, 'r') as f:
                        reference_map = json.load(f)
                except Exception as e:
                    logger.error(f"⚠ Could not read reference metadata: {e}")

            if session.original_avatar_path and os.path.exists(session.original_avatar_path):
                logger.error(f"⚠️ NO NEW IMAGE - Using cached path: {session.original_avatar_path}")
                input_image_path = session.original_avatar_path
            elif session.avatar_path and os.path.exists(session.avatar_path):
                input_image_path = session.avatar_path

        if not input_image_path:
            return Response(
                {'status': 'error', 'message': 'No image available.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------------------
        # SMART AVATAR PROCESSING
        # Uses preprocess_for_avatar which:
        # - Detects if image is selfie or full-body
        # - Selfie: Generates full-body avatar with DALL-E 3 + Face Swap
        # - Full-body: Skips generation, uses original image directly
        # ---------------------------------------------------------
        try:
            temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp')
            os.makedirs(temp_dir, exist_ok=True)

            # Use unique temp path to avoid race conditions
            import time
            output_path = os.path.join(
                temp_dir, f"fullbody_temp_{int(time.time() * 1000)}.png"
            )

            # Extract measurement data for prompt enhancement
            measurements = {
                "gender": request.data.get('gender', 'Person'),
                "height": request.data.get('height', ''),
                "weight": request.data.get('weight', ''),
                "chest": request.data.get('chest', ''),
                "waist": request.data.get('waist', ''),
                "hips": request.data.get('hips', ''),
            }

            # ---------------------------------------------------------
            # UNIT CONVERSION (Imperial -> Metric)
            # User Input: "5'10" or "70" (inches), "150" (lbs)
            # AI Prompt expects: cm, kg
            # ---------------------------------------------------------
            
            # Helper to convert inches to cm
            def to_cm(val):
                if not val: return ''
                try:
                    # Handle 5'10" format
                    if "'" in str(val):
                        parts = str(val).split("'")
                        feet = float(parts[0])
                        inches = float(parts[1].replace('"', '')) if len(parts) > 1 and parts[1] else 0
                        total_inches = (feet * 12) + inches
                        return f"{int(total_inches * 2.54)}"
                    # Handle raw inches
                    return f"{int(float(val) * 2.54)}"
                except:
                    return val

            # Helper to convert lbs to kg
            def to_kg(val):
                if not val: return ''
                try:
                    return f"{int(float(val) * 0.453592)}"
                except:
                    return val

            # Check for explicitly provided units
            height_unit = request.data.get('height_unit', 'in') # Default to inches (US)
            weight_unit = request.data.get('weight_unit', 'lbs') # Default to lbs (US)

            # Convert Height
            if height_unit == 'in':
                measurements['height'] = to_cm(measurements['height'])
            
            # Convert Weight
            if weight_unit == 'lbs':
                measurements['weight'] = to_kg(measurements['weight'])
                
            # Convert other measurements based on height_unit (Primary Unit System)
            # If height is set to inches (default), assume chest/waist/hips are also inches
            if height_unit == 'in':
                for key in ['chest', 'waist', 'hips']:
                    if measurements[key]:
                        measurements[key] = to_cm(measurements[key])
            
            # Calculate Body Shape / BMI
            body_shape_desc = ""
            try:
                # Need weight in kg and height in cm to calculate BMI
                if measurements.get('weight') and measurements.get('height'):
                    w_kg = float(measurements['weight'])
                    h_cm = float(measurements['height'])
                    if h_cm > 0:
                        h_m = h_cm / 100.0
                        bmi = w_kg / (h_m * h_m)
                        print(f"📊 Calculated BMI: {bmi:.1f}")
                        
                        if bmi < 18.5:
                            body_shape_desc = "slim, slender, thin physique"
                        elif 18.5 <= bmi < 25:
                            body_shape_desc = "average, healthy, fit build"
                        elif 25 <= bmi < 30:
                            body_shape_desc = "chubby, stocky, fuller figure, thick build"
                        elif 30 <= bmi < 40:
                            body_shape_desc = "plus size, heavy-set, overweight, large body"
                        else: # bmi >= 40
                            body_shape_desc = "extremely plus size, highly overweight, giant body frame, very heavy-set"
            except Exception as e:
                print(f"⚠️ Error calculating BMI: {e}")

            # Construct description
            description_parts = [measurements['gender']]
            if measurements['height']: description_parts.append(f"Height: {measurements['height']}cm")
            if measurements['weight']: description_parts.append(f"Weight: {measurements['weight']}kg")
            if body_shape_desc: description_parts.append(f"Body Type: {body_shape_desc}")
            
            body_details = []
            if measurements['chest']: body_details.append(f"Chest {measurements['chest']}cm")
            if measurements['waist']: body_details.append(f"Waist {measurements['waist']}cm")
            if measurements['hips']: body_details.append(f"Hips {measurements['hips']}cm")
            
            if body_details:
                description_parts.append(f"Measurements: {', '.join(body_details)}")
                
            user_description = ", ".join(description_parts)
            print(f"📋 User Description for Avatar: {user_description}")

            # Use smart preprocessing
            reference_order = []
            for key in ['front', 'side', 'back', 'face']:
                path_value = reference_map.get(key)
                if path_value and (path_value.startswith('http') or os.path.exists(path_value)):
                    reference_order.append(path_value)
            if not reference_order:
                reference_order = [input_image_path]

            output_path, is_full_body = preprocess_for_avatar(
                input_image_path=input_image_path,
                output_path=output_path,
                full_body=True,
                include_shoes=True,
                user_description=user_description,
                reference_images=reference_order,
                face_image_path=reference_map.get('face')
            )

            with open(output_path, 'rb') as f:
                final_image_data = f.read()

            if session.avatar_path and os.path.exists(session.avatar_path):
                try:
                    os.remove(session.avatar_path)
                except Exception:
                    pass

            saved_path = self.save_image_locally(
                final_image_data,
                session_id,
                suffix="fullbody" if not is_full_body else "original_fullbody"
            )

            session.avatar_path = saved_path
            session.is_full_body = is_full_body  # Track image type for virtual try-on routing
            session.latest_tryon_path = None  # Reset tryon compounding state for new avatar
            session.save()

            relative_path = os.path.relpath(saved_path, settings.MEDIA_ROOT)
            avatar_url = get_media_url() + relative_path.replace("\\", "/")

            response_data = {
                "status": "success",
                "session_id": str(session_id),
                "avatar_url": avatar_url,
                "saved_path": saved_path,
                "is_full_body": is_full_body,  # Inform client about image type
                "image_source": "original" if is_full_body else "generated",
                "tryon_model": "Nano Banana Pro"  # Using Nano Banana Pro API for virtual try-on
            }

            if include_base64:
                response_data["image_base64"] = base64.b64encode(
                    final_image_data
                ).decode("utf-8")

            try:
                os.remove(output_path)
            except Exception:
                pass

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"💥 Avatar Generation Failed: {str(e)}")
            logger.error(error_trace)
            return Response(
                {
                    "status": "error",
                    "message": str(e),
                    "trace": error_trace if settings.DEBUG else None
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )








            
