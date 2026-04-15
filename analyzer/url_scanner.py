"""
URL Safety Scanner — Heuristic-based URL threat analysis.
Extracts URLs from message bodies and scores them for phishing/malware risk.
No external API keys required.
"""
import re
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Suspicious TLDs commonly used in phishing
SUSPICIOUS_TLDS = {
    '.tk', '.ml', '.ga', '.cf', '.gq', '.xyz', '.top', '.buzz',
    '.club', '.work', '.date', '.racing', '.win', '.bid', '.stream',
    '.click', '.link', '.download', '.loan', '.trade',
}

# Known URL shortener domains
URL_SHORTENERS = {
    'bit.ly', 'tinyurl.com', 'goo.gl', 't.co', 'is.gd', 'buff.ly',
    'ow.ly', 'rebrand.ly', 'shorte.st', 'adf.ly', 'cutt.ly',
    'rb.gy', 'v.gd', 'shorturl.at',
}

# Phishing keywords in URL path/query
PHISHING_KEYWORDS = {
    'login', 'signin', 'verify', 'account', 'secure', 'update',
    'confirm', 'suspended', 'unusual', 'password', 'credential',
    'banking', 'paypal', 'wallet', 'urgent', 'immediately',
}

# Homoglyph patterns (characters that look like latin letters)
HOMOGLYPH_PATTERN = re.compile(r'[а-яА-Яàáâãäåèéêëìíîïòóôõöùúûüýÿ]')

# URL extraction regex
URL_REGEX = re.compile(
    r'https?://[^\s<>"\'{}|\\^`\[\]]+',
    re.IGNORECASE
)


def extract_urls(text):
    """Extract all HTTP/HTTPS URLs from text."""
    if not text:
        return []
    urls = URL_REGEX.findall(text)
    # Clean trailing punctuation
    cleaned = []
    for url in urls:
        url = url.rstrip('.,;:!?)')
        if len(url) > 10:  # filter noise
            cleaned.append(url)
    return list(set(cleaned))  # deduplicate


def scan_url(url):
    """
    Perform heuristic safety analysis on a single URL.
    Returns dict: {is_safe: bool, risk_score: int (0-100), flags: [str]}
    """
    flags = []
    risk_score = 0

    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        path = parsed.path.lower()
        full_url = url.lower()
    except Exception:
        return {'is_safe': False, 'risk_score': 90, 'flags': ['Malformed URL']}

    # --- Check 1: IP address as domain ---
    ip_pattern = re.compile(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}')
    if ip_pattern.match(domain.split(':')[0]):
        flags.append('IP address used as domain')
        risk_score += 30

    # --- Check 2: Suspicious TLD ---
    for tld in SUSPICIOUS_TLDS:
        if domain.endswith(tld):
            flags.append(f'Suspicious TLD: {tld}')
            risk_score += 20
            break

    # --- Check 3: URL shortener ---
    base_domain = '.'.join(domain.split('.')[-2:]) if '.' in domain else domain
    if base_domain in URL_SHORTENERS or domain in URL_SHORTENERS:
        flags.append('URL shortener detected')
        risk_score += 15

    # --- Check 4: Phishing keywords in path ---
    keyword_hits = [kw for kw in PHISHING_KEYWORDS if kw in path or kw in full_url]
    if keyword_hits:
        flags.append(f'Phishing keywords: {", ".join(keyword_hits[:3])}')
        risk_score += min(len(keyword_hits) * 10, 30)

    # --- Check 5: Excessive subdomains (> 3 levels) ---
    subdomain_count = domain.count('.')
    if subdomain_count > 3:
        flags.append(f'Excessive subdomains ({subdomain_count} levels)')
        risk_score += 15

    # --- Check 6: Homoglyph characters ---
    if HOMOGLYPH_PATTERN.search(url):
        flags.append('Homoglyph/deceptive characters detected')
        risk_score += 35

    # --- Check 7: Excessively long URL (> 200 chars) ---
    if len(url) > 200:
        flags.append('Excessively long URL')
        risk_score += 10

    # --- Check 8: @ symbol in URL (credential harvesting) ---
    if '@' in parsed.netloc:
        flags.append('@ symbol in domain (potential credential trick)')
        risk_score += 25

    # --- Check 9: Punycode / IDN domain ---
    if 'xn--' in domain:
        flags.append('Punycode/IDN domain detected')
        risk_score += 20

    # Cap at 100
    risk_score = min(risk_score, 100)
    is_safe = risk_score < 40

    return {
        'is_safe': is_safe,
        'risk_score': risk_score,
        'flags': flags if flags else ['No issues detected'],
    }


def scan_url_virustotal(url):
    """
    Optional: Check URL against VirusTotal API if a key is provided.
    Requires settings.VIRUSTOTAL_API_KEY.
    """
    import requests
    from django.conf import settings
    
    api_key = getattr(settings, 'VIRUSTOTAL_API_KEY', None)
    if not api_key:
        return None
        
    try:
        # 1. Get URL ID (base64 without padding)
        import base64
        url_id = base64.urlsafe_b64encode(url.encode()).decode().strip("=")
        
        # 2. Query VT API
        url_api = f"https://www.virustotal.com/api/v3/urls/{url_id}"
        headers = {"x-apikey": api_key}
        response = requests.get(url_api, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            stats = data['data']['attributes']['last_analysis_stats']
            malicious = stats.get('malicious', 0)
            suspicious = stats.get('suspicious', 0)
            return {
                "malicious": malicious,
                "suspicious": suspicious,
                "total_engines": sum(stats.values()),
                "permalink": data['data']['links']['self']
            }
    except Exception as e:
        logger.error(f"VirusTotal scan failed: {e}")
    return None


def scan_message_urls(message_obj):
    """
    Extract and scan all URLs in a message body.
    Features: Heuristic scoring + Optional VirusTotal verification.
    """
    from .models import URLScan

    urls = extract_urls(message_obj.body)
    if not urls:
        message_obj.urls_scanned = True
        message_obj.save(update_fields=['urls_scanned'])
        return {'total': 0, 'dangerous': 0, 'urls': []}

    results = []
    dangerous_count = 0

    for url in urls[:10]:
        # 1. Heuristic Scan (Always)
        heuristic = scan_url(url)
        
        # 2. Deep Scan if score is medium/high risk
        vt_report = None
        if heuristic['risk_score'] > 40:
            vt_report = scan_url_virustotal(url)
            if vt_report and vt_report['malicious'] > 0:
                heuristic['is_safe'] = False
                heuristic['risk_score'] = max(heuristic['risk_score'], 90)
                heuristic['flags'].append(f"VIRUSTOTAL: {vt_report['malicious']} engines flagged this URL")

        URLScan.objects.create(
            message=message_obj,
            url=url,
            is_safe=heuristic['is_safe'],
            risk_score=heuristic['risk_score'],
            flags=heuristic['flags'],
        )
        if not heuristic['is_safe']:
            dangerous_count += 1
        results.append({**heuristic, 'url': url, 'vt_report': vt_report})

    message_obj.urls_scanned = True
    message_obj.save(update_fields=['urls_scanned'])

    return {
        'total': len(results),
        'dangerous': dangerous_count,
        'urls': results,
    }
