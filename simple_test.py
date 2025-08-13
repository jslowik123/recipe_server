import requests
import time
import json

def simple_test():
    """
    Ganz simpler Test - nur Zutaten und Schritte
    """
    print("🚀 Simpler Test - nur Zutaten und Schritte")
    
    # 1. Task starten
    print("\n1️⃣ Task starten...")
    response = requests.post("http://localhost:8000/scrape/async", 
                           json={
                               "url": "https://www.tiktok.com/@simple.home.edit/video/7309754078010051841",
                               "process_with_ai": True
                           })
    
    if response.status_code != 200:
        print(f"❌ Fehler: {response.status_code}")
        print(response.text)
        return
    
    task_id = response.json()["task_id"]
    print(f"✅ Task gestartet: {task_id}")
    
    # 2. Warten bis fertig
    print("\n2️⃣ Warten auf Ergebnis...")
    
    for i in range(30):  # Max 5 Minuten
        time.sleep(10)
        
        status = requests.get(f"http://localhost:8000/task/{task_id}")
        data = status.json()
        print(data)
        if data["status"] == "SUCCESS":
            print("✅ Fertig!")
            
            # 3. Nur Zutaten und Schritte zeigen
            if data.get("ai_recipe"):
                recipe = data["ai_recipe"]
                
                print("\n" + "="*40)
                print("🥄 ZUTATEN:")
                for i, ingredient in enumerate(recipe.get("ingredients", []), 1):
                    print(f"  {i}. {ingredient}")
                
                print(f"\n👨‍🍳 SCHRITTE:")
                for i, step in enumerate(recipe.get("steps", []), 1):
                    print(f"  {i}. {step}")
                print("="*40)
                
                # Als JSON speichern
                simple_result = {
                    "ingredients": recipe.get("ingredients", []),
                    "steps": recipe.get("steps", [])
                }
                
                with open('simple_recipe.json', 'w', encoding='utf-8') as f:
                    json.dump(simple_result, f, indent=2, ensure_ascii=False)
                
                print(f"\n💾 Gespeichert in: simple_recipe.json")
                
            else:
                print("❌ Kein AI-Rezept gefunden")
            
            break
            
        elif data["status"] == "FAILURE":
            print(f"❌ Fehler: {data.get('error', 'Unbekannt')}")
            break
        else:
            print(f"⏳ Status: {data['status']} (Versuch {i+1}/30)")
    
    print("\n✅ Test beendet")

if __name__ == "__main__":
    simple_test()
