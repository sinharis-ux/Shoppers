from django.db import models
from django.core.validators import MinValueValidator
import json
# models.py
import uuid
import os
from django.db import models


class AvatarSession(models.Model):
    session_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    avatar_path = models.CharField(max_length=500, null=True, blank=True)
    original_avatar_path = models.CharField(max_length=500, null=True, blank=True)
    latest_tryon_path = models.CharField(max_length=500, null=True, blank=True)
    prompt_used = models.TextField(null=True, blank=True)
    avatar_description = models.TextField(null=True, blank=True)
    original_prompt = models.TextField(null=True, blank=True)
    is_full_body = models.BooleanField(default=False)  # True if original was full-body, False if selfie/generated
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'avatar_sessions'
        ordering = ['-created_at']

    def __str__(self):
        return f"Session {self.session_id}"

        
class NordstromFilter(models.Model):
    """
    Knowledge base for Nordstrom dashboard filters and information.
    Stores categories, brands, sizes, colors, and other filter options.
    """
    filter_type = models.CharField(max_length=100, db_index=True)  # e.g., 'category', 'brand', 'size', 'color'
    filter_name = models.CharField(max_length=255, db_index=True)  # The filter value
    filter_data = models.JSONField(default=dict)  # Additional metadata (count, sub-filters, etc.)
    url = models.URLField(max_length=500, blank=True, null=True)  # URL associated with filter
    parent_category = models.CharField(max_length=255, blank=True, null=True)  # For hierarchical filters
    extracted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'nordstrom_filters'
        unique_together = [['filter_type', 'filter_name']]
        indexes = [
            models.Index(fields=['filter_type', 'filter_name']),
            models.Index(fields=['extracted_at']),
        ]
    
    def __str__(self):
        return f"{self.filter_type}: {self.filter_name}"


class NordstromProduct(models.Model):
    """
    Knowledge base for Nordstrom products.
    Stores product information for fast retrieval and search.
    """
    product_id = models.CharField(max_length=255, unique=True, db_index=True)
    title = models.CharField(max_length=500, db_index=True)
    brand = models.CharField(max_length=255, db_index=True, blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    original_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    currency = models.CharField(max_length=10, default='USD')
    url = models.URLField(max_length=1000, blank=True, null=True)
    image_url = models.URLField(max_length=1000, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    category = models.CharField(max_length=255, db_index=True, blank=True, null=True)
    subcategory = models.CharField(max_length=255, blank=True, null=True)
    sizes = models.JSONField(default=list, blank=True)  # Available sizes
    colors = models.JSONField(default=list, blank=True)  # Available colors
    in_stock = models.BooleanField(default=True, db_index=True)
    rating = models.FloatField(blank=True, null=True, validators=[MinValueValidator(0.0)])
    review_count = models.IntegerField(default=0)
    additional_data = models.JSONField(default=dict, blank=True)  # Store any extra fields
    scraped_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'nordstrom_products'
        indexes = [
            models.Index(fields=['brand', 'category']),
            models.Index(fields=['price']),
            models.Index(fields=['scraped_at']),
            models.Index(fields=['in_stock', 'category']),
        ]
    
    def __str__(self):
        return f"{self.brand or 'Unknown'} - {self.title[:50]}"


class AmazonProduct(models.Model):
    """
    Stores Amazon product data fetched from RapidAPI (Real-Time Amazon Data).
    Data is refreshed every 2 hours via Celery Beat — old data is deleted and replaced.
    """
    CATEGORY_CHOICES = [
        ('Men', 'Men'),
        ('Women', 'Women'),
        ('Children', 'Children'),
    ]

    asin = models.CharField(max_length=50, unique=True, db_index=True)
    title = models.CharField(max_length=500)
    price = models.CharField(max_length=50, blank=True, null=True)
    original_price = models.CharField(max_length=50, blank=True, null=True)
    currency = models.CharField(max_length=10, default='USD')
    image_url = models.URLField(max_length=1000, blank=True, null=True)
    product_url = models.URLField(max_length=1000, blank=True, null=True)
    rating = models.FloatField(blank=True, null=True)
    review_count = models.IntegerField(default=0)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, db_index=True)
    is_prime = models.BooleanField(default=False)
    is_best_seller = models.BooleanField(default=False)
    is_amazon_choice = models.BooleanField(default=False)
    sales_volume = models.CharField(max_length=100, blank=True, null=True)
    delivery = models.CharField(max_length=255, blank=True, null=True)
    coupon_text = models.CharField(max_length=255, blank=True, null=True)
    minimum_offer_price = models.CharField(max_length=50, blank=True, null=True)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'amazon_products'
        ordering = ['-fetched_at']

    def __str__(self):
        return f"{self.category} - {self.title[:50]}"
