from django.contrib import admin
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
from django import forms
import csv
import io
import re
from decimal import Decimal
from .models import NordstromFilter, NordstromProduct, AmazonProduct, AvatarSession


class CsvImportForm(forms.Form):
    """Form for CSV file upload."""
    csv_file = forms.FileField(label='CSV File')


@admin.register(NordstromFilter)
class NordstromFilterAdmin(admin.ModelAdmin):
    list_display = ('filter_type', 'filter_name', 'parent_category', 'extracted_at', 'updated_at')
    list_filter = ('filter_type', 'extracted_at')
    search_fields = ('filter_name', 'filter_type')
    readonly_fields = ('extracted_at', 'updated_at')


@admin.register(NordstromProduct)
class NordstromProductAdmin(admin.ModelAdmin):
    list_display = ('title', 'brand', 'category', 'price', 'in_stock', 'scraped_at')
    list_filter = ('brand', 'category', 'in_stock', 'scraped_at')
    search_fields = ('title', 'brand', 'category', 'product_id')
    readonly_fields = ('scraped_at', 'updated_at')
    ordering = ('-scraped_at',)
    change_list_template = "admin/api/nordstromproduct_changelist.html"

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path('import-csv/', self.import_csv, name='api_nordstromproduct_import_csv'),
        ]
        return my_urls + urls

    def import_csv(self, request):
        """Handle CSV import for Nordstrom products."""
        if request.method == "POST":
            csv_file = request.FILES.get("csv_file")
            
            if not csv_file:
                messages.error(request, "Please upload a CSV file.")
                return redirect("..")
            
            if not csv_file.name.endswith('.csv'):
                messages.error(request, "File must be a CSV file.")
                return redirect("..")
            
            try:
                # Read and decode the CSV file
                decoded_file = csv_file.read().decode('utf-8')
                io_string = io.StringIO(decoded_file)
                reader = csv.reader(io_string)
                
                # Skip header row
                next(reader, None)
                
                created_count = 0
                skipped_count = 0
                error_count = 0
                
                for row in reader:
                    try:
                        # Skip empty rows
                        if not row or not any(row):
                            continue
                        
                        # Parse data from CSV columns
                        # Column 0: image_url (P9JC8 src)
                        image_url = row[0].strip() if len(row) > 0 and row[0] else None
                        
                        # Column 1: url (AFBJb href)
                        url = row[1].strip() if len(row) > 1 and row[1] else None
                        
                        # Column 2: title (dls-ogz194)
                        title = row[2].strip() if len(row) > 2 and row[2] else "Unknown Product"
                        
                        # Column 3: brand (dls-ogz194 (2))
                        brand = row[3].strip() if len(row) > 3 and row[3] else None
                        
                        # Column 4: price (qHz0a) - current price
                        price = self._parse_price(row[4]) if len(row) > 4 and row[4] else None
                        
                        # Column 5: Current price display text (He8hw) - skip
                        
                        # Column 6: original_price (fj69a) - previous price
                        original_price = self._parse_price(row[6]) if len(row) > 6 and row[6] else None
                        
                        # Column 7: Previous price display text (He8hw (2)) - skip
                        
                        # Column 8: Review URL (Cz9X9 href) - extract product_id
                        review_url = row[8].strip() if len(row) > 8 and row[8] else None
                        
                        # Column 9: rating (M8Loy)
                        rating = self._parse_rating(row[9]) if len(row) > 9 and row[9] else None
                        
                        # Column 10: review_count (Z22Hw)
                        review_count = self._parse_review_count(row[10]) if len(row) > 10 and row[10] else 0
                        
                        # Column 11: special_note (Bo6XV) - "Only a few left" etc.
                        special_note = row[11].strip() if len(row) > 11 and row[11] else None
                        
                        # Column 12: is_sponsored (Yw5es)
                        is_sponsored = row[12].strip() if len(row) > 12 and row[12] else None
                        
                        # Column 13: extra (dg0ca)
                        extra = row[13].strip() if len(row) > 13 and row[13] else None
                        
                        # Extract product_id from URL
                        product_id = self._extract_product_id(url or review_url)
                        if not product_id:
                            # Generate a unique ID if extraction fails
                            import hashlib
                            product_id = hashlib.md5(f"{title}{brand}{url}".encode()).hexdigest()[:16]
                        
                        # Build additional_data
                        additional_data = {}
                        if special_note:
                            additional_data['special_note'] = special_note
                        if is_sponsored:
                            additional_data['is_sponsored'] = True
                        if extra:
                            additional_data['extra'] = extra
                        
                        # Check if product already exists
                        if NordstromProduct.objects.filter(product_id=product_id).exists():
                            skipped_count += 1
                            continue

                        # Create the product
                        NordstromProduct.objects.create(
                            product_id=product_id,
                            title=title,
                            brand=brand,
                            price=price,
                            original_price=original_price,
                            currency='INR',  # Based on ₹ symbol in CSV
                            url=url,
                            image_url=image_url,
                            rating=rating,
                            review_count=review_count,
                            additional_data=additional_data,
                            in_stock=True,
                        )
                        created_count += 1
                            
                    except Exception as e:
                        error_count += 1
                        print(f"Error processing row: {row}. Error: {str(e)}")
                
                messages.success(
                    request, 
                    f"CSV imported successfully! Created: {created_count}, Skipped (Duplicate): {skipped_count}, Errors: {error_count}"
                )
                
            except Exception as e:
                messages.error(request, f"Error processing CSV file: {str(e)}")
            
            return redirect("..")
        
        form = CsvImportForm()
        context = {
            "form": form,
            "opts": self.model._meta,
            "title": "Import Nordstrom Products from CSV",
        }
        return render(request, "admin/csv_form.html", context)
    
    def _parse_price(self, price_str):
        """Parse price string to Decimal, handling currency symbols and ranges."""
        if not price_str:
            return None
        
        try:
            # Remove currency symbols and whitespace
            cleaned = price_str.strip()
            # Remove ₹ symbol
            cleaned = cleaned.replace('₹', '').strip()
            
            # Handle price ranges (e.g., "6,569.82 – 10,949.69")
            if '–' in cleaned or '-' in cleaned:
                # Take the first (lower) price
                parts = re.split(r'[–-]', cleaned)
                cleaned = parts[0].strip()
            
            # Remove commas from numbers
            cleaned = cleaned.replace(',', '')
            
            # Parse to Decimal
            return Decimal(cleaned)
        except Exception:
            return None
    
    def _parse_rating(self, rating_str):
        """Parse rating string to float."""
        if not rating_str:
            return None
        
        try:
            return float(rating_str.strip())
        except Exception:
            return None
    
    def _parse_review_count(self, review_str):
        """Parse review count string to integer, removing parentheses."""
        if not review_str:
            return 0
        
        try:
            # Remove parentheses: "(389)" -> "389"
            cleaned = re.sub(r'[()]', '', review_str.strip())
            return int(cleaned)
        except Exception:
            return 0
    
    def _extract_product_id(self, url):
        """Extract product ID from Nordstrom URL."""
        if not url:
            return None
        
        try:
            # Pattern: /s/product-name/7838886 or /s/7838886
            match = re.search(r'/s/(?:[^/]+/)?(\d+)', url)
            if match:
                return match.group(1)
            return None
        except Exception:
            return None



@admin.register(AmazonProduct)
class AmazonProductAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'price', 'original_price', 'is_prime', 'is_best_seller', 'sales_volume', 'fetched_at')
    list_filter = ('category', 'is_prime', 'is_best_seller', 'is_amazon_choice', 'fetched_at')
    search_fields = ('title', 'category', 'asin')
    readonly_fields = ('fetched_at',)
    ordering = ('-fetched_at',)

@admin.register(AvatarSession)
class AvatarSessionAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'created_at', 'updated_at', 'is_full_body')
    list_filter = ('is_full_body', 'created_at', 'updated_at')
    search_fields = ('session_id', 'avatar_path', 'original_avatar_path', 'latest_tryon_path')
    readonly_fields = ('session_id', 'created_at', 'updated_at')
    ordering = ('-created_at',)