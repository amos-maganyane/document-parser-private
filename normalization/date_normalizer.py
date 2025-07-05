# normalization/date_normalizer.py

import dateparser
import re
from datetime import datetime

class DateNormalizer:
    def __init__(self):
        self.month_map = {
            'jan': '01', 'january': '01',
            'feb': '02', 'february': '02',
            'mar': '03', 'march': '03',
            'apr': '04', 'april': '04',
            'may': '05',
            'jun': '06', 'june': '06',
            'jul': '07', 'july': '07',
            'aug': '08', 'august': '08',
            'sep': '09', 'september': '09',
            'oct': '10', 'october': '10',
            'nov': '11', 'november': '11',
            'dec': '12', 'december': '12'
        }
    
    def normalize(self, date_str: str) -> str:
        if not date_str:
            return None
            
        parsed = dateparser.parse(date_str)
        if parsed:
            try:
                datetime(parsed.year, parsed.month, parsed.day)
                return parsed.strftime('%Y-%m-%d')
            except ValueError:
                pass
        
        return self._fallback_parse(date_str)
    
    def _fallback_parse(self, date_str: str) -> str:
        quarter_match = re.search(r'\bQ([1-4])\s*(\d{4})\b', date_str, re.IGNORECASE)
        if quarter_match:
            return None
            
        patterns = [
            r'(?P<month>[a-z]+)[^\d]*(?P<year>\d{4})',
            r'(?P<month>\d{1,2})[^\d]*(?P<year>\d{4})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, date_str, re.IGNORECASE)
            if not match:
                continue
                
            data = match.groupdict()
            year = data.get('year')
            
            month = '01'
            if 'month' in data:
                month_str = data['month'].lower()
                
                if month_str.isdigit():
                    month_num = int(month_str)
                    if 1 <= month_num <= 12:
                        month = f"{month_num:02d}"
                    else:
                        continue
                else:
                    month = self.month_map.get(month_str) or \
                            self.month_map.get(month_str[:3])
                    if not month:
                        continue
            
            if not year or not year.isdigit() or len(year) != 4:
                continue
                
            try:
                datetime(int(year), int(month), 1)
                return f"{year}-{month}-01"
            except ValueError:
                continue
                
        all_numbers = re.findall(r'\d+', date_str)
        if len(all_numbers) == 1 and len(all_numbers[0]) == 4:
            year = all_numbers[0]
            try:
                datetime(int(year), 1, 1)
                return f"{year}-01-01"
            except ValueError:
                pass
                
        return None