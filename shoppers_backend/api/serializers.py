from rest_framework import serializers
from .models import NordstromFilter, NordstromProduct, AmazonProduct
from .models import AvatarSession

class AmazonProductSerializer(serializers.ModelSerializer):
    product_id = serializers.CharField(source='asin', read_only=True)
    
    class Meta:
        model = AmazonProduct
        fields = '__all__'

class AvatarSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AvatarSession
        fields = ['session_id', 'avatar_path', 'prompt_used', 'created_at', 'updated_at']
        read_only_fields = ['session_id', 'created_at', 'updated_at']


class NordstromFilterSerializer(serializers.ModelSerializer):
    """Serializer for NordstromFilter model."""
    
    class Meta:
        model = NordstromFilter
        fields = '__all__'
        read_only_fields = ('extracted_at', 'updated_at')


class NordstromProductSerializer(serializers.ModelSerializer):
    """Lightweight frontend serializer with key product fields."""

    class Meta:
        model = NordstromProduct
        fields = [
            'product_id',
            'title',
            'brand',
            'price',
            'original_price',
            'currency',
            'image_url',
            'url',
            'category',
            'colors',
            'sizes',
            'in_stock',
            'rating',
            'review_count'
        ]