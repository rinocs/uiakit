"""Regenerate deterministic document fixtures; stdlib only."""
from pathlib import Path
import io
import zipfile

HERE = Path(__file__).parent


def pdf(pages):
    objects = {}
    objects[1] = b'<< /Type /Catalog /Pages 2 0 R >>'
    kids = ' '.join(f'{3 + i * 2} 0 R' for i in range(len(pages)))
    objects[2] = f'<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>'.encode()
    font_id = 3 + len(pages) * 2
    for i, text in enumerate(pages):
        page_id = 3 + i * 2
        content_id = page_id + 1
        stream = f'BT /F1 24 Tf 72 720 Td ({text}) Tj ET'.encode()
        objects[page_id] = (f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
                            f'/Contents {content_id} 0 R /Resources << /Font << /F1 {font_id} 0 R >> >> >>').encode()
        objects[content_id] = b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream'
    objects[font_id] = b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'
    data = bytearray(b'%PDF-1.4\n')
    offsets = {}
    for number in sorted(objects):
        offsets[number] = len(data)
        data += f'{number} 0 obj\n'.encode() + objects[number] + b'\nendobj\n'
    xref = len(data)
    size = max(objects) + 1
    data += f'xref\n0 {size}\n'.encode()
    data += b'0000000000 65535 f \n'
    for number in range(1, size):
        data += f'{offsets[number]:010d} 00000 n \n'.encode()
    data += f'trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    return bytes(data)


def docx(paragraphs, hostile=False):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types/>')
        body = ''.join(f'<w:p><w:r><w:t>{text}</w:t></w:r></w:p>' for text in paragraphs)
        archive.writestr('word/document.xml',
                         '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                         f'<w:body>{body}</w:body></w:document>')
        if hostile:
            archive.writestr('word/vbaProject.bin', 'macro')
    return buffer.getvalue()


(HERE / 'sample.txt').write_bytes('Hello TXT\r\nUnicode: caffè\n'.encode())
(HERE / 'sample.md').write_text('# Title\n\nSome **markdown** text.\n', encoding='utf-8')
(HERE / 'sample.html').write_text(
    '<!doctype html><html><head><style>body{}</style><script>alert(1)</script></head>'
    '<body><h1>Hello</h1><p>World &amp; friends</p><img src="http://example.invalid/x"></body></html>',
    encoding='utf-8')
(HERE / 'sample.pdf').write_bytes(pdf(['Page one', 'Page two']))
(HERE / 'no_text.pdf').write_bytes(pdf(['']))
(HERE / 'sample.docx').write_bytes(docx(['First paragraph', 'Second paragraph']))
(HERE / 'hostile.docx').write_bytes(docx(['unsafe'], hostile=True))
(HERE / 'corrupt.pdf').write_bytes(b'%PDF-1.4\nnot a valid pdf')
(HERE / 'corrupt.docx').write_bytes(b'PK\x03\x04not a zip')
print('fixtures written')
