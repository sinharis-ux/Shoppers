"""
Django management command to import products from Nordstrom Excel file.
This script reads the Excel file and saves products to the knowledge base.

Usage:
    python manage.py import_from_excel --file nordstrom_dresses.xlsx
    python manage.py import_from_excel --file nordstrom_dresses.xlsx --dry-run  # Preview without saving
"""
import os
import re
import uuid
import pandas as pd
from urllib.parse import urlparse, parse_qs
from django.core.management.base import BaseCommand
from django.db import transaction
from api.models import NordstromProduct


class Command(BaseCommand):
    help = 'Import products from Nordstrom Excel file to knowledge base'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            required=True,
            help='Path to Excel file',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview what will be imported without actually saving',
        )

    def extract_product_id(self, url):
        """Extract product ID from Nordstrom URL."""
        if not url or pd.isna(url):
            return None
        
        try:
            # Try to extract from URL path like /s/product-name/7737947
            match = re.search(r'/(\d{7,})', str(url))
            if match:
                return match.group(1)
            
            # Try query parameter
            parsed = urlparse(str(url))
            query_params = parse_qs(parsed.query)
            if 'productid' in query_params:
                return query_params['productid'][0]
            
            # Fallback: use hash of URL
            return str(hash(str(url)))[:20]
        except:
            return None

    def parse_price(self, price_str):
        """Parse price string to decimal. Handles ranges like '₹ 6,048.61 – ₹ 11,840.06'."""
        if not price_str or pd.isna(price_str):
            return None
        
        try:
            price_str = str(price_str).strip()
            
            # Handle price ranges - take the minimum price
            if '–' in price_str or '-' in price_str:
                # Split by range indicator
                parts = re.split(r'[–-]', price_str)
                price_str = parts[0].strip() if parts else price_str
            
            # Remove currency symbols and extract number
            # Remove ₹, $, commas, and other non-numeric except decimal point
            price_clean = re.sub(r'[^\d.]', '', price_str)
            if price_clean:
                return float(price_clean)
        except:
            pass
        return None

    def parse_rating(self, rating_str):
        """Parse rating string to float."""
        if not rating_str or pd.isna(rating_str):
            return None
        
        try:
            rating_str = str(rating_str).strip()
            # Extract number from "Rated 4.3 out of 5 stars."
            match = re.search(r'(\d+\.?\d*)', rating_str)
            if match:
                rating = float(match.group(1))
                # If rating > 5, it might be out of 10, so divide
                if rating > 5:
                    rating = rating / 2
                return rating
        except:
            pass
        return None

    def parse_review_count(self, review_count):
        """Parse review count to integer."""
        if pd.isna(review_count):
            return 0
        
        try:
            # If it's already a number
            if isinstance(review_count, (int, float)):
                return int(review_count)
            
            # If it's a string, extract number
            review_str = str(review_count).strip()
            match = re.search(r'(\d+)', review_str)
            if match:
                return int(match.group(1))
        except:
            pass
        return 0

    def parse_colors(self, colors_str):
        """Parse colors string to list."""
        if not colors_str or pd.isna(colors_str):
            return []
        
        try:
            colors_str = str(colors_str).strip()
            if not colors_str or colors_str == 'N/A':
                return []
            
            # Split by comma and clean
            colors = [c.strip() for c in colors_str.split(',') if c.strip()]
            return colors
        except:
            return []

    def parse_images(self, images_str):
        """Parse images string (pipe-separated) to list."""
        if not images_str or pd.isna(images_str):
            return []
        
        try:
            images_str = str(images_str).strip()
            if not images_str or images_str == 'N/A':
                return []
            
            # Split by pipe and clean
            images = [img.strip() for img in images_str.split('|') if img.strip()]
            return images
        except:
            return []

    def extract_category(self, url):
        """Extract category from Nordstrom URL."""
        if not url or pd.isna(url):
            return None
        
        try:
            url_str = str(url)
            # Extract from /browse/women/clothing/dresses
            match = re.search(r'/browse/([^/?]+)', url_str)
            if match:
                parts = match.group(1).split('/')
                if len(parts) >= 2:
                    return f"{parts[0]}/{parts[1]}"
                return parts[0]
            
            # Try to extract from breadcrumb
            if 'breadcrumb' in url_str:
                match = re.search(r'breadcrumb=([^&]+)', url_str)
                if match:
                    breadcrumb = match.group(1)
                    # Decode URL encoding
                    from urllib.parse import unquote
                    breadcrumb = unquote(breadcrumb)
                    parts = breadcrumb.split('/')
                    if len(parts) >= 2:
                        return f"{parts[0]}/{parts[1]}"
        except:
            pass
        return None

    def handle(self, *args, **options):
        """Main command handler."""
        file_path = options.get('file')
        dry_run = options.get('dry_run', False)
        
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'✗ Error: File not found: {file_path}'))
            return
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*70))
        self.stdout.write(self.style.SUCCESS('📦 IMPORTING PRODUCTS FROM EXCEL'))
        self.stdout.write(self.style.SUCCESS('='*70 + '\n'))
        self.stdout.write(f'📁 File: {file_path}\n')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No changes will be made\n'))
        
        try:
            # Read Excel file
            self.stdout.write('📖 Reading Excel file...')
            df = pd.read_excel(file_path)
            self.stdout.write(self.style.SUCCESS(f'   ✓ Found {len(df)} products in file\n'))
            
            if len(df) == 0:
                self.stdout.write(self.style.WARNING('⚠️  No products found in file'))
                return
            
            # Process products
            saved = 0
            updated = 0
            errors = []
            
            self.stdout.write('💾 Processing products...')
            self.stdout.write('='*70)
            
            with transaction.atomic():
                for idx, row in df.iterrows():
                    try:
                        # Extract product ID from URL
                        product_id = self.extract_product_id(row.get('url'))
                        if not product_id:
                            product_id = str(uuid.uuid4())
                            self.stdout.write(self.style.WARNING(f'   ⚠ Row {idx+1}: Could not extract product ID, using UUID'))
                        
                        # Parse prices
                        current_price = self.parse_price(row.get('current_price'))
                        original_price = self.parse_price(row.get('original_price'))
                        
                        # Parse rating
                        rating = self.parse_rating(row.get('rating'))
                        
                        # Parse review count
                        review_count = self.parse_review_count(row.get('review_count'))
                        
                        # Parse colors
                        colors = self.parse_colors(row.get('all_colors'))
                        
                        # Parse images
                        images = self.parse_images(row.get('images'))
                        image_url = images[0] if images else None
                        
                        # Extract category
                        category = self.extract_category(row.get('url'))
                        
                        # Prepare additional data
                        additional_data = {
                            'current_color': str(row.get('current_color', 'N/A')) if not pd.isna(row.get('current_color')) else 'N/A',
                            'colors_available': str(row.get('colors_available', 'N/A')) if not pd.isna(row.get('colors_available')) else 'N/A',
                            'fit_feedback': str(row.get('fit_feedback', 'N/A')) if not pd.isna(row.get('fit_feedback')) else 'N/A',
                            'size_guide': str(row.get('size_guide', 'N/A')) if not pd.isna(row.get('size_guide')) else 'N/A',
                            'people_viewing': str(row.get('people_viewing', 'N/A')) if not pd.isna(row.get('people_viewing')) else 'N/A',
                            'sold_by': str(row.get('sold_by', 'N/A')) if not pd.isna(row.get('sold_by')) else 'N/A',
                            'returns_info': str(row.get('returns_info', 'N/A')) if not pd.isna(row.get('returns_info')) else 'N/A',
                            'discount': str(row.get('discount', 'N/A')) if not pd.isna(row.get('discount')) else 'N/A',
                            'all_images': images
                        }
                        
                        # Get title and brand
                        title = str(row.get('title', 'N/A'))[:500] if not pd.isna(row.get('title')) else 'N/A'
                        brand = None
                        brand_str = row.get('brand')
                        if not pd.isna(brand_str) and str(brand_str).strip() != 'N/A':
                            brand = str(brand_str).strip()[:255]
                        
                        # Get URL
                        url = str(row.get('url', ''))[:1000] if not pd.isna(row.get('url')) else None
                        
                        # Determine currency (check if price contains ₹ or $)
                        currency = 'USD'
                        price_str = str(row.get('current_price', ''))
                        if '₹' in price_str:
                            currency = 'INR'
                        
                        if not dry_run:
                            # Create or update product
                            product, created = NordstromProduct.objects.update_or_create(
                                product_id=product_id,
                                defaults={
                                    'title': title,
                                    'brand': brand,
                                    'price': current_price,
                                    'original_price': original_price,
                                    'currency': currency,
                                    'url': url,
                                    'image_url': str(image_url)[:1000] if image_url else None,
                                    'description': None,
                                    'category': category,
                                    'subcategory': None,
                                    'sizes': [],
                                    'colors': colors,
                                    'in_stock': True,
                                    'rating': rating,
                                    'review_count': review_count,
                                    'additional_data': additional_data
                                }
                            )
                            
                            if created:
                                saved += 1
                                self.stdout.write(self.style.SUCCESS(f'   ✓ [{idx+1}/{len(df)}] Saved: {title[:50]}'))
                            else:
                                updated += 1
                                self.stdout.write(self.style.WARNING(f'   ↻ [{idx+1}/{len(df)}] Updated: {title[:50]}'))
                        else:
                            # Dry run - just preview
                            action = "Would save" if not NordstromProduct.objects.filter(product_id=product_id).exists() else "Would update"
                            self.stdout.write(f'   🔍 [{idx+1}/{len(df)}] {action}: {title[:50]}')
                            saved += 1  # Count as would-be saved for preview
                        
                    except Exception as e:
                        error_msg = f"Row {idx+1}: {str(e)}"
                        errors.append(error_msg)
                        self.stdout.write(self.style.ERROR(f'   ✗ [{idx+1}/{len(df)}] Error: {error_msg}'))
            
            # Summary
            self.stdout.write('\n' + '='*70)
            if dry_run:
                self.stdout.write(self.style.SUCCESS(f'✅ DRY RUN COMPLETE'))
                self.stdout.write(f'   Would import: {saved} products')
            else:
                self.stdout.write(self.style.SUCCESS(f'✅ IMPORT COMPLETE'))
                self.stdout.write(f'   Products saved: {saved}')
                self.stdout.write(f'   Products updated: {updated}')
            
            if errors:
                self.stdout.write(self.style.ERROR(f'   Errors: {len(errors)}'))
                for error in errors[:5]:  # Show first 5 errors
                    self.stdout.write(self.style.ERROR(f'     - {error}'))
                if len(errors) > 5:
                    self.stdout.write(self.style.ERROR(f'     ... and {len(errors) - 5} more errors'))
            
            self.stdout.write('='*70 + '\n')
            
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            self.stdout.write(self.style.ERROR(f'\n❌ ERROR:\n{error_trace}\n'))
            return

