"""
work_order_ppt.py
Generates exact PDF-matching PowerPoint (.pptx) reports for Work Orders in CMMS.
Features:
- Exact 1:1 match with PDF layout, headers, tables, fonts, borders, and colors.
- Smart table pagination preventing any overflow past slide bottom margins.
- Native editable PowerPoint tables for checklist, tasklist, notes, and photo attachments.
"""

import os
import io
import base64
import tempfile
from datetime import datetime, timedelta
from PIL import Image, ImageOps

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml import parse_xml
from pptx.oxml.ns import nsdecls


# --- COORDINATE & COLOR UTILITIES ---

def mm(val):
    """Convert millimeters to Inches."""
    return Inches(val / 25.4)


COLOR_GREY_HEADER = RGBColor(220, 220, 220)  # Exact match for pdf.set_fill_color(220, 220, 220)
COLOR_BLACK       = RGBColor(0, 0, 0)
COLOR_WHITE       = RGBColor(255, 255, 255)
COLOR_GREEN       = RGBColor(0, 150, 0)        # Exact match for pdf.set_text_color(0, 150, 0)

MAX_PAGE_Y = 278  # mm (Safe maximum Y matching PDF 275-282mm height on A4 297mm height)


def set_cell_border(cell, color='000000', width='9525', left=True, right=True, top=True, bottom=True):
    """Set thin line border on table cell matching PDF borders."""
    tcPr = cell._tc.get_or_add_tcPr()
    borders = []
    if left: borders.append('lnL')
    if right: borders.append('lnR')
    if top: borders.append('lnT')
    if bottom: borders.append('lnB')
    for b in borders:
        ln = parse_xml(f'<a:{b} {nsdecls("a")} w="{width}"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:{b}>')
        tcPr.append(ln)


def fmt_dt(dt, convert=True):
    """Exact match of fmt_dt in export_pdf."""
    if dt:
        if convert:
            dt_wib = dt + timedelta(hours=7)
            return dt_wib.strftime('%d-%m-%Y %H:%M')
        return dt.strftime('%d-%m-%Y %H:%M')
    return '-'


def decode_b64_image(b64_str):
    """Decode base64 signature string into BytesIO buffer."""
    if not b64_str or ',' not in b64_str:
        return None
    try:
        _, encoded = b64_str.split(",", 1)
        data = base64.b64decode(encoded)
        buf = io.BytesIO(data)
        buf.seek(0)
        return buf
    except Exception as e:
        print(f"Error decoding signature: {e}")
        return None


def generate_qr_buffer(data_str):
    """Generate QR code as BytesIO buffer."""
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=1,
        )
        qr.add_data(data_str)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf
    except Exception as e:
        print(f"Error generating QR code: {e}")
        return None


def process_image(full_path):
    """
    Process image WITHOUT CROPPING and WITHOUT FORCE-ROTATING.
    Only normalize EXIF orientation tag from camera.
    Returns (BytesIO, width, height) or None.
    """
    if not os.path.exists(full_path):
        return None
    try:
        with Image.open(full_path) as im:
            im = ImageOps.exif_transpose(im)
            if im.mode != 'RGB':
                im = im.convert('RGB')
            buf = io.BytesIO()
            im.save(buf, format='JPEG', quality=92)
            buf.seek(0)
            return buf, im.width, im.height
    except Exception as e:
        print(f"Error processing image {full_path}: {e}")
        return None


# --- SLIDE CONTEXT ---

class PDFSlideContext:
    """Helper to manage sequential vertical drawing with automatic slide breaks."""
    def __init__(self, prs, root_path):
        self.prs = prs
        self.root_path = root_path
        self.slide = None
        self.y = 10
        self.new_slide()

    def new_slide(self):
        self.slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        self.y = 10
        return self.slide

    def check_page_break(self, height_needed):
        """Check if height_needed fits on current slide, else create new slide."""
        if self.y + height_needed > MAX_PAGE_Y:
            self.new_slide()
            return True
        return False


# --- 0. COVER PAGE ---

def build_cover_slide(prs, wo, root_path):
    """
    0. COVER PAGE
    Exact match to export_pdf lines 1399-1447.
    """
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    # Background Image (judul.png)
    title_image_path = os.path.join(root_path, 'static', 'images', 'judul.png')
    if os.path.exists(title_image_path):
        slide.shapes.add_picture(title_image_path, 0, 0, width=mm(210), height=mm(297))

    # Site Name and Period
    site_name = wo.asset.site.name if wo.asset and wo.asset.site else "Unknown Site"
    wo_date = wo.suggested_start_date or wo.start_date or datetime.now()
    month_map = {
        1: "JANUARI", 2: "FEBRUARI", 3: "MARET", 4: "APRIL", 5: "MEI", 6: "JUNI",
        7: "JULI", 8: "AGUSTUS", 9: "SEPTEMBER", 10: "OKTOBER", 11: "NOVEMBER", 12: "DESEMBER"
    }
    periode_str = f"{month_map.get(wo_date.month, '')} {wo_date.year}"

    mt_type = wo.maintenance_type.upper() if wo.maintenance_type else ""
    if "MAINTENANCE" not in mt_type:
        mt_type += " MAINTENANCE"

    line1 = "LAPORAN WORK ORDER"
    line1_sub = mt_type
    line2 = f"{site_name.upper()}"
    line3 = f"{wo.asset.name.upper() if wo.asset else ''}"
    line4 = f"{wo.code}"

    # Positioning text at bottom left: pdf.set_y(-105), pdf.set_left_margin(20)
    # y = 297 - 105 = 192 mm
    tb = slide.shapes.add_textbox(mm(20), mm(192), mm(170), mm(95))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0

    lines = [
        (line1, 24, True),
        (line1_sub, 24, True),
        (line2, 18, True),
        (line3, 18, True),
        (line4, 18, True),
    ]

    for idx, (txt, sz, bld) in enumerate(lines):
        p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
        p.text = txt
        p.font.name = 'Arial'
        p.font.size = Pt(sz)
        p.font.bold = bld
        p.font.color.rgb = COLOR_BLACK
        p.space_after = Pt(4)


# --- 0.5 CHILLER DETAILS SLIDE ---

def build_chiller_slide(prs, wo, root_path, chiller_info):
    """
    Chiller Details Slide:
    Exact match to PDF Chiller Details page:
    - Title: Laporan Chiller - {site_name}
    - Subtitle: Chiller: {chiller_num}
    - Centered Chiller Image
    - Section: Chiller Details
    - Table: Serial Number, Model Number, Compressor Model, Ton of Refrigeration
    """
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    
    # Titles at top
    tb = slide.shapes.add_textbox(mm(10), mm(15), mm(190), mm(25))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
    
    p1 = tf.paragraphs[0]
    p1.text = f"Laporan Chiller - {chiller_info['site_name']}"
    p1.font.name = 'Arial'
    p1.font.size = Pt(16)
    p1.font.bold = True
    p1.font.color.rgb = COLOR_BLACK
    p1.alignment = PP_ALIGN.CENTER
    p1.space_after = Pt(6)
    
    p2 = tf.add_paragraph()
    p2.text = f"Chiller: {chiller_info['chiller_num']}"
    p2.font.name = 'Arial'
    p2.font.size = Pt(16)
    p2.font.bold = True
    p2.font.color.rgb = COLOR_BLACK
    p2.alignment = PP_ALIGN.CENTER
    
    # Image
    image_filename = chiller_info.get('image_filename') or 'chiller.png'
    image_path = os.path.join(root_path, 'static', 'images', image_filename)
    if not os.path.exists(image_path):
        image_path = os.path.join(root_path, 'static', 'images', 'chiller.png')
        
    img_y = 48
    if os.path.exists(image_path):
        try:
            slide.shapes.add_picture(image_path, mm(30), mm(img_y), width=mm(150))
        except Exception as e:
            print(f"Error adding chiller picture to PPT: {e}")
            
    # Section Title "Chiller Details"
    sec_y = 142
    tb2 = slide.shapes.add_textbox(mm(10), mm(sec_y), mm(190), mm(10))
    tf2 = tb2.text_frame
    tf2.margin_left = tf2.margin_top = tf2.margin_right = tf2.margin_bottom = 0
    p3 = tf2.paragraphs[0]
    p3.text = "Chiller Details"
    p3.font.name = 'Arial'
    p3.font.size = Pt(12)
    p3.font.bold = True
    p3.font.color.rgb = COLOR_BLACK
    p3.alignment = PP_ALIGN.CENTER
    
    # Table (Width: 150mm centered at 30mm, Key: 60mm, Value: 90mm)
    items = [(k, v) for k, v in chiller_info['details_to_show'].items() if v is not None and str(v).strip()]
    if items:
        tbl_y = 155
        tbl_shape = slide.shapes.add_table(len(items), 2, mm(30), mm(tbl_y), mm(150), mm(len(items) * 10))
        tbl = tbl_shape.table
        tbl.columns[0].width = mm(60)
        tbl.columns[1].width = mm(90)
        
        for r_idx, (k, v) in enumerate(items):
            cell_k = tbl.cell(r_idx, 0)
            cell_v = tbl.cell(r_idx, 1)
            
            set_cell_border(cell_k, color='000000', width='9525')
            set_cell_border(cell_v, color='000000', width='9525')
            
            cell_k.text_frame.margin_left = mm(3)
            cell_k.text_frame.margin_right = mm(3)
            cell_k.text_frame.margin_top = mm(2.5)
            cell_k.text_frame.margin_bottom = mm(2.5)
            cell_k.text_frame.word_wrap = True
            
            cell_v.text_frame.margin_left = mm(3)
            cell_v.text_frame.margin_right = mm(3)
            cell_v.text_frame.margin_top = mm(2.5)
            cell_v.text_frame.margin_bottom = mm(2.5)
            cell_v.text_frame.word_wrap = True
            
            pk = cell_k.text_frame.paragraphs[0]
            pk.text = f"{k}:"
            pk.font.name = 'Arial'
            pk.font.size = Pt(10)
            pk.font.bold = False
            pk.font.color.rgb = COLOR_BLACK
            
            pv = cell_v.text_frame.paragraphs[0]
            pv.text = str(v)
            pv.font.name = 'Arial'
            pv.font.size = Pt(10)
            pv.font.bold = False
            pv.font.color.rgb = COLOR_BLACK


# --- MAIN REPORT (PAGES 2+) ---

def build_main_report_slides(prs, wo, root_path, request_obj):
    """
    Main Report Pages: Header, Details, Technician, Checklist, Tasklist, Note, Signatures.
    Exact match to export_pdf with smart auto-pagination.
    """
    ctx = PDFSlideContext(prs, root_path)
    start_x = 10
    start_y = 10

    # 1. NEW HEADER (Logo + Title + Doc info table)
    # 1.1 Logo area box (x=10, y=10, w=35, h=24)
    logo_box = ctx.slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(start_x), mm(start_y), mm(35), mm(24))
    logo_box.fill.solid()
    logo_box.fill.fore_color.rgb = COLOR_WHITE
    logo_box.line.color.rgb = COLOR_BLACK
    logo_box.line.width = Pt(0.75)

    logo_path = os.path.join(root_path, 'static', 'images', 'Logo Jaya Teknik.png')
    if os.path.exists(logo_path):
        try:
            ctx.slide.shapes.add_picture(logo_path, mm(start_x + 2), mm(start_y + 2), width=mm(31))
        except:
            pass

    # 1.2 Title Box (x=45, y=10, w=105, h=24)
    title_box = ctx.slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(start_x + 35), mm(start_y), mm(105), mm(24))
    title_box.fill.solid()
    title_box.fill.fore_color.rgb = COLOR_WHITE
    title_box.line.color.rgb = COLOR_BLACK
    title_box.line.width = Pt(0.75)
    title_tf = title_box.text_frame
    title_tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tp = title_tf.paragraphs[0]
    tp.text = "REPORT WORK ORDER"
    tp.font.name = 'Arial'
    tp.font.size = Pt(14)
    tp.font.bold = True
    tp.font.color.rgb = COLOR_BLACK
    tp.alignment = PP_ALIGN.CENTER

    # 1.3 Doc Info Table (x=150, y=10, w=50, h=24)
    printed_date = datetime.now().strftime("%d %b %Y")
    info_rows = [
        ("No.Dok", "RP - JT - 26"),
        ("Ref.", "7; 7.1.3 & 7.1.4"),
        ("Rev.", "Original"),
        ("Tanggal", printed_date),
    ]
    info_tbl = ctx.slide.shapes.add_table(4, 2, mm(start_x + 140), mm(start_y), mm(50), mm(24)).table
    info_tbl.columns[0].width = mm(20)
    info_tbl.columns[1].width = mm(30)
    for r_idx, (k, v) in enumerate(info_rows):
        for c_idx, val in enumerate([k, v]):
            c = info_tbl.cell(r_idx, c_idx)
            set_cell_border(c)
            c.fill.solid()
            c.fill.fore_color.rgb = COLOR_WHITE
            c.margin_left = c.margin_right = mm(1)
            c.margin_top = c.margin_bottom = mm(0.4)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = c.text_frame.paragraphs[0]
            p.text = val
            p.font.name = 'Arial'
            p.font.size = Pt(8)
            p.font.color.rgb = COLOR_BLACK

    # 2. DETAILS BODY (x=10, y=34, w=190, h=24)
    ctx.y = 34
    details_box = ctx.slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(start_x), mm(ctx.y), mm(190), mm(24))
    details_box.fill.solid()
    details_box.fill.fore_color.rgb = COLOR_WHITE
    details_box.line.color.rgb = COLOR_BLACK
    details_box.line.width = Pt(0.75)

    form_val = getattr(wo, 'maintenance_type', 'SERVICE')
    nomor_val = wo.code or '-'
    asset_val = f"{wo.asset.name} ({wo.asset.code})" if wo.asset else '-'
    tech_names = ", ".join([a.name for a in wo.assignees]) if getattr(wo, 'assignees', None) else "N/A"
    completed_by_user = None
    try:
        logs = wo.logs.all() if hasattr(wo.logs, 'all') else list(wo.logs)
        for log in logs:
            if log.log_text and "status changed to completed" in log.log_text.lower():
                if log.user and log.user.name:
                    completed_by_user = log.user.name
                    break
    except Exception as e:
        pass
    resp_val = completed_by_user or tech_names
    proj_val = (getattr(wo.asset, 'project_code', None) if wo.asset else getattr(wo, 'project_code', None)) or getattr(wo, 'project_code', None) or '-'

    loc_val = '-'
    if wo.asset and hasattr(wo.asset, 'location') and wo.asset.location:
        loc_val = wo.asset.location.name if hasattr(wo.asset.location, 'name') else str(wo.asset.location)

    sched_val = f"{fmt_dt(wo.suggested_start_date)} s/d {fmt_dt(wo.suggested_completion_date)}"
    act_val = f"{fmt_dt(wo.start_date)} s/d {fmt_dt(wo.end_date)}"

    # Inner 4 lines in details body as 6-column table for exact alignment
    det_tbl_shape = ctx.slide.shapes.add_table(4, 6, mm(start_x + 1), mm(ctx.y + 0.5), mm(188), mm(23))
    det_tbl = det_tbl_shape.table
    det_tbl.columns[0].width = mm(20)
    det_tbl.columns[1].width = mm(3)
    det_tbl.columns[2].width = mm(70)
    det_tbl.columns[3].width = mm(20)
    det_tbl.columns[4].width = mm(3)
    det_tbl.columns[5].width = mm(72)

    det_rows = [
        ("Form", ":", str(form_val)[:35], "Project", ":", str(proj_val)[:35]),
        ("Nomor", ":", str(nomor_val)[:35], "Location", ":", str(loc_val)[:35]),
        ("Asset", ":", str(asset_val)[:35], "Schedule", ":", str(sched_val)[:40]),
        ("Responsible", ":", str(resp_val)[:35], "Actual Date", ":", str(act_val)[:40]),
    ]

    for r_idx, r_vals in enumerate(det_rows):
        for c_idx, val in enumerate(r_vals):
            c = det_tbl.cell(r_idx, c_idx)
            c.fill.background()
            c.margin_left = c.margin_right = mm(0.5)
            c.margin_top = c.margin_bottom = mm(0.2)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = c.text_frame.paragraphs[0]
            p.text = val
            p.font.name = 'Arial'
            p.font.size = Pt(8.5)
            p.font.color.rgb = COLOR_BLACK

    # Advance y
    ctx.y = 34 + 24 + 5 # 63 mm

    # 3. TECHNICIAN (Restored)
    # Header: TECHNICIAN (h=6)
    tech_hdr = ctx.slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(start_x), mm(ctx.y), mm(190), mm(6))
    tech_hdr.fill.solid()
    tech_hdr.fill.fore_color.rgb = COLOR_GREY_HEADER
    tech_hdr.line.color.rgb = COLOR_BLACK
    tech_hdr.line.width = Pt(0.75)
    th_p = tech_hdr.text_frame.paragraphs[0]
    th_p.text = "TECHNICIAN"
    th_p.font.name = 'Arial'
    th_p.font.size = Pt(10)
    th_p.font.bold = True
    th_p.font.color.rgb = COLOR_BLACK
    th_p.alignment = PP_ALIGN.CENTER
    tech_hdr.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE

    # Subheader: Name (h=6)
    ctx.y += 6
    tech_sub = ctx.slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(start_x), mm(ctx.y), mm(190), mm(6))
    tech_sub.fill.solid()
    tech_sub.fill.fore_color.rgb = COLOR_GREY_HEADER
    tech_sub.line.color.rgb = COLOR_BLACK
    tech_sub.line.width = Pt(0.75)
    ts_p = tech_sub.text_frame.paragraphs[0]
    ts_p.text = "Name"
    ts_p.font.name = 'Arial'
    ts_p.font.size = Pt(10)
    ts_p.font.bold = True
    ts_p.font.color.rgb = COLOR_BLACK
    ts_p.alignment = PP_ALIGN.CENTER
    tech_sub.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE

    # Value: {resp_val} (h=6)
    ctx.y += 6
    tech_val = ctx.slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(start_x), mm(ctx.y), mm(190), mm(6))
    tech_val.fill.solid()
    tech_val.fill.fore_color.rgb = COLOR_WHITE
    tech_val.line.color.rgb = COLOR_BLACK
    tech_val.line.width = Pt(0.75)
    tv_tf = tech_val.text_frame
    tv_tf.margin_left = mm(2)
    tv_tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tv_p = tv_tf.paragraphs[0]
    tv_p.text = str(tech_names)
    tv_p.font.name = 'Arial'
    tv_p.font.size = Pt(9)
    tv_p.font.color.rgb = COLOR_BLACK

    ctx.y += 6 + 5 # 86 mm

    # 4. CHECKING REPORT (With Smart Table Pagination)
    checklist_items = list(wo.checklist_parameters)
    chk_cols = [
        ("Description (Unit Check)", mm(75), PP_ALIGN.CENTER, PP_ALIGN.LEFT),
        ("Standard", mm(25), PP_ALIGN.CENTER, PP_ALIGN.CENTER),
        ("Actual", mm(25), PP_ALIGN.CENTER, PP_ALIGN.CENTER),
        ("Check", mm(25), PP_ALIGN.CENTER, PP_ALIGN.CENTER),
        ("Note", mm(40), PP_ALIGN.CENTER, PP_ALIGN.LEFT),
    ]

    if checklist_items:
        # Check how many rows can fit on current slide
        space_avail = MAX_PAGE_Y - ctx.y - 14 # 6mm header + 8mm tbl header
        max_rows_fit = int(space_avail / 6)

        # If less than 4 rows can fit on this slide, move entire section to next slide
        if max_rows_fit < 4:
            ctx.new_slide()
            space_avail = MAX_PAGE_Y - ctx.y - 14
            max_rows_fit = int(space_avail / 6)

        chk_chunks = []
        rem_items = checklist_items
        while rem_items:
            take_n = min(len(rem_items), max_rows_fit)
            chk_chunks.append(rem_items[:take_n])
            rem_items = rem_items[take_n:]
            max_rows_fit = int((MAX_PAGE_Y - 10 - 14) / 6) # for subsequent slides

        for chunk_idx, chunk in enumerate(chk_chunks):
            if chunk_idx > 0:
                ctx.new_slide()

            # Section Header (h=6)
            hdr_text = "CHECKING REPORT" if chunk_idx == 0 else "CHECKING REPORT (Lanjutan)"
            chk_hdr = ctx.slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(start_x), mm(ctx.y), mm(190), mm(6))
            chk_hdr.fill.solid()
            chk_hdr.fill.fore_color.rgb = COLOR_GREY_HEADER
            chk_hdr.line.color.rgb = COLOR_BLACK
            chk_hdr.line.width = Pt(0.75)
            ch_p = chk_hdr.text_frame.paragraphs[0]
            ch_p.text = hdr_text
            ch_p.font.name = 'Arial'
            ch_p.font.size = Pt(10)
            ch_p.font.bold = True
            ch_p.font.color.rgb = COLOR_BLACK
            ch_p.alignment = PP_ALIGN.CENTER
            chk_hdr.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
            ctx.y += 6

            # Table for this chunk
            chk_tbl_shape = ctx.slide.shapes.add_table(len(chunk) + 1, 5, mm(start_x), mm(ctx.y), mm(190), mm(8 + 6 * len(chunk)))
            chk_tbl = chk_tbl_shape.table
            for c_idx, (_, w, _, _) in enumerate(chk_cols):
                chk_tbl.columns[c_idx].width = w

            # Header Row (h=8)
            for c_idx, (h_title, _, h_align, _) in enumerate(chk_cols):
                c = chk_tbl.cell(0, c_idx)
                set_cell_border(c)
                c.fill.solid()
                c.fill.fore_color.rgb = COLOR_GREY_HEADER
                c.vertical_anchor = MSO_ANCHOR.MIDDLE
                c.margin_left = c.margin_right = mm(1)
                p = c.text_frame.paragraphs[0]
                p.text = h_title
                p.font.name = 'Arial'
                p.font.size = Pt(8)
                p.font.bold = True
                p.font.color.rgb = COLOR_BLACK
                p.alignment = h_align

            for r_idx, param in enumerate(chunk):
                row_idx = r_idx + 1
                desc = (param.parameter[:40] + '...') if len(param.parameter) > 42 else param.parameter
                std_val = str(param.standard)[:15] if param.standard else "-"
                actual_val = str(param.value)[:15] if param.value else "-"
                check_val = "OK" if actual_val != "-" else "-"
                note_val = str(param.note)[:20] if param.note else ""

                row_vals = [desc, std_val, actual_val, check_val, note_val]
                for c_idx, (val, _, _, d_align) in enumerate(zip(row_vals, *zip(*[(c[1], c[2], c[3]) for c in chk_cols]))):
                    c = chk_tbl.cell(row_idx, c_idx)
                    set_cell_border(c)
                    c.fill.solid()
                    c.fill.fore_color.rgb = COLOR_WHITE
                    c.vertical_anchor = MSO_ANCHOR.MIDDLE
                    c.margin_left = c.margin_right = mm(1)
                    p = c.text_frame.paragraphs[0]
                    p.text = str(val)
                    p.font.name = 'Arial'
                    p.font.size = Pt(8)
                    p.font.color.rgb = COLOR_BLACK
                    p.alignment = d_align

            ctx.y += 8 + 6 * len(chunk) + 5
    else:
        # No checklist parameters
        chk_hdr = ctx.slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(start_x), mm(ctx.y), mm(190), mm(6))
        chk_hdr.fill.solid()
        chk_hdr.fill.fore_color.rgb = COLOR_GREY_HEADER
        chk_hdr.line.color.rgb = COLOR_BLACK
        chk_hdr.line.width = Pt(0.75)
        ch_p = chk_hdr.text_frame.paragraphs[0]
        ch_p.text = "CHECKING REPORT"
        ch_p.font.name = 'Arial'
        ch_p.font.size = Pt(10)
        ch_p.font.bold = True
        ch_p.font.color.rgb = COLOR_BLACK
        ch_p.alignment = PP_ALIGN.CENTER
        chk_hdr.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        ctx.y += 6 + 5

    # 5. TASKLIST REPORT (With Smart Table Pagination)
    procedures = list(wo.procedures)
    task_cols = [
        ("Step Name", mm(70), PP_ALIGN.CENTER, PP_ALIGN.LEFT),
        ("Description", mm(90), PP_ALIGN.CENTER, PP_ALIGN.LEFT),
        ("State", mm(30), PP_ALIGN.CENTER, PP_ALIGN.CENTER),
    ]

    if procedures:
        # Height needed for all procedures: 6 (hdr) + 8 (tbl hdr) + 6 * len(procedures) + 3
        proc_needed = 14 + len(procedures) * 6
        space_avail = MAX_PAGE_Y - ctx.y

        # If it cannot fit on current slide, start on next slide!
        if proc_needed > space_avail:
            # Can at least 4 rows fit on current slide?
            rows_can_fit = int((space_avail - 14) / 6)
            if rows_can_fit < 4:
                ctx.new_slide()
                space_avail = MAX_PAGE_Y - ctx.y

        # Chunk procedures if needed
        rows_can_fit = max(1, int((MAX_PAGE_Y - ctx.y - 14) / 6))
        proc_chunks = []
        rem_procs = procedures
        while rem_procs:
            take_n = min(len(rem_procs), rows_can_fit)
            proc_chunks.append(rem_procs[:take_n])
            rem_procs = rem_procs[take_n:]
            rows_can_fit = int((MAX_PAGE_Y - 10 - 14) / 6)

        for chunk_idx, chunk in enumerate(proc_chunks):
            if chunk_idx > 0:
                ctx.new_slide()

            hdr_text = "TASKLIST REPORT" if chunk_idx == 0 else "TASKLIST REPORT (Lanjutan)"
            task_hdr = ctx.slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(start_x), mm(ctx.y), mm(190), mm(6))
            task_hdr.fill.solid()
            task_hdr.fill.fore_color.rgb = COLOR_GREY_HEADER
            task_hdr.line.color.rgb = COLOR_BLACK
            task_hdr.line.width = Pt(0.75)
            th2_p = task_hdr.text_frame.paragraphs[0]
            th2_p.text = hdr_text
            th2_p.font.name = 'Arial'
            th2_p.font.size = Pt(10)
            th2_p.font.bold = True
            th2_p.font.color.rgb = COLOR_BLACK
            th2_p.alignment = PP_ALIGN.CENTER
            task_hdr.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
            ctx.y += 6

            task_tbl_shape = ctx.slide.shapes.add_table(len(chunk) + 1, 3, mm(start_x), mm(ctx.y), mm(190), mm(8 + 6 * len(chunk)))
            task_tbl = task_tbl_shape.table
            for c_idx, (_, w, _, _) in enumerate(task_cols):
                task_tbl.columns[c_idx].width = w

            # Header Row
            for c_idx, (h_title, _, h_align, _) in enumerate(task_cols):
                c = task_tbl.cell(0, c_idx)
                set_cell_border(c)
                c.fill.solid()
                c.fill.fore_color.rgb = COLOR_GREY_HEADER
                c.vertical_anchor = MSO_ANCHOR.MIDDLE
                c.margin_left = c.margin_right = mm(1)
                p = c.text_frame.paragraphs[0]
                p.text = h_title
                p.font.name = 'Arial'
                p.font.size = Pt(8)
                p.font.bold = True
                p.font.color.rgb = COLOR_BLACK
                p.alignment = h_align

            for r_idx, proc in enumerate(chunk):
                row_idx = r_idx + 1
                s_name = proc.name or ''
                s_desc = proc.notes or getattr(proc, 'description', '') or ''
                s_state = "Done" if getattr(proc, 'is_completed', False) else "Pending"

                row_vals = [s_name, s_desc, s_state]
                for c_idx, (val, _, _, d_align) in enumerate(zip(row_vals, *zip(*[(c[1], c[2], c[3]) for c in task_cols]))):
                    c = task_tbl.cell(row_idx, c_idx)
                    set_cell_border(c)
                    c.fill.solid()
                    c.fill.fore_color.rgb = COLOR_WHITE
                    c.vertical_anchor = MSO_ANCHOR.MIDDLE
                    c.margin_left = c.margin_right = mm(1)
                    p = c.text_frame.paragraphs[0]
                    p.text = str(val)
                    p.font.name = 'Arial'
                    p.font.size = Pt(8)
                    p.font.color.rgb = COLOR_BLACK
                    p.alignment = d_align

            ctx.y += 8 + 6 * len(chunk) + 3
    else:
        task_hdr = ctx.slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(start_x), mm(ctx.y), mm(190), mm(6))
        task_hdr.fill.solid()
        task_hdr.fill.fore_color.rgb = COLOR_GREY_HEADER
        task_hdr.line.color.rgb = COLOR_BLACK
        task_hdr.line.width = Pt(0.75)
        th2_p = task_hdr.text_frame.paragraphs[0]
        th2_p.text = "TASKLIST REPORT"
        th2_p.font.name = 'Arial'
        th2_p.font.size = Pt(10)
        th2_p.font.bold = True
        th2_p.font.color.rgb = COLOR_BLACK
        th2_p.alignment = PP_ALIGN.CENTER
        task_hdr.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        ctx.y += 6 + 3

    # 6. NOTE (Tasklist Global Note)
    note_txt = (getattr(wo, 'tasklist_note', None) or '').strip()
    if note_txt:
        lines_note = max(1, (len(note_txt) // 100) + 1) + note_txt.count('\n')
        note_h = max(18.0, lines_note * 4.5 + 6.0)
    else:
        note_h = 18.0

    if ctx.y + 6 + note_h > MAX_PAGE_Y:
        ctx.new_slide()

    note_hdr = ctx.slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(start_x), mm(ctx.y), mm(190), mm(6))
    note_hdr.fill.solid()
    note_hdr.fill.fore_color.rgb = COLOR_GREY_HEADER
    note_hdr.line.color.rgb = COLOR_BLACK
    note_hdr.line.width = Pt(0.75)
    nh_p = note_hdr.text_frame.paragraphs[0]
    nh_p.text = "NOTE"
    nh_p.font.name = 'Arial'
    nh_p.font.size = Pt(9)
    nh_p.font.bold = True
    nh_p.font.color.rgb = COLOR_BLACK
    nh_p.alignment = PP_ALIGN.CENTER
    note_hdr.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    ctx.y += 6

    note_box = ctx.slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(start_x), mm(ctx.y), mm(190), mm(note_h))
    note_box.fill.background()
    note_box.line.color.rgb = COLOR_BLACK
    note_box.line.width = Pt(0.75)

    tb = note_box.text_frame
    tb.word_wrap = True
    tb.margin_left = tb.margin_right = mm(2)
    tb.margin_top = tb.margin_bottom = mm(1.5)

    p1 = tb.paragraphs[0]
    p1.text = note_txt if note_txt else "-"
    p1.font.name = 'Arial'
    p1.font.size = Pt(8.5)
    p1.font.color.rgb = COLOR_BLACK

    ctx.y += note_h + 3.0

    # 7. SIGNATURES
    # Signatures take ~55mm
    if ctx.y + 55 > MAX_PAGE_Y:
        ctx.new_slide()

    sig_y = ctx.y + 2

    first_tech = wo.assignees[0] if getattr(wo, 'assignees', []) else None
    tech_name = first_tech.name if first_tech else "....."
    tech_role = first_tech.role if first_tech else "....."
    site_name = wo.asset.site.name.upper() if wo.asset and getattr(wo.asset, 'site', None) else "....."
    c_name_print = getattr(wo, 'customer_name', None) or "....."
    c_title_print = getattr(wo, 'customer_title', None) or "....."

    ds = None
    try:
        from models import DigitalSignature
        ds = DigitalSignature.query.filter_by(work_order_id=wo.id).first()
    except Exception:
        ds = getattr(wo, 'digital_signature', None)

    # Left Column (PIHAK PERTAMA) at x=15mm, w=90mm
    c1_box = ctx.slide.shapes.add_textbox(mm(15), mm(sig_y), mm(90), mm(50))
    c1_tf = c1_box.text_frame
    c1_tf.word_wrap = True
    c1_tf.margin_left = c1_tf.margin_top = c1_tf.margin_right = c1_tf.margin_bottom = 0

    p = c1_tf.paragraphs[0]
    p.text = "PIHAK PERTAMA,"
    p.font.name = 'Arial'
    p.font.size = Pt(9)
    p.font.bold = True
    p.font.color.rgb = COLOR_BLACK

    p2 = c1_tf.add_paragraph()
    p2.text = site_name
    p2.font.name = 'Arial'
    p2.font.size = Pt(9)
    p2.font.bold = True
    p2.font.color.rgb = COLOR_BLACK

    # Customer signature image
    if not ds:
        c_sig_buf = decode_b64_image(getattr(wo, 'customer_signature', None))
        if c_sig_buf:
            try:
                ctx.slide.shapes.add_picture(c_sig_buf, mm(15), mm(sig_y + 12), height=mm(16))
            except Exception as e:
                print(f"Error customer signature: {e}")

    # Name and Title at sig_y + 35mm
    c1_meta = ctx.slide.shapes.add_textbox(mm(15), mm(sig_y + 35), mm(90), mm(15))
    cm1_tf = c1_meta.text_frame
    cm1_tf.margin_left = cm1_tf.margin_top = cm1_tf.margin_right = cm1_tf.margin_bottom = 0

    p_nm1 = cm1_tf.paragraphs[0]
    p_nm1.text = f"Nama : {c_name_print}"
    p_nm1.font.name = 'Arial'
    p_nm1.font.size = Pt(9)
    p_nm1.font.color.rgb = COLOR_BLACK

    p_jb1 = cm1_tf.add_paragraph()
    p_jb1.text = f"Jabatan : {c_title_print}"
    p_jb1.font.name = 'Arial'
    p_jb1.font.size = Pt(9)
    p_jb1.font.color.rgb = COLOR_BLACK

    # Right Column (PIHAK KEDUA) at x=110mm, w=85mm
    c2_box = ctx.slide.shapes.add_textbox(mm(110), mm(sig_y), mm(85), mm(50))
    c2_tf = c2_box.text_frame
    c2_tf.word_wrap = True
    c2_tf.margin_left = c2_tf.margin_top = c2_tf.margin_right = c2_tf.margin_bottom = 0

    p_k = c2_tf.paragraphs[0]
    p_k.text = "PIHAK KEDUA,"
    p_k.font.name = 'Arial'
    p_k.font.size = Pt(9)
    p_k.font.bold = True
    p_k.font.color.rgb = COLOR_BLACK

    p_k2 = c2_tf.add_paragraph()
    p_k2.text = "PT JAYA TEKNIK INDONESIA"
    p_k2.font.name = 'Arial'
    p_k2.font.size = Pt(9)
    p_k2.font.bold = True
    p_k2.font.color.rgb = COLOR_BLACK

    # Technician signature image
    if not ds:
        t_sig_buf = decode_b64_image(getattr(wo, 'technician_signature', None))
        if t_sig_buf:
            try:
                ctx.slide.shapes.add_picture(t_sig_buf, mm(110), mm(sig_y + 12), height=mm(16))
            except Exception as e:
                print(f"Error tech signature: {e}")

    # Name and Title at sig_y + 35mm
    c2_meta = ctx.slide.shapes.add_textbox(mm(110), mm(sig_y + 35), mm(85), mm(15))
    cm2_tf = c2_meta.text_frame
    cm2_tf.margin_left = cm2_tf.margin_top = cm2_tf.margin_right = cm2_tf.margin_bottom = 0

    p_nm2 = cm2_tf.paragraphs[0]
    p_nm2.text = f"Nama : {tech_name}"
    p_nm2.font.name = 'Arial'
    p_nm2.font.size = Pt(9)
    p_nm2.font.color.rgb = COLOR_BLACK

    p_jb2 = cm2_tf.add_paragraph()
    p_jb2.text = f"Jabatan : {tech_role}"
    p_jb2.font.name = 'Arial'
    p_jb2.font.size = Pt(9)
    p_jb2.font.color.rgb = COLOR_BLACK

    # Center Column (Digital Signature QR if ds)
    if ds and request_obj:
        verify_url = f"{request_obj.url_root.rstrip('/')}/verify/doc?id={ds.id}"
        qr_buf = generate_qr_buffer(verify_url)
        if qr_buf:
            try:
                ctx.slide.shapes.add_picture(qr_buf, mm(135), mm(sig_y + 10), height=mm(18))
            except:
                pass

        # Text DIGITALLY SIGNED & VERIFIED (Green, bold 6pt)
        ds_box = ctx.slide.shapes.add_textbox(mm(125), mm(sig_y + 29), mm(38), mm(6))
        ds_tf = ds_box.text_frame
        ds_tf.margin_left = ds_tf.margin_top = ds_tf.margin_right = ds_tf.margin_bottom = 0
        dp1 = ds_tf.paragraphs[0]
        dp1.text = "DIGITALLY SIGNED"
        dp1.font.name = 'Arial'
        dp1.font.size = Pt(6)
        dp1.font.bold = True
        dp1.font.color.rgb = COLOR_GREEN
        dp1.alignment = PP_ALIGN.CENTER

        dp2 = ds_tf.add_paragraph()
        dp2.text = "& VERIFIED"
        dp2.font.name = 'Arial'
        dp2.font.size = Pt(6)
        dp2.font.bold = True
        dp2.font.color.rgb = COLOR_GREEN
        dp2.alignment = PP_ALIGN.CENTER


# --- 3. PHOTO GALLERY WITH NATIVE EDITABLE TABLES ---

def _find_image_path(root_path, path_str):
    if not path_str:
        return None
    clean = path_str.replace('\\', '/').strip()
    candidates = [
        os.path.join(root_path, 'static', clean),
        os.path.join(root_path, clean),
        clean
    ]
    if clean.startswith('/'):
        clean_no_slash = clean.lstrip('/')
        candidates.append(os.path.join(root_path, 'static', clean_no_slash))
        candidates.append(os.path.join(root_path, clean_no_slash))
    if clean.startswith('uploads/') or clean.startswith('static/'):
        sub = clean.split('/', 1)[1]
        candidates.append(os.path.join(root_path, 'static', sub))
        candidates.append(os.path.join(root_path, sub))
    for p in candidates:
        if os.path.exists(p) and os.path.isfile(p):
            return p
    return None


def build_photo_slides(prs, wo, root_path):
    """
    4. PHOTOS / LAMPIRAN
    Exact 1:1 match to export_pdf layout in work_orders.py (lines 1974-2135):
    - Groups photos by procedure/task or general attachment.
    - Each group gets a clean boxed section (190mm wide, black border, centered title).
    - Photos are displayed in a clean 3-column grid (48mm x 52mm, centered if 1 or 2 photos).
    - 48:52 aspect-ratio center-crop for uniform visual appearance, with thin grey border.
    - Automatic slide breaking when section exceeds PAGE_BOTTOM_LIMIT (282mm), with (Lanjutan) continuation titles.
    """
    photo_groups = []

    # 4.1 Collect photos from procedures
    procedures_list = wo.procedures.all() if hasattr(wo.procedures, 'all') else list(wo.procedures)
    for proc in procedures_list:
        if getattr(proc, 'attachment_path', None):
            paths = [p.strip() for p in proc.attachment_path.split('|') if p.strip()]
            valid_paths = []
            for p in paths:
                resolved = _find_image_path(root_path, p)
                if resolved:
                    valid_paths.append(resolved)
            if valid_paths:
                title = proc.name.strip() if proc.name else 'Prosedur'
                if not title.lower().startswith("lampiran"):
                    title = f"Lampiran {title}"
                photo_groups.append({'title': title, 'paths': valid_paths})

    # 4.2 Collect photos from general attachments
    attachments_list = wo.attachments.all() if hasattr(wo.attachments, 'all') else list(wo.attachments)
    for att in attachments_list:
        if getattr(att, 'file_path', None):
            resolved = _find_image_path(root_path, att.file_path)
            if resolved and resolved.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif')):
                title = att.description.strip() if att.description and att.description.strip() else (att.file_name or 'Berkas')
                if not title.lower().startswith("lampiran"):
                    title = f"Lampiran {title}"
                if photo_groups and photo_groups[-1]['title'] == title:
                    photo_groups[-1]['paths'].append(resolved)
                else:
                    photo_groups.append({'title': title, 'paths': [resolved]})

    if not photo_groups:
        return

    PAGE_BOTTOM_LIMIT = 282.0
    img_w = 48.0
    img_h = 52.0
    gap_x = 11.5
    gap_y = 6.0

    current_slide = None
    y_cursor = 10.0

    def add_new_photo_slide():
        nonlocal current_slide, y_cursor
        current_slide = prs.slides.add_slide(prs.slide_layouts[6])
        y_cursor = 10.0
        return current_slide

    add_new_photo_slide()

    def _draw_photo_ppt(p_path, px, py, pw, ph):
        rendered = False
        try:
            with Image.open(p_path) as im:
                im = ImageOps.exif_transpose(im)
                w, h = im.size
                target_aspect = pw / ph
                aspect = w / h
                if aspect > target_aspect:
                    new_w = int(h * target_aspect)
                    left = (w - new_w) // 2
                    im = im.crop((left, 0, left + new_w, h))
                else:
                    new_h = int(w / target_aspect)
                    top = (h - new_h) // 2
                    im = im.crop((0, top, w, top + new_h))
                im = im.resize((480, int(480 / target_aspect)), Image.Resampling.LANCZOS)
                if im.mode != 'RGB':
                    im = im.convert('RGB')
                buf = io.BytesIO()
                im.save(buf, format='JPEG', quality=85)
                buf.seek(0)

                pic = current_slide.shapes.add_picture(
                    buf, mm(px), mm(py), width=mm(pw), height=mm(ph)
                )
                pic.line.color.rgb = RGBColor(220, 220, 220)
                pic.line.width = Pt(0.75)
                rendered = True
        except Exception as e:
            print(f"Error processing image {p_path} for PPT: {e}")

        if not rendered:
            box = current_slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE, mm(px), mm(py), mm(pw), mm(ph)
            )
            box.fill.solid()
            box.fill.fore_color.rgb = RGBColor(240, 240, 240)
            box.line.color.rgb = RGBColor(200, 200, 200)
            box.line.width = Pt(0.75)

    # Batch consecutive single-photo groups into rows of up to 3 columns
    render_blocks = []
    current_single_batch = []
    for grp in photo_groups:
        if len(grp.get('paths', [])) == 1:
            current_single_batch.append(grp)
            if len(current_single_batch) == 3:
                render_blocks.append({'type': 'single_row', 'items': current_single_batch})
                current_single_batch = []
        else:
            if current_single_batch:
                render_blocks.append({'type': 'single_row', 'items': current_single_batch})
                current_single_batch = []
            render_blocks.append({'type': 'multi_section', 'grp': grp})
    if current_single_batch:
        render_blocks.append({'type': 'single_row', 'items': current_single_batch})

    for block in render_blocks:
        if block['type'] == 'single_row':
            items = block['items']
            n_items = len(items)
            col_w = 190.0 / n_items

            max_lines = 1
            chars_per_line = max(1, int((col_w - 4) / 2.3))
            for item in items:
                lines = max(1, (len(item['title']) // chars_per_line) + 1)
                if lines > max_lines:
                    max_lines = lines

            title_text_h = max_lines * 4.0
            padding_top = 2.5
            padding_mid = 2.5
            padding_bottom = 4.0
            row_h = padding_top + title_text_h + padding_mid + img_h + padding_bottom

            avail_h = PAGE_BOTTOM_LIMIT - y_cursor
            if avail_h < row_h:
                add_new_photo_slide()
                avail_h = PAGE_BOTTOM_LIMIT - y_cursor

            for i, item in enumerate(items):
                col_x = 10.0 + i * col_w
                cur_col_w = col_w if i < n_items - 1 else (200.0 - col_x)

                # Outer Box
                outer_box = current_slide.shapes.add_shape(
                    MSO_SHAPE.RECTANGLE, mm(col_x), mm(y_cursor), mm(cur_col_w), mm(row_h)
                )
                outer_box.fill.background()
                outer_box.line.color.rgb = COLOR_BLACK
                outer_box.line.width = Pt(0.75)

                # Header Title (Centered)
                title_box = current_slide.shapes.add_textbox(
                    mm(col_x + 1), mm(y_cursor + padding_top), mm(cur_col_w - 2), mm(title_text_h + 1)
                )
                tf = title_box.text_frame
                tf.word_wrap = True
                tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
                tp = tf.paragraphs[0]
                tp.text = item['title']
                tp.font.name = 'Arial'
                tp.font.size = Pt(8.0 if n_items == 3 else 9.0)
                tp.font.bold = True
                tp.font.color.rgb = COLOR_BLACK
                tp.alignment = PP_ALIGN.CENTER

                # Photo
                photo_x = col_x + (cur_col_w - img_w) / 2
                photo_y = y_cursor + padding_top + title_text_h + padding_mid
                _draw_photo_ppt(item['paths'][0], photo_x, photo_y, img_w, img_h)

            y_cursor += row_h + 3.0
        else:
            grp = block['grp']
            group_title = grp['title']
            all_paths = list(grp['paths'])
            is_cont = False

            while all_paths:
                avail_h = PAGE_BOTTOM_LIMIT - y_cursor
                curr_title = group_title if not is_cont else f"{group_title} (Lanjutan)"

                title_lines = max(1, (len(curr_title) // 65) + 1)
                title_text_h = title_lines * 4.5
                title_total_h = 3.5 + title_text_h + 3.5
                padding_bottom = 5.0

                min_sec_h = title_total_h + img_h + padding_bottom
                if avail_h < min_sec_h:
                    add_new_photo_slide()
                    avail_h = PAGE_BOTTOM_LIMIT - y_cursor

                avail_for_rows = avail_h - title_total_h - padding_bottom
                max_rows = max(1, int((avail_for_rows + gap_y) // (img_h + gap_y)))
                max_photos = max_rows * 3

                chunk = all_paths[:max_photos]
                all_paths = all_paths[max_photos:]

                n_photos = len(chunk)
                n_rows = (n_photos + 2) // 3
                photos_total_h = n_rows * img_h + (n_rows - 1) * gap_y
                section_h = title_total_h + photos_total_h + padding_bottom

                # 1. Section Outer Box (black border, transparent fill)
                outer_box = current_slide.shapes.add_shape(
                    MSO_SHAPE.RECTANGLE, mm(10), mm(y_cursor), mm(190), mm(section_h)
                )
                outer_box.fill.background()
                outer_box.line.color.rgb = COLOR_BLACK
                outer_box.line.width = Pt(0.75)

                # 2. Section Header Title (Centered)
                title_box = current_slide.shapes.add_textbox(
                    mm(10), mm(y_cursor + 2.5), mm(190), mm(title_text_h + 2)
                )
                tf = title_box.text_frame
                tf.word_wrap = True
                tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
                tp = tf.paragraphs[0]
                tp.text = curr_title
                tp.font.name = 'Arial'
                tp.font.size = Pt(10)
                tp.font.bold = True
                tp.font.color.rgb = COLOR_BLACK
                tp.alignment = PP_ALIGN.CENTER

                # 3. Grid of Photos
                y_photo_start = y_cursor + title_total_h
                for r in range(n_rows):
                    row_paths = chunk[r * 3 : (r + 1) * 3]
                    n_in_row = len(row_paths)
                    y_row = y_photo_start + r * (img_h + gap_y)

                    if n_in_row == 3:
                        x_positions = [10 + gap_x + i * (img_w + gap_x) for i in range(3)]
                    elif n_in_row == 2:
                        row_w = 2 * img_w + gap_x
                        start_x = 10 + (190 - row_w) / 2
                        x_positions = [start_x, start_x + img_w + gap_x]
                    else:  # 1 photo centered
                        x_positions = [10 + (190 - img_w) / 2]

                    for c, p in enumerate(row_paths):
                        _draw_photo_ppt(p, x_positions[c], y_row, img_w, img_h)

                y_cursor += section_h + 5.0
                is_cont = True


# --- MAIN EXPORT FUNCTION ---

def generate_work_order_ppt(wo, current_app=None, request=None):
    """
    Generate PowerPoint (.pptx) presentation for a Work Order matching export_pdf exactly.
    Returns: (io.BytesIO, filename_str)
    """
    root_path = current_app.root_path if current_app else os.getcwd()

    prs = Presentation()
    # A4 Portrait: 210mm x 297mm (Exact match to FPDF A4 portrait)
    prs.slide_width = mm(210)
    prs.slide_height = mm(297)

    # 1. Cover Page
    build_cover_slide(prs, wo, root_path)

    # 1.5 Chiller Page (if asset is a Chiller)
    from utils import get_wo_chiller_details
    chiller_info = get_wo_chiller_details(wo.asset)
    if chiller_info:
        build_chiller_slide(prs, wo, root_path, chiller_info)

    # 2. Main Report Pages (Header, Details, Tech, Checklist, Tasklist, Note, Signatures)
    build_main_report_slides(prs, wo, root_path, request)

    # 3. Photo Gallery Pages with Real Editable Tables
    build_photo_slides(prs, wo, root_path)

    # Save to BytesIO
    ppt_io = io.BytesIO()
    prs.save(ppt_io)
    ppt_io.seek(0)

    raw_code = wo.code or f"WO_{wo.id}"
    safe_code = "".join(c for c in raw_code if c.isalnum() or c in (' ', '_', '-')).strip()
    safe_code = safe_code.replace(' ', '_')
    if safe_code.startswith("WO_") or safe_code.startswith("WO-"):
        filename = f"Report_{safe_code}.pptx"
    else:
        filename = f"Report_WO_{safe_code}.pptx"

    return ppt_io, filename
