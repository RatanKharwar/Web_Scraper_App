from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import time
import json
import os

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, WebDriverException

app = Flask(__name__)
CORS(app)

def setup_chrome_driver():
    """Setup Chrome driver with optimal options"""
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-images")
    chrome_options.add_argument("--disable-javascript")  # For faster loading when not needed
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    
    # Fixed: Use Service class and separate options
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

def extract_data_from_elements(elements, attribute, method="beautifulsoup"):
    """Extract data from elements based on attribute and method"""
    results = []
    
    for el in elements:
        try:
            value = None
            
            if method == "selenium":
                if attribute.lower() == "text content":
                    value = el.text.strip()
                else:
                    # For Selenium, use get_attribute for HTML attributes
                    value = el.get_attribute(attribute.lower())
                    # If no attribute found, try getting the property
                    if not value:
                        value = el.get_property(attribute.lower())
            else:  # BeautifulSoup
                if attribute.lower() == "text content":
                    value = el.get_text(strip=True)
                else:
                    # For BeautifulSoup, get the attribute
                    value = el.get(attribute.lower())
                    # If attribute is 'class', it returns a list, so join it
                    if attribute.lower() == "class" and isinstance(value, list):
                        value = " ".join(value)
            
            # Add the value even if it's empty (but not None)
            if value is not None:
                # Convert to string and strip whitespace
                value_str = str(value).strip()
                results.append({
                    "value": value_str if value_str else f"[Empty {attribute}]",
                    "index": len(results) + 1
                })
                print(f"✅ Extracted {attribute}: '{value_str}'")
            else:
                # Add a placeholder for missing attributes
                results.append({
                    "value": f"[No {attribute} attribute]",
                    "index": len(results) + 1
                })
                print(f"⚠️ No {attribute} attribute found")
                
        except Exception as e:
            print(f"⚠️ Error extracting {attribute} from element: {str(e)}")
            results.append({
                "value": f"[Error extracting {attribute}]",
                "index": len(results) + 1
            })
            continue
    
    return results

@app.route('/')
def home():
    return render_template("index.html")

@app.route('/scrape/beautifulsoup', methods=['POST'])
def scrape_beautifulsoup():
    """Scrape using Beautiful Soup only"""
    try:
        data = request.json
        url = data.get("url")
        selector = data.get("selector")
        attribute = data.get("attribute", "Text Content")
        
        print(f"🌟 BeautifulSoup scraping: {url}")
        start_time = time.time()
        
        # Custom headers to avoid blocking
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        elements = soup.select(selector) if selector else []
        
        results = extract_data_from_elements(elements, attribute, "beautifulsoup")
        execution_time = round(time.time() - start_time, 2)
        
        return jsonify({
            "success": True,
            "results": results,
            "method": "Beautiful Soup",
            "execution_time": execution_time,
            "total_found": len(results)
        })
        
    except requests.RequestException as e:
        return jsonify({
            "success": False,
            "error": f"Network error: {str(e)}",
            "method": "Beautiful Soup"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "method": "Beautiful Soup"
        })

@app.route('/scrape/selenium', methods=['POST'])
def scrape_selenium():
    """Scrape using Selenium"""
    driver = None
    try:
        data = request.json
        url = data.get("url")
        selector = data.get("selector")
        attribute = data.get("attribute", "Text Content")
        wait_time = data.get("wait_time", 10)
        
        print(f"🤖 Selenium scraping: {url}")
        start_time = time.time()
        
        driver = setup_chrome_driver()
        driver.get(url)
        
        # Wait for elements to load
        try:
            WebDriverWait(driver, wait_time).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector))
            )
        except TimeoutException:
            print("⚠️ Timeout waiting for elements, proceeding anyway...")
        
        # Additional wait for dynamic content
        time.sleep(2)
        
        selenium_elements = driver.find_elements(By.CSS_SELECTOR, selector)
        results = extract_data_from_elements(selenium_elements, attribute, "selenium")
        
        execution_time = round(time.time() - start_time, 2)
        
        return jsonify({
            "success": True,
            "results": results,
            "method": "Selenium",
            "execution_time": execution_time,
            "total_found": len(results)
        })
        
    except WebDriverException as e:
        return jsonify({
            "success": False,
            "error": f"WebDriver error: {str(e)}",
            "method": "Selenium"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "method": "Selenium"
        })
    finally:
        if driver:
            driver.quit()

@app.route('/scrape/auto', methods=['POST'])
def scrape_auto():
    """Auto scraping - tries Beautiful Soup first, falls back to Selenium"""
    try:
        data = request.json
        print(f"🔄 Auto scraping: {data.get('url')}")
        
        # Try Beautiful Soup first
        bs_response = scrape_beautifulsoup()
        bs_data = bs_response.get_json()
        
        if bs_data.get("success") and bs_data.get("total_found", 0) > 0:
            bs_data["method"] = "Beautiful Soup (Auto)"
            return jsonify(bs_data)
        
        print("⚠️ Beautiful Soup found no results, trying Selenium...")
        
        # Fallback to Selenium
        selenium_response = scrape_selenium()
        selenium_data = selenium_response.get_json()
        selenium_data["method"] = "Selenium (Auto Fallback)"
        
        return jsonify(selenium_data)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "method": "Auto"
        })

@app.route('/validate-url', methods=['POST'])
def validate_url():
    """Validate if URL is accessible"""
    try:
        data = request.json
        url = data.get("url")
        
        response = requests.head(url, timeout=5)
        return jsonify({
            "valid": True,
            "status_code": response.status_code,
            "content_type": response.headers.get('content-type', 'Unknown')
        })
    except Exception as e:
        return jsonify({
            "valid": False,
            "error": str(e)
        })

@app.route('/export-csv', methods=['POST'])
def export_csv():
    """Export scraped results to CSV format"""
    try:
        data = request.json
        results = data.get("results", [])
        metadata = data.get("metadata", {})
        
        if not results:
            return jsonify({
                "success": False,
                "error": "No data to export"
            })
        
        # Create CSV content
        import csv
        from io import StringIO
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Write headers
        headers = ["Index", "Value"]
        if metadata.get("url"):
            headers.append("Source URL")
        if metadata.get("selector"):
            headers.append("CSS Selector")
        if metadata.get("attribute"):
            headers.append("Attribute")
        if metadata.get("method"):
            headers.append("Method")
        
        writer.writerow(headers)
        
        # Write data rows
        for i, item in enumerate(results):
            row = [i + 1, item.get("value", "")]
            if metadata.get("url"):
                row.append(metadata["url"])
            if metadata.get("selector"):
                row.append(metadata["selector"])
            if metadata.get("attribute"):
                row.append(metadata["attribute"])
            if metadata.get("method"):
                row.append(metadata["method"])
            writer.writerow(row)
        
        csv_content = output.getvalue()
        output.close()
        
        return jsonify({
            "success": True,
            "csv_content": csv_content,
            "filename": f"web_scraper_results_{int(time.time())}.csv"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))