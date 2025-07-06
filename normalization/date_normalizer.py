# normalization/date_normalizer.py

from datetime import datetime, date
import dateparser
import re
from typing import Optional

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
    
    def normalize(self, date_str: str) -> Optional[date]:
        """Normalize date string to date object"""
        if not date_str:
            return None
            
        # Handle 'Present' or 'Current'
        if re.search(r'\b(present|current)\b', date_str, re.IGNORECASE):
            return date.today()
            
        parsed = dateparser.parse(date_str)
        if parsed:
            try:
                return date(parsed.year, parsed.month, parsed.day)
            except ValueError:
                pass
        
        return self._fallback_parse(date_str)
    
    def _fallback_parse(self, date_str: str) -> Optional[date]:
        """Fallback date parsing for special formats"""
        # Handle quarters (Q1-Q4)
        quarter_match = re.search(r'\bQ([1-4])\s*(\d{4})\b', date_str, re.IGNORECASE)
        if quarter_match:
            quarter, year = quarter_match.groups()
            month = (int(quarter) - 1) * 3 + 1  # Q1->1, Q2->4, Q3->7, Q4->10
            try:
                return date(int(year), month, 1)
            except ValueError:
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
                return date(int(year), int(month), 1)
            except ValueError:
                continue
                
        # Handle year-only dates
        all_numbers = re.findall(r'\d+', date_str)
        if len(all_numbers) == 1 and len(all_numbers[0]) == 4:
            year = all_numbers[0]
            try:
                return date(int(year), 1, 1)
            except ValueError:
                pass
                
        return None