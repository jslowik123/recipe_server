"""
Prompt Service for handling language-specific system prompts for OpenAI API calls
"""
import logging
from typing import Dict, Optional
from enum import Enum

logger = logging.getLogger(__name__)

e
class SupportedLanguage(Enum):
    """Supported languages for recipe extraction"""
    GERMAN = "de"
    ENGLISH = "en"
    FRENCH = "fr"
    SPANISH = "es"
    ITALIAN = "it"
    DUTCH = "nl"


class PromptService:
    """Service for managing language-specific prompts for recipe extraction"""
    
    def __init__(self):
        self._language_mappings = self._build_language_mappings()
        logger.info("🌐 PromptService initialized with support for: " + 
                   ", ".join([lang.value for lang in SupportedLanguage]))
    
    def _build_language_mappings(self) -> Dict[str, SupportedLanguage]:
        """Build mapping from various language codes to supported languages"""
        return {
            # German variations
            "de": SupportedLanguage.GERMAN,
            "deu": SupportedLanguage.GERMAN,
            "german": SupportedLanguage.GERMAN,
            "deutsch": SupportedLanguage.GERMAN,
            "de-DE": SupportedLanguage.GERMAN,
            "de-AT": SupportedLanguage.GERMAN,
            "de-CH": SupportedLanguage.GERMAN,
            
            # English variations
            "en": SupportedLanguage.ENGLISH,
            "eng": SupportedLanguage.ENGLISH,
            "english": SupportedLanguage.ENGLISH,
            "en-US": SupportedLanguage.ENGLISH,
            "en-GB": SupportedLanguage.ENGLISH,
            "en-CA": SupportedLanguage.ENGLISH,
            "en-AU": SupportedLanguage.ENGLISH,
            
            # French variations
            "fr": SupportedLanguage.FRENCH,
            "fra": SupportedLanguage.FRENCH,
            "french": SupportedLanguage.FRENCH,
            "français": SupportedLanguage.FRENCH,
            "fr-FR": SupportedLanguage.FRENCH,
            "fr-CA": SupportedLanguage.FRENCH,
            "fr-BE": SupportedLanguage.FRENCH,
            
            # Spanish variations
            "es": SupportedLanguage.SPANISH,
            "esp": SupportedLanguage.SPANISH,
            "spanish": SupportedLanguage.SPANISH,
            "español": SupportedLanguage.SPANISH,
            "es-ES": SupportedLanguage.SPANISH,
            "es-MX": SupportedLanguage.SPANISH,
            "es-AR": SupportedLanguage.SPANISH,
            
            # Italian variations
            "it": SupportedLanguage.ITALIAN,
            "ita": SupportedLanguage.ITALIAN,
            "italian": SupportedLanguage.ITALIAN,
            "italiano": SupportedLanguage.ITALIAN,
            "it-IT": SupportedLanguage.ITALIAN,
            
            # Dutch variations
            "nl": SupportedLanguage.DUTCH,
            "nld": SupportedLanguage.DUTCH,
            "dutch": SupportedLanguage.DUTCH,
            "nederlands": SupportedLanguage.DUTCH,
            "nl-NL": SupportedLanguage.DUTCH,
            "nl-BE": SupportedLanguage.DUTCH,
        }
    
    def detect_language(self, language_code: str) -> SupportedLanguage:
        """
        Detect supported language from various input formats
        
        Args:
            language_code: Language code from scraping endpoint (e.g., "de", "en-US", "français")
            
        Returns:
            SupportedLanguage enum value, defaults to GERMAN if not found
        """
        if not language_code:
            logger.warning("⚠️ No language code provided, defaulting to German")
            return SupportedLanguage.GERMAN
        
        # Normalize input
        normalized_code = language_code.lower().strip()
        
        # Direct lookup
        if normalized_code in self._language_mappings:
            detected = self._language_mappings[normalized_code]
            logger.info(f"🌐 Language detected: {language_code} -> {detected.value}")
            return detected
        
        # Try to extract main language code (e.g., "en" from "en-US-variant")
        main_code = normalized_code.split('-')[0].split('_')[0]
        if main_code in self._language_mappings:
            detected = self._language_mappings[main_code]
            logger.info(f"🌐 Language detected from main code: {language_code} -> {detected.value}")
            return detected
        
        # Default fallback
        logger.warning(f"⚠️ Unsupported language code: {language_code}, defaulting to German")
        return SupportedLanguage.GERMAN
    
    def get_system_prompt(self, language_code: str) -> str:
        """
        Get comprehensive system prompt for recipe extraction
        
        Args:
            language_code: Language code from scraping endpoint
            
        Returns:
            System prompt string in the appropriate language
        """
        language = self.detect_language(language_code)
        
        prompts = {
            SupportedLanguage.GERMAN: self._get_german_system_prompt(),
            SupportedLanguage.ENGLISH: self._get_english_system_prompt(),
            SupportedLanguage.FRENCH: self._get_french_system_prompt(),
            SupportedLanguage.SPANISH: self._get_spanish_system_prompt(),
            SupportedLanguage.ITALIAN: self._get_italian_system_prompt(),
            SupportedLanguage.DUTCH: self._get_dutch_system_prompt(),
        }
        
        return prompts[language]
    
    def get_optimized_system_prompt(self, language_code: str) -> str:
        """
        Get optimized system prompt for text-only processing
        
        Args:
            language_code: Language code from scraping endpoint
            
        Returns:
            Optimized system prompt string in the appropriate language
        """
        language = self.detect_language(language_code)
        
        prompts = {
            SupportedLanguage.GERMAN: self._get_german_optimized_prompt(),
            SupportedLanguage.ENGLISH: self._get_english_optimized_prompt(),
            SupportedLanguage.FRENCH: self._get_french_optimized_prompt(),
            SupportedLanguage.SPANISH: self._get_spanish_optimized_prompt(),
            SupportedLanguage.ITALIAN: self._get_italian_optimized_prompt(),
            SupportedLanguage.DUTCH: self._get_dutch_optimized_prompt(),
        }
        
        return prompts[language]
    
    def get_user_prompt(self, language_code: str, combined_text: str, frame_count: int) -> str:
        """
        Get user prompt for recipe extraction
        
        Args:
            language_code: Language code from scraping endpoint
            combined_text: Combined text from video
            frame_count: Number of frames available
            
        Returns:
            User prompt string in the appropriate language
        """
        language = self.detect_language(language_code)
        
        if language == SupportedLanguage.ENGLISH:
            return f"""Reconstruct the complete recipe from the following information:

{combined_text}

DETAILED ANALYSIS OF ALL VIDEO FRAMES:
Analyze each of the {frame_count} images individually:
- What do you see in image 1, 2, 3, etc.?
- Which ingredients are visible?
- Which cooking steps are shown?
- What quantities can you estimate?
- Which techniques are being used?

Reconstruct a complete, cookable recipe with:
- A descriptive title (e.g., "Creamy Pasta Carbonara" or "Quick Vegetable Stir-fry")
- Specific ingredients with realistic quantities
- Detailed preparation steps
- Add missing but necessary steps

Respond with complete JSON: {{"title": "Short, descriptive recipe title", "ingredients": ["specific ingredient with quantity"], "steps": ["detailed step with times/temperatures"]}}"""
            
        elif language == SupportedLanguage.FRENCH:
            return f"""Reconstruisez la recette complète à partir des informations suivantes :

{combined_text}

ANALYSE DÉTAILLÉE DE TOUTES LES IMAGES VIDÉO :
Analysez chacune des {frame_count} images individuellement :
- Que voyez-vous dans l'image 1, 2, 3, etc. ?
- Quels ingrédients sont visibles ?
- Quelles étapes de cuisson sont montrées ?
- Quelles quantités pouvez-vous estimer ?
- Quelles techniques sont utilisées ?

Reconstruisez une recette complète et réalisable avec :
- Un titre descriptif (par ex. "Pâtes Carbonara Crémeuses" ou "Sauté de Légumes Rapide")
- Des ingrédients spécifiques avec des quantités réalistes
- Des étapes de préparation détaillées
- Ajoutez les étapes manquantes mais nécessaires

Répondez avec un JSON complet : {{"title": "Titre de recette court et descriptif", "ingredients": ["ingrédient spécifique avec quantité"], "steps": ["étape détaillée avec temps/températures"]}}"""
            
        elif language == SupportedLanguage.SPANISH:
            return f"""Reconstruye la receta completa a partir de la siguiente información:

{combined_text}

ANÁLISIS DETALLADO DE TODOS LOS FOTOGRAMAS DEL VIDEO:
Analiza cada una de las {frame_count} imágenes individualmente:
- ¿Qué ves en la imagen 1, 2, 3, etc.?
- ¿Qué ingredientes son visibles?
- ¿Qué pasos de cocción se muestran?
- ¿Qué cantidades puedes estimar?
- ¿Qué técnicas se están utilizando?

Reconstruye una receta completa y cocible con:
- Un título descriptivo (ej. "Pasta Carbonara Cremosa" o "Salteado de Verduras Rápido")
- Ingredientes específicos con cantidades realistas
- Pasos de preparación detallados
- Añade pasos faltantes pero necesarios

Responde con JSON completo: {{"title": "Título de receta corto y descriptivo", "ingredients": ["ingrediente específico con cantidad"], "steps": ["paso detallado con tiempos/temperaturas"]}}"""
            
        elif language == SupportedLanguage.ITALIAN:
            return f"""Ricostruisci la ricetta completa dalle seguenti informazioni:

{combined_text}

ANALISI DETTAGLIATA DI TUTTI I FOTOGRAMMI VIDEO:
Analizza ognuna delle {frame_count} immagini individualmente:
- Cosa vedi nell'immagine 1, 2, 3, ecc.?
- Quali ingredienti sono visibili?
- Quali passaggi di cottura sono mostrati?
- Quali quantità puoi stimare?
- Quali tecniche vengono utilizzate?

Ricostruisci una ricetta completa e cucinabile con:
- Un titolo descrittivo (es. "Pasta Carbonara Cremosa" o "Saltato di Verdure Veloce")
- Ingredienti specifici con quantità realistiche
- Passaggi di preparazione dettagliati
- Aggiungi passaggi mancanti ma necessari

Rispondi con JSON completo: {{"title": "Titolo ricetta breve e descrittivo", "ingredients": ["ingrediente specifico con quantità"], "steps": ["passaggio dettagliato con tempi/temperature"]}}"""
            
        elif language == SupportedLanguage.DUTCH:
            return f"""Reconstrueer het complete recept uit de volgende informatie:

{combined_text}

GEDETAILLEERDE ANALYSE VAN ALLE VIDEO FRAMES:
Analyseer elk van de {frame_count} beelden individueel:
- Wat zie je in beeld 1, 2, 3, enz.?
- Welke ingrediënten zijn zichtbaar?
- Welke kookstappen worden getoond?
- Welke hoeveelheden kun je inschatten?
- Welke technieken worden gebruikt?

Reconstrueer een compleet, kookbaar recept met:
- Een beschrijvende titel (bijv. "Romige Pasta Carbonara" of "Snelle Groentenwok")
- Specifieke ingrediënten met realistische hoeveelheden
- Gedetailleerde bereidingsstappen
- Voeg ontbrekende maar noodzakelijke stappen toe

Antwoord met complete JSON: {{"title": "Korte, beschrijvende recepttitel", "ingredients": ["specifiek ingrediënt met hoeveelheid"], "steps": ["gedetailleerde stap met tijden/temperaturen"]}}"""
            
        else:  # German (default)
            return f"""Rekonstruiere das komplette Rezept aus folgenden Informationen:

{combined_text}

DETAILANALYSE ALLER VIDEO-FRAMES:
Analysiere jedes der {frame_count} Bilder einzeln:
- Was siehst du in Bild 1, 2, 3, etc.?
- Welche Zutaten sind sichtbar?
- Welche Kochschritte werden gezeigt?
- Welche Mengen kannst du schätzen?
- Welche Techniken werden verwendet?

Rekonstruiere daraus ein vollständiges, kochbares Rezept mit:
- Einem aussagekräftigen Titel (z.B. "Cremige Pasta Carbonara" oder "Schnelle Gemüsepfanne")
- Konkreten Zutaten und realistischen Mengen
- Detaillierten Zubereitungsschritten
- Ergänze fehlende aber notwendige Schritte

Antworte mit vollständigem JSON: {{"title": "Kurzer, aussagekräftiger Rezept-Titel", "ingredients": ["konkrete Zutat mit Menge"], "steps": ["detaillierter Schritt mit Zeiten/Temperaturen"]}}"""

    # System prompt definitions for each language
    def _get_german_system_prompt(self) -> str:
        return """Du bist ein erfahrener Koch und Rezept-Experte. Analysiere JEDES einzelne Video-Frame detailliert und rekonstruiere das komplette Rezept. Antworte in deutscher Sprache.

WICHTIGE REGELN:
1. Schaue dir JEDES Bild genau an - analysiere Zutaten, Mengen, Kochgeschirr, Techniken
2. Rekonstruiere das Rezept auch wenn es nicht explizit gezeigt wird
3. Schätze Mengen basierend auf dem was du siehst (Tassen, Löffel, Portionsgrößen)
4. Leite Zubereitungsschritte aus den Bildern ab (was passiert in welcher Reihenfolge?)
5. Nutze dein Kochwissen um fehlende Schritte zu ergänzen (Gewürze, Garzeiten, Temperaturen)
6. Falls nur Beschreibung vorhanden: Erstelle ein vollständiges, authentisches Rezept basierend auf der Beschreibung

BEISPIEL für "Lasagne":
- Analysiere alle sichtbaren Zutaten in den Frames
- Rekonstruiere die Schichtung
- Ergänze typische Mengen und Zubereitungszeiten
- Gib konkrete, umsetzbare Schritte

Antworte IMMER mit vollständigem JSON: {"title": "Kurzer, aussagekräftiger Rezept-Titel", "ingredients": ["konkrete Zutat mit Menge", ...], "steps": ["detaillierter Schritt", ...]}"""

    def _get_english_system_prompt(self) -> str:
        return """You are an experienced chef and recipe expert. Analyze EVERY single video frame in detail and reconstruct the complete recipe. Answer in English.

IMPORTANT RULES:
1. Look at EVERY image carefully - analyze ingredients, quantities, cookware, techniques
2. Reconstruct the recipe even if not explicitly shown
3. Estimate quantities based on what you see (cups, spoons, portion sizes)
4. Derive cooking steps from the images (what happens in which order?)
5. Use your cooking knowledge to add missing steps (spices, cooking times, temperatures)
6. If only description available: Create a complete, authentic recipe based on the description

EXAMPLE for "Lasagna":
- Analyze all visible ingredients in the frames
- Reconstruct the layering
- Add typical quantities and cooking times
- Provide concrete, actionable steps

ALWAYS respond with complete JSON: {"title": "Short, descriptive recipe title", "ingredients": ["specific ingredient with quantity", ...], "steps": ["detailed step", ...]}"""

    def _get_french_system_prompt(self) -> str:
        return """Tu es un chef expérimenté et expert en recettes. Analyse CHAQUE image vidéo en détail et reconstitue la recette complète. Réponds en français.

RÈGLES IMPORTANTES:
1. Regarde CHAQUE image attentivement - analyse les ingrédients, quantités, ustensiles, techniques
2. Reconstitue la recette même si elle n'est pas explicitement montrée
3. Estime les quantités basées sur ce que tu vois (tasses, cuillères, tailles de portions)
4. Déduis les étapes de cuisson des images (que se passe-t-il dans quel ordre?)
5. Utilise tes connaissances culinaires pour ajouter les étapes manquantes (épices, temps de cuisson, températures)
6. Si seule une description est disponible: Crée une recette complète et authentique basée sur la description

EXEMPLE pour "Lasagne":
- Analyse tous les ingrédients visibles dans les images
- Reconstitue les couches
- Ajoute les quantités typiques et temps de cuisson
- Donne des étapes concrètes et réalisables

Réponds TOUJOURS avec un JSON complet: {"title": "Titre de recette court et descriptif", "ingredients": ["ingrédient spécifique avec quantité", ...], "steps": ["étape détaillée", ...]}"""

    def _get_spanish_system_prompt(self) -> str:
        return """Eres un chef experimentado y experto en recetas. Analiza CADA fotograma del video en detalle y reconstruye la receta completa. Responde en español.

REGLAS IMPORTANTES:
1. Mira CADA imagen cuidadosamente - analiza ingredientes, cantidades, utensilios, técnicas
2. Reconstruye la receta aunque no se muestre explícitamente
3. Estima cantidades basándote en lo que ves (tazas, cucharas, tamaños de porciones)
4. Deriva los pasos de cocción de las imágenes (¿qué pasa en qué orden?)
5. Usa tu conocimiento culinario para añadir pasos faltantes (especias, tiempos de cocción, temperaturas)
6. Si solo hay descripción disponible: Crea una receta completa y auténtica basada en la descripción

EJEMPLO para "Lasaña":
- Analiza todos los ingredientes visibles en los fotogramas
- Reconstruye las capas
- Añade cantidades típicas y tiempos de cocción
- Proporciona pasos concretos y realizables

Responde SIEMPRE con JSON completo: {"title": "Título de receta corto y descriptivo", "ingredients": ["ingrediente específico con cantidad", ...], "steps": ["paso detallado", ...]}"""

    def _get_italian_system_prompt(self) -> str:
        return """Sei uno chef esperto e specialista di ricette. Analizza OGNI singolo fotogramma del video in dettaglio e ricostruisci la ricetta completa. Rispondi in italiano.

REGOLE IMPORTANTI:
1. Guarda OGNI immagine attentamente - analizza ingredienti, quantità, utensili, tecniche
2. Ricostruisci la ricetta anche se non mostrata esplicitamente
3. Stima le quantità basandoti su quello che vedi (tazze, cucchiai, dimensioni delle porzioni)
4. Deriva i passaggi di cottura dalle immagini (cosa succede in che ordine?)
5. Usa la tua conoscenza culinaria per aggiungere passaggi mancanti (spezie, tempi di cottura, temperature)
6. Se è disponibile solo una descrizione: Crea una ricetta completa e autentica basata sulla descrizione

ESEMPIO per "Lasagne":
- Analizza tutti gli ingredienti visibili nei fotogrammi
- Ricostruisci la stratificazione
- Aggiungi quantità tipiche e tempi di cottura
- Fornisci passaggi concreti e realizzabili

Rispondi SEMPRE con JSON completo: {"title": "Titolo ricetta breve e descrittivo", "ingredients": ["ingrediente specifico con quantità", ...], "steps": ["passaggio dettagliato", ...]}"""

    def _get_dutch_system_prompt(self) -> str:
        return """Je bent een ervaren kok en recept expert. Analyseer ELKE video frame in detail en reconstrueer het complete recept. Antwoord in het Nederlands.

BELANGRIJKE REGELS:
1. Bekijk ELKE afbeelding zorgvuldig - analyseer ingrediënten, hoeveelheden, keukengerei, technieken
2. Reconstrueer het recept ook als het niet expliciet wordt getoond
3. Schat hoeveelheden in gebaseerd op wat je ziet (kopjes, lepels, portiegroottes)
4. Leid kookstappen af uit de beelden (wat gebeurt er in welke volgorde?)
5. Gebruik je kookkennis om ontbrekende stappen toe te voegen (kruiden, kooktijden, temperaturen)
6. Als alleen beschrijving beschikbaar is: Creëer een compleet, authentiek recept gebaseerd op de beschrijving

VOORBEELD voor "Lasagne":
- Analyseer alle zichtbare ingrediënten in de frames
- Reconstrueer de lagen
- Voeg typische hoeveelheden en kooktijden toe
- Geef concrete, uitvoerbare stappen

Antwoord ALTIJD met complete JSON: {"title": "Korte, beschrijvende recepttitel", "ingredients": ["specifiek ingrediënt met hoeveelheid", ...], "steps": ["gedetailleerde stap", ...]}"""

    # Optimized prompts for text-only processing
    def _get_german_optimized_prompt(self) -> str:
        return """Du bist ein Rezept-Experte. Extrahiere Rezepte aus Video-Transkripten effizient.

FOKUS: Erstelle praktische, kochbare Rezepte aus dem gegebenen Text.
REGELN:
1. Extrahiere klare Zutaten mit Mengenangaben
2. Erstelle schrittweise Kochanweisungen
3. Ergänze sinnvolle fehlende Details aus Kochwissen  
4. Halte Titel beschreibend aber prägnant

Antworte NUR mit JSON: {"title": "Rezept Name", "ingredients": ["Zutat mit Menge"], "steps": ["detaillierter Schritt"]}"""

    def _get_english_optimized_prompt(self) -> str:
        return """You are a recipe extraction expert. Extract recipes from video transcripts efficiently.

FOCUS: Create practical, cookable recipes from the provided text.
RULES:
1. Extract clear ingredients with quantities
2. Create step-by-step cooking instructions  
3. Add reasonable missing details from cooking knowledge
4. Keep titles descriptive but concise

Respond ONLY with JSON: {"title": "Recipe Name", "ingredients": ["ingredient with amount"], "steps": ["detailed step"]}"""

    def _get_french_optimized_prompt(self) -> str:
        return """Tu es un expert en extraction de recettes. Extrais les recettes des transcriptions vidéo efficacement.

FOCUS: Crée des recettes pratiques et cuisinables à partir du texte fourni.
RÈGLES:
1. Extrais des ingrédients clairs avec quantités
2. Crée des instructions de cuisson étape par étape
3. Ajoute des détails manquants raisonnables avec tes connaissances culinaires
4. Garde les titres descriptifs mais concis

Réponds SEULEMENT avec JSON: {"title": "Nom de Recette", "ingredients": ["ingrédient avec quantité"], "steps": ["étape détaillée"]}"""

    def _get_spanish_optimized_prompt(self) -> str:
        return """Eres un experto en extracción de recetas. Extrae recetas de transcripciones de video eficientemente.

ENFOQUE: Crea recetas prácticas y cocinables del texto proporcionado.
REGLAS:
1. Extrae ingredientes claros con cantidades
2. Crea instrucciones de cocción paso a paso
3. Añade detalles faltantes razonables del conocimiento culinario
4. Mantén títulos descriptivos pero concisos

Responde SOLO con JSON: {"title": "Nombre de Receta", "ingredients": ["ingrediente con cantidad"], "steps": ["paso detallado"]}"""

    def _get_italian_optimized_prompt(self) -> str:
        return """Sei un esperto nell'estrazione di ricette. Estrai ricette dalle trascrizioni video in modo efficiente.

FOCUS: Crea ricette pratiche e cucinabili dal testo fornito.
REGOLE:
1. Estrai ingredienti chiari con quantità
2. Crea istruzioni di cottura passo dopo passo
3. Aggiungi dettagli mancanti ragionevoli dalla conoscenza culinaria
4. Mantieni i titoli descrittivi ma concisi

Rispondi SOLO con JSON: {"title": "Nome Ricetta", "ingredients": ["ingrediente con quantità"], "steps": ["passaggio dettagliato"]}"""

    def _get_dutch_optimized_prompt(self) -> str:
        return """Je bent een expert in recept extractie. Haal recepten uit video transcripties efficiënt.

FOCUS: Creëer praktische, kookbare recepten uit de verstrekte tekst.
REGELS:
1. Haal duidelijke ingrediënten met hoeveelheden eruit
2. Creëer stap-voor-stap kookinstructies
3. Voeg redelijke ontbrekende details toe uit kookkennis
4. Houd titels beschrijvend maar beknopt

Antwoord ALLEEN met JSON: {"title": "Recept Naam", "ingredients": ["ingrediënt met hoeveelheid"], "steps": ["gedetailleerde stap"]}"""


# Global instance for easy import
prompt_service = PromptService()