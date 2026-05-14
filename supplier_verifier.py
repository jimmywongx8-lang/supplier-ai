import requests
import json
import re
from bs4 import BeautifulSoup
from openai import OpenAI
import base64
from pathlib import Path

client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

class SupplierVerifier:
    def __init__(self):
        self.report = {
            "platform_analysis": {},
            "certification_check": {},
            "satellite_analysis": {},
            "trust_score": 50,
            "flags": []
        }

    def analyze_platform_listing(self, store_url: str) -> dict:
        """Analyze Alibaba/GS store for trading company signals"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
            res = requests.get(store_url, headers=headers, timeout=8)
            
            # If status is not 200, record the error in the report
            if res.status_code != 200:
                self.report["platform_analysis"] = {
                    "status": "blocked",
                    "code": res.status_code,
                    "message": "Alibaba blocked the request or URL is invalid",
                    "manual_check": "Open URL in browser to verify"
                }
                return self.report["platform_analysis"]
            
            soup = BeautifulSoup(res.text, "lxml")
            
            # Try to extract categories
            categories = [c.text.strip() for c in soup.select(".category-name, .product-category, a[class*='cat']") if c.text.strip()]
            categories = list(set(categories))[:10]
            
            # If no categories found, record that in the report
            if not categories:
                self.report["platform_analysis"] = {
                    "status": "no_data",
                    "message": "Could not extract categories (Alibaba requires JavaScript or Login)",
                    "manual_check": "Open URL in browser"
                }
                return self.report["platform_analysis"]
            
            # If data IS found, calculate score
            unique_roots = len(set([c.split()[0].lower() for c in categories if c]))
            coherence_score = max(0, 10 - (unique_roots - 1) * 2)
            
            self.report["platform_analysis"] = {
                "status": "success",
                "url": store_url,
                "categories_found": len(categories),
                "category_coherence_score": coherence_score,
                "trading_company_risk": "High" if coherence_score < 5 else "Medium" if coherence_score < 7 else "Low",
                "sample_categories": categories[:5]
            }
            return self.report["platform_analysis"]
            
        except requests.exceptions.Timeout:
            self.report["platform_analysis"] = {"status": "timeout", "message": "Request timed out - Alibaba is slow"}
            return self.report["platform_analysis"]
        except Exception as e:
            self.report["platform_analysis"] = {"status": "error", "message": str(e)}
            return self.report["platform_analysis"]

    def verify_certification(self, cert_type: str, cert_number: str, company_name: str) -> dict:
        """Check certification against public registries"""
        result = {"cert_type": cert_type, "cert_number": cert_number, "status": "unchecked", "match": False}
        
        try:
            if cert_type.upper() == "UL":
                url = f"https://productiq.ul.com/proddetail?cert={cert_number}"
                res = requests.get(url, timeout=8)
                result["status"] = "valid" if res.status_code == 200 and "active" in res.text.lower() else "invalid/not_found"
                
            elif cert_type.upper() == "CE":
                nb_match = re.match(r"^(\d{4})\s*CE", cert_number)
                result["status"] = "format_valid" if nb_match else "invalid_format"
                result["notified_body"] = nb_match.group(1) if nb_match else None
                
            elif cert_type.upper() in ["IEC", "CB"]:
                url = f"https://www.iec.ch/standards/certification/cb-scheme/certificates?cert={cert_number}"
                res = requests.get(url, timeout=8)
                result["status"] = "found" if res.status_code == 200 else "not_found"
                
            if result["status"] in ["valid", "found", "format_valid"]:
                result["match"] = True
                
            self.report["certification_check"] = result
            return result
        except Exception as e:
            self.report["certification_check"] = {"error": str(e)}
            return self.report["certification_check"]

    def calculate_trust_score(self) -> int:
        """Weighted scoring based on verification signals"""
        score = 50
        
        plat = self.report.get("platform_analysis", {})
        # Only add points if we actually got data
        if plat.get("status") == "success":
            score += plat.get("category_coherence_score", 0) * 2
        elif plat.get("status") == "blocked":
            score -= 10 # Penalty for being blocked (suspicious)
            
        cert = self.report.get("certification_check", {})
        if cert.get("status") in ["valid", "found"]:
            score += 15
        elif cert.get("status") in ["invalid", "not_found", "invalid_format"]:
            score -= 20
            
        self.report["trust_score"] = max(0, min(100, score))
        return self.report["trust_score"]

    def generate_report(self) -> dict:
        self.calculate_trust_score()
        return self.report