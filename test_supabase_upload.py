#!/usr/bin/env python3
"""
Test Supabase recipe upload and retrieval
"""
import os
from dotenv import load_dotenv
from services import SupabaseService

load_dotenv()

def test_recipe_upload_and_read():
    """Test uploading a recipe and reading it back"""

    # Test data structure (simulating what comes from TikTok scraper)
    test_recipe_data = {
        'status': 'SUCCESS',
        'url': 'https://test.com/video123',
        'result': {
            'url': 'https://test.com/video123',
            'text': 'Some video text...',
            'subtitles': 'Video subtitles...',
            'processed_recipe': {
                'title': 'Test Ultimate Lasagne Recipe',
                'ingredients': [
                    '500g ground beef',
                    '300g lasagne sheets',
                    '400ml tomato sauce',
                    '250g mozzarella cheese',
                    '100g parmesan cheese',
                    '2 tbsp olive oil',
                    'Salt and pepper to taste'
                ],
                'steps': [
                    'Preheat oven to 180°C',
                    'Brown the ground beef with olive oil',
                    'Add tomato sauce and season',
                    'Layer lasagne sheets with meat sauce',
                    'Top with mozzarella and parmesan',
                    'Bake for 45 minutes until golden'
                ]
            }
        },
        'has_subtitles': True,
        'has_ai_processing': True,
        'processed_at': 1726488000.0
    }

    # Test JWT token (you'll need a real one)
    test_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVlZHJoa29oeWFkYWh2bnJra295Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQ5Nzk1MzQsImV4cCI6MjA3MDU1NTUzNH0.3kmyfINRRo28_WnWCoPZRTt9FQzP-J08lKFKQfYRPbk"
    test_user_id = "09b49905-62d0-4a87-9ca6-43d3ce34a1fa"

    print("🧪 Testing Supabase Recipe Upload...")

    try:
        # Initialize service
        supabase_service = SupabaseService()

        # Upload recipe
        print("📤 Uploading test recipe...")
        uploaded_recipe = supabase_service.upload_recipe(
            user_id=test_user_id,
            recipe_data=test_recipe_data,
            original_url="https://test.com/video123",
            jwt_token=test_jwt
        )

        print(f"✅ Recipe uploaded successfully!")
        print(f"   Recipe ID: {uploaded_recipe.get('id')}")
        print(f"   Recipe Name: {uploaded_recipe.get('name')}")
        print(f"   Ingredients Count: {len(uploaded_recipe.get('ingredients', []))}")
        print(f"   Steps Count: {len(uploaded_recipe.get('steps', []))}")

        # Now try to read it back
        recipe_id = uploaded_recipe.get('id')
        if recipe_id:
            print(f"\n📖 Reading back recipe {recipe_id}...")

            # Read back from Supabase
            response = supabase_service.client.table('recipes').select('*').eq('id', recipe_id).execute()

            if response.data and len(response.data) > 0:
                retrieved_recipe = response.data[0]
                print(f"✅ Recipe retrieved successfully!")
                print(f"   Name: {retrieved_recipe.get('name')}")
                print(f"   Description: {retrieved_recipe.get('description')}")
                print(f"   Original Link: {retrieved_recipe.get('original_link')}")
                print(f"   Ingredients: {retrieved_recipe.get('ingredients')[:2]}... (showing first 2)")
                print(f"   Steps: {retrieved_recipe.get('steps')[:2]}... (showing first 2)")
                print(f"   User ID: {retrieved_recipe.get('user_id')}")

                return True
            else:
                print("❌ Failed to retrieve recipe")
                return False
        else:
            print("❌ No recipe ID returned")
            return False

    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_recipe_upload_and_read()
    print(f"\n🎯 Test {'PASSED' if success else 'FAILED'}")