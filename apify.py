import requests
from apify_client import ApifyClient
from openai import OpenAI
from dotenv import load_dotenv

# Initialisiere den Apify-Client mit deinem API-Token
client = ApifyClient("apify_api_iYcAqVugvyZlguYWGWoOY5DVwbDKI83GSqR2")

# Definiere die Eingaben für den TikTok Scraper
run_input = {
    "postURLs": ["https://www.tiktok.com/@simple.home.edit/video/7309754078010051841?q=recipe&t=1754926838675"],
    "scrapeRelatedVideos": False,
    "resultsPerPage": 1,
    "shouldDownloadVideos": False,
    "shouldDownloadCovers": False,
    "shouldDownloadSubtitles": True,
    "shouldDownloadSlideshowImages": False,
}
# Starte den TikTok Scraper Actor
run = client.actor("S5h7zRLfKFEr8pdj7").call(run_input=run_input)

# Prüfe, ob der Run erfolgreich war und ein Dataset existiert
if run and "defaultDatasetId" in run:
    dataset_id = run["defaultDatasetId"]
    print(f"Daten sind hier verfügbar: https://console.apify.com/storage/datasets/{dataset_id}")

    # Hole die Ergebnisse aus dem Dataset
    for item in client.dataset(dataset_id).iterate_items():
        text = item["text"]
        
        # Check if subtitles exist before accessing
        if "videoMeta" in item and "subtitleLinks" in item["videoMeta"] and len(item["videoMeta"]["subtitleLinks"]) > 0:
            subtitle_url = item["videoMeta"]["subtitleLinks"][0]["downloadLink"]
            print(f"Subtitle URL: {subtitle_url}")
            
            # Download subtitle content
            transcript_response = requests.get(subtitle_url)
            if transcript_response.status_code == 200:
                transcript_content = transcript_response.text
                print(f"Transcript content:\n{transcript_content}")
            else:
                print(f"Failed to download transcript: {transcript_response.status_code}")
        else:
            print("No subtitles available for this video")
        
        print(f"Video text: {text}")
else:
    print("Der Actor konnte nicht ausgeführt werden oder hat kein Dataset erstellt.")

# load_dotenv()
# client = OpenAI()

# response = client.responses.create(
#     model="gpt-5-mini",
#     input=f"You are an expert in creating a structured recipe based on a given Text. Return a clean recipe based on the following text: {text}"
# )

# print(response.output_text)

