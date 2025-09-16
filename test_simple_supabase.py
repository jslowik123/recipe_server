#!/usr/bin/env python3
"""
Simple test for Supabase recipe upload
"""
import os
from dotenv import load_dotenv
from supabase import create_client, Client
from datetime import datetime
import logging

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_simple_upload():
    """Test uploading a recipe directly to Supabase"""

    # Supabase config - use service key for testing
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")  # Use service key to bypass RLS for testing

    print(f"🔗 Connecting to Supabase: {url[:30]}...")

    supabase: Client = create_client(url, key)

    # Test JWT token
    test_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVlZHJoa29oeWFkYWh2bnJra295Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQ5Nzk1MzQsImV4cCI6MjA3MDU1NTUzNH0.3kmyfINRRo28_WnWCoPZRTt9FQzP-J08lKFKQfYRPbk"
    test_user_id = "09b49905-62d0-4a87-9ca6-43d3ce34a1fa"

    # Test recipe data - simulate the corrected structure
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
                    '250g mozzarella cheese'
                ],
                'steps': [
                    'Preheat oven to 180°C',
                    'Brown the ground beef with olive oil',
                    'Add tomato sauce and season'
                ]
            }
        }
    }

    try:
        # Using service key - no need to set additional JWT for testing
        print("🔐 Using service key - bypassing RLS for test...")

        # Extract recipe using our corrected logic
        result_data = test_recipe_data.get('result', {})
        recipe = result_data.get('processed_recipe', {})

        print(f"🔍 Debug info:")
        print(f"   recipe_data keys: {list(test_recipe_data.keys())}")
        print(f"   result_data keys: {list(result_data.keys())}")
        print(f"   recipe keys: {list(recipe.keys())}")
        print(f"   recipe title: {recipe.get('title', 'NO TITLE')}")

        # Prepare recipe record
        recipe_record = {
            'name': recipe.get('title', 'Untitled Recipe')[:255],
            'description': recipe.get('title', 'Extracted recipe from TikTok')[:255],
            'original_link': 'https://test.com/video123',
            'ingredients': recipe.get('ingredients', []),
            'steps': recipe.get('steps', []),
            'user_id': test_user_id,
            'created_at': datetime.utcnow().isoformat() + "Z"
        }

        print(f"📤 Uploading recipe: {recipe_record['name']}")
        print(f"   Ingredients: {len(recipe_record['ingredients'])}")
        print(f"   Steps: {len(recipe_record['steps'])}")

        # Upload to Supabase
        response = supabase.table('recipes').insert(recipe_record).execute()

        if response.data and len(response.data) > 0:
            created_recipe = response.data[0]
            recipe_id = created_recipe.get('id')

            print(f"✅ Upload successful!")
            print(f"   Recipe ID: {recipe_id}")
            print(f"   Recipe Name: {created_recipe.get('name')}")

            # Now read it back
            print(f"\n📖 Reading back recipe {recipe_id}...")
            read_response = supabase.table('recipes').select('*').eq('id', recipe_id).execute()

            if read_response.data and len(read_response.data) > 0:
                retrieved = read_response.data[0]
                print(f"✅ Retrieved successfully!")
                print(f"   Name: {retrieved.get('name')}")
                print(f"   Ingredients count: {len(retrieved.get('ingredients', []))}")
                print(f"   Steps count: {len(retrieved.get('steps', []))}")
                print(f"   First ingredient: {retrieved.get('ingredients', ['None'])[0]}")
                print(f"   First step: {retrieved.get('steps', ['None'])[0]}")

                return True
            else:
                print("❌ Failed to read back recipe")
                return False
        else:
            print("❌ Upload failed - no data returned")
            return False

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_simple_upload()
    print(f"\n🎯 Test {'PASSED' if success else 'FAILED'}")