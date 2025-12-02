from django.core.management.base import BaseCommand, CommandError
from django.core.files import File
from django.db import transaction
from products.models import Category, Brand, Product, ProductImage
from decimal import Decimal
import json
import os
import re


class Command(BaseCommand):
    help = 'Import scraped Soundwave Audio products from JSON file'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default='soundwave_audio_cleaned.json',
            help='Path to JSON file (default: soundwave_audio_cleaned.json)'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing products before import'
        )

    def handle(self, *args, **options):
        json_file = options['file']
        clear_existing = options['clear']

        self.stdout.write(self.style.SUCCESS('\n' + '='*70))
        self.stdout.write(self.style.SUCCESS('🚀 SOUNDWAVE PRODUCTS IMPORT'))
        self.stdout.write(self.style.SUCCESS('='*70 + '\n'))

        # Check if file exists
        if not os.path.exists(json_file):
            raise CommandError(f'JSON file not found: {json_file}')

        # Load JSON data
        self.stdout.write('📂 Loading JSON data...')
        with open(json_file, 'r', encoding='utf-8') as f:
            products_data = json.load(f)

        self.stdout.write(self.style.SUCCESS(f'✅ Loaded {len(products_data)} products\n'))

        # Clear existing data if requested
        if clear_existing:
            self.stdout.write(self.style.WARNING('⚠️  Clearing existing products...'))
            Product.objects.all().delete()
            Category.objects.all().delete()
            Brand.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('✅ Cleared existing data\n'))

        # Import products
        stats = {
            'categories': 0,
            'brands': 0,
            'products': 0,
            'images': 0,
            'errors': 0
        }

        self.stdout.write('📦 Importing products...\n')
        
        for idx, product_data in enumerate(products_data, 1):
            try:
                with transaction.atomic():
                    result = self._import_product(product_data, idx, len(products_data))
                    
                    # Update stats
                    if result['category_created']:
                        stats['categories'] += 1
                    if result['brand_created']:
                        stats['brands'] += 1
                    if result['product_created']:
                        stats['products'] += 1
                    stats['images'] += result['images_count']

            except Exception as e:
                stats['errors'] += 1
                self.stdout.write(
                    self.style.ERROR(f'   ❌ Error importing product {idx}: {str(e)}')
                )

        # Print final report
        self._print_report(stats)

    def _import_product(self, data, index, total):
        """Import a single product with its relationships"""
        result = {
            'category_created': False,
            'brand_created': False,
            'product_created': False,
            'images_count': 0
        }

        # Progress indicator
        self.stdout.write(f'   [{index}/{total}] {data["name"][:50]}...')

        # Get or create Category
        category_name = data.get('category', 'Car Audio').strip()
        category, created = Category.objects.get_or_create(
            name=category_name,
            defaults={'description': f'Products in {category_name}'}
        )
        result['category_created'] = created

        # Get or create Brand
        brand_name = data.get('brand', 'Others').strip()
        brand, created = Brand.objects.get_or_create(
            name=brand_name,
            defaults={'description': f'{brand_name} products'}
        )
        result['brand_created'] = created

        # Extract price
        price = self._extract_price(data.get('price', 'kes 0'))

        # Create or update Product
        product, created = Product.objects.update_or_create(
            sku=data.get('sku', f'PROD-{index:04d}'),
            defaults={
                'name': data.get('name', 'Unknown Product'),
                'description': data.get('full_description', data.get('short_description', '')),
                'category': category,
                'brand': brand,
                'price': price,
                'stock_quantity': 10,  # Default stock
                'specifications': self._parse_specifications(data),
                'meta_title': data.get('name', '')[:255],
                'meta_description': data.get('short_description', '')[:500],
            }
        )
        result['product_created'] = created

        # Handle main image only (as primary)
        if created:  # Only add images for new products
            main_image_path = data.get('downloaded_images', {}).get('main_image', '')
            if main_image_path and os.path.exists(f'products/{main_image_path}'):
                self._add_product_image(product, f'products/{main_image_path}', is_primary=True)
                result['images_count'] += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'      ✅ {"Created" if created else "Updated"} | '
                f'Images: {result["images_count"]}'
            )
        )

        return result

    def _extract_price(self, price_str):
        """Extract numeric price from string like 'kes 5000'"""
        try:
            # Extract numbers from string
            numbers = re.findall(r'\d+\.?\d*', str(price_str))
            if numbers:
                return Decimal(numbers[0])
            return Decimal('0.00')
        except:
            return Decimal('0.00')

    def _parse_specifications(self, data):
        """Parse specifications from various fields"""
        specs = data.get('specifications', {})
        
        # Add features to specifications if available
        features = data.get('features', [])
        if features:
            specs['key_features'] = features[:5]  # Limit to 5 features
        
        return specs

    def _add_product_image(self, product, image_path, is_primary=False):
        """Add image to product"""
        try:
            with open(image_path, 'rb') as img_file:
                # Get filename from path
                filename = os.path.basename(image_path)
                
                # Create ProductImage
                product_image = ProductImage(
                    product=product,
                    alt_text=product.name,
                    is_primary=is_primary,
                    order=0 if is_primary else 1
                )
                product_image.image.save(filename, File(img_file), save=True)
                
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f'      ⚠️  Image error: {str(e)}')
            )

    def _print_report(self, stats):
        """Print final import report"""
        self.stdout.write('\n' + '='*70)
        self.stdout.write(self.style.SUCCESS('📊 IMPORT REPORT'))
        self.stdout.write('='*70 + '\n')
        
        self.stdout.write(f"✅ Categories created: {stats['categories']}")
        self.stdout.write(f"✅ Brands created: {stats['brands']}")
        self.stdout.write(f"✅ Products imported: {stats['products']}")
        self.stdout.write(f"✅ Images added: {stats['images']}")
        
        if stats['errors'] > 0:
            self.stdout.write(
                self.style.WARNING(f"⚠️  Errors encountered: {stats['errors']}")
            )
        
        self.stdout.write('\n' + '='*70)
        self.stdout.write(self.style.SUCCESS('✅ IMPORT COMPLETED'))
        self.stdout.write('='*70 + '\n')
        
        # Print next steps
        self.stdout.write('\n📝 Next Steps:')
        self.stdout.write('   1. Run: python manage.py shell')
        self.stdout.write('   2. Verify: Product.objects.count()')
        self.stdout.write('   3. Check admin: http://localhost:8000/admin')
        self.stdout.write('   4. Test API: http://localhost:8000/api/products/\n')