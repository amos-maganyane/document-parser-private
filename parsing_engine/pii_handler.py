import hashlib
import re
from typing import Dict, Tuple
from collections import defaultdict
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry, PatternRecognizer, Pattern
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

class PIIAnonymizer:
    def __init__(self, config: Dict):
        self.replacement_strategy = config.get("replacement_strategy", "hash")
        self.salt = config.get("hash_salt", "secure_salt_value")
        self.pii_cache = {}
        self.current_pii_map = {}
        
        # Create custom recognizers from config
        registry = RecognizerRegistry()
        for pii_type, patterns in config["detection_rules"].items():
            for pattern in patterns:
                regex_recognizer = PatternRecognizer(
                    supported_entity=pii_type.upper(),
                    patterns=[Pattern(name=f"{pii_type}_pattern", regex=pattern, score=0.8)]
                )
                registry.add_recognizer(regex_recognizer)
        
        self.analyzer = AnalyzerEngine(registry=registry)
        self.anonymizer = AnonymizerEngine()
        
    def anonymize(self, text: str) -> Tuple[str, Dict]:
        # Analyze text to find PII entities
        results = self.analyzer.analyze(text=text, language="en")
        pii_map = {}
        
        # Create operator config based on replacement strategy
        operators = {}
        entity_counters = defaultdict(int)
        
        # Store replacements per result
        replacements_per_result = []
        # Sort results by start index to handle overlaps
        results = sorted(results, key=lambda x: x.start)
        
        for result in results:
            operator_name = "replace"
            params = {}
            
            if self.replacement_strategy == "hash":
                original_value = text[result.start:result.end]
                hashed_value = self._hash_value(original_value)
                replacement = f"[{result.entity_type}_{hashed_value}]"
                params = {"new_value": replacement}
            elif self.replacement_strategy == "mask":
                original_value = text[result.start:result.end]
                if result.entity_type == "EMAIL":
                    parts = original_value.split('@')
                    if len(parts) == 2 and len(parts[0]) > 0:
                        replacement = f"{parts[0][0]}***@{parts[1]}"
                    else:
                        replacement = "[EMAIL_REDACTED]"
                    params = {"new_value": replacement}
                elif result.entity_type == "PHONE":
                    digits = re.sub(r'\D', '', original_value)
                    if len(digits) >= 7:
                        replacement = f"{digits[:3]}***{digits[-4:]}"
                    else:
                        replacement = "[PHONE_REDACTED]"
                    params = {"new_value": replacement}
                else:
                    replacement = f"[{result.entity_type}_REDACTED]"
                    params = {"new_value": replacement}
            else:  # token strategy
                entity_counters[result.entity_type] += 1
                replacement = f"[{result.entity_type}_{entity_counters[result.entity_type]}]"
                params = {"new_value": replacement}
            
            operators[result.entity_type] = OperatorConfig(operator_name, params)
            replacements_per_result.append((result, replacement))
        
        # Anonymize text
        anonymized_result = self.anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=operators
        )
        
        # Build PII map with context
        pii_map = {}
        for result, replacement in replacements_per_result:
            original_value = text[result.start:result.end]
            context = self._get_context(text, result.start, result.end)
            pii_map[replacement] = {
                "type": result.entity_type,
                "original": original_value,
                "context": context
            }
        
        # Cache for restoration
        self.pii_cache[anonymized_result.text] = pii_map
        self.current_pii_map = pii_map
        
        return anonymized_result.text, pii_map
    
    def _hash_value(self, value: str) -> str:
        return hashlib.sha256(f"{value}{self.salt}".encode()).hexdigest()[:8]
    
    def _get_context(self, text: str, start: int, end: int, window: int = 50) -> str:
        context_start = max(0, start - window)
        context_end = min(len(text), end + window)
        context = text[context_start:context_end]
        
        prefix = "..." if context_start > 0 else ""
        suffix = "..." if context_end < len(text) else ""
        
        return f"{prefix}{context}{suffix}"
    
    def restore_original(self, anonymized_text: str) -> str:
        pii_map = self.pii_cache.get(anonymized_text, self.current_pii_map)
        if not pii_map:
            return anonymized_text
            
        restored_text = anonymized_text
        for replacement, info in pii_map.items():
            restored_text = restored_text.replace(replacement, info["original"])
        return restored_text 