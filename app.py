import streamlit as st
import json
import base64
import re
from openai import OpenAI
import io
from PIL import Image
from supplier_verifier import SupplierVerifier
from phase2_tools import Phase2Tools

client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

st.set_page_config(page_title="AI Product Analyzer", layout="wide")
st.title("AI Product Analyzer")

if "analysis" not in st.session_state:
    st.session_state.analysis = None

analysis_method = st.radio("Analysis Method:", ["AI Image Analysis", "Manual Input"])

if analysis_method == "AI Image Analysis":
    uploaded_file = st.file_uploader("Upload Product Image", type=["jpg", "jpeg", "png", "webp"])
    
    if uploaded_file is not None:
        st.image(uploaded_file, caption="Uploaded Image", use_container_width=True)
        
        if st.button("Analyze Product", type="primary"):
            try:
                img = Image.open(uploaded_file)
                img = img.resize((512, 512))
                if img.mode == "RGBA":
                    img = img.convert("RGB")
                
                buffered = io.BytesIO()
                img.save(buffered, format="JPEG")
                encoded = base64.b64encode(buffered.getvalue()).decode()
                
                prompt = "Describe this product: name, material, main features. Keep it brief."
                
                with st.spinner("Analyzing image..."):
                    response = client.chat.completions.create(
                        model="llava",
                        messages=[{"role": "user", "content": prompt, "images": [encoded]}],
                        temperature=0.1,
                        max_tokens=300
                    )
                
                raw_text = response.choices[0].message.content
                st.success("Analysis Complete!")
                
                st.session_state.analysis = {
                    "raw_description": raw_text,
                    "product_name": raw_text.split(":")[0] if ":" in raw_text else "Product",
                    "material": "Unknown",
                    "key_features": [],
                    "search_terms": []
                }
                
            except Exception as e:
                st.error("AI Analysis Failed: " + str(e))
                
elif analysis_method == "Manual Input":
    st.subheader("Enter Product Details Manually")
    col1, col2 = st.columns(2)
    with col1:
        manual_name = st.text_input("Product Name")
        manual_material = st.text_input("Material")
    with col2:
        manual_features = st.text_area("Key Features (comma-separated)")
    
    if st.button("Use Manual Data", type="primary"):
        st.session_state.analysis = {
            "product_name": manual_name or "Product",
            "material": manual_material or "Unknown",
            "key_features": [f.strip() for f in manual_features.split(",") if f.strip()],
            "search_terms": [manual_name + " supplier", manual_name + " manufacturer"]
        }
        st.success("Data saved!")

if st.session_state.analysis:
    tab1, tab2, tab3, tab4 = st.tabs(["Product", "Verify", "Email", "Phase 2"])
    
    with tab1:
        st.subheader("Product Information")
        st.json(st.session_state.analysis)
        
    with tab2:
        st.subheader("Supplier Verification")
        s_name = st.text_input("Company Name", key="v_name")
        s_url = st.text_input("Alibaba URL", key="v_url")
        s_cert = st.text_input("Cert Number", key="v_cert")
        
        if st.button("Run Check"):
            v = SupplierVerifier()
            if s_url:
                v.analyze_platform_listing(s_url)
            if s_cert:
                v.verify_certification("UL", s_cert, s_name)
            report = v.generate_report()
            score = report["trust_score"]
            
            msg = "Trust Score: " + str(score) + "/100"
            if score >= 70:
                st.success(msg + " (Low Risk)")
            elif score >= 50:
                st.warning(msg + " (Medium Risk)")
            else:
                st.error(msg + " (High Risk)")
            st.json(report)
            
    with tab3:
        p_name = st.session_state.analysis["product_name"]
        email_txt = "Subject: RFQ - " + p_name + "\n\nProduct: " + p_name + "\n\nPlease send quote."
        st.text_area("Email", email_txt, height=150)
        
    with tab4:
        st.write("Phase 2 Tools")
        imp_n = st.text_input("Company for Import Check")
        if st.button("Check Imports"):
            tools = Phase2Tools()
            res = tools.fetch_us_import_records(imp_n)
            st.json(res)
else:
    st.info("Upload an image or enter product details to start")