from django.urls import path
from .views import (
    # GenerateAvatarView,
    # CreateSessionView,
    # GenerateAvatarView,
    # GetSessionAvatarsView,
    # GetAvatarDetailView,
    # DeleteAvatarView,
    # ToggleFavoriteView,
    CreateSessionView,
    GetSessionView, 
    ListProductsAPI, 
    ApplyProductDallE2EditAPI,
    VirtualTryOnView,
    GenerateAvatarAPI,
    FetchAmazonDataAPI,
    AmazonProductListAPI,
    AmazonSearchProxyAPI
)
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('generate-avatar/', GenerateAvatarAPI.as_view(), name='generate_avatar'),
    # path('extract-filters/', ExtractFiltersView.as_view(), name='extract_filters'),
    path('session/create/', CreateSessionView.as_view(), name='create-session'),
    path('session/<uuid:session_id>/', GetSessionView.as_view(), name='get-session'),
    path('products/', ListProductsAPI.as_view(), name='list-products'),
    path('amazon/fetch/', FetchAmazonDataAPI.as_view(), name='amazon-fetch'),
    path('amazon/products/', AmazonProductListAPI.as_view(), name='amazon-list'),
    path('amazon/search-proxy/', AmazonSearchProxyAPI.as_view(), name='amazon-search-proxy'),
    path('apply-product-to-avatar/', ApplyProductDallE2EditAPI.as_view(), name='apply-product-to-avatar'),
    path('virtual-tryon/', VirtualTryOnView.as_view(), name='virtual-tryon'),
    # path('apply-3d-effects/', Apply3DEffectsView.as_view(), name='apply-3d-effects'),
    # Session
    # path('session/create/', CreateSessionView.as_view(), name='create-session'),
        
    # Avatar retrieval
    # path('session/<str:session_id>/avatars/', GetSessionAvatarsView.as_view(), name='session-avatars'),
    # path('session/<str:session_id>/avatar/<int:avatar_id>/', GetAvatarDetailView.as_view(), name='avatar-detail'),
    
    # Avatar actions
    # path('session/<str:session_id>/avatar/<int:avatar_id>/delete/', DeleteAvatarView.as_view(), name='delete-avatar'),
    # path('session/<str:session_id>/avatar/<int:avatar_id>/favorite/', ToggleFavoriteView.as_view(), name='toggle-favorite'),
]
# Add media files serving in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)