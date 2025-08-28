from locust import HttpUser, task
import time
from test import SupabaseJWTGenerator


class TikTokScraperUser(HttpUser):
    host = "https://api.recipifydata.com"
    
    def on_start(self):
        # JWT Token bei User-Start generieren
        self.jwt_generator = SupabaseJWTGenerator()
        self.token = self.jwt_generator.create_jwt()
        self.has_run = False
    
    @task
    def scrape_and_poll(self):
        if self.has_run:
            return  # Task nur einmal ausführen
        
        self.has_run = True
        # Start scraping task
        response = self.client.post("/scrape/async", 
            json={"url": "https://www.tiktok.com/@test/video/123"},
            headers={"Authorization": f"Bearer {self.token}"}
        )
        
        if response.status_code == 200:
            task_id = response.json()["task_id"]
            
            # Poll until complete
            while True:
                status_response = self.client.get(f"/task/{task_id}",
                    headers={"Authorization": f"Bearer {self.token}"}
                )
                
                if status_response.status_code == 200:
                    status = status_response.json().get("status")
                    if status in ["SUCCESS", "FAILURE"]:
                        break
                
                time.sleep(3)
