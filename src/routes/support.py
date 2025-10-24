from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/support")
def get_support(lang: str = Query("en", regex="^(de|en)$")):
    """
    Support contact information for App Store

    Query params:
    - lang: de or en (default: de)

    Examples:
    - /support?lang=de
    - /support?lang=en
    """
    title = "Support" if lang == "en" else "Support"
    heading = "Support" if lang == "en" else "Support"
    text = "If you need assistance or have any questions, please contact us:" if lang == "en" else "Wenn Sie Unterstützung benötigen oder Fragen haben, kontaktieren Sie uns bitte:"
    email_label = "Email" if lang == "en" else "E-Mail"

    html_content = f"""<!DOCTYPE html>
<html lang="{lang}">
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
        .contact {{
            margin-top: 30px;
            font-size: 1.1em;
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
        <a href="/support?lang=de" class="{'active' if lang == 'de' else ''}">Deutsch</a>
        <a href="/support?lang=en" class="{'active' if lang == 'en' else ''}">English</a>
    </div>
    <h1>{heading}</h1>
    <div class="contact">
        <p>{text}</p>
        <p><strong>{email_label}:</strong> <a href="mailto:contact@resimply.app">contact@resimply.app</a></p>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html_content)
