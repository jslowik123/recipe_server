import os
import logging
import base64
from typing import Dict, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class ClothingAI:
    """
    AI-Klasse für die Analyse von Kleidungsstücken mit OpenAI Vision API
    """
    
    def __init__(self, api_key: str = None):
        """
        Initialisiert die ClothingAI
        
        Args:
            api_key: OpenAI API Key (falls nicht als ENV Variable gesetzt)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        
        if not self.api_key:
            raise ValueError("OpenAI API Key muss gesetzt sein")
        
        self.client = OpenAI(api_key=self.api_key)
        self.logger = logging.getLogger(__name__)
    
    def analyze_clothing_image(self, image_content: bytes) -> Dict[str, Any]:
        """
        Analysiert ein Kleidungsstück-Bild mit OpenAI Vision API
        
        Args:
            image_content: Binärdaten des Bildes
            
        Returns:
            Dict mit erkannten Eigenschaften des Kleidungsstücks
        """
        try:
            # Bild zu Base64 konvertieren
            image_base64 = base64.b64encode(image_content).decode('utf-8')
            
            # Prompt für Kleidungsanalyse
            system_prompt = """
            Du bist ein Experte für Kleidung und Mode. Analysiere das hochgeladene Bild eines Kleidungsstücks und gib die Informationen in folgendem JSON-Format zurück:

            {
                "category": "Kategorie des Kleidungsstücks",
                "color": "Hauptfarbe",
                "style": "Stil des Kleidungsstücks", 
                "season": "Passende Saison",
                "material": "Vermutetes Material",
                "occasion": "Geeigneter Anlass",
                "confidence": "Vertrauenswert der Analyse (0-1)"
            }

            Kategorien: Oberteil, Hose, Kleid, Rock, Jacke, Mantel, Pullover, T-Shirt, Hemd, Bluse, Shorts, Jeans, Schuhe, Stiefel, Sneaker, Sandalen, Accessoire, Gürtel, Mütze, Schal

            Farben: schwarz, weiß, grau, braun, beige, rot, rosa, orange, gelb, grün, blau, lila, bunt, gemustert

            Stile: casual, elegant, sportlich, business, vintage, modern, bohemian, minimalistisch, extravagant

            Saisons: Frühling, Sommer, Herbst, Winter, Ganzjährig, Übergangszeit

            Anlässe: Alltag, Arbeit, Sport, Freizeit, Ausgehen, Formal, Strand, Zuhause

            Antworte NUR mit dem JSON-Objekt, ohne zusätzlichen Text.
            """
            
            # API-Aufruf
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Analysiere dieses Kleidungsstück:"
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=500,
                temperature=0.3
            )
            
            # Response verarbeiten
            content = response.choices[0].message.content.strip()
            
            # JSON parsen
            import json
            try:
                analysis_result = json.loads(content)
                
                # Validierung und Defaults
                result = self._validate_and_normalize_result(analysis_result)
                
                self.logger.info(f"Kleidungsanalyse erfolgreich: {result['category']}")
                return result
                
            except json.JSONDecodeError:
                self.logger.error(f"Konnte AI-Response nicht als JSON parsen: {content}")
                return self._get_fallback_result()
                
        except Exception as e:
            self.logger.error(f"Fehler bei der Kleidungsanalyse: {e}")
            return self._get_fallback_result()
    
    def _validate_and_normalize_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validiert und normalisiert das AI-Analyseergebnis
        
        Args:
            result: Rohes AI-Ergebnis
            
        Returns:
            Validiertes und normalisiertes Ergebnis
        """
        # Erlaubte Werte definieren
        allowed_categories = [
            "Oberteil", "Hose", "Kleid", "Rock", "Jacke", "Mantel", "Pullover", 
            "T-Shirt", "Hemd", "Bluse", "Shorts", "Jeans", "Schuhe", "Stiefel", 
            "Sneaker", "Sandalen", "Accessoire", "Gürtel", "Mütze", "Schal"
        ]
        
        allowed_colors = [
            "schwarz", "weiß", "grau", "braun", "beige", "rot", "rosa", "orange", 
            "gelb", "grün", "blau", "lila", "bunt", "gemustert"
        ]
        
        allowed_styles = [
            "casual", "elegant", "sportlich", "business", "vintage", "modern", 
            "bohemian", "minimalistisch", "extravagant"
        ]
        
        allowed_seasons = [
            "Frühling", "Sommer", "Herbst", "Winter", "Ganzjährig", "Übergangszeit"
        ]
        
        # Validierung mit Fallbacks
        validated_result = {
            "category": result.get("category", "Oberteil"),
            "color": result.get("color", "unbekannt"),
            "style": result.get("style", "casual"),
            "season": result.get("season", "Ganzjährig"),
            "material": result.get("material", "unbekannt"),
            "occasion": result.get("occasion", "Alltag"),
            "confidence": float(result.get("confidence", 0.8))
        }
        
        # Kategorie validieren
        if validated_result["category"] not in allowed_categories:
            validated_result["category"] = "Oberteil"
        
        # Farbe validieren
        if validated_result["color"] not in allowed_colors:
            validated_result["color"] = "unbekannt"
            
        # Stil validieren
        if validated_result["style"] not in allowed_styles:
            validated_result["style"] = "casual"
            
        # Saison validieren
        if validated_result["season"] not in allowed_seasons:
            validated_result["season"] = "Ganzjährig"
        
        return validated_result
    
    def _get_fallback_result(self) -> Dict[str, Any]:
        """
        Gibt ein Standard-Ergebnis zurück falls die AI-Analyse fehlschlägt
        
        Returns:
            Standard-Analyseergebnis
        """
        return {
            "category": "Oberteil",
            "color": "unbekannt", 
            "style": "casual",
            "season": "Ganzjährig",
            "material": "unbekannt",
            "occasion": "Alltag",
            "confidence": 0.0
        }
    
    
    def encode_image(self, image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def extract_clothing(self, image_content: bytes) -> bytes:
        """
        Extrahiert Kleidungsstücke aus einem Bild mit OpenAI Responses API
        Verwendet image_generation tool um das Kleidungsstück auf weißem Hintergrund zu generieren

        Args:
            image_content: Binärdaten des Bildes

        Returns:
            bytes: Generiertes Bild als PNG-Bytes
        """
        try:
            # Eingehende Bildbytes in Base64 konvertieren
            base64_image = base64.b64encode(image_content).decode("utf-8")

            prompt = "Erstelle ein fotorealistisches Bild des Kleidungsstücks aus dem Referenzbild, isoliert auf weißem Hintergrund. Entferne den Hintergrund und zeige nur das Kleidungsstück."

            response = self.client.responses.create(
                model="gpt-4o",  # Model für reasoning/understanding
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": prompt},
                            {
                                "type": "input_image",
                                "image_url": f"data:image/jpeg;base64,{base64_image}",
                            },
                        ],
                    }
                ],
                tools=[{
                    "type": "image_generation",
                    "model": "gpt-image-1",  # Spezifisches Model für Image Generation
                    "background": "opaque",  # Weißer Hintergrund
                }],
            )

            # Extrahiere image_generation_call aus der Response
            image_generation_calls = [
                output for output in response.output if output.type == "image_generation_call"
            ]

            if image_generation_calls:
                # Das generierte Bild ist in base64 im result
                generated_image_base64 = image_generation_calls[0].result
                generated_image_bytes = base64.b64decode(generated_image_base64)

                self.logger.info(f"Kleidungsstück erfolgreich extrahiert ({len(generated_image_bytes)} bytes)")
                return generated_image_bytes
            else:
                raise RuntimeError("Image generation call fehlgeschlagen - keine Bild-Generierung in der Response")
        except Exception as e:
            self.logger.error(f"Fehler bei der Kleidungsextraktion: {e}")
            raise
    
    def health_check(self) -> bool:
        """
        Überprüft die Verbindung zur OpenAI API
        
        Returns:
            True wenn API erreichbar ist
        """
        try:
            # Einfacher Test-Call zur OpenAI API
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Hallo"}],
                max_tokens=5
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Health Check fehlgeschlagen: {e}")
            return False

            

