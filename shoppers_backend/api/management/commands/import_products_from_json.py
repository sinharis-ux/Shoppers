"""
Django management command to import products from Nordstrom JSON response file.
This script parses the JSON response and saves products to the knowledge base.

Usage:
    python manage.py import_products_from_json --file /path/to/scraping_response.txt
"""
import os
import sys
import json
import re
from urllib.parse import urljoin
from django.core.management.base import BaseCommand
from django.db import transaction
from api.models import NordstromProduct


class Command(BaseCommand):
    help = 'Import products from Nordstrom JSON response file to knowledge base'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            required=True,
            help='Path to JSON response file',
        )

    def extract_price(self, price_data):
        """Extract numeric price from price data structure."""
        if not price_data:
            return None, None
        
        price = None
        original_price = None
        
        if isinstance(price_data, dict):
            # Handle Nordstrom price structure with units and nanos
            # Check for totalPriceRange first (sale price)
            total_price_range = price_data.get("totalPriceRange", {})
            if total_price_range:
                min_price = total_price_range.get("min", {})
                max_price = total_price_range.get("max", {})
                if min_price and isinstance(min_price, dict):
                    units = min_price.get("units", 0)
                    nanos = min_price.get("nanos", 0)
                    price = float(units) + (float(nanos) / 1000000000.0)
            
            # Check for regular price
            regular_price = price_data.get("regular", {})
            if regular_price:
                price_range = regular_price.get("priceRange", {})
                if price_range:
                    min_price = price_range.get("min", {})
                    max_price = price_range.get("max", {})
                    if min_price and isinstance(min_price, dict):
                        units = min_price.get("units", 0)
                        nanos = min_price.get("nanos", 0)
                        regular_price_value = float(units) + (float(nanos) / 1000000000.0)
                        if not price:  # If no sale price, use regular
                            price = regular_price_value
                        else:
                            original_price = regular_price_value
            
            # Check for compareAt (original price)
            compare_at = price_data.get("compareAt", {})
            if compare_at:
                price_range = compare_at.get("priceRange", {})
                if price_range:
                    min_price = price_range.get("min", {})
                    if min_price and isinstance(min_price, dict):
                        units = min_price.get("units", 0)
                        nanos = min_price.get("nanos", 0)
                        compare_price = float(units) + (float(nanos) / 1000000000.0)
                        if not original_price:
                            original_price = compare_price
            
            # Fallback to simpler price fields
            if not price:
                if "sale" in price_data:
                    price = float(price_data["sale"]) if price_data["sale"] else None
                elif "current" in price_data:
                    price = float(price_data["current"]) if price_data["current"] else None
                elif "price" in price_data:
                    price = float(price_data["price"]) if price_data["price"] else None
            
            # Fallback for original price
            if not original_price:
                if "original" in price_data:
                    original_price = float(price_data["original"]) if price_data["original"] else None
                elif "list" in price_data:
                    original_price = float(price_data["list"]) if price_data["list"] else None
                    
        elif isinstance(price_data, (int, float)):
            price = float(price_data)
        elif isinstance(price_data, str):
            # Extract numeric value from string
            match = re.search(r'[\d,]+\.?\d*', price_data.replace(',', ''))
            if match:
                price = float(match.group())
        
        # Only set original_price if it's different from price
        if original_price and original_price == price:
            original_price = None
        
        return price, original_price

    def extract_image_url(self, media_data, product_id):
        """Extract primary image URL from media data."""
        if not media_data:
            return None
        
        # Handle Nordstrom mediaById structure
        if isinstance(media_data, dict):
            # Look for images with group='main' first, then 'alt'
            media_by_id = media_data
            
            # Try to find main image
            for media_id, media_info in media_by_id.items():
                if isinstance(media_info, dict):
                    media_group = media_info.get("group", "")
                    if media_group == "main":
                        image_url = media_info.get("src") or media_info.get("url")
                        if image_url:
                            return image_url
            
            # Fallback to first image found
            for media_id, media_info in media_by_id.items():
                if isinstance(media_info, dict):
                    image_url = media_info.get("src") or media_info.get("url")
                    if image_url:
                        return image_url
        
        elif isinstance(media_data, list) and len(media_data) > 0:
            first_item = media_data[0]
            if isinstance(first_item, dict):
                return first_item.get("url") or first_item.get("src") or first_item.get("href")
            elif isinstance(first_item, str):
                return first_item
        
        elif isinstance(media_data, str):
            return media_data
        
        return None

    def extract_colors(self, colors_data):
        """Extract color information."""
        colors = []
        if not colors_data:
            return colors
        
        if isinstance(colors_data, dict):
            # colorsById structure
            for color_id, color_info in colors_data.items():
                if isinstance(color_info, dict):
                    label = color_info.get("label") or color_info.get("name")
                    if label:
                        colors.append(str(label))
                elif isinstance(color_info, str):
                    colors.append(color_info)
        elif isinstance(colors_data, list):
            for color_item in colors_data:
                if isinstance(color_item, dict):
                    label = color_item.get("label") or color_item.get("name") or color_item.get("color")
                    if label:
                        colors.append(str(label))
                elif isinstance(color_item, str):
                    colors.append(color_item)
        
        return colors

    def extract_sizes(self, sizes_data):
        """Extract size information."""
        sizes = []
        if not sizes_data:
            return sizes
        
        if isinstance(sizes_data, dict):
            # sizesById structure
            for size_id, size_info in sizes_data.items():
                if isinstance(size_info, dict):
                    label = size_info.get("label") or size_info.get("name") or size_info.get("size")
                    if label:
                        sizes.append(str(label))
                elif isinstance(size_info, str):
                    sizes.append(size_info)
        elif isinstance(sizes_data, list):
            for size_item in sizes_data:
                if isinstance(size_item, dict):
                    label = size_item.get("label") or size_item.get("name") or size_item.get("size")
                    if label:
                        sizes.append(str(label))
                elif isinstance(size_item, str):
                    sizes.append(size_item)
        
        return sizes

    def extract_product_url(self, product_data, product_id):
        """Extract product URL."""
        # Try various URL fields
        url = (
            product_data.get("url") or
            product_data.get("productUrl") or
            product_data.get("link") or
            product_data.get("href")
        )
        
        if url:
            if not url.startswith('http'):
                url = urljoin('https://www.nordstrom.com', url)
            return url
        
        # Construct URL from product ID if available
        if product_id:
            return f"https://www.nordstrom.com/p/{product_id}"
        
        return None

    def handle(self, *args, **options):
        """Main command handler."""
        file_path = options.get('file')
        
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'✗ Error: File not found: {file_path}'))
            return
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*70))
        self.stdout.write(self.style.SUCCESS('📦 IMPORTING PRODUCTS FROM JSON'))
        self.stdout.write(self.style.SUCCESS('='*70 + '\n'))
        self.stdout.write(f'📁 File: {file_path}\n')
        
        try:
            # Load JSON file
            self.stdout.write('📖 Reading JSON file...')
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Extract products
            products_by_id = data.get('productsById', {})
            self.stdout.write(self.style.SUCCESS(f'   ✓ Found {len(products_by_id)} products in file\n'))
            
            if not products_by_id:
                self.stdout.write(self.style.WARNING('⚠️  No products found in file'))
                return
            
            # Extract category from page data
            category = None
            page_data = data.get('pageData', {})
            if page_data:
                category = page_data.get('name') or page_data.get('h1Tag', '').replace("'s", "").split(":")[0].strip()
            
            # Process products
            saved = 0
            updated = 0
            errors = []
            
            self.stdout.write('💾 Saving products to knowledge base...')
            self.stdout.write('='*70)
            
            with transaction.atomic():
                for product_id, product_data in products_by_id.items():
                    try:
                        # Extract product ID
                        product_id_str = str(product_id) or str(product_data.get('id')) or str(product_data.get('styleNumber'))
                        if not product_id_str or product_id_str == 'None':
                            continue
                        
                        # Extract title
                        title = (
                            product_data.get('name') or
                            product_data.get('title') or
                            product_data.get('displayName') or
                            'Unknown Product'
                        )
                        
                        # Extract brand
                        brand = product_data.get('brandName') or product_data.get('brand')
                        
                        # Extract price
                        price_data = product_data.get('price', {})
                        price, original_price = self.extract_price(price_data)
                        
                        # Extract currency
                        currency = product_data.get('priceCurrencyCode', 'USD')
                        
                        # Extract URL
                        product_url = self.extract_product_url(product_data, product_id_str)
                        
                        # Extract image
                        media_data = product_data.get('mediaById', {})
                        image_url = self.extract_image_url(media_data, product_id_str)
                        
                        # Extract colors
                        colors_data = product_data.get('colorsById', {}) or product_data.get('colorIds', [])
                        colors = self.extract_colors(colors_data)
                        
                        # Extract sizes (may not be in this structure, but try)
                        sizes_data = product_data.get('sizesById', {}) or product_data.get('sizes', [])
                        sizes = self.extract_sizes(sizes_data)
                        
                        # Extract description
                        description = (
                            product_data.get('description') or
                            product_data.get('longDescription') or
                            product_data.get('extraNameCopy')
                        )
                        
                        # Extract rating and reviews if available
                        rating = product_data.get('rating') or product_data.get('averageRating')
                        review_count = product_data.get('reviewCount') or product_data.get('review_count', 0)
                        
                        # Check stock status
                        in_stock = not product_data.get('isSoldOut', False)
                        
                        # Create or update product
                        obj, created = NordstromProduct.objects.update_or_create(
                            product_id=product_id_str,
                            defaults={
                                'title': str(title)[:500],
                                'brand': str(brand)[:255] if brand else None,
                                'price': price,
                                'original_price': original_price,
                                'currency': currency,
                                'url': str(product_url)[:1000] if product_url else None,
                                'image_url': str(image_url)[:1000] if image_url else None,
                                'description': str(description)[:5000] if description else None,
                                'category': str(category)[:255] if category else None,
                                'colors': colors[:50],  # Limit to 50 colors
                                'sizes': sizes[:50],  # Limit to 50 sizes
                                'in_stock': in_stock,
                                'rating': float(rating) if rating else None,
                                'review_count': int(review_count) if review_count else 0,
                                'additional_data': product_data,  # Store full product data
                            }
                        )
                        
                        if created:
                            saved += 1
                            price_str = f"${obj.price:.2f}" if obj.price else "N/A"
                            self.stdout.write(f'    ✓ Saved: {obj.title[:55]}... ({price_str})')
                        else:
                            updated += 1
                    
                    except Exception as e:
                        error_msg = f"Error processing product {product_id}: {str(e)}"
                        errors.append(error_msg)
                        self.stdout.write(self.style.WARNING(f'    ⚠️  {error_msg}'))
                        continue
            
            # Summary
            self.stdout.write(self.style.SUCCESS(f'\n📊 SUMMARY'))
            self.stdout.write(self.style.SUCCESS('='*70))
            self.stdout.write(self.style.SUCCESS(f'✅ Products Saved: {saved}'))
            self.stdout.write(self.style.SUCCESS(f'🔄 Products Updated: {updated}'))
            self.stdout.write(self.style.SUCCESS(f'📦 Total Products in KB: {NordstromProduct.objects.count()}'))
            if errors:
                self.stdout.write(self.style.WARNING(f'⚠️  Errors: {len(errors)}'))
            self.stdout.write(self.style.SUCCESS('='*70 + '\n'))
            
        except json.JSONDecodeError as e:
            self.stdout.write(self.style.ERROR(f'✗ Error: Invalid JSON file - {str(e)}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Fatal error: {str(e)}'))
            import traceback
            self.stdout.write(traceback.format_exc())
            raise

