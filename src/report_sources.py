"""Source-structure extraction and conservative presentation, independent of the LLM.

Rules apply to first-party sites, not to one company. Structured projects describe
installations listed by a company; they never imply ownership or financial assets.
"""
import re
from collections import Counter
from urllib.parse import urlsplit


def tidy(text):
    return re.sub(r'\s+', ' ', text).strip()


def official(url, domain):
    host = urlsplit(url).hostname or ''
    target = domain.lower().removeprefix('www.')
    return host.lower().removeprefix('www.') == target


def page_kind(url):
    path = urlsplit(url).path.lower().rstrip('/')
    if re.search(r'\.(mp4|webm|mov|mp3|jpg|png|zip)$', path):
        return 'media'
    if re.search(r'/(tag|portfolio-category|category)/', path):
        return 'index'
    if re.search(r'team|leadership|board|management', path):
        return 'people'
    if re.search(r'/(references|projects|case-studies)/[^/]+$', path):
        return 'project'
    if not path or re.search(r'about|who-we-are|corporate-profile', path):
        return 'profile'
    if re.search(r'services|solutions|products|technolog|offering|industries|rental', path):
        return 'offering'
    if re.search(r'contact|careers|request-a-quote|get-started', path):
        return 'utility'
    return 'article'


def prepare_pages(pages):
    """Find repeated leading navigation from this dataset, without site literals."""
    counts = Counter()
    texts = [p.get('text_snippet', '') for p in pages if p.get('text_snippet', '').strip()]
    for text in texts:
        lines = text.splitlines(keepends=True)
        for n in range(1, min(45, len(lines)) + 1):
            prefix = ''.join(lines[:n])
            if len(prefix) <= 1000:
                counts[prefix] += 1
    repeated = [p for p, count in counts.items() if count >= max(3, len(texts) * .6)]
    prefix = max(repeated, key=len, default='')
    result = {}
    for page in pages:
        text = page.get('text_snippet', '')
        body = text.removeprefix(prefix) if prefix else text
        body = re.split(r'\n\s*(?:Copyright|Related Projects)\b', body, maxsplit=1, flags=re.I)[0]
        result[page.get('url', '')] = dict(page, body=body)
    return result


def record(category, value, quote, source, domain, **extras):
    fields = 'category entity metric value currency year period scope status quote'.split()
    f = dict.fromkeys(fields, '')
    f.update(category=category, entity=domain, value=value, quote=quote, source=source,
             method='Source structure', **extras)
    return f


def source_facts(page, domain):
    url, text = page.get('url', ''), page.get('body', page.get('text_snippet', ''))
    if not official(url, domain):
        return []
    kind = page_kind(url)
    result = []
    if kind == 'project':
        # Require several labelled attributes, including a numeric capacity, not
        # a loose customer mention or a related-project link.
        labels = r'Industry / Application|Plant type|Total capacity|Location|Contracted|Deployed'
        fields = dict((m[0], tidy(m[1])) for m in re.findall(r'^(' + labels + r')\s*\t\s*([^\n]+)', text, re.M))
        headings = [tidy(h) for h in page.get('headings', []) if tidy(h) and not re.match(r'related|references|projects$', tidy(h), re.I)]
        if headings and len(fields) >= 3 and re.search(r'\d', fields.get('Total capacity', '')):
            title = headings[0]
            details = '; '.join(f'{k}: {v}' for k, v in fields.items())
            if re.search(r'\d,\d{3}\s*MWp\b', fields.get('Total capacity', ''), re.I):
                details += '; Capacity unit needs verification (value transcribed as published)'
            result.append(record('project', title, 'Page heading: ' + title + '\n' + '\n'.join(f'{k}\t{v}' for k, v in fields.items()), url, domain,
                                 metric='Listed installation', details=details, structured=True))
    if kind == 'profile':
        # Preserve explanatory paragraphs in the site's own wording; exclude
        # slogans, navigation and testimonial quotations.
        key = re.escape(domain.removeprefix('www.').split('.')[0])
        paras = [tidy(p) for p in re.split(r'\n\s*\n', text)]
        for para in paras:
            if 50 <= len(para) <= 850 and re.match(rf'(?:{key}\b|We\b|Our\b|Since the company\b)', para, re.I):
                category = 'description' if re.search(r'\b(?:is|provide|combine|solutions|offers|speciali[sz])\b', para, re.I) else 'highlight'
                result.append(record(category, para, para, url, domain, metric='Company statement'))
                match = re.match(rf'{key}\s+is\s+(?:the\s+)?(?:first and leading\s+|a\s+|an\s+)?(.+?)\s+(?:in|for|with)\s+', para, re.I)
                if match and len(match[1]) < 100 and re.search(r'utility|manufacturer|provider|supplier|company|group|developer|distributor|operator|consultancy', match[1], re.I):
                    result.append(record('industry', match[1], para, url, domain, metric='Company self-description'))
    if kind == 'offering':
        # Heading + immediately following explanatory prose is a verifiable
        # offering record; no fuzzy keyword mapping to a different service.
        for heading in page.get('headings', []):
            title = tidy(heading)
            if '/industries/' in urlsplit(url).path or title.isupper() or not 5 <= len(title) <= 80 or '?' in title or re.search(r'^(our |how |what |services$|technology$|off-grid services$)', title, re.I):
                continue
            pos = text.find(heading)
            if pos < 0:
                continue
            tail = text[pos + len(heading):].lstrip()
            paragraph = re.split(r'\n\s*\n', tail, maxsplit=1)[0]
            company = re.escape(domain.removeprefix('www.').split('.')[0])
            if 60 <= len(paragraph) <= 1200 and re.search(r'\b(?:our|we|systems?|offers?|solutions?|monitor\w*|cleaning|power|' + company + r')\b', paragraph, re.I):
                result.append(record('service', title, heading + '\n' + paragraph, url, domain, metric='Offering', structured=True))
    return result


def report_view(facts):
    """Compact primary sheet; every accepted fact remains in Evidence."""
    from report_evidence import fact_line
    def unique(items):
        seen, out = set(), []
        for value in items:
            key = tidy(value).casefold()
            if key not in seen:
                seen.add(key)
                out.append(value)
        return out
    descriptions = [f for f in facts if f['category'] == 'description']
    descriptions.sort(key=lambda f: ('about' not in f['source'], f.get('method') != 'Source structure'))
    # Keep explanatory paragraphs rather than every repeated company claim.
    summary = unique(f['value'] for f in descriptions if len(f['value']) >= 50)
    summary = [s for s in summary if not any(s != other and tidy(s).casefold() in tidy(other).casefold() for other in summary)]
    summary = summary[:3]
    industries = unique(f['value'] for f in facts if f['category'] == 'industry')
    services = [f for f in facts if f['category'] == 'service']
    services.sort(key=lambda f: (not f.get('structured', False), len(f['value'])))
    section_sources = {f['source'] for f in services if f.get('structured')}
    selected = []
    for f in services:
        if not f.get('structured') and (f['source'] in section_sources or page_kind(f['source']) != 'offering'):
            continue
        value = tidy(f['value']).casefold()
        if len(value) > 180:
            continue  # Full prose remains in Evidence; the report lists offerings.
        if any(value in tidy(x['value']).casefold() or tidy(x['value']).casefold() in value for x in selected):
            continue
        # Promotional claims and corporate descriptions are not products.
        if re.search(r'utility company|cheapest|cleanest|world.s first|^reliable, transportable|^cost efficient and cleaner', value):
            continue
        selected.append(f)
    structured_urls = {f['source'] for f in facts if f['category'] == 'project' and f.get('structured')}
    projects = [f for f in facts if f['category'] == 'project' and (f.get('structured') or f['source'] not in structured_urls)]
    # A news listing can repeat old headlines without project dates or details.
    # Retain its evidence, but prefer actual case-study records in the report.
    projects = [f for f in projects if f.get('structured') or not re.search(r'/news[^/]*$', urlsplit(f['source']).path)]
    highlights = [f for f in facts if f['category'] in ('highlight', 'headcount')]
    for f in facts:
        if f['category'] == 'description' and re.search(r'\b\d+\b|\b(?:founded|countries|capacity)\b', f['value'], re.I):
            highlights.append(f)
    return {'description': '\n\n'.join(summary) or 'No supported company description in saved sources.',
            'industry': '; '.join(industries) or 'Not established from saved sources',
            'services': unique(fact_line(f) for f in selected),
            'projects': unique(fact_line(f) for f in projects),
            'highlights': unique(fact_line(f) for f in highlights),
            'esg': unique(fact_line(f) for f in facts if f['category'] == 'esg' and
                          (re.search(r'certificat|award', f['value'], re.I) or
                           (re.search(r'\d', f['value']) and re.search(r'carbon|emission|CO2|energy|water', f['quote'], re.I))))}
