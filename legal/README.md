# Legal Documents

Rechtliche Dokumente in Markdown-Format mit Lokalisierung.

## Struktur

```
legal/
├── de/
│   ├── privacy_policy_content_de.md       # Datenschutzerklärung
│   ├── terms_of_service_content_de.md     # Nutzungsbedingungen
│   └── imprint_content_de.md              # Impressum
└── en/
    ├── privacy_policy_content_en.md       # Privacy Policy
    ├── terms_of_service_content_en.md     # Terms of Service
    └── imprint_content_en.md              # Imprint
```

## API-Zugriff

**Privacy Policy / Datenschutzerklärung:**
- JSON (für App): `GET /legal/privacy?lang=de`
- HTML (für Browser/App Store): `GET /legal/privacy?lang=de&format=html`

**Terms of Service / Nutzungsbedingungen:**
- JSON: `GET /legal/terms?lang=de`
- HTML: `GET /legal/terms?lang=de&format=html`

**Imprint / Impressum:**
- JSON: `GET /legal/imprint?lang=de`
- HTML: `GET /legal/imprint?lang=de&format=html`

## App Store URLs

Verwende die HTML-Varianten für App Store Submissions:
- **Privacy Policy URL:** `https://your-domain.com/legal/privacy?lang=de&format=html`
- **Terms URL:** `https://your-domain.com/legal/terms?lang=de&format=html`