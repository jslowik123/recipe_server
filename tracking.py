#!/usr/bin/env python3
"""
Token and request tracking for recipe extraction
"""

import pandas as pd
import json
import datetime
import os
from typing import Dict, Any, Optional

class RequestTracker:
    """Track API requests, tokens, and results"""
    
    def __init__(self, excel_file: str = "recipe_extraction_tracking.xlsx"):
        self.excel_file = excel_file
        self.data = []
        
        # Load existing data if file exists
        if os.path.exists(excel_file):
            try:
                existing_df = pd.read_excel(excel_file)
                self.data = existing_df.to_dict('records')
                print(f"📊 Loaded {len(self.data)} existing records from {excel_file}")
            except Exception as e:
                print(f"⚠️ Could not load existing tracking file: {e}")
    
    def track_request(self, 
                     url: str,
                     task_id: str,
                     frames_count: int = 0,
                     model_used: str = "",
                     prompt_tokens: int = 0,
                     completion_tokens: int = 0,
                     total_tokens: int = 0,
                     cost_estimate: float = 0.0,
                     processing_time: float = 0.0,
                     ingredients_count: int = 0,
                     steps_count: int = 0,
                     success: bool = False,
                     error_message: str = "",
                     raw_response: Dict[Any, Any] = None):
        """Track a single request"""
        
        record = {
            'timestamp': datetime.datetime.now().isoformat(),
            'url': url,
            'task_id': task_id,
            'frames_count': frames_count,
            'model_used': model_used,
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'total_tokens': total_tokens,
            'cost_estimate_usd': cost_estimate,
            'processing_time_seconds': processing_time,
            'ingredients_count': ingredients_count,
            'steps_count': steps_count,
            'success': success,
            'error_message': error_message,
            'raw_response': json.dumps(raw_response) if raw_response else ""
        }
        
        self.data.append(record)
        self.save_to_excel()
        
        print(f"📝 Tracked request: {url} | Tokens: {total_tokens} | Cost: ${cost_estimate:.4f}")
    
    def save_to_excel(self):
        """Save data to Excel file"""
        try:
            df = pd.DataFrame(self.data)
            
            # Reorder columns for better readability
            column_order = [
                'timestamp', 'url', 'task_id', 'success',
                'frames_count', 'model_used', 
                'prompt_tokens', 'completion_tokens', 'total_tokens',
                'cost_estimate_usd', 'processing_time_seconds',
                'ingredients_count', 'steps_count',
                'error_message', 'raw_response'
            ]
            
            # Only include columns that exist
            available_columns = [col for col in column_order if col in df.columns]
            df = df[available_columns]
            
            df.to_excel(self.excel_file, index=False)
            print(f"💾 Saved tracking data to {self.excel_file}")
            
        except Exception as e:
            print(f"❌ Error saving tracking data: {e}")
    
    def get_stats(self):
        """Get summary statistics"""
        if not self.data:
            return "No tracking data available"
        
        df = pd.DataFrame(self.data)
        
        stats = {
            'total_requests': len(df),
            'successful_requests': len(df[df['success'] == True]),
            'total_tokens': df['total_tokens'].sum(),
            'total_cost_usd': df['cost_estimate_usd'].sum(),
            'avg_processing_time': df['processing_time_seconds'].mean(),
            'avg_frames_per_request': df['frames_count'].mean(),
            'total_ingredients_extracted': df['ingredients_count'].sum(),
            'total_steps_extracted': df['steps_count'].sum(),
        }
        
        return stats

def calculate_openai_cost(prompt_tokens: int, completion_tokens: int, model: str = "gpt-4o") -> float:
    """Calculate estimated OpenAI API cost"""
    
    # OpenAI pricing (as of 2024) - Update these as needed
    pricing = {
        "gpt-4o": {"input": 0.0025, "output": 0.01},  # per 1K tokens
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "gpt-4": {"input": 0.03, "output": 0.06},
        "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    }
    
    if model not in pricing:
        model = "gpt-4o"  # Default
    
    input_cost = (prompt_tokens / 1000) * pricing[model]["input"]
    output_cost = (completion_tokens / 1000) * pricing[model]["output"]
    
    return input_cost + output_cost

# Global tracker instance
tracker = RequestTracker()