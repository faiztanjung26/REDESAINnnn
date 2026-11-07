"""
pdf_utils.py - Safe PDF utilities for CMMS
Prevents FPDFUnicodeEncodingException when generating PDFs with core fonts (e.g., helvetica).
Standard core fonts in FPDF/fpdf2 only support latin-1 characters. User input often contains
typographical characters like ellipsis ('…'), curly quotes, dashes, bullets, emojis, etc.
This module replaces them safely with ASCII/latin-1 equivalents or safe fallback characters.
"""
import os
import sys

try:
    from fpdf import FPDF
except ImportError:
    FPDF = object

# Mapping of non-latin-1 Unicode characters to safe ASCII/latin-1 equivalents
UNICODE_REPLACEMENTS = {
    '\u2026': '...',  # ellipsis …
    '\u22ef': '...',  # midline ellipsis ⋯
    '\u2013': '-',    # en-dash –
    '\u2014': '--',   # em-dash —
    '\u2015': '--',   # horizontal bar ―
    '\u2012': '-',    # figure dash ‒
    '\u2212': '-',    # minus sign −
    '\u2018': "'",    # left single quote ‘
    '\u2019': "'",    # right single quote ’
    '\u201a': "'",    # single low-9 quote ‚
    '\u201b': "'",    # single high-reversed-9 quote ‛
    '\u201c': '"',    # left double quote “
    '\u201d': '"',    # right double quote ”
    '\u201e': '"',    # double low-9 quote „
    '\u201f': '"',    # double high-reversed-9 quote ‟
    '\u00ab': '"',    # left-pointing double angle quote «
    '\u00bb': '"',    # right-pointing double angle quote »
    '\u2039': "'",    # single left-pointing angle quote ‹
    '\u203a': "'",    # single right-pointing angle quote ›
    '\u2022': '*',    # bullet •
    '\u25e6': '*',    # white bullet ◦
    '\u25aa': '*',    # black small square ▪
    '\u25ab': '*',    # white small square ▫
    '\u2023': '>',    # triangular bullet ‣
    '\u2043': '-',    # hyphen bullet ⁃
    '\u2713': 'OK',   # checkmark ✓
    '\u2714': 'OK',   # heavy checkmark ✔
    '\u2611': 'OK',   # ballot box with check ☑
    '\u2717': 'X',    # ballot X ✗
    '\u2718': 'X',    # heavy ballot X ✘
    '\u2612': 'X',    # ballot box with X ☒
    '\u00b1': '+/-',  # plus-minus ±
    '\u2264': '<=',   # less than or equal ≤
    '\u2265': '>=',   # greater than or equal ≥
    '\u2260': '!=',   # not equal ≠
    '\u2248': '~',    # approximately ≈
    '\u00d7': 'x',    # multiplication sign ×
    '\u00f7': '/',    # division sign ÷
    '\u2192': '->',   # right arrow →
    '\u2190': '<-',   # left arrow ←
    '\u2194': '<->',  # left-right arrow ↔
    '\u2191': '^',    # up arrow ↑
    '\u2193': 'v',    # down arrow ↓
    '\u20ac': 'EUR',  # euro €
    '\u2122': '(TM)', # trademark ™
    '\u0153': 'oe',   # oe ligature œ
    '\u0152': 'OE',   # OE ligature Œ
    '\u00a0': ' ',    # non-breaking space
    '\u2002': ' ',    # en space
    '\u2003': ' ',    # em space
    '\u2009': ' ',    # thin space
    '\u200a': ' ',    # hair space
    '\u202f': ' ',    # narrow no-break space
    '\u200b': '',     # zero-width space
    '\u200c': '',     # zero-width non-joiner
    '\u200d': '',     # zero-width joiner
    '\u2060': '',     # word joiner
    '\ufeff': '',     # byte order mark
    '\u2028': '\n',   # line separator
    '\u2029': '\n',   # paragraph separator
}

def clean_pdf_text(text) -> str:
    """
    Sanitize text to be strictly safe for standard FPDF core fonts (latin-1).
    Replaces common Unicode typography with ASCII approximations, and encodes
    unsupported characters with '?' instead of raising FPDFUnicodeEncodingException.
    """
    if text is None:
        return ""
    text = str(text)
    for char, replacement in UNICODE_REPLACEMENTS.items():
        if char in text:
            text = text.replace(char, replacement)
    
    # Safely convert any remaining characters that can't be represented in latin-1
    try:
        text = text.encode('latin-1', 'replace').decode('latin-1')
    except Exception:
        pass
        
    return text


class SafeFPDF(FPDF):
    """
    Drop-in replacement for FPDF that intercepts text normalization to prevent
    FPDFUnicodeEncodingException whenever core fonts (helvetica, courier, times) are used.
    """
    def normalize_text(self, text: str) -> str:
        if text is None:
            return ""
            
        # If font is not a TTF unicode font, sanitize the text
        if not getattr(self, 'is_ttf_font', False):
            text = clean_pdf_text(text)
            
        if hasattr(super(), 'normalize_text'):
            try:
                return super().normalize_text(text)
            except Exception:
                return clean_pdf_text(text)
                
        return clean_pdf_text(text)


def calc_num_lines(pdf, text, col_width: float) -> int:
    """
    Calculate the number of lines needed to render text inside a cell of width col_width.
    Takes into account font metrics, existing line breaks, and word wrapping.
    """
    if not text:
        return 1
    max_w = max(1.0, float(col_width) - 3.0)
    total_lines = 0
    for p in str(text).split('\n'):
        if not p.strip():
            total_lines += 1
            continue
        words = p.split(' ')
        current_line = ''
        p_lines = 1
        for word in words:
            if not word:
                continue
            w_width = pdf.get_string_width(word)
            if w_width > max_w:
                if current_line:
                    p_lines += 1
                    current_line = ''
                extra_lines = int(w_width / max_w)
                p_lines += extra_lines
                continue
                
            test_line = f"{current_line} {word}".strip()
            if pdf.get_string_width(test_line) <= max_w:
                current_line = test_line
            else:
                p_lines += 1
                current_line = word
        total_lines += p_lines
    return max(1, total_lines)
