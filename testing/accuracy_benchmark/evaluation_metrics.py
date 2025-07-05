from typing import Dict, List
import pandas as pd
from sklearn.metrics import precision_recall_fscore_support
from rapidfuzz import fuzz

class ParserEvaluator:
    def __init__(self, ground_truth: pd.DataFrame):
        self.ground_truth = ground_truth
    
    def evaluate_parsing(self, parser_output: pd.DataFrame) -> Dict:
        merged = pd.merge(
            self.ground_truth,
            parser_output,
            on='document_id',
            suffixes=('_true', '_pred')
        )
        
        results = {}
        for entity_type in ['skills', 'companies', 'education']:
            true = merged[f"{entity_type}_true"]
            pred = merged[f"{entity_type}_pred"]
            results[entity_type] = self._calculate_entity_metrics(true, pred)
        
        return results
    
    def _calculate_entity_metrics(self, true: List, pred: List) -> Dict:
        # Token-level evaluation
        tp, fp, fn = 0, 0, 0
        
        for t, p in zip(true, pred):
            t_set = set(t)
            p_set = set(p)
            
            tp += len(t_set & p_set)
            fp += len(p_set - t_set)
            fn += len(t_set - p_set)
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        
        # String similarity metrics
        similarity = sum(fuzz.token_set_ratio(str(t), str(p)) for t, p in zip(true, pred)) / len(true)
        
        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "similarity": round(similarity, 1)
        }
    
    def generate_report(self, results: Dict, output_path: str):
        # Generate comprehensive PDF report with visualizations
        # (Implementation would use matplotlib/seaborn)
        pass
