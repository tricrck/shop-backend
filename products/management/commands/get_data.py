import requests
from bs4 import BeautifulSoup
import json
import pandas as pd
import time
from urllib.parse import urljoin, urlparse
import re
import os
from collections import defaultdict

URL = "https://soundwaveaudio.co.ke/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/117.0.0.0 Safari/537.36"
}

# ==============================================================================
# DATA CLEANING FUNCTIONS - Integrated into scraper
# ==============================================================================

def clean_sku(sku, product_name, index):
    """Generate valid SKU if missing or invalid"""
    if not sku or sku in ["N/A", "BRAND:", "", "BRAND"]:
        # Generate SKU from product name
        clean_name = re.sub(r'[^a-zA-Z0-9\s]', '', product_name)
        words = clean_name.split()[:3]
        base_sku = ''.join(word[:3].upper() for word in words if word)
        if not base_sku:
            base_sku = "PROD"
        return f"{base_sku}-{index:04d}"

    # Clean up problematic SKUs like "BRAND:"
    if sku.endswith(':'):
        sku = sku.rstrip(':')
        if not sku or sku == "BRAND":
            clean_name = re.sub(r'[^a-zA-Z0-9\s]', '', product_name)
            words = clean_name.split()[:3]
            base_sku = ''.join(word[:3].upper() for word in words if word)
            return f"{base_sku}-{index:04d}" if base_sku else f"PROD-{index:04d}"

    return sku

def clean_price(price_str):
    """Extract numeric price from string"""
    if not price_str or price_str == "N/A":
        return "kes 0"

    # Extract numbers
    numbers = re.findall(r'\d+\.?\d*', str(price_str))
    if numbers:
        return f"kes {numbers[0]}"
    return "kes 0"

def clean_brand(brand):
    """Fix brand field"""
    if not brand or brand == "N/A" or brand == "BRAND:" or brand == "BRAND":
        return "Others"
    return brand.strip()

def clean_category(category):
    """Ensure valid category"""
    if not category or category == "N/A":
        return "Car Audio"
    return category.strip()

def sanitize_folder_name(name):
    """Create safe folder name from text"""
    # Remove special characters, keep only alphanumeric, dash, underscore
    safe_name = re.sub(r'[^\w\s-]', '', name)
    # Replace whitespace with underscore
    safe_name = re.sub(r'\s+', '-', safe_name)
    # Remove multiple consecutive dashes
    safe_name = re.sub(r'-+', '-', safe_name)
    # Trim and limit length
    safe_name = safe_name.strip('-')[:50]
    return safe_name if safe_name else "product"

# ==============================================================================
# FOLDER AND IMAGE MANAGEMENT
# ==============================================================================

def create_products_folder():
    """Create products folder if it doesn't exist"""
    products_folder = "products"
    if not os.path.exists(products_folder):
        os.makedirs(products_folder)
        print(f"✅ Created '{products_folder}' directory")
    return products_folder

def get_product_folder_name(sku, product_name):
    """Get consistent folder name using cleaned SKU"""
    if sku and sku != "N/A":
        # Use sanitized SKU
        return sanitize_folder_name(sku)
    else:
        # Fallback to sanitized product name
        return sanitize_folder_name(product_name)

def download_image(image_url, folder_path, filename):
    """Download and save an image from URL"""
    try:
        if not image_url or image_url == "N/A":
            return None

        # Make sure URL is absolute
        if image_url.startswith('//'):
            image_url = 'https:' + image_url
        elif image_url.startswith('/'):
            image_url = urljoin(URL, image_url)

        # Get image extension from URL or content type
        parsed_url = urlparse(image_url)
        path = parsed_url.path
        if '.' in path:
            extension = path.split('.')[-1].lower()
            # Clean up extension (remove query parameters if any)
            extension = extension.split('?')[0]
            if extension not in ['jpg', 'jpeg', 'png', 'webp', 'gif']:
                extension = 'jpg'  # default extension
        else:
            extension = 'jpg'

        # Create safe filename
        safe_filename = re.sub(r'[^\w\-_.]', '_', filename)
        full_filename = f"{safe_filename}.{extension}"
        filepath = os.path.join(folder_path, full_filename)

        # Skip if already downloaded
        if os.path.exists(filepath):
            print(f"   📁 Image already exists: {full_filename}")
            return full_filename

        # Download image
        response = requests.get(image_url, headers=headers, timeout=30)
        response.raise_for_status()

        # Save image
        with open(filepath, 'wb') as f:
            f.write(response.content)

        print(f"   ✅ Downloaded: {full_filename}")
        return full_filename

    except Exception as e:
        print(f"   ❌ Error downloading {image_url}: {e}")
        return None

def download_product_images(product_data, products_folder, cleaned_sku):
    """Download all images for a product using cleaned SKU"""
    downloaded_images = {
        'main_image': '',
        'thumbnail': '',
        'additional_images': []
    }

    # Use cleaned SKU for folder name
    product_folder_name = get_product_folder_name(cleaned_sku, product_data['name'])
    product_folder = os.path.join(products_folder, product_folder_name)

    if not os.path.exists(product_folder):
        os.makedirs(product_folder)
        print(f"   📂 Created folder: {product_folder_name}/")

    # Download main image
    main_image_url = product_data.get('main_image')
    if main_image_url and main_image_url != "N/A":
        main_filename = download_image(
            main_image_url,
            product_folder,
            "main_image"
        )
        if main_filename:
            downloaded_images['main_image'] = f"{product_folder_name}/{main_filename}"

    # Download thumbnail image from homepage (if different from main)
    thumbnail_url = product_data.get('image_url')
    if thumbnail_url and thumbnail_url != "N/A" and thumbnail_url != main_image_url:
        thumbnail_filename = download_image(
            thumbnail_url,
            product_folder,
            "thumbnail"
        )
        if thumbnail_filename:
            downloaded_images['thumbnail'] = f"{product_folder_name}/{thumbnail_filename}"

    # Download additional images
    additional_urls = product_data.get('additional_images', [])

    for i, img_url in enumerate(additional_urls):
        if img_url and img_url != "N/A":
            additional_filename = download_image(
                img_url,
                product_folder,
                f"additional_{i+1}"
            )
            if additional_filename:
                downloaded_images['additional_images'].append(
                    f"{product_folder_name}/{additional_filename}"
                )

    return downloaded_images

# ==============================================================================
# WEB SCRAPING FUNCTIONS
# ==============================================================================

def scrape_product_details(product_url):
    """Scrape detailed information from individual product pages"""
    try:
        print(f"   🔍 Scraping details...")
        resp = requests.get(product_url, headers=headers, timeout=30)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.content, "html.parser")

        product_details = {}

        # Extract product name
        name_elem = soup.select_one("h1.product-name")
        product_details['name'] = name_elem.get_text(strip=True) if name_elem else "N/A"

        # Extract SKU and Brand
        meta_elem = soup.select_one("div.product-meta")
        if meta_elem:
            meta_text = meta_elem.get_text()
            sku_match = re.search(r"SKU:\s*([^\s]+)", meta_text)
            brand_match = re.search(r"BRAND:\s*([^\n]+)", meta_text)
            product_details['sku'] = sku_match.group(1) if sku_match else "N/A"
            product_details['brand'] = brand_match.group(1).strip() if brand_match else "N/A"
        else:
            product_details['sku'] = "N/A"
            product_details['brand'] = "N/A"

        # Extract price
        price_elem = soup.select_one("div.product-price")
        product_details['price'] = price_elem.get_text(strip=True) if price_elem else "N/A"

        # Extract rating
        rating_elem = soup.select_one("div.ratings-full span.ratings")
        if rating_elem:
            rating_style = rating_elem.get('style', '')
            rating_match = re.search(r'width:(\d+)%', rating_style)
            product_details['rating_percentage'] = rating_match.group(1) + '%' if rating_match else "80%"
        else:
            product_details['rating_percentage'] = "80%"

        # Extract review count
        review_elem = soup.select_one("a.rating-reviews")
        if review_elem:
            review_text = review_elem.get_text(strip=True)
            review_match = re.search(r'\((\d+)\s+reviews\)', review_text)
            product_details['review_count'] = review_match.group(1) if review_match else "0"
        else:
            product_details['review_count'] = "0"

        # Extract short description
        short_desc_elem = soup.select_one("p.product-short-desc")
        product_details['short_description'] = short_desc_elem.get_text(strip=True) if short_desc_elem else "N/A"

        # Extract full description from tabs
        desc_tab = soup.select_one("#product-tab-description")
        if desc_tab:
            description_text = desc_tab.get_text(strip=True)
            description_text = re.sub(r'\s+', ' ', description_text)
            product_details['full_description'] = description_text
        else:
            product_details['full_description'] = "N/A"

        # Extract features/key points from description
        features = []
        if desc_tab:
            feature_items = desc_tab.find_all('li')
            for item in feature_items:
                feature_text = item.get_text(strip=True)
                if feature_text:
                    features.append(feature_text)

            strong_elems = desc_tab.find_all('strong')
            for elem in strong_elems:
                feature_text = elem.get_text(strip=True)
                if feature_text and len(feature_text) > 10:
                    features.append(feature_text)

        product_details['features'] = features if features else []

        # Extract main product image
        main_img_elem = soup.select_one("div.product-single-carousel img")
        product_details['main_image'] = main_img_elem.get('src') if main_img_elem else "N/A"

        # Extract additional images
        additional_imgs = soup.select("div.product-single-carousel img")
        product_details['additional_images'] = [
            img.get('src') for img in additional_imgs
            if img.get('src') and img.get('src') != product_details['main_image']
        ]

        # Extract shipping information
        shipping_tab = soup.select_one("#product-tab-shipping-returns")
        product_details['shipping_info'] = shipping_tab.get_text(strip=True) if shipping_tab else "N/A"

        # Extract product specifications
        additional_tab = soup.select_one("#product-tab-additional")
        if additional_tab:
            specs_table = additional_tab.find('table')
            if specs_table:
                specs = {}
                rows = specs_table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['th', 'td'])
                    if len(cells) >= 2:
                        key = cells[0].get_text(strip=True)
                        value = cells[1].get_text(strip=True)
                        if key and value:
                            specs[key] = value
                product_details['specifications'] = specs
            else:
                product_details['specifications'] = {}
        else:
            product_details['specifications'] = {}

        # Extract WhatsApp order link
        whatsapp_elem = soup.select_one('a[href*="wa.me"]')
        product_details['whatsapp_order_link'] = whatsapp_elem.get('href') if whatsapp_elem else "N/A"

        # Extract phone order link
        phone_elem = soup.select_one('a[href*="tel:"]')
        product_details['phone_order_link'] = phone_elem.get('href') if phone_elem else "N/A"

        print(f"   ✅ Scraped: {product_details['name']}")
        return product_details

    except Exception as e:
        print(f"   ❌ Error scraping details: {e}")
        return {}

# ==============================================================================
# MAIN SCRAPING FUNCTION WITH AUTO-CLEANING
# ==============================================================================

def scrape_soundwave_audio():
    """Main function to scrape all products with auto-cleaning"""
    try:
        # Create products folder
        products_folder = create_products_folder()

        resp = requests.get(URL, headers=headers)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.content, "html.parser")
        products_data = []
        used_skus = defaultdict(int)

        # Find all product grid items from homepage
        products = soup.select("div.product.text-center")

        print(f"\n🎯 Found {len(products)} products on homepage\n")
        print("="*70)

        for i, product in enumerate(products, 1):
            try:
                print(f"\n📦 Processing {i}/{len(products)}")

                # Extract basic info from homepage
                name_elem = product.select_one("h3.product-name a")
                name = name_elem.get_text(strip=True) if name_elem else "N/A"
                product_url = name_elem.get("href") if name_elem else "N/A"

                # Skip if no product URL
                if product_url == "N/A":
                    print(f"   ⚠️  Skipping: No URL found")
                    continue

                # Make sure URL is absolute
                if product_url.startswith('/'):
                    product_url = urljoin(URL, product_url)

                print(f"   📌 {name[:60]}")

                # Extract basic info from homepage
                price_elem = product.select_one("span.product-price")
                price = price_elem.get_text(strip=True) if price_elem else "N/A"

                cat_elem = product.select_one("div.product-cat a")
                category = cat_elem.get_text(strip=True) if cat_elem else "N/A"

                img_elem = product.select_one("img")
                image_url = img_elem.get("src") if img_elem else "N/A"

                # Scrape detailed information from product page
                detailed_info = scrape_product_details(product_url)

                # Combine basic and detailed information
                raw_product_data = {
                    "name": name,
                    "price": price,
                    "category": category,
                    "url": product_url,
                    "image_url": image_url,
                    **detailed_info
                }

                # ===== AUTO-CLEAN DATA =====
                print(f"   🧹 Cleaning data...")

                # Clean SKU
                original_sku = raw_product_data.get('sku', '')
                cleaned_sku = clean_sku(original_sku, name, i)

                # Ensure SKU uniqueness
                if cleaned_sku in used_skus:
                    used_skus[cleaned_sku] += 1
                    cleaned_sku = f"{cleaned_sku}-{used_skus[cleaned_sku]}"
                else:
                    used_skus[cleaned_sku] = 0

                if original_sku != cleaned_sku:
                    print(f"   🔧 Fixed SKU: '{original_sku}' → '{cleaned_sku}'")

                # Clean other fields
                cleaned_product_data = {
                    "name": name,
                    "price": clean_price(raw_product_data.get('price')),
                    "category": clean_category(raw_product_data.get('category')),
                    "url": product_url,
                    "image_url": image_url,
                    "sku": cleaned_sku,
                    "brand": clean_brand(raw_product_data.get('brand')),
                    "rating_percentage": raw_product_data.get('rating_percentage', '80%'),
                    "review_count": raw_product_data.get('review_count', '0'),
                    "short_description": raw_product_data.get('short_description', ''),
                    "full_description": raw_product_data.get('full_description', ''),
                    "features": raw_product_data.get('features', []),
                    "main_image": raw_product_data.get('main_image', ''),
                    "additional_images": raw_product_data.get('additional_images', []),
                    "shipping_info": raw_product_data.get('shipping_info', ''),
                    "specifications": raw_product_data.get('specifications', {}),
                    "whatsapp_order_link": raw_product_data.get('whatsapp_order_link', ''),
                    "phone_order_link": raw_product_data.get('phone_order_link', '')
                }

                # Ensure descriptions aren't empty
                if not cleaned_product_data['short_description'] or cleaned_product_data['short_description'] == "N/A":
                    cleaned_product_data['short_description'] = f"{name} from Soundwave Audio"

                if not cleaned_product_data['full_description'] or cleaned_product_data['full_description'] == "N/A":
                    cleaned_product_data['full_description'] = cleaned_product_data['short_description']

                # Download images with cleaned SKU
                print(f"   📸 Downloading images...")
                downloaded_images = download_product_images(
                    cleaned_product_data,
                    products_folder,
                    cleaned_sku
                )
                cleaned_product_data['downloaded_images'] = downloaded_images

                products_data.append(cleaned_product_data)

                print(f"   ✅ Completed: {len(downloaded_images)} image types downloaded")
                print("   " + "-"*60)

                # Add delay to be respectful to the server
                time.sleep(2)

            except Exception as e:
                print(f"   ❌ Error processing product {i}: {e}")
                continue

        return products_data

    except requests.RequestException as e:
        print(f"❌ Error fetching the website: {e}")
        return []

# ==============================================================================
# DATA SAVING AND REPORTING
# ==============================================================================

def save_data(products_data):
    """Save the scraped and cleaned data"""
    if not products_data:
        print("❌ No data to save")
        return

    # Save to JSON (primary format)
    json_file = "soundwave_audio_cleaned.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(products_data, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Cleaned JSON saved: {json_file}")

    # Save to CSV
    df = pd.DataFrame(products_data)

    # Handle complex columns for CSV
    for col in ['features', 'additional_images']:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: json.dumps(x) if isinstance(x, list) else str(x))

    for col in ['specifications', 'downloaded_images']:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: json.dumps(x) if isinstance(x, dict) else str(x))

    csv_file = "soundwave_audio_cleaned.csv"
    df.to_csv(csv_file, index=False, encoding='utf-8')
    print(f"✅ Cleaned CSV saved: {csv_file}")

    # Generate detailed report
    generate_scraping_report(products_data)

def generate_scraping_report(products_data):
    """Generate a detailed scraping report"""
    print("\n" + "="*70)
    print("📊 SCRAPING REPORT")
    print("="*70)

    # Statistics
    total_products = len(products_data)
    total_images = 0
    products_with_specs = 0
    products_with_features = 0

    categories = defaultdict(int)
    brands = defaultdict(int)

    for product in products_data:
        # Count images
        img_data = product.get('downloaded_images', {})
        if img_data.get('main_image'):
            total_images += 1
        if img_data.get('thumbnail'):
            total_images += 1
        total_images += len(img_data.get('additional_images', []))

        # Count products with specs/features
        if product.get('specifications') and product['specifications']:
            products_with_specs += 1
        if product.get('features') and len(product['features']) > 0:
            products_with_features += 1

        # Category and brand statistics
        categories[product.get('category', 'Unknown')] += 1
        brands[product.get('brand', 'Unknown')] += 1

    print(f"\n📦 Products")
    print(f"   Total products scraped: {total_products}")
    print(f"   Products with specifications: {products_with_specs}")
    print(f"   Products with features: {products_with_features}")

    print(f"\n🖼️  Images")
    print(f"   Total images downloaded: {total_images}")
    print(f"   Average images per product: {total_images/total_products:.1f}")

    print(f"\n📂 Categories ({len(categories)})")
    for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"   {cat}: {count} products")

    print(f"\n🏷️  Brands ({len(brands)})")
    for brand, count in sorted(brands.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"   {brand}: {count} products")

    print(f"\n📁 File Structure")
    print(f"   products/")
    print(f"   ├── [product_sku]/")
    print(f"   │   ├── main_image.jpg")
    print(f"   │   ├── thumbnail.jpg")
    print(f"   │   └── additional_*.jpg")
    print(f"   ├── soundwave_audio_cleaned.json")
    print(f"   └── soundwave_audio_cleaned.csv")

    print("\n" + "="*70)

# ==============================================================================
# MAIN EXECUTION
# ==============================================================================

def main():
    print("\n" + "="*70)
    print("🚀 GOD-LEVEL SOUNDWAVE AUDIO SCRAPER")
    print("   With Auto-Cleaning & Image Management")
    print("="*70)

    # Scrape and clean data
    products = scrape_soundwave_audio()

    if not products:
        print("\n❌ No products scraped. Exiting.")
        return

    print(f"\n✅ Successfully scraped {len(products)} products")

    # Display sample results
    print("\n" + "="*70)
    print("📋 SAMPLE PRODUCTS")
    print("="*70)

    for i, product in enumerate(products[:3], 1):
        print(f"\n{i}. {product.get('name', 'N/A')[:60]}")
        print(f"   SKU: {product.get('sku', 'N/A')}")
        print(f"   Brand: {product.get('brand', 'N/A')}")
        print(f"   Price: {product.get('price', 'N/A')}")
        print(f"   Category: {product.get('category', 'N/A')}")

        img_data = product.get('downloaded_images', {})
        img_count = sum([
            1 if img_data.get('main_image') else 0,
            1 if img_data.get('thumbnail') else 0,
            len(img_data.get('additional_images', []))
        ])
        print(f"   Images: {img_count} downloaded")
        print(f"   Features: {len(product.get('features', []))}")
        print(f"   Specs: {len(product.get('specifications', {}))}")

    # Save all data
    save_data(products)

    print("\n" + "="*70)
    print("✅ SCRAPING COMPLETED SUCCESSFULLY!")
    print("="*70)
    print("\n📝 Next Steps:")
    print("   1. Review: soundwave_audio_cleaned.json")
    print("   2. Verify: products/ folder structure")
    print("   3. Import: Use Django management command")
    print("\n" + "="*70)

if __name__ == "__main__":
    main()