import fitz 
import re
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

class TrafficFinePDFParser:
    """
    Bilingual (Kazakh/Russian) traffic fine PDF parser
    Handles documents from Almaty Region Police Department
    """
    
    # Regex patterns for data extraction
    PATTERNS = {
        'prescription_number': r'№\s*(\d{15})',
        'license_plate': r'(?:Госномер|Мемл\. нөмірі):\s*(\w+)',
        'vehicle_certificate': r'(?:№ СРТС|КҚТК №):\s*(\w+)',
        'vehicle_make': r'(?:Марка, модель|Маркасы, үлгісі):\s*([A-Z\s]+)',
        'vehicle_color': r'(?:Цвет|Түсі):\s*(\w+)',
        'violation_datetime': r'(?:Дата, время совершения|Жасалған күні, уақыты):\s*(\d{2}\.\d{2}\.\d{4})\s*(\d{2}:\d{2})',
        'violation_location': r'(?:Место совершения|Жасалған орны):\s*([^\n]+)',
        'detected_speed': r'(?:зафиксированная скорость|анықталған жылдамдық)\s*-\s*([\d,\.]+)\s*км',
        'allowed_speed': r'(?:разрешенная скорость|рұқсат етілген жылдамдық)\s*-\s*([\d,\.]+)\s*км',
        'speed_with_margin': r'(?:исключающая погрешность|ауытқушылығын есепке алмайтын)\s*-\s*([\d,\.]+)\s*км',
        'fine_amount': r'(?:Сумма наложенного штрафа|Салынған айыппұл сомасы):\s*([\d,\.]+)\s*тенге',
        'discounted_amount': r'\(\s*([\d,\.]+)\s*\)',
        'device_name': r'(?:SUNQAR)',
        'device_serial': r'(?:Серийный номер|Сериялық нөмірі):\s*([\w-]+)',
        'certificate_number': r'(?:Номер сертификата|Сынақ куәлігінің нөмірі):\s*([\w-]+)',
        'certificate_date': r'(?:Дата поверки|Сынақ күні):\s*(\d{2}\.\d{2}\.\d{4})',
        'certificate_valid': r'(?:действительна до|дейін):\s*(\d{2}\.\d{2}\.\d{4})',
        'owner_name': r'(?:Наименование юридического лица|Заңды тұлғаның атауы):\s*([^\n]+)',
        'owner_bin': r'(?:ИИН/БИН|ЖСН/БСН):\s*(\d+)',
        'owner_address': r'(?:Адрес|Мекен-жайы):\s*([^\n]+)',
        'issuing_officer': r'(?:подписал|қол қойды):\s*([А-ЯЁ\s]+),',
        'article_code': r'статьей\s*(\d+)\s*частью\s*(\d+)',
    }
    
    def __init__(self):
        self.data: Dict[str, Any] = {}
    
    def parse_file(self, pdf_path: Path) -> Dict[str, Any]:
        """
        Parse PDF file and extract structured data
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Structured dictionary with fine details
        """
        doc = fitz.open(pdf_path)
        full_text = ""
        
        # Extract text from all pages
        for page in doc:
            full_text += page.get_text()
        
        doc.close()
        
        # Extract data using patterns
        self.data = self._extract_data(full_text)
        return self.data
    
    def _extract_data(self, text: str) -> Dict[str, Any]:
        """Extract all relevant data from text using regex patterns"""
        result = {}
        
        # Prescription number
        if match := re.search(self.PATTERNS['prescription_number'], text):
            result['prescription_number'] = match.group(1)
        
        # Vehicle information
        if match := re.search(self.PATTERNS['license_plate'], text):
            result['license_plate'] = match.group(1).strip()
        
        if match := re.search(self.PATTERNS['vehicle_certificate'], text):
            result['vehicle_certificate'] = match.group(1).strip()
        
        if match := re.search(self.PATTERNS['vehicle_make'], text):
            result['vehicle_make_model'] = match.group(1).strip()
        
        if match := re.search(self.PATTERNS['vehicle_color'], text):
            result['vehicle_color'] = match.group(1).strip()
        
        # Violation datetime
        if match := re.search(self.PATTERNS['violation_datetime'], text):
            date_str = match.group(1)
            time_str = match.group(2)
            result['violation_datetime'] = datetime.strptime(
                f"{date_str} {time_str}", "%d.%m.%Y %H:%M"
            )
        
        # Violation location
        if match := re.search(self.PATTERNS['violation_location'], text):
            result['violation_location'] = match.group(1).strip()
        
        # Speed data
        if match := re.search(self.PATTERNS['detected_speed'], text):
            result['detected_speed'] = float(match.group(1).replace(',', '.'))
        
        if match := re.search(self.PATTERNS['allowed_speed'], text):
            result['allowed_speed'] = float(match.group(1).replace(',', '.'))
        
        if match := re.search(self.PATTERNS['speed_with_margin'], text):
            result['speed_with_margin'] = float(match.group(1).replace(',', '.'))
        
        # Financial data
        if match := re.search(self.PATTERNS['fine_amount'], text):
            result['fine_amount'] = float(match.group(1).replace(',', '.'))
        
        # Find discounted amount (50%)
        fine_matches = re.findall(r'\(\s*([\d,\.]+)\s*\)', text)
        if fine_matches:
            result['discounted_amount'] = float(fine_matches[0].replace(',', '.'))
        
        # Device information
        if 'SUNQAR' in text:
            result['device_name'] = 'SUNQAR'
        
        if match := re.search(self.PATTERNS['device_serial'], text):
            result['device_serial'] = match.group(1).strip()
        
        if match := re.search(self.PATTERNS['certificate_number'], text):
            result['certificate_number'] = match.group(1).strip()
        
        if match := re.search(self.PATTERNS['certificate_date'], text):
            result['certificate_date'] = datetime.strptime(
                match.group(1), "%d.%m.%Y"
            )
        
        if match := re.search(self.PATTERNS['certificate_valid'], text):
            result['certificate_valid_until'] = datetime.strptime(
                match.group(1), "%d.%m.%Y"
            )
        
        # Owner information
        if match := re.search(self.PATTERNS['owner_name'], text):
            result['owner_name'] = match.group(1).strip()
        
        if match := re.search(self.PATTERNS['owner_bin'], text):
            result['owner_bin'] = match.group(1).strip()
        
        if match := re.search(self.PATTERNS['owner_address'], text):
            result['owner_address'] = match.group(1).strip()
        
        # Issuing information
        if match := re.search(self.PATTERNS['issuing_officer'], text):
            result['issuing_officer'] = match.group(1).strip()
        
        if match := re.search(self.PATTERNS['article_code'], text):
            result['article_code'] = f"{match.group(1)}.{match.group(2)}"
        
        # Extract violation description
        result['violation_description'] = self._extract_violation_description(text)
        
        # Extract issuing department
        result['issuing_department'] = self._extract_department(text)
        
        return result
    
    def _extract_violation_description(self, text: str) -> str:
        """Extract detailed violation description"""
        patterns = [
            r'(?:Сущность правонарушения|Құқық бұзушылық мәні):\s*([^\n]+(?:\n(?!\w+:)[^\n]+)*)',
        ]
        
        for pattern in patterns:
            if match := re.search(pattern, text):
                return match.group(1).strip()
        
        return ""
    
    def _extract_department(self, text: str) -> str:
        """Extract issuing department name"""
        patterns = [
            r'(ДЕПАРТАМЕНТ ПОЛИЦИИ [^\n]+)',
            r'(ПОЛИЦИЯ ДЕПАРТАМЕНТІНІҢ [^\n]+)',
        ]
        
        for pattern in patterns:
            if match := re.search(pattern, text):
                return match.group(1).strip()
        
        return "Алматы облысы Полиция Департаменті"
