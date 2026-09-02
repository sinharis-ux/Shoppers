"""
Django management command to delete products without images from the knowledge base.

Usage:
    python manage.py clean_products_without_images
    python manage.py clean_products_without_images --dry-run  # Preview what will be deleted
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from api.models import NordstromProduct


class Command(BaseCommand):
    help = 'Delete all products from knowledge base that do not have an image URL'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview what will be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        """Main command handler."""
        dry_run = options.get('dry_run', False)
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*70))
        self.stdout.write(self.style.SUCCESS('🧹 CLEANING PRODUCTS WITHOUT IMAGES'))
        self.stdout.write(self.style.SUCCESS('='*70 + '\n'))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No changes will be made\n'))
        
        try:
            # Find products without images
            # Products where image_url is None or empty string
            products_without_images = NordstromProduct.objects.filter(
                image_url__isnull=True
            ) | NordstromProduct.objects.filter(
                image_url__exact=''
            )
            
            count = products_without_images.count()
            
            if count == 0:
                self.stdout.write(self.style.SUCCESS('✅ All products have images. Nothing to clean!'))
                return
            
            self.stdout.write(f'📦 Found {count} products without images')
            
            if dry_run:
                self.stdout.write('\n📋 Products that would be deleted:')
                self.stdout.write('='*70)
                for product in products_without_images[:20]:  # Show first 20
                    price_str = f"${product.price:.2f}" if product.price else "N/A"
                    self.stdout.write(f'  - {product.product_id}: {product.title[:60]}... ({price_str})')
                if count > 20:
                    self.stdout.write(f'  ... and {count - 20} more products')
                self.stdout.write('='*70)
                self.stdout.write(self.style.WARNING(f'\n⚠️  DRY RUN: Would delete {count} products'))
                self.stdout.write(self.style.WARNING('   Run without --dry-run to actually delete'))
            else:
                # Actually delete the products
                self.stdout.write('\n🗑️  Deleting products without images...')
                
                # Get product IDs for logging
                product_ids = list(products_without_images.values_list('product_id', flat=True))
                
                with transaction.atomic():
                    deleted_count, _ = products_without_images.delete()
                
                self.stdout.write(self.style.SUCCESS(f'   ✓ Deleted {deleted_count} products'))
                
                # Summary
                remaining_count = NordstromProduct.objects.count()
                self.stdout.write(self.style.SUCCESS(f'\n📊 SUMMARY'))
                self.stdout.write(self.style.SUCCESS('='*70))
                self.stdout.write(self.style.SUCCESS(f'🗑️  Products Deleted: {deleted_count}'))
                self.stdout.write(self.style.SUCCESS(f'📦 Remaining Products: {remaining_count}'))
                self.stdout.write(self.style.SUCCESS('='*70 + '\n'))
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n✗ Fatal error: {str(e)}'))
            import traceback
            self.stdout.write(traceback.format_exc())
            raise







