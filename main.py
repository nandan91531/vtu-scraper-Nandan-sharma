import os
import warnings
import time
import io
from typing import Any, Dict, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor

# Flask and CORS
from flask import Flask, jsonify, request, send_file, render_template 
from flask_cors import CORS 
from dotenv import load_dotenv

# Web Scraping Libraries
import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import urllib3

# Tesseract OCR and Image Processing
import pytesseract
import cv2
import numpy as np

# --- Configuration & Initialization ---

warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

app = Flask(__name__)
# CORS ko pure access ke liye open kar diya hai hosting ke liye
CORS(app)

class Config:
    DEFAULT_INDEX_URL = 'https://results.vtu.ac.in/D25J26Ecbcs/index.php'
    DEFAULT_RESULT_URL = 'https://results.vtu.ac.in/D25J26Ecbcs/resultpage.php'
    
    # Cloud hosting pe path environment variable se uthayega
    TESSERACT_PATH = os.getenv('TESSERACT_PATH', None)
    MAX_SCRAPER_WORKERS = 15 
    MAX_RETRY_ATTEMPTS = 22
    TEMP_EXCEL_STORAGE: Dict[str, io.BytesIO] = {} 
    
    @classmethod
    def init_tesseract(cls):
        if cls.TESSERACT_PATH:
            pytesseract.pytesseract.tesseract_cmd = cls.TESSERACT_PATH
        try:
            pytesseract.get_tesseract_version()
            print("--- Tesseract Found Successfully ---")
            return True
        except Exception as e:
            print(f"--- Tesseract Error: {e} ---")
            return False

class CaptchaSolver:
    def __init__(self, target_color=102, tolerance=25):
        self.target_color = target_color
        self.tolerance = tolerance
    
    def preprocess_captcha(self, image_bytes: bytes) -> Optional[np.ndarray]:
        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None: return None
            img = cv2.resize(img, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            lower = np.array([self.target_color - self.tolerance] * 3)
            upper = np.array([self.target_color + self.tolerance] * 3)
            mask = cv2.inRange(img, lower, upper)
            kernel = np.ones((2, 2), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            return cv2.bitwise_not(mask)
        except Exception:
            return None
    
    def solve(self, image_content: bytes) -> Optional[str]:
        try:
            processed_image = self.preprocess_captcha(image_content)
            if processed_image is None: return None
            custom_config = r'--oem 1 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
            extracted_text = pytesseract.image_to_string(processed_image, config=custom_config).strip()
            captcha_code = ''.join(c for c in extracted_text if c.isalnum())
            return captcha_code if len(captcha_code) == 6 else None
        except Exception:
            return None

class VTUScraper:
    def __init__(self, captcha_solver: CaptchaSolver):
        self.captcha_solver = captcha_solver

    def fetch_result(self, usn: str, index_url: str, result_url: str, target_sub: str = None) -> Optional[dict]:
        session = requests.Session()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
            'Referer': index_url
        }
        
        for attempt in range(1, Config.MAX_RETRY_ATTEMPTS + 1):
            try:
                r = session.get(index_url, headers=headers, verify=False, timeout=10)
                soup = BeautifulSoup(r.text, 'html.parser')
                token = soup.find('input', {'name': 'Token'})['value']
                captcha_img = soup.find('img', alt='CAPTCHA') or soup.find('img', src=lambda s: s and 'captcha' in s.lower())
                
                captcha_src = urljoin(index_url, captcha_img['src'])
                captcha_r = session.get(captcha_src, headers=headers, verify=False, timeout=10)
                captcha_code = self.captcha_solver.solve(captcha_r.content)
                if not captcha_code: continue 
                
                data = {'Token': token, 'lns': usn, 'captchacode': captcha_code}
                post_r = session.post(result_url, data=data, headers=headers, verify=False, timeout=15)
                
                if 'Student Name' not in post_r.text: continue
                
                result_soup = BeautifulSoup(post_r.text, 'html.parser')
                name = "Unknown"
                name_label = result_soup.find('b', string=lambda t: t and 'Student Name' in t)
                if name_label:
                    tds = name_label.find_parent('td').find_next_siblings('td')
                    for td in tds:
                        txt = td.get_text(strip=True)
                        if txt and txt != ':':
                            name = txt
                            break

                subjects = []
                table_body = result_soup.find('div', {'class': 'divTableBody'})
                if table_body:
                    for row in table_body.find_all('div', {'class': 'divTableRow'})[1:]:
                        cells = row.find_all('div', {'class': 'divTableCell'})
                        if len(cells) >= 7:
                            s_code = cells[0].get_text(strip=True)
                            if target_sub and target_sub.upper() != s_code.upper():
                                continue

                            subjects.append({
                                'code': s_code,
                                'name': cells[1].get_text(strip=True),
                                'internals': cells[2].get_text(strip=True),
                                'externals': cells[3].get_text(strip=True),
                                'total': cells[4].get_text(strip=True),
                                'result': cells[5].get_text(strip=True)
                            })
                
                if not subjects: return None
                return {'usn': usn, 'name': name, 'subjects': subjects}
            except Exception:
                continue
        return None

    def get_bulk_results(self, usn_list, index_url, result_url, target_sub=None):
        successful_results, failed_usns = [], []
        with ThreadPoolExecutor(max_workers=Config.MAX_SCRAPER_WORKERS) as executor:
            results = list(executor.map(lambda u: self.fetch_result(u, index_url, result_url, target_sub), usn_list))
            for i, r in enumerate(results):
                if r: successful_results.append(r)
                else: failed_usns.append(usn_list[i])
        return successful_results, failed_usns

def generate_bulk_excel_file(results_data: List[dict]) -> tuple[str, io.BytesIO]:
    consolidated_rows = []
    for result in results_data:
        for sub in result['subjects']:
            consolidated_rows.append({
                'USN': result['usn'], 
                'Name': result['name'],
                'Subject Code': sub['code'], 
                'Subject Name': sub['name'],
                'Internal Marks': sub['internals'],
                'External Marks': sub['externals'],
                'Total': sub['total'], 
                'Result': sub['result']
            })
    df = pd.DataFrame(consolidated_rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    return f"VTU_Results_{int(time.time())}.xlsx", output

CAPTCHA_SOLVER = CaptchaSolver()
VTU_SCRAPER = VTUScraper(CAPTCHA_SOLVER)

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html', default_index_url=Config.DEFAULT_INDEX_URL, default_result_url=Config.DEFAULT_RESULT_URL)

@app.route('/api/vtu/results', methods=['POST'])
def get_bulk_vtu_results():
    try:
        data = request.get_json()
        usn_list = [str(u).strip() for u in data.get('usns', []) if str(u).strip()]
        idx_url = data.get('index_url', Config.DEFAULT_INDEX_URL)
        res_url = data.get('result_url', Config.DEFAULT_RESULT_URL)
        target_sub = data.get('subject_code', None) 
        
        success, failed = VTU_SCRAPER.get_bulk_results(usn_list, idx_url, res_url, target_sub)
        
        download_url = None
        if success:
            filename, stream = generate_bulk_excel_file(success)
            Config.TEMP_EXCEL_STORAGE[filename] = stream
            download_url = f"{request.url_root.rstrip('/')}/api/vtu/download/{filename}"

        return jsonify({
            "status": "success",
            "total_successful": len(success),
            "failed_count": len(failed),
            "download_url": download_url,
            "results": success
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/vtu/download/<filename>', methods=['GET'])
def download_excel(filename):
    excel_stream = Config.TEMP_EXCEL_STORAGE.pop(filename, None)
    if not excel_stream: return jsonify({"error": "Expired or Not Found"}), 404
    return send_file(excel_stream, as_attachment=True, download_name=filename)

if __name__ == '__main__':
    Config.init_tesseract()
    # Cloud hosting ke liye port dynamic hona chahiye
    port = int(os.environ.get("PORT", 5000))
    # 0.0.0.0 par host karna cloud ke liye zaruri hai
    app.run(host='0.0.0.0', port=port, debug=False)