"""Read Word OOXML without starting Word or executing embedded content."""
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def paragraph_text(node):
    parts = []
    for element in node.iter():
        if element.tag == W + 't':
            parts.append(element.text or '')
        elif element.tag == W + 'tab':
            parts.append('\t')
        elif element.tag in (W + 'br', W + 'cr'):
            parts.append('\n')
    return ''.join(parts)


def read_word(path):
    """Yield labelled body blocks in reading order; Word pages are not stable.

    Table cells retain tabs and rows retain newlines. Long blocks are split by
    the existing evidence runner, with the same caching and source checks.
    """
    path = Path(path)
    with ZipFile(path) as archive:
        member = archive.getinfo('word/document.xml')
        if member.file_size > 50 * 1024 * 1024:
            raise ValueError('Word document XML exceeds the 50 MB safety limit')
        root = ET.fromstring(archive.read(member))
        body = root.find(W + 'body')
        if body is None:
            raise ValueError('Word document has no readable body')
        number = 0
        # Paragraph traversal preserves order, including paragraphs in tables
        # and content controls. Gather nearby paragraphs to retain table titles
        # and currency/unit headings rather than send isolated numeric cells.
        paragraphs = []
        size = 0
        def blocks(parent):
            for node in parent:
                if node.tag == W + 'p':
                    yield paragraph_text(node)
                elif node.tag == W + 'tbl':
                    yield '\n'.join('\t'.join('\n'.join(paragraph_text(p) for p in cell.iter(W + 'p')) for cell in row.findall(W + 'tc')) for row in node.findall(W + 'tr'))
                else:
                    yield from blocks(node)

        for text in blocks(body):
            text = text.strip()
            if not text:
                continue
            paragraphs.append(text)
            size += len(text) + 1
            if size >= 2400:
                number += 1
                yield f'{path.name} text block {number}', '\n'.join(paragraphs)
                paragraphs, size = [], 0
        if paragraphs:
            number += 1
            yield f'{path.name} text block {number}', '\n'.join(paragraphs)
        if number == 0:
            raise ValueError('No readable Word body text; image-only documents require OCR')


def document_entries(folder, metadata):
    """Also discover locally supplied Word files; the scanner downloads PDFs."""
    entries = list(metadata)
    known = {str(d.get('filename', '')).casefold() for d in entries}
    directory = Path(folder) / 'documents'
    if directory.exists():
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.suffix.lower() in ('.docx', '.doc') and not path.name.startswith('~$') and path.name.casefold() not in known:
                entries.append({'filename': path.name})
                known.add(path.name.casefold())
    return entries
