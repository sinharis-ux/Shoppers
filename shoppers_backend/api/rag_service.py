"""
RAG (Retrieval-Augmented Generation) service for optimized product retrieval.
Uses OpenAI embeddings for semantic search and GPT for answer generation.
"""
import os
import json
import numpy as np
from typing import List, Dict, Any, Optional
from openai import OpenAI
from django.conf import settings
from .models import NordstromProduct


class RAGProductRetrieval:
    """RAG service for semantic product search and retrieval."""
    
    def __init__(self):
        """Initialize RAG service with OpenAI client."""
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        
        self.client = OpenAI(api_key=api_key)
        self.embedding_model = "text-embedding-3-small"  # Fast and cost-effective
        self.gpt_model = "gpt-4o-mini"  # Fast and affordable for RAG
        
    def create_product_embedding(self, product: NordstromProduct) -> List[float]:
        """
        Create embedding vector for a product.
        
        Args:
            product: NordstromProduct instance
            
        Returns:
            List of floats representing the embedding vector
        """
        # Create searchable text from product attributes
        searchable_text = self._create_searchable_text(product)
        
        # Get embedding from OpenAI
        response = self.client.embeddings.create(
            model=self.embedding_model,
            input=searchable_text
        )
        
        return response.data[0].embedding
    
    def _create_searchable_text(self, product: NordstromProduct) -> str:
        """Create searchable text representation of product."""
        parts = []
        
        if product.title:
            parts.append(product.title)
        if product.brand:
            parts.append(f"Brand: {product.brand}")
        if product.category:
            parts.append(f"Category: {product.category}")
        if product.description:
            parts.append(product.description[:500])  # Limit description length
        if product.colors:
            parts.append(f"Colors: {', '.join(product.colors[:5])}")
        if product.sizes:
            parts.append(f"Sizes: {', '.join(product.sizes[:5])}")
        
        return " | ".join(parts)
    
    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))
    
    def search_products_semantic(
        self, 
        query: str, 
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Semantic search for products using embeddings.
        
        Args:
            query: Search query text
            limit: Maximum number of results
            filters: Optional filters (brand, category, min_price, max_price, in_stock)
            
        Returns:
            List of product dictionaries with similarity scores
        """
        # Get query embedding
        query_embedding_response = self.client.embeddings.create(
            model=self.embedding_model,
            input=query
        )
        query_embedding = query_embedding_response.data[0].embedding
        
        # Get products with optional filters
        products_query = NordstromProduct.objects.all()
        
        if filters:
            if filters.get('brand'):
                products_query = products_query.filter(brand__icontains=filters['brand'])
            if filters.get('category'):
                products_query = products_query.filter(category__icontains=filters['category'])
            if filters.get('min_price'):
                products_query = products_query.filter(price__gte=float(filters['min_price']))
            if filters.get('max_price'):
                products_query = products_query.filter(price__lte=float(filters['max_price']))
            if filters.get('in_stock') is not None:
                products_query = products_query.filter(in_stock=filters['in_stock'])
        
        # Get all matching products
        products = list(products_query)
        
        if not products:
            return []
        
        # Calculate similarities
        product_scores = []
        for product in products:
            # Get or create embedding
            embedding = self._get_or_create_embedding(product)
            if embedding:
                similarity = self.cosine_similarity(query_embedding, embedding)
                product_scores.append({
                    'product': product,
                    'similarity': similarity
                })
        
        # Sort by similarity (highest first)
        product_scores.sort(key=lambda x: x['similarity'], reverse=True)
        
        # Return top results
        results = []
        for item in product_scores[:limit]:
            product = item['product']
            results.append({
                'product_id': product.product_id,
                'title': product.title,
                'brand': product.brand,
                'price': float(product.price) if product.price else None,
                'original_price': float(product.original_price) if product.original_price else None,
                'currency': product.currency,
                'url': product.url,
                'image_url': product.image_url,
                'category': product.category,
                'colors': product.colors,
                'sizes': product.sizes,
                'in_stock': product.in_stock,
                'rating': float(product.rating) if product.rating else None,
                'review_count': product.review_count,
                'similarity_score': item['similarity']
            })
        
        return results
    
    def _get_or_create_embedding(self, product: NordstromProduct) -> Optional[List[float]]:
        """Get embedding from cache or create new one."""
        # Check if embedding exists in additional_data
        if product.additional_data and 'embedding' in product.additional_data:
            return product.additional_data['embedding']
        
        # Create new embedding
        try:
            embedding = self.create_product_embedding(product)
            
            # Save embedding to product
            if not product.additional_data:
                product.additional_data = {}
            product.additional_data['embedding'] = embedding
            product.save(update_fields=['additional_data'])
            
            return embedding
        except Exception as e:
            print(f"Error creating embedding for product {product.product_id}: {str(e)}")
            return None
    
    def generate_answer_with_context(
        self,
        query: str,
        retrieved_products: List[Dict[str, Any]],
        max_products: int = 5
    ) -> Dict[str, Any]:
        """
        Generate an answer using RAG - Retrieval-Augmented Generation.
        
        Args:
            query: User query
            retrieved_products: List of retrieved products
            max_products: Maximum number of products to include in context
            
        Returns:
            Dictionary with answer and product recommendations
        """
        if not retrieved_products:
            return {
                'answer': "I couldn't find any products matching your query.",
                'products': [],
                'count': 0
            }
        
        # Limit products for context
        context_products = retrieved_products[:max_products]
        
        # Build context from retrieved products
        context = self._build_product_context(context_products)
        
        # Create prompt for GPT
        prompt = f"""You are a helpful shopping assistant for Nordstrom products. 
Answer the user's question based on the following products from our catalog.

User Query: {query}

Available Products:
{context}

Instructions:
1. Provide a natural, conversational answer to the user's query
2. Highlight relevant products that match their needs
3. Mention key features like price, brand, colors, or categories when relevant
4. If the user is looking for something specific, recommend the best matching products
5. Be concise and helpful

Answer:"""
        
        # Generate answer using GPT
        try:
            response = self.client.chat.completions.create(
                model=self.gpt_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a friendly and knowledgeable shopping assistant for Nordstrom. Help users find the best products based on their queries."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=500
            )
            
            answer = response.choices[0].message.content
            
            return {
                'answer': answer,
                'products': context_products,
                'count': len(context_products),
                'total_matches': len(retrieved_products)
            }
            
        except Exception as e:
            return {
                'answer': f"I found {len(retrieved_products)} products matching your query.",
                'products': context_products,
                'count': len(context_products),
                'error': str(e)
            }
    
    def _build_product_context(self, products: List[Dict[str, Any]]) -> str:
        """Build text context from products for GPT."""
        context_parts = []
        
        for i, product in enumerate(products, 1):
            parts = [f"Product {i}:"]
            parts.append(f"  Title: {product.get('title', 'N/A')}")
            
            if product.get('brand'):
                parts.append(f"  Brand: {product['brand']}")
            if product.get('price'):
                parts.append(f"  Price: ${product['price']:.2f}")
            if product.get('category'):
                parts.append(f"  Category: {product['category']}")
            if product.get('colors'):
                parts.append(f"  Available Colors: {', '.join(product['colors'][:3])}")
            
            context_parts.append("\n".join(parts))
        
        return "\n\n".join(context_parts)
    
    def rag_search(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        generate_answer: bool = True,
        max_context_products: int = 5
    ) -> Dict[str, Any]:
        """
        Complete RAG search: semantic retrieval + answer generation.
        
        Args:
            query: Search query
            limit: Maximum products to retrieve
            filters: Optional filters
            generate_answer: Whether to generate an answer using GPT
            max_context_products: Max products to use in answer context
            
        Returns:
            Complete RAG response with products and answer
        """
        # Step 1: Semantic search
        products = self.search_products_semantic(query, limit=limit, filters=filters)
        
        # Step 2: Generate answer if requested
        if generate_answer:
            result = self.generate_answer_with_context(
                query, 
                products, 
                max_products=max_context_products
            )
        else:
            result = {
                'answer': None,
                'products': products,
                'count': len(products)
            }
        
        return result







