"""
Nano Banana Pro API Service

A wrapper around the Nano Banana Pro API (Gemini 3 Pro Image) for:
- Avatar generation (text-to-image)
- Virtual try-on (image-to-image editing)
"""
import os
import time
import base64
import requests
import tempfile
from pathlib import Path
from typing import Optional, List, Union
from PIL import Image
from io import BytesIO

from django.conf import settings


class NanoBananaClient:
    """
    Client for Nano Banana Pro API (Gemini 3 Pro Image wrapper).
    
    Documentation: https://docs.nanobananaapi.ai
    """
    
    BASE_URL = "https://api.nanobananaapi.ai/api/v1/nanobanana"
    
    # Task status codes
    STATUS_GENERATING = 0
    STATUS_SUCCESS = 1
    STATUS_CREATE_FAILED = 2
    STATUS_GENERATE_FAILED = 3
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize the client with API key."""
        self.api_key = api_key or getattr(settings, 'NANO_BANANA_PRO_API_KEY', None) or os.getenv('NANO_BANANA_PRO_API_KEY')
        
        if not self.api_key:
            raise ValueError("NANO_BANANA_PRO_API_KEY is required. Set it in environment or Django settings.")
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make HTTP request to Nano Banana API."""
        url = f"{self.BASE_URL}/{endpoint}"
        
        if 'headers' not in kwargs:
            kwargs['headers'] = self.headers
        
        # Add a default timeout of 120 seconds for API requests to avoid hanging
        kwargs.setdefault('timeout', 120)
        
        response = requests.request(method, url, **kwargs)
        result = response.json()
        
        if response.status_code != 200 or result.get('code') != 200:
            error_msg = result.get('msg', 'Unknown error')
            raise Exception(f"Nano Banana API error: {error_msg}")
        
        return result
    
    def generate_image(
        self,
        prompt: str,
        image_size: str = "1:1",
        num_images: int = 1,
        callback_url: Optional[str] = None
    ) -> str:
        """
        Generate image from text prompt.
        
        Args:
            prompt: Text description of desired image
            image_size: Aspect ratio (1:1, 9:16, 16:9, 3:4, 4:3, etc.)
            num_images: Number of images (1-4)
            callback_url: Optional webhook for completion notification
            
        Returns:
            task_id: Task ID for polling
        """
        payload = {
            "prompt": prompt,
            "type": "TEXTTOIAMGE",  # Note: API uses this spelling
            "numImages": num_images,
            "image_size": image_size,
        }
        
        if callback_url:
            payload["callBackUrl"] = callback_url
        else:
            # API requires callback URL, use placeholder if not provided
            payload["callBackUrl"] = "https://example.com/callback"
        
        result = self._make_request("POST", "generate", json=payload)
        return result["data"]["taskId"]
    
    def edit_image(
        self,
        prompt: str,
        image_urls: List[str],
        image_size: str = "1:1",
        num_images: int = 1,
        callback_url: Optional[str] = None
    ) -> str:
        """
        Edit/combine images based on prompt.
        
        Args:
            prompt: Instructions for image editing
            image_urls: List of input image URLs (up to 10-14 images)
            image_size: Output aspect ratio
            num_images: Number of output images (1-4)
            callback_url: Optional webhook for completion notification
            
        Returns:
            task_id: Task ID for polling
        """
        payload = {
            "prompt": prompt,
            "type": "IMAGETOIAMGE",  # Note: API uses this spelling
            "imageUrls": image_urls,
            "numImages": num_images,
            "image_size": image_size,
        }
        
        if callback_url:
            payload["callBackUrl"] = callback_url
        else:
            payload["callBackUrl"] = "https://example.com/callback"
        
        result = self._make_request("POST", "generate", json=payload)
        return result["data"]["taskId"]
    
    def get_task_status(self, task_id: str) -> dict:
        """
        Get task status and result.
        
        Returns:
            dict with:
                - successFlag: 0=generating, 1=success, 2=create_failed, 3=generate_failed
                - response.resultImageUrl: Result image URL (when successFlag=1)
                - errorMessage: Error details (when failed)
        """
        result = self._make_request("GET", f"record-info?taskId={task_id}")
        return result.get("data", result)
    
    def poll_for_result(
        self,
        task_id: str,
        timeout: int = 90,
        poll_interval: float = 1.0
    ) -> str:
        """
        Poll until task completes and return result image URL.
        
        Args:
            task_id: Task ID from generate/edit call
            timeout: Maximum wait time in seconds
            poll_interval: Time between polls in seconds
            
        Returns:
            Result image URL
            
        Raises:
            TimeoutError: If task doesn't complete in time
            Exception: If task fails
        """
        start_time = time.time()
        
        while (time.time() - start_time) < timeout:
            status = self.get_task_status(task_id)
            success_flag = status.get("successFlag")
            
            if success_flag == self.STATUS_SUCCESS:
                response = status.get("response", {})
                
                # DEBUG: Print full response to diagnose try-on issues
                print(f"\n🔍 DEBUG - Full task status response:")
                print(f"   Response keys: {response.keys() if response else 'None'}")
                print(f"   resultImageUrl: {response.get('resultImageUrl', 'NOT FOUND')}")
                print(f"   originImageUrl: {response.get('originImageUrl', 'NOT FOUND')}")
                
                # Check all possible keys for the generated image URL
                result_url = (
                    response.get("resultImageUrl") or 
                    response.get("outputImageUrl") or 
                    response.get("generatedImageUrl") or
                    response.get("url")
                )
                
                if not result_url:
                    result_urls = response.get("resultImageUrls") or response.get("images") or response.get("outputImageUrls") or []
                    if result_urls and len(result_urls) > 0:
                        result_url = result_urls[0] if isinstance(result_urls[0], str) else result_urls[0].get("url")
                        print(f"   Using first URL from array: {result_url}")
                
                origin_url = response.get("originImageUrl")
                
                # Ensure we got a valid result URL and it's not just returning the input origin image
                if result_url and result_url != origin_url:
                    print(f"✓ Task {task_id} completed successfully!")
                    print(f"   ✓ Using result URL: {result_url[:80]}...")
                    return result_url
                else:
                    raise Exception(
                        f"Nano Banana API completed task {task_id} but did not generate a new image "
                        f"(resultImageUrl is missing or identical to input image). Full response: {response}"
                    )
                    
            elif success_flag == self.STATUS_CREATE_FAILED:
                raise Exception(f"Task creation failed: {status.get('errorMessage', 'Unknown error')}")
                
            elif success_flag == self.STATUS_GENERATE_FAILED:
                raise Exception(f"Image generation failed: {status.get('errorMessage', 'Unknown error')}")
                
            elif success_flag == self.STATUS_GENERATING:
                print(f"  → Task {task_id} is generating... ({int(time.time() - start_time)}s)")
                time.sleep(poll_interval)
            else:
                print(f"  → Unknown status {success_flag}, waiting...")
                time.sleep(poll_interval)
        
        raise TimeoutError(f"Task {task_id} did not complete within {timeout} seconds")
    
    def download_image(self, url: str, save_path: str) -> str:
        """
        Download image from URL and save to local path.
        
        Args:
            url: Image URL to download
            save_path: Local path to save image
            
        Returns:
            Path to saved image
        """
        # Increased timeout to 120 to avoid 1-minute timeout errors
        response = requests.get(url, timeout=120)
        response.raise_for_status()
        
        # Ensure directory exists
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(save_path, 'wb') as f:
            f.write(response.content)
        
        print(f"✓ Downloaded image to: {save_path}")
        return save_path
    
    def generate_and_download(
        self,
        prompt: str,
        save_path: str,
        image_size: str = "1:1",
        timeout: int = 120
    ) -> str:
        """
        Convenience method: Generate image and download result.
        
        Args:
            prompt: Text prompt for image generation
            save_path: Path to save the result
            image_size: Aspect ratio
            timeout: Max wait time in seconds
            
        Returns:
            Path to saved image
        """
        print(f"\n🎨 Generating image with Nano Banana Pro...")
        print(f"   Prompt: {prompt[:100]}...")
        
        task_id = self.generate_image(prompt, image_size=image_size)
        print(f"   Task ID: {task_id}")
        
        result_url = self.poll_for_result(task_id, timeout=timeout)
        return self.download_image(result_url, save_path)
    
    def edit_and_download(
        self,
        prompt: str,
        image_urls: List[str],
        save_path: str,
        image_size: str = "1:1",
        timeout: int = 120
    ) -> str:
        """
        Convenience method: Edit images and download result.
        
        Args:
            prompt: Instructions for editing
            image_urls: Input image URLs
            save_path: Path to save the result
            image_size: Output aspect ratio
            timeout: Max wait time in seconds
            
        Returns:
            Path to saved image
        """
        print(f"\n🎨 Editing images with Nano Banana Pro...")
        print(f"   Prompt: {prompt[:100]}...")
        print(f"   Input images: {len(image_urls)}")
        for i, url in enumerate(image_urls):
            print(f"   Image {i+1} URL: {url[:70]}...")
        print(f"   Output aspect ratio: {image_size}")
        
        task_id = self.edit_image(prompt, image_urls, image_size=image_size)
        print(f"   Task ID: {task_id}")
        
        result_url = self.poll_for_result(task_id, timeout=timeout)
        print(f"   📥 Downloading result from: {result_url[:70]}...")
        return self.download_image(result_url, save_path)


def upload_to_imgbb(image_path: str) -> str:
    """
    Upload image to imgbb and return the public URL.
    
    imgbb provides free image hosting with direct URLs that work
    with external APIs like Nano Banana Pro.
    
    Args:
        image_path: Local path to the image
        
    Returns:
        Public URL to the uploaded image
    """
    api_key = getattr(settings, 'IMGBB_API_KEY', None) or os.getenv('IMGBB_API_KEY')
    
    if not api_key:
        raise ValueError("IMGBB_API_KEY is required for image hosting. Get a free key at https://api.imgbb.com/")
    
    print(f"   📤 Uploading to imgbb: {Path(image_path).name}")
    
    # Read and encode image
    with open(image_path, 'rb') as f:
        image_data = base64.b64encode(f.read()).decode('utf-8')
    
    # Upload to imgbb
    response = requests.post(
        "https://api.imgbb.com/1/upload",
        data={
            "key": api_key,
            "image": image_data,
            "expiration": 600,  # 10 minutes expiration
        },
        timeout=120
    )
    
    result = response.json()
    
    if not result.get('success'):
        error = result.get('error', {}).get('message', 'Unknown error')
        raise Exception(f"imgbb upload failed: {error}")
    
    image_url = result['data']['url']
    print(f"   ✓ Uploaded: {image_url}")
    return image_url


def get_public_url_for_image(image_path: str) -> str:
    """
    Get a publicly accessible URL for an image by uploading to imgbb.
    
    Args:
        image_path: Local path to the image
        
    Returns:
        Public URL for the image
    """
    # Check if already a URL
    if image_path.startswith('http://') or image_path.startswith('https://'):
        return image_path
    
    # Upload to imgbb for a reliable public URL
    return upload_to_imgbb(image_path)


def upload_image_to_temp_storage(image_path: str) -> str:
    """
    Upload image to temporary storage and return URL.
    Uses imgbb for reliable hosting.
    
    Args:
        image_path: Local path to image
        
    Returns:
        Public URL to the image
    """
    return upload_to_imgbb(image_path)


# Create a default client instance for convenience
def get_client() -> NanoBananaClient:
    """Get or create default NanoBanana client."""
    return NanoBananaClient()
