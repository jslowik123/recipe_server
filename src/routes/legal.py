from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
import markdown


router = APIRouter(prefix="/legal", tags=["legal"])


def get_legal_document(doc_type: str, lang: str = "de") -> dict:
    """
    Load legal document from legal/{lang}/{doc_type}_content_{lang}.md

    Args:
        doc_type: Type of document (privacy_policy, terms_of_service, imprint)
        lang: Language code (de, en)

    Returns:
        dict with content and metadata
    """
    # Validate inputs
    valid_types = ["privacy_policy", "terms_of_service", "imprint"]
    valid_langs = ["de", "en"]

    if doc_type not in valid_types:
        raise HTTPException(status_code=404, detail=f"Invalid document type. Must be one of: {', '.join(valid_types)}")

    if lang not in valid_langs:
        raise HTTPException(status_code=400, detail=f"Invalid language. Supported: {', '.join(valid_langs)}")

    # Build file path using your naming convention
    file_path = Path("legal") / lang / f"{doc_type}_content_{lang}.md"

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Document not found: {doc_type} ({lang}). Please create {file_path}"
        )

    try:
        content = file_path.read_text(encoding="utf-8")
        return {
            "type": doc_type,
            "language": lang,
            "content": content,
            "path": str(file_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read document: {str(e)}")


def render_legal_html(doc: dict) -> str:
    """
    Render legal document as HTML page

    Args:
        doc: Document dict from get_legal_document()

    Returns:
        HTML string
    """
    html_content = markdown.markdown(doc["content"])

    # Map document types to titles and routes
    titles = {
        "privacy_policy": {"de": "Datenschutzerklärung", "en": "Privacy Policy"},
        "terms_of_service": {"de": "Nutzungsbedingungen", "en": "Terms of Service"},
        "imprint": {"de": "Impressum", "en": "Imprint"}
    }

    routes = {
        "privacy_policy": "privacy",
        "terms_of_service": "terms",
        "imprint": "imprint"
    }

    title = titles.get(doc["type"], {}).get(doc["language"], "Legal Document")
    route = routes.get(doc["type"], "")
    current_lang = doc["language"]
    other_lang = "en" if current_lang == "de" else "de"
    other_lang_label = "English" if current_lang == "de" else "Deutsch"

    return f"""<!DOCTYPE html>
<html lang="{doc['language']}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            color: #333;
        }}
        .language-switcher {{
            position: absolute;
            top: 20px;
            right: 20px;
            display: flex;
            gap: 10px;
        }}
        .language-switcher a {{
            text-decoration: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 0.9em;
            transition: all 0.3s;
        }}
        .language-switcher a.active {{
            background: #007AFF;
            color: white;
            font-weight: 600;
        }}
        .language-switcher a:not(.active) {{
            background: #f0f0f0;
            color: #666;
        }}
        .language-switcher a:not(.active):hover {{
            background: #e0e0e0;
            color: #333;
        }}
        h1 {{
            border-bottom: 2px solid #007AFF;
            padding-bottom: 10px;
            margin-top: 40px;
        }}
        h2 {{
            margin-top: 30px;
            color: #007AFF;
        }}
        h3 {{
            margin-top: 20px;
        }}
        a {{
            color: #007AFF;
        }}
        @media (max-width: 600px) {{
            body {{
                padding: 10px;
                padding-top: 60px;
            }}
            .language-switcher {{
                top: 10px;
                right: 10px;
            }}
            h1 {{
                margin-top: 20px;
            }}
        }}
    </style>
</head>
<body>
    <div class="language-switcher">
        <a href="/legal/{route}?lang=de&format=html" class="{'active' if current_lang == 'de' else ''}">Deutsch</a>
        <a href="/legal/{route}?lang=en&format=html" class="{'active' if current_lang == 'en' else ''}">English</a>
    </div>
    {html_content}
</body>
</html>"""


@router.get("/privacy")
def get_privacy_policy(lang: str = Query("de", regex="^(de|en)$"), format: str = Query("json", regex="^(json|html)$")):
    """
    Get privacy policy / Datenschutzerklärung

    Query params:
    - lang: de or en (default: de)
    - format: json or html (default: json)

    Examples:
    - /legal/privacy?lang=de&format=html
    - /legal/privacy?lang=en&format=json
    """
    doc = get_legal_document("privacy_policy", lang)

    if format == "html":
        return HTMLResponse(content=render_legal_html(doc))

    return JSONResponse(content={
        "type": doc["type"],
        "language": doc["language"],
        "content": doc["content"]
    })


@router.get("/terms")
def get_terms_of_service(lang: str = Query("de", regex="^(de|en)$"), format: str = Query("json", regex="^(json|html)$")):
    """
    Get terms of service / Nutzungsbedingungen

    Query params:
    - lang: de or en (default: de)
    - format: json or html (default: json)

    Examples:
    - /legal/terms?lang=de&format=html
    - /legal/terms?lang=en&format=json
    """
    doc = get_legal_document("terms_of_service", lang)

    if format == "html":
        return HTMLResponse(content=render_legal_html(doc))

    return JSONResponse(content={
        "type": doc["type"],
        "language": doc["language"],
        "content": doc["content"]
    })


@router.get("/imprint")
def get_imprint(lang: str = Query("de", regex="^(de|en)$"), format: str = Query("json", regex="^(json|html)$")):
    """
    Get imprint / Impressum

    Query params:
    - lang: de or en (default: de)
    - format: json or html (default: json)

    Examples:
    - /legal/imprint?lang=de&format=html
    - /legal/imprint?lang=en&format=json
    """
    doc = get_legal_document("imprint", lang)

    if format == "html":
        return HTMLResponse(content=render_legal_html(doc))

    return JSONResponse(content={
        "type": doc["type"],
        "language": doc["language"],
        "content": doc["content"]
    })
