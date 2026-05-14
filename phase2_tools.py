import requests
import json
import re
from urllib.parse import quote
from pathlib import Path
import pandas as pd
from supplier_verifier import SupplierVerifier
from openai import OpenAI
import base64
import tempfile

client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

class Phase2Tools:
    def __init__(self):
        self.verifier = SupplierVerifier()

    def fetch_us_import_records(self, company_name: str) -> dict:
        """Fetch US import data from ImportYeti"""
        try:
            url = f"https://importyeti.com/search?company={quote(company_name)}"
            headers = {"User-Agent": "Mozilla/5.0"}
            res = requests.get(url, headers=headers, timeout=10)
            
            if res.status_code != 200:
                return {"status": "error", "message": "Could not fetch data"}
            
            # Simple parsing
            shipments_found = "shipments" in res.text.lower()
            
            return {
                "status": "success",
                "company": company_name,
                "has_records": shipments_found,
                "note": "Check ImportYeti.com for detailed records"
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def generate_samr_lookup(self, company_name: str, credit_code: str = "") -> dict:
        """Generate SAMR registry lookup"""
        search_url = f"https://www.gsxt.gov.cn/corp-query-entprise-info-{quote(company_name)}.html"
        
        prompt = """Analyze SAMR data and return JSON:
{
  "company_type": "manufacturing/trading/service",
  "registered_capital": "amount",
  "establishment_date": "YYYY-MM-DD",
  "risk_flags": [],
  "manufacturer_probability": "high/medium/low"
}

Data: [PASTE SAMR DATA HERE]"""
        
        return {
            "status": "success",
            "search_url": search_url,
            "direct_url": f"https://www.gsxt.gov.cn/{quote(credit_code)}.html" if credit_code else None,
            "ai_parser_prompt": prompt
        }

    def analyze_satellite_facility(self, address: str) -> dict:
        """Analyze satellite imagery with LLaVA"""
        try:
            from geopy.geocoders import Nominatim
            
            geolocator = Nominatim(user_agent="supplier_ai")
            location = geolocator.geocode(address)
            
            if not location:
                return {"status": "error", "message": "Address not found"}
            
            lat, lon = location.latitude, location.longitude
            
            # Download map tile
            tile_url = f"https://tile.openstreetmap.org/18/{int(lat)}/{int(lon)}.png"
            res = requests.get(tile_url, timeout=10)
            
            if res.status_code != 200:
                return {"status": "error", "message": "Could not fetch map"}
            
            # Save temp
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                tmp.write(res.content)
                img_path = tmp.name
            
            # Analyze with LLaVA
            with open(img_path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode()
            
            prompt = "Classify this facility: factory/warehouse/office/residential. Return JSON with facility_type and confidence."
            
            response = client.chat.completions.create(
                model="llava",
                messages=[{"role": "user", "content": prompt, "images": [encoded]}],
                temperature=0.1,
                max_tokens=500
            )
            
            match = re.search(r'\{.*\}', response.choices[0].message.content, re.DOTALL)
            analysis = json.loads(match.group()) if match else {"raw": response.choices[0].message.content}
            
            Path(img_path).unlink(missing_ok=True)
            
            return {"status": "success", "analysis": analysis, "coords": [lat, lon]}
            
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def process_batch_suppliers(self, csv_path: str) -> list:
        """Batch process suppliers"""
        try:
            df = pd.read_csv(csv_path)
            results = []
            
            for idx, row in df.iterrows():
                v = SupplierVerifier()
                name = row.get("company_name", "")
                
                if pd.notna(row.get("alibaba_url")):
                    v.analyze_platform_listing(row["alibaba_url"])
                if pd.notna(row.get("cert_number")):
                    v.verify_certification(row.get("cert_type", "CE"), row["cert_number"], name)
                
                report = v.generate_report()
                results.append({
                    "company": name,
                    "trust_score": report["trust_score"]
                })
            
            return {"status": "success", "results": results}
        except Exception as e:
            return {"status": "error", "message": str(e)}