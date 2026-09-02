# utils.py
import os
import uuid
import base64
import hashlib
from io import BytesIO
from PIL import Image
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.cache import cache


def get_client_ip(request):
    """Extract client IP from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def optimize_image(image_data, max_size=(1024, 1024), quality=85):
    """
    Optimize image for storage.
    Returns optimized image bytes and dimensions.
    """
    img = Image.open(BytesIO(image_data))
    
    # Convert to RGB if necessary
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    
    # Resize if larger than max_size
    img.thumbnail(max_size, Image.LANCZOS)
    
    # Save optimized
    output = BytesIO()
    img.save(output, format='PNG', optimize=True, quality=quality)
    output.seek(0)
    
    return output.getvalue(), img.width, img.height


def get_image_base64_cached(avatar_id, image_path):
    """
    Get base64 encoded image with caching.
    """
    cache_key = f"avatar_b64_{avatar_id}"
    cached = cache.get(cache_key)
    
    if cached:
        return cached
    
    if os.path.exists(image_path):
        with open(image_path, 'rb') as f:
            image_data = f.read()
            b64_data = base64.b64encode(image_data).decode('utf-8')
            cache.set(cache_key, b64_data, timeout=3600)  # Cache for 1 hour
            return b64_data
    
    return None


def clear_avatar_cache(avatar_id):
    """Clear cached data for an avatar."""
    cache.delete(f"avatar_b64_{avatar_id}")


def generate_file_hash(file_data):
    """Generate MD5 hash for file deduplication."""
    return hashlib.md5(file_data).hexdigest()