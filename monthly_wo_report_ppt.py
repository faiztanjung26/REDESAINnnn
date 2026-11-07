import os
import io
import tempfile
from datetime import datetime
from PIL import Image, ImageOps

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE


def mm(val):
    """Konversi milimeter ke Inches untuk python-pptx."""
    return Inches(val / 25.4)


class MonthlyWOReportPPT:
    """
    Generator Laporan Bulanan Work Order (Portrait PPTX A4)
    PT Jaya Teknik Indonesia
    Sesuai format resmi ISO & Rapi dalam format Portrait (1:1 dengan versi PDF)
    """

    # Warna Standar
    COLOR_TEXT_PRIMARY   = RGBColor(15, 23, 42)
    COLOR_TEXT_SECONDARY = RGBColor(71, 85, 105)
    COLOR_TEXT_MUTED     = RGBColor(100, 116, 139)
    COLOR_BORDER         = RGBColor(180, 190, 205)
    COLOR_HEADER_BG      = RGBColor(240, 244, 250)
    COLOR_WHITE          = RGBColor(255, 255, 255)
    COLOR_RED_ACCENT     = RGBColor(220, 38, 38)
    COLOR_STATUS_CLOSED  = RGBColor(22, 101, 52)   # Hijau
    COLOR_STATUS_ACTIVE  = RGBColor(29, 78, 216)   # Biru
    COLOR_STATUS_PENDING = RGBColor(180, 83, 9)    # Amber

    def __init__(self, site_name='ALL SITES', period_str='', include_cover=True, root_path=None):
        self.site_name = site_name or 'ALL SITES'
        self.period_str = period_str or datetime.now().strftime('%B %Y').upper()
        self.include_cover = include_cover
        self.root_path = root_path or os.path.dirname(os.path.abspath(__file__))

        self.prs = Presentation()
        # A4 Portrait: 210mm x 297mm
        self.prs.slide_width = mm(210)
        self.prs.slide_height = mm(297)

        self.temp_files_to_clean = []
        self.content_slides = []  # List slide konten untuk update nomor halaman
        self.total_pages = 0

    def _fmt_dt(self, dt):
        """Helper format tanggal & waktu"""
        if not dt:
            return '-'
        return dt.strftime('%d-%m-%Y %H:%M')

    def _find_image_path(self, path_str):
        """Helper pencarian file gambar secara komprehensif"""
        if not path_str:
            return None
        clean_path = path_str.replace('\\', '/').strip()
        candidates = [
            os.path.join(self.root_path, 'static', clean_path),
            os.path.join(self.root_path, clean_path),
        ]
        if clean_path.startswith('/'):
            candidates.append(os.path.join(self.root_path, 'static', clean_path.lstrip('/')))
            candidates.append(os.path.join(self.root_path, clean_path.lstrip('/')))
        elif not clean_path.startswith('static/'):
            candidates.append(os.path.join(self.root_path, 'static', 'uploads', clean_path))

        for p in candidates:
            if os.path.exists(p) and os.path.isfile(p):
                return p
        return None

    def _process_image(self, img_path):
        """Memproses gambar: auto-orientasi EXIF, rotasi otomatis portrait ke landscape, fit proporsional tanpa crop"""
        full_path = self._find_image_path(img_path)
        if not full_path or not os.path.exists(full_path):
            return None
        try:
            with Image.open(full_path) as im:
                im = ImageOps.exif_transpose(im)
                if im.height > im.width:
                    im = im.rotate(90, expand=True)

                target_size = (390, 280)
                try:
                    im_padded = ImageOps.pad(im, target_size, color=(255, 255, 255), centering=(0.5, 0.5))
                except AttributeError:
                    im.thumbnail(target_size, Image.Resampling.LANCZOS)
                    im_padded = Image.new('RGB', target_size, (255, 255, 255))
                    off_x = (target_size[0] - im.width) // 2
                    off_y = (target_size[1] - im.height) // 2
                    im_padded.paste(im, (off_x, off_y))

                tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
                if im_padded.mode != 'RGB':
                    im_padded = im_padded.convert('RGB')
                im_padded.save(tmp.name, 'JPEG', quality=90)
                tmp.close()
                self.temp_files_to_clean.append(tmp.name)
                return tmp.name
        except Exception as e:
            print(f"Error processing image {full_path}: {e}")
            return None

    def draw_cover(self):
        """Merender Halaman Cover Portrait dengan panel kartu elegan di bagian bawah"""
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])

        # Background cover portrait (judul.png atau cover_wo_landscape.png)
        cover_path = os.path.join(self.root_path, 'static', 'images', 'judul.png')
        if not os.path.exists(cover_path):
            cover_path = os.path.join(self.root_path, 'static', 'images', 'cover_wo_landscape.png')
        if os.path.exists(cover_path):
            slide.shapes.add_picture(cover_path, 0, 0, width=mm(210), height=mm(297))

        box_x = 15
        box_y = 195
        box_w = 180
        box_h = 55

        # Kartu putih frosted
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, mm(box_x), mm(box_y), mm(box_w), mm(box_h))
        card.fill.solid()
        card.fill.fore_color.rgb = self.COLOR_WHITE
        card.line.color.rgb = RGBColor(203, 213, 225)
        card.line.width = Pt(0.75)

        # Garis aksen merah PT Jaya Teknik di sisi kiri kartu
        accent = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, mm(box_x + 1.5), mm(box_y + 2.5), mm(3), mm(box_h - 5))
        accent.fill.solid()
        accent.fill.fore_color.rgb = self.COLOR_RED_ACCENT
        accent.line.fill.background()

        # Text Frame di dalam kartu
        cx = box_x + 9
        cy = box_y + 5
        tb = slide.shapes.add_textbox(mm(cx), mm(cy), mm(box_w - 14), mm(box_h - 8))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0

        # Judul Utama
        p1 = tf.paragraphs[0]
        p1.text = "LAPORAN BULANAN WORK ORDER"
        p1.font.name = 'Arial'
        p1.font.size = Pt(16)
        p1.font.bold = True
        p1.font.color.rgb = self.COLOR_TEXT_PRIMARY
        p1.space_after = Pt(2)

        # Sub-judul
        p2 = tf.add_paragraph()
        p2.text = "PREVENTIVE & CORRECTIVE MAINTENANCE"
        p2.font.name = 'Arial'
        p2.font.size = Pt(10.5)
        p2.font.bold = True
        p2.font.color.rgb = self.COLOR_RED_ACCENT
        p2.space_after = Pt(4)

        # Site / Proyek
        p3 = tf.add_paragraph()
        p3.text = f"SITE / PROYEK  : {self.site_name.upper()}"
        p3.font.name = 'Arial'
        p3.font.size = Pt(9)
        p3.font.bold = True
        p3.font.color.rgb = self.COLOR_TEXT_PRIMARY
        p3.space_after = Pt(1)

        # Periode
        p4 = tf.add_paragraph()
        p4.text = f"PERIODE            : {self.period_str.upper()}"
        p4.font.name = 'Arial'
        p4.font.size = Pt(9)
        p4.font.bold = True
        p4.font.color.rgb = self.COLOR_TEXT_PRIMARY
        p4.space_after = Pt(1)

        # Tanggal Cetak
        p5 = tf.add_paragraph()
        p5.text = f"TANGGAL CETAK : {datetime.now().strftime('%d %B %Y').upper()}"
        p5.font.name = 'Arial'
        p5.font.size = Pt(8.5)
        p5.font.color.rgb = self.COLOR_TEXT_MUTED

    def _draw_header_bar(self, slide, page_num):
        """Header Dokumen ISO Resmi PT Jaya Teknik pada Slide Konten Portrait (210mm x 297mm)"""
        start_x = 10
        start_y = 8
        h_total = 24

        # Kotak 1: Logo Perusahaan (Kiri, 35mm x 24mm)
        logo_box = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(start_x), mm(start_y), mm(35), mm(h_total))
        logo_box.fill.solid()
        logo_box.fill.fore_color.rgb = self.COLOR_WHITE
        logo_box.line.color.rgb = self.COLOR_BORDER
        logo_box.line.width = Pt(0.75)

        logo_path = os.path.join(self.root_path, 'static', 'images', 'Logo Jaya Teknik.png')
        if os.path.exists(logo_path):
            try:
                slide.shapes.add_picture(logo_path, mm(start_x + 2), mm(start_y + 3), width=mm(31), height=mm(18))
            except Exception:
                pass

        # Kotak 2: Judul Dokumen (Tengah, 105mm x 24mm)
        mid_box = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(start_x + 35), mm(start_y), mm(105), mm(h_total))
        mid_box.fill.solid()
        mid_box.fill.fore_color.rgb = self.COLOR_WHITE
        mid_box.line.color.rgb = self.COLOR_BORDER
        mid_box.line.width = Pt(0.75)

        tf_mid = mid_box.text_frame
        tf_mid.word_wrap = True
        tf_mid.vertical_anchor = MSO_ANCHOR.MIDDLE

        p_co = tf_mid.paragraphs[0]
        p_co.text = "PT JAYA TEKNIK INDONESIA"
        p_co.font.name = 'Arial'
        p_co.font.size = Pt(8)
        p_co.font.bold = True
        p_co.font.color.rgb = self.COLOR_TEXT_MUTED
        p_co.alignment = PP_ALIGN.CENTER

        p_title = tf_mid.add_paragraph()
        p_title.text = "LAPORAN BULANAN WORK ORDER"
        p_title.font.name = 'Arial'
        p_title.font.size = Pt(12)
        p_title.font.bold = True
        p_title.font.color.rgb = self.COLOR_TEXT_PRIMARY
        p_title.alignment = PP_ALIGN.CENTER

        p_meta = tf_mid.add_paragraph()
        p_meta.text = f"SITE: {self.site_name.upper()}   |   PERIODE: {self.period_str.upper()}"
        p_meta.font.name = 'Arial'
        p_meta.font.size = Pt(7.5)
        p_meta.font.color.rgb = self.COLOR_TEXT_SECONDARY
        p_meta.alignment = PP_ALIGN.CENTER

        # Kotak 3: Data Pengendalian Dokumen ISO Grid 4 Baris (Kanan, 50mm x 24mm)
        rx = start_x + 35 + 105
        rw = 50
        rh = 6

        doc_rows = [
            ('No. Dokumen', 'RP-JT-WO-MTH'),
            ('Revisi', '00 (Original)'),
            ('Tanggal Cetak', datetime.now().strftime("%d/%m/%Y")),
            ('Halaman', f'{page_num} dari {{TOTAL}}')
        ]

        page_shape = None
        for idx, (lbl, val) in enumerate(doc_rows):
            row_y = start_y + (idx * rh)

            # Label box (20mm)
            l_box = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(rx), mm(row_y), mm(20), mm(rh))
            l_box.fill.solid()
            l_box.fill.fore_color.rgb = self.COLOR_WHITE
            l_box.line.color.rgb = self.COLOR_BORDER
            l_box.line.width = Pt(0.75)
            tf_l = l_box.text_frame
            tf_l.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf_l.margin_left = mm(1)
            p_l = tf_l.paragraphs[0]
            p_l.text = lbl
            p_l.font.name = 'Arial'
            p_l.font.size = Pt(6.5)
            p_l.font.bold = True
            p_l.font.color.rgb = self.COLOR_TEXT_SECONDARY

            # Value box (30mm)
            v_box = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(rx + 20), mm(row_y), mm(rw - 20), mm(rh))
            v_box.fill.solid()
            v_box.fill.fore_color.rgb = self.COLOR_WHITE
            v_box.line.color.rgb = self.COLOR_BORDER
            v_box.line.width = Pt(0.75)
            tf_v = v_box.text_frame
            tf_v.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf_v.margin_left = mm(1)
            p_v = tf_v.paragraphs[0]
            p_v.text = val
            p_v.font.name = 'Arial'
            p_v.font.size = Pt(6.5)
            p_v.font.color.rgb = self.COLOR_TEXT_PRIMARY

            if idx == 3:
                page_shape = v_box

        # Footer
        tb_foot = slide.shapes.add_textbox(mm(10), mm(285), mm(190), mm(6))
        p_foot = tb_foot.text_frame.paragraphs[0]
        p_foot.text = f"PT JAYA TEKNIK INDONESIA | Halaman {page_num} dari {{TOTAL}}"
        p_foot.font.name = 'Arial'
        p_foot.font.size = Pt(7.5)
        p_foot.font.italic = True
        p_foot.font.color.rgb = self.COLOR_TEXT_MUTED
        p_foot.alignment = PP_ALIGN.CENTER

        return page_shape, tb_foot

    def _draw_table_header(self, slide, y_pos):
        """Header Tabel Laporan Portrait (Total 190mm)"""
        cols = [
            (10, 36, 'WO Number'),
            (46, 40, 'Asset'),
            (86, 44, 'Tanggal'),
            (130, 70, 'Lampiran Foto')
        ]
        for x, w, title in cols:
            box = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(x), mm(y_pos), mm(w), mm(8))
            box.fill.solid()
            box.fill.fore_color.rgb = self.COLOR_HEADER_BG
            box.line.color.rgb = self.COLOR_BORDER
            box.line.width = Pt(0.75)
            tf = box.text_frame
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = tf.paragraphs[0]
            p.text = title
            p.font.name = 'Arial'
            p.font.size = Pt(8.5)
            p.font.bold = True
            p.font.color.rgb = RGBColor(25, 35, 60)
            p.alignment = PP_ALIGN.CENTER
        return y_pos + 8

    def _draw_signatures(self, slide, y_cursor):
        """Bagian Pengesahan / Lembar Tanda Tangan di Akhir Dokumen Portrait"""
        sig_height = 40
        if y_cursor + sig_height > 275:
            # Buat slide baru jika tidak muat
            new_slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
            page_shape, foot_shape = self._draw_header_bar(new_slide, len(self.content_slides) + 1 + (1 if self.include_cover else 0))
            self.content_slides.append({
                'slide': new_slide,
                'page_num': len(self.content_slides) + 1 + (1 if self.include_cover else 0),
                'page_shape': page_shape,
                'foot_shape': foot_shape
            })
            slide = new_slide
            y_cursor = 36
        else:
            y_cursor += 5

        box_w = 80
        x_client = 15
        x_jti = 115

        # Kotak Pihak Pertama (Klien)
        tb1 = slide.shapes.add_textbox(mm(x_client), mm(y_cursor), mm(box_w), mm(12))
        tf1 = tb1.text_frame
        p1_h = tf1.paragraphs[0]
        p1_h.text = "PIHAK PERTAMA (KLIEN)"
        p1_h.font.name = 'Arial'
        p1_h.font.size = Pt(8.5)
        p1_h.font.bold = True
        p1_h.alignment = PP_ALIGN.CENTER

        p1_s = tf1.add_paragraph()
        p1_s.text = self.site_name.upper()
        p1_s.font.name = 'Arial'
        p1_s.font.size = Pt(7.5)
        p1_s.alignment = PP_ALIGN.CENTER

        line1 = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(x_client + 8), mm(y_cursor + 27), mm(box_w - 16), mm(0.4))
        line1.fill.solid()
        line1.fill.fore_color.rgb = self.COLOR_BORDER
        line1.line.fill.background()

        tb1_desc = slide.shapes.add_textbox(mm(x_client), mm(y_cursor + 28), mm(box_w), mm(7))
        p1_d = tb1_desc.text_frame.paragraphs[0]
        p1_d.text = "Nama / Jabatan / Tanggal"
        p1_d.font.name = 'Arial'
        p1_d.font.size = Pt(7.5)
        p1_d.alignment = PP_ALIGN.CENTER

        # Kotak Pihak Kedua (Pelaksana)
        tb2 = slide.shapes.add_textbox(mm(x_jti), mm(y_cursor), mm(box_w), mm(12))
        tf2 = tb2.text_frame
        p2_h = tf2.paragraphs[0]
        p2_h.text = "PIHAK KEDUA (PELAKSANA)"
        p2_h.font.name = 'Arial'
        p2_h.font.size = Pt(8.5)
        p2_h.font.bold = True
        p2_h.alignment = PP_ALIGN.CENTER

        p2_s = tf2.add_paragraph()
        p2_s.text = "PT JAYA TEKNIK INDONESIA"
        p2_s.font.name = 'Arial'
        p2_s.font.size = Pt(7.5)
        p2_s.alignment = PP_ALIGN.CENTER

        line2 = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(x_jti + 8), mm(y_cursor + 27), mm(box_w - 16), mm(0.4))
        line2.fill.solid()
        line2.fill.fore_color.rgb = self.COLOR_BORDER
        line2.line.fill.background()

        tb2_desc = slide.shapes.add_textbox(mm(x_jti), mm(y_cursor + 28), mm(box_w), mm(7))
        p2_d = tb2_desc.text_frame.paragraphs[0]
        p2_d.text = "Supervisor / Project Engineer"
        p2_d.font.name = 'Arial'
        p2_d.font.size = Pt(7.5)
        p2_d.alignment = PP_ALIGN.CENTER

    def render_work_orders(self, work_orders):
        """Merender baris-baris Work Order ke dalam slide-slide PowerPoint Portrait"""
        # Slide Konten Pertama
        cur_slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        page_num = 2 if self.include_cover else 1
        page_shape, foot_shape = self._draw_header_bar(cur_slide, page_num)
        self.content_slides.append({
            'slide': cur_slide,
            'page_num': page_num,
            'page_shape': page_shape,
            'foot_shape': foot_shape
        })
        y_cursor = self._draw_table_header(cur_slide, 34)

        for wo in work_orders:
            # 1. Ambil foto: tepat 1 foto per tasklist yang memiliki foto
            photos = []
            procedures_list = wo.procedures.all() if hasattr(wo.procedures, 'all') else list(wo.procedures)
            for proc in procedures_list:
                if proc.attachment_path:
                    paths = [p.strip() for p in proc.attachment_path.split('|') if p.strip()]
                    if paths:
                        photos.append({
                            'caption': proc.name,
                            'path': paths[0]
                        })

            # Jika tidak ada foto prosedur, periksa attachments umum WO
            if not photos and hasattr(wo, 'attachments'):
                att_list = wo.attachments.all() if hasattr(wo.attachments, 'all') else list(wo.attachments)
                for att in att_list:
                    if getattr(att, 'file_path', None) and att.file_path.strip():
                        cap = att.description or att.file_name or 'Lampiran'
                        photos.append({
                            'caption': cap,
                            'path': att.file_path.strip()
                        })

            # 2. Hitung tinggi baris yang diperlukan (Portrait: kolom 70mm, 2 foto per baris)
            num_photos = len(photos)
            if num_photos == 0:
                row_height = 28
            elif num_photos == 1:
                row_height = 42
            else:
                photo_subrows = ((num_photos - 1) // 2) + 1
                row_height = max(30, photo_subrows * 32 + 4)

            # 3. Cek apakah muat di slide saat ini (batas bawah portrait 275mm)
            if y_cursor + row_height > 275:
                cur_slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
                page_num = len(self.content_slides) + 1 + (1 if self.include_cover else 0)
                page_shape, foot_shape = self._draw_header_bar(cur_slide, page_num)
                self.content_slides.append({
                    'slide': cur_slide,
                    'page_num': page_num,
                    'page_shape': page_shape,
                    'foot_shape': foot_shape
                })
                y_cursor = self._draw_table_header(cur_slide, 34)

            x_start = 10
            y_start = y_cursor

            # --- KOLOM 1: WO Number (36 mm) ---
            b1 = cur_slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(x_start), mm(y_start), mm(36), mm(row_height))
            b1.fill.solid()
            b1.fill.fore_color.rgb = self.COLOR_WHITE
            b1.line.color.rgb = self.COLOR_BORDER
            b1.line.width = Pt(0.75)

            tb1 = cur_slide.shapes.add_textbox(mm(x_start + 1.5), mm(y_start + 1.5), mm(33), mm(row_height - 3))
            tf1 = tb1.text_frame
            tf1.word_wrap = True
            tf1.margin_left = tf1.margin_top = tf1.margin_right = tf1.margin_bottom = 0

            p_code = tf1.paragraphs[0]
            p_code.text = wo.code or '-'
            p_code.font.name = 'Arial'
            p_code.font.size = Pt(8)
            p_code.font.bold = True
            p_code.font.color.rgb = RGBColor(20, 35, 60)
            p_code.space_after = Pt(1.5)

            p_type = tf1.add_paragraph()
            p_type.text = f"Tipe: {wo.maintenance_type or '-'}"
            p_type.font.name = 'Arial'
            p_type.font.size = Pt(7)
            p_type.font.color.rgb = RGBColor(90, 100, 115)

            p_prio = tf1.add_paragraph()
            p_prio.text = f"Prioritas: {wo.priority or '-'}"
            p_prio.font.name = 'Arial'
            p_prio.font.size = Pt(7)
            p_prio.font.color.rgb = RGBColor(90, 100, 115)

            status_text = wo.current_status.name if wo.current_status else 'Draft'
            p_stat = tf1.add_paragraph()
            p_stat.text = f"Status: {status_text}"
            p_stat.font.name = 'Arial'
            p_stat.font.size = Pt(7)
            p_stat.font.bold = True
            if wo.current_status and wo.current_status.control_type == 'Closed':
                p_stat.font.color.rgb = self.COLOR_STATUS_CLOSED
            elif wo.current_status and wo.current_status.control_type == 'Active':
                p_stat.font.color.rgb = self.COLOR_STATUS_ACTIVE
            else:
                p_stat.font.color.rgb = self.COLOR_STATUS_PENDING

            # --- KOLOM 2: Asset (40 mm) ---
            b2 = cur_slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(x_start + 36), mm(y_start), mm(40), mm(row_height))
            b2.fill.solid()
            b2.fill.fore_color.rgb = self.COLOR_WHITE
            b2.line.color.rgb = self.COLOR_BORDER
            b2.line.width = Pt(0.75)

            tb2 = cur_slide.shapes.add_textbox(mm(x_start + 37.5), mm(y_start + 1.5), mm(37), mm(row_height - 3))
            tf2 = tb2.text_frame
            tf2.word_wrap = True
            tf2.margin_left = tf2.margin_top = tf2.margin_right = tf2.margin_bottom = 0

            asset_name = wo.asset.name if wo.asset else '-'
            p_aname = tf2.paragraphs[0]
            p_aname.text = asset_name
            p_aname.font.name = 'Arial'
            p_aname.font.size = Pt(8)
            p_aname.font.bold = True
            p_aname.font.color.rgb = RGBColor(20, 35, 60)
            p_aname.space_after = Pt(1.5)

            asset_code = wo.asset.code if (wo.asset and wo.asset.code) else '-'
            p_acode = tf2.add_paragraph()
            p_acode.text = f"Kode: {asset_code}"
            p_acode.font.name = 'Arial'
            p_acode.font.size = Pt(7)
            p_acode.font.color.rgb = RGBColor(90, 100, 115)

            loc_name = '-'
            if wo.asset and wo.asset.location:
                loc_name = wo.asset.location.name if hasattr(wo.asset.location, 'name') else str(wo.asset.location)
            p_loc = tf2.add_paragraph()
            p_loc.text = f"Lokasi: {loc_name[:18]}"
            p_loc.font.name = 'Arial'
            p_loc.font.size = Pt(7)
            p_loc.font.color.rgb = RGBColor(90, 100, 115)

            # --- KOLOM 3: Tanggal (44 mm) ---
            b3 = cur_slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(x_start + 76), mm(y_start), mm(44), mm(row_height))
            b3.fill.solid()
            b3.fill.fore_color.rgb = self.COLOR_WHITE
            b3.line.color.rgb = self.COLOR_BORDER
            b3.line.width = Pt(0.75)

            tb3 = cur_slide.shapes.add_textbox(mm(x_start + 77.5), mm(y_start + 1.5), mm(41), mm(row_height - 3))
            tf3 = tb3.text_frame
            tf3.word_wrap = True
            tf3.margin_left = tf3.margin_top = tf3.margin_right = tf3.margin_bottom = 0

            date_items = [
                ("Sug. Start", self._fmt_dt(wo.suggested_start_date)[:16]),
                ("Sug. Date", self._fmt_dt(wo.suggested_completion_date)[:16]),
                ("Act. Start", self._fmt_dt(wo.start_date)[:16]),
                ("Act. End", self._fmt_dt(wo.end_date)[:16])
            ]
            for d_idx, (d_lbl, d_val) in enumerate(date_items):
                p_dt = tf3.paragraphs[0] if d_idx == 0 else tf3.add_paragraph()
                p_dt.text = f"{d_lbl:10} : {d_val}"
                p_dt.font.name = 'Arial'
                p_dt.font.size = Pt(6.5)
                p_dt.font.color.rgb = RGBColor(70, 80, 95)

            # --- KOLOM 4: Lampiran Foto (70 mm) ---
            col4_x = x_start + 120
            col4_w = 70
            b4 = cur_slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(col4_x), mm(y_start), mm(col4_w), mm(row_height))
            b4.fill.solid()
            b4.fill.fore_color.rgb = self.COLOR_WHITE
            b4.line.color.rgb = self.COLOR_BORDER
            b4.line.width = Pt(0.75)

            if not photos:
                tb4_empty = cur_slide.shapes.add_textbox(mm(col4_x + 2), mm(y_start + (row_height / 2) - 4), mm(col4_w - 4), mm(8))
                p_empty = tb4_empty.text_frame.paragraphs[0]
                p_empty.text = "- Tidak ada foto tasklist -"
                p_empty.font.name = 'Arial'
                p_empty.font.size = Pt(7.5)
                p_empty.font.italic = True
                p_empty.font.color.rgb = RGBColor(160, 170, 185)
                p_empty.alignment = PP_ALIGN.CENTER
            elif num_photos == 1:
                img_w = 46
                img_h = 30
                px = col4_x + (col4_w - img_w) / 2
                py = y_start + 2
                processed_path = self._process_image(photos[0]['path'])

                if processed_path:
                    f_box = cur_slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(px), mm(py), mm(img_w), mm(img_h))
                    f_box.fill.solid()
                    f_box.fill.fore_color.rgb = self.COLOR_WHITE
                    f_box.line.color.rgb = RGBColor(210, 215, 225)
                    f_box.line.width = Pt(0.5)

                    try:
                        cur_slide.shapes.add_picture(processed_path, mm(px + 0.5), mm(py + 0.5), width=mm(img_w - 1), height=mm(img_h - 1))
                    except Exception as e:
                        print(f"Error adding picture to PPT: {e}")
                else:
                    f_box = cur_slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(px), mm(py), mm(img_w), mm(img_h))
                    f_box.fill.solid()
                    f_box.fill.fore_color.rgb = RGBColor(248, 250, 252)
                    f_box.line.color.rgb = RGBColor(225, 230, 240)
                    f_box.line.width = Pt(0.5)

                    tb_noimg = cur_slide.shapes.add_textbox(mm(px), mm(py + 10), mm(img_w), mm(8))
                    p_noimg = tb_noimg.text_frame.paragraphs[0]
                    p_noimg.text = "Foto tidak tersedia"
                    p_noimg.font.name = 'Arial'
                    p_noimg.font.size = Pt(6.5)
                    p_noimg.font.italic = True
                    p_noimg.font.color.rgb = RGBColor(160, 170, 185)
                    p_noimg.alignment = PP_ALIGN.CENTER

                cap_text = photos[0]['caption']
                if len(cap_text) > 36:
                    cap_text = cap_text[:34] + '..'
                tb_cap = cur_slide.shapes.add_textbox(mm(px), mm(py + img_h + 0.5), mm(img_w), mm(8))
                tf_cap = tb_cap.text_frame
                tf_cap.word_wrap = True
                tf_cap.margin_left = tf_cap.margin_top = tf_cap.margin_right = tf_cap.margin_bottom = 0
                p_cap = tf_cap.paragraphs[0]
                p_cap.text = cap_text
                p_cap.font.name = 'Arial'
                p_cap.font.size = Pt(6.5)
                p_cap.font.color.rgb = RGBColor(40, 50, 65)
                p_cap.alignment = PP_ALIGN.CENTER
            else:
                img_w = 31
                img_h = 22
                gap = 4
                num_subrows = ((num_photos - 1) // 2) + 1

                for subrow_idx in range(num_subrows):
                    start_idx = subrow_idx * 2
                    end_idx = min(start_idx + 2, num_photos)
                    row_photos = photos[start_idx:end_idx]
                    n_in_row = len(row_photos)

                    total_row_width = (n_in_row * img_w) + ((n_in_row - 1) * gap)
                    offset_x = (col4_w - total_row_width) / 2
                    py = y_start + 2 + (subrow_idx * 31)

                    for col_idx, pinfo in enumerate(row_photos):
                        px = col4_x + offset_x + (col_idx * (img_w + gap))
                        processed_path = self._process_image(pinfo['path'])

                        if processed_path:
                            f_box = cur_slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(px), mm(py), mm(img_w), mm(img_h))
                            f_box.fill.solid()
                            f_box.fill.fore_color.rgb = self.COLOR_WHITE
                            f_box.line.color.rgb = RGBColor(210, 215, 225)
                            f_box.line.width = Pt(0.5)

                            try:
                                cur_slide.shapes.add_picture(processed_path, mm(px + 0.5), mm(py + 0.5), width=mm(img_w - 1), height=mm(img_h - 1))
                            except Exception as e:
                                print(f"Error adding picture to PPT: {e}")
                        else:
                            f_box = cur_slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, mm(px), mm(py), mm(img_w), mm(img_h))
                            f_box.fill.solid()
                            f_box.fill.fore_color.rgb = RGBColor(248, 250, 252)
                            f_box.line.color.rgb = RGBColor(225, 230, 240)
                            f_box.line.width = Pt(0.5)

                            tb_noimg = cur_slide.shapes.add_textbox(mm(px), mm(py + 8), mm(img_w), mm(8))
                            p_noimg = tb_noimg.text_frame.paragraphs[0]
                            p_noimg.text = "Foto tidak tersedia"
                            p_noimg.font.name = 'Arial'
                            p_noimg.font.size = Pt(6)
                            p_noimg.font.italic = True
                            p_noimg.font.color.rgb = RGBColor(160, 170, 185)
                            p_noimg.alignment = PP_ALIGN.CENTER

                        cap_text = pinfo['caption']
                        if len(cap_text) > 28:
                            cap_text = cap_text[:26] + '..'
                        tb_cap = cur_slide.shapes.add_textbox(mm(px), mm(py + img_h + 0.5), mm(img_w), mm(8))
                        tf_cap = tb_cap.text_frame
                        tf_cap.word_wrap = True
                        tf_cap.margin_left = tf_cap.margin_top = tf_cap.margin_right = tf_cap.margin_bottom = 0
                        p_cap = tf_cap.paragraphs[0]
                        p_cap.text = cap_text
                        p_cap.font.name = 'Arial'
                        p_cap.font.size = Pt(6)
                        p_cap.font.color.rgb = RGBColor(40, 50, 65)
                        p_cap.alignment = PP_ALIGN.CENTER

            y_cursor += row_height

        # Lembar Tanda Tangan di Akhir
        self._draw_signatures(cur_slide, y_cursor)

    def _finalize_page_numbers(self):
        """Update placeholder {TOTAL} dengan total halaman sebenarnya"""
        total = len(self.prs.slides)
        for sinfo in self.content_slides:
            p_num = sinfo['page_num']
            if sinfo['page_shape']:
                tf = sinfo['page_shape'].text_frame
                tf.paragraphs[0].text = f"{p_num} dari {total}"
            if sinfo['foot_shape']:
                tf_f = sinfo['foot_shape'].text_frame
                tf_f.paragraphs[0].text = f"PT JAYA TEKNIK INDONESIA | Halaman {p_num} dari {total}"

    def build_ppt(self, work_orders):
        """Membuat seluruh slide dan mengembalikan BytesIO data presentation"""
        if self.include_cover:
            self.draw_cover()
        self.render_work_orders(work_orders)
        self._finalize_page_numbers()

        ppt_io = io.BytesIO()
        self.prs.save(ppt_io)
        ppt_io.seek(0)

        # Bersihkan file temporer
        for tf in self.temp_files_to_clean:
            try:
                os.unlink(tf)
            except Exception:
                pass
        self.temp_files_to_clean.clear()

        return ppt_io
