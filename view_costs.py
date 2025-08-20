#!/usr/bin/env python3
"""
View cost tracking and statistics from the recipe extraction system
"""

import os
import pandas as pd
import json
from datetime import datetime

def view_tracking_data():
    """Display cost tracking data and statistics"""
    
    excel_file = "recipe_extraction_tracking.xlsx"
    
    if not os.path.exists(excel_file):
        print("❌ No tracking file found yet.")
        print(f"   Expected: {excel_file}")
        print("   Run some recipe extractions first to generate tracking data.")
        return
    
    try:
        df = pd.read_excel(excel_file)
        print(f"📊 Loaded {len(df)} tracking records from {excel_file}")
        print("=" * 80)
        
        # Overall Statistics
        total_requests = len(df)
        successful_requests = len(df[df['success'] == True])
        failed_requests = total_requests - successful_requests
        
        total_cost = df['cost_estimate_usd'].sum()
        total_tokens = df['total_tokens'].sum()
        avg_processing_time = df['processing_time_seconds'].mean()
        
        print("📈 OVERALL STATISTICS")
        print(f"   Total Requests: {total_requests}")
        print(f"   ✅ Successful: {successful_requests}")
        print(f"   ❌ Failed: {failed_requests}")
        print(f"   💰 Total Cost: ${total_cost:.4f}")
        print(f"   🪙 Total Tokens: {total_tokens:,}")
        print(f"   ⏱️ Avg Processing Time: {avg_processing_time:.1f}s")
        print()
        
        # Recent Requests (last 10)
        print("📝 RECENT REQUESTS (Last 10)")
        print("-" * 80)
        
        recent = df.tail(10)
        for _, row in recent.iterrows():
            timestamp = row.get('timestamp', 'Unknown')
            url = row.get('url', 'Unknown')[:50] + '...' if len(row.get('url', '')) > 50 else row.get('url', 'Unknown')
            cost = row.get('cost_estimate_usd', 0)
            tokens = row.get('total_tokens', 0)
            success = '✅' if row.get('success') else '❌'
            
            print(f"{success} {timestamp} | ${cost:.4f} | {tokens:,} tokens")
            print(f"   🔗 {url}")
            
            if not row.get('success') and row.get('error_message'):
                print(f"   💥 Error: {row.get('error_message', '')[:100]}...")
            print()
        
        # Cost Breakdown by Model
        if 'model_used' in df.columns:
            print("🤖 COST BY MODEL")
            print("-" * 40)
            model_stats = df.groupby('model_used').agg({
                'cost_estimate_usd': ['count', 'sum', 'mean'],
                'total_tokens': 'sum'
            }).round(4)
            print(model_stats)
            print()
        
        # Daily Usage (if enough data)
        if len(df) > 1:
            print("📅 USAGE OVER TIME")
            print("-" * 40)
            df['date'] = pd.to_datetime(df['timestamp']).dt.date
            daily_stats = df.groupby('date').agg({
                'cost_estimate_usd': 'sum',
                'total_tokens': 'sum',
                'url': 'count'
            }).round(4)
            daily_stats.columns = ['Cost ($)', 'Tokens', 'Requests']
            print(daily_stats.tail(7))  # Last 7 days
            print()
        
        # Recipe Extraction Success
        successful_df = df[df['success'] == True]
        if len(successful_df) > 0:
            print("🍳 RECIPE EXTRACTION STATS")
            print("-" * 40)
            avg_ingredients = successful_df['ingredients_count'].mean()
            avg_steps = successful_df['steps_count'].mean()
            total_recipes = len(successful_df)
            
            print(f"   Total Recipes Extracted: {total_recipes}")
            print(f"   Avg Ingredients per Recipe: {avg_ingredients:.1f}")
            print(f"   Avg Steps per Recipe: {avg_steps:.1f}")
            print()
        
        # Cost Projections
        if successful_requests > 0:
            avg_cost_per_success = df[df['success'] == True]['cost_estimate_usd'].mean()
            print("💡 COST PROJECTIONS")
            print("-" * 40)
            print(f"   Average cost per successful extraction: ${avg_cost_per_success:.4f}")
            print(f"   Cost for 100 extractions: ${avg_cost_per_success * 100:.2f}")
            print(f"   Cost for 1000 extractions: ${avg_cost_per_success * 1000:.2f}")
            print()
        
        print("📄 Full data available in:", excel_file)
        
    except Exception as e:
        print(f"❌ Error reading tracking data: {e}")

def view_latest_recipe():
    """Show the latest extracted recipe"""
    excel_file = "recipe_extraction_tracking.xlsx"
    
    if not os.path.exists(excel_file):
        print("❌ No tracking file found.")
        return
    
    try:
        df = pd.read_excel(excel_file)
        successful_df = df[df['success'] == True]
        
        if len(successful_df) == 0:
            print("❌ No successful extractions found yet.")
            return
        
        latest = successful_df.iloc[-1]
        
        print("🍳 LATEST EXTRACTED RECIPE")
        print("=" * 60)
        print(f"🔗 URL: {latest.get('url', 'Unknown')}")
        print(f"📅 Date: {latest.get('timestamp', 'Unknown')}")
        print(f"💰 Cost: ${latest.get('cost_estimate_usd', 0):.4f}")
        print(f"🪙 Tokens: {latest.get('total_tokens', 0):,}")
        print()
        
        # Parse and display the recipe
        raw_response = latest.get('raw_response', '')
        if raw_response:
            try:
                recipe = json.loads(raw_response) if isinstance(raw_response, str) else raw_response
                
                print(f"📝 Title: {recipe.get('title', 'Untitled')}")
                print()
                
                ingredients = recipe.get('ingredients', [])
                print(f"🥘 Ingredients ({len(ingredients)}):")
                for i, ingredient in enumerate(ingredients, 1):
                    print(f"   {i}. {ingredient}")
                print()
                
                steps = recipe.get('steps', [])
                print(f"👨‍🍳 Steps ({len(steps)}):")
                for i, step in enumerate(steps, 1):
                    print(f"   {i}. {step}")
                
            except json.JSONDecodeError:
                print(f"📄 Raw response: {raw_response}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    print("💰 TikTok Recipe Extraction - Cost Tracking Viewer")
    print("=" * 60)
    print()
    
    while True:
        print("Choose an option:")
        print("1. View all tracking statistics")
        print("2. View latest extracted recipe")
        print("3. Exit")
        
        choice = input("\nEnter choice (1-3): ").strip()
        
        if choice == '1':
            print()
            view_tracking_data()
        elif choice == '2':
            print()
            view_latest_recipe()
        elif choice == '3':
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice. Please enter 1, 2, or 3.")
        
        print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    main()