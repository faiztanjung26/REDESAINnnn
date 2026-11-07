import os
import tempfile
import base64
from datetime import datetime, timedelta
from PIL import Image, ImageOps

try:
    from pdf_utils import SafeFPDF as FPDF, calc_num_lines, clean_pdf_text
except ImportError:
    try:
        from fpdf import FPDF
        from pdf_utils import calc_num_lines, clean_pdf_text
    except ImportError as err:
        raise ImportError(
            "Paket 'fpdf2' belum terinstall di environment server. "
            "Solusi di server: Jalankan 'pip install fpdf2' lalu restart service Flask."
        ) from err

from utils import get_wo_chiller_details


class MonthlyWOReportPDF(FPDF):
    """
    Generator Laporan Bulanan Work Order (Portrait A4)
    PT Jaya Teknik Indonesia
    Format laporan gabungan:
    Judul (Cover) -> Chiller Details -> REPORT WORK ORDER -> Foto Lampiran -> lanjut ke Chiller/WO berikutnya.
    """
    def __init__(self, site_name='ALL SITES', period_str='', include_cover=True, root_path=None):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.site_name = site_name or 'ALL SITES'
        self.period_str = period_str or datetime.now().strftime('%B %Y').upper()
        self.include_cover = include_cover
        self.root_path = root_path or os.path.dirname(os.path.abspath(__file__))
        self.set_auto_page_break(auto=True, margin=15)
        self.alias_nb_pages()
        self.temp_files_to_clean = []

    def draw_cover(self):
        """Merender Halaman Judul / Cover Laporan Bulanan Work Order Portrait"""
        self.add_page()
        self.set_left_margin(10)
        self.set_right_margin(10)
        self.set_auto_page_break(auto=False)

        # Background Image (judul.png)
        title_image_path = os.path.join(self.root_path, 'static', 'images', 'judul.png')
        if not os.path.exists(title_image_path):
            title_image_path = os.path.join(self.root_path, 'static', 'images', 'cover_wo_landscape.png')

        if os.path.exists(title_image_path):
            self.image(title_image_path, x=0, y=0, w=self.w, h=self.h)

        line1 = "LAPORAN BULANAN WORK ORDER"
        line1_sub = "PREVENTIVE & CORRECTIVE MAINTENANCE"
        line2 = f"{self.site_name.upper()}"
        line3 = f"PERIODE: {self.period_str.upper()}"
        line4 = datetime.now().strftime("%d %B %Y").upper()

        # Posisi teks di kiri bawah persis seperti cover WO satuan
        self.set_y(-105)
        self.set_left_margin(20)

        self.set_font('helvetica', 'B', 24)
        self.cell(0, 12, line1, 0, 1, 'L')
        self.set_font('helvetica', 'B', 24)
        self.cell(0, 12, line1_sub, 0, 1, 'L')

        self.set_font('helvetica', 'B', 18)
        self.cell(0, 10, line2, 0, 1, 'L')

        self.set_font('helvetica', 'B', 18)
        self.cell(0, 10, line3, 0, 1, 'L')

        self.set_font('helvetica', 'B', 16)
        self.cell(0, 9, line4, 0, 1, 'L')

        self.set_left_margin(10)
        self.set_auto_page_break(auto=True, margin=15)

    def _resolve_img_path(self, raw_p):
        """Helper pencarian file gambar secara komprehensif"""
        if not raw_p:
            return None
        clean = raw_p.replace('\\', '/').strip()
        candidates = [
            os.path.join(self.root_path, 'static', clean),
            os.path.join(self.root_path, clean),
            clean
        ]
        if clean.startswith('uploads/') or clean.startswith('static/'):
            sub = clean.split('/', 1)[1]
            candidates.append(os.path.join(self.root_path, 'static', sub))
            candidates.append(os.path.join(self.root_path, sub))
        else:
            candidates.append(os.path.join(self.root_path, 'static', 'uploads', clean))

        for c in candidates:
            if os.path.exists(c) and os.path.isfile(c):
                return c
        return None

    def _save_temp_image(self, b64_str):
        """Helper decode base64 signature image ke file temporer"""
        if not b64_str or ',' not in b64_str:
            return None
        try:
            _, encoded = b64_str.split(",", 1)
            data = base64.b64decode(encoded)
            fd, temp_path = tempfile.mkstemp(suffix='.png')
            with os.fdopen(fd, 'wb') as f:
                f.write(data)
            self.temp_files_to_clean.append(temp_path)
            return temp_path
        except Exception:
            return None

    def _fmt_dt(self, dt, convert=True):
        """Helper format tanggal & waktu WIB"""
        if dt:
            if convert:
                dt_wib = dt + timedelta(hours=7)
                return dt_wib.strftime('%d-%m-%Y %H:%M')
            return dt.strftime('%d-%m-%Y %H:%M')
        return '-'

    def render_chiller_details(self, wo):
        """Merender Halaman Chiller Details jika aset WO merupakan unit Chiller"""
        if not wo.asset:
            return

        chiller_info = get_wo_chiller_details(wo.asset)
        if not chiller_info:
            return

        self.add_page()
        self.set_left_margin(10)
        self.set_right_margin(10)
        self.set_auto_page_break(auto=True, margin=15)

        self.set_font('helvetica', 'B', 16)
        self.cell(0, 10, f"Laporan Chiller - {chiller_info['site_name']}", 0, 1, 'C')
        self.cell(0, 10, f"Chiller: {chiller_info['chiller_num']}", 0, 1, 'C')
        self.ln(10)

        # Gambar Chiller
        image_filename = chiller_info.get('image_filename') or 'chiller.png'
        image_path = os.path.join(self.root_path, 'static', 'images', image_filename)
        if not os.path.exists(image_path):
            image_path = os.path.join(self.root_path, 'static', 'images', 'chiller.png')

        if os.path.exists(image_path):
            image_width = 150
            page_width = self.w - self.l_margin - self.r_margin
            x_centered = self.l_margin + (page_width - image_width) / 2
            calc_h = 85
            try:
                with Image.open(image_path) as im:
                    im_w, im_h = im.size
                    calc_h = (image_width / im_w) * im_h
            except Exception:
                calc_h = 85

            self.image(image_path, x=x_centered, y=self.get_y(), w=image_width)
            self.ln(calc_h + 5)

        # Tabel Chiller Details
        self.set_font('helvetica', 'B', 12)
        self.cell(0, 10, 'Chiller Details', 0, 1, 'C')
        self.ln(5)
        self.set_font('helvetica', '', 10)
        table_width = 150
        col_width_key = 60
        col_width_value = 90
        start_x = (self.w - table_width) / 2

        for key, value in chiller_info['details_to_show'].items():
            if value is not None and str(value).strip():
                self.set_x(start_x)
                self.cell(col_width_key, 10, f'{key}:', 1, 0)
                self.cell(col_width_value, 10, str(value), 1, 1)
        self.ln(10)

    def render_work_order(self, wo):
        """Merender Halaman REPORT WORK ORDER (Header, Details, Tech, Checking, Tasklist, Note, Signatures)"""
        self.add_page()
        self.set_left_margin(10)
        self.set_right_margin(10)
        self.set_auto_page_break(auto=True, margin=15)

        self.set_font("helvetica", style="B", size=10)
        start_x = self.get_x()
        start_y = self.get_y()

        # 1. HEADER REPORT WORK ORDER
        self.cell(35, 24, "", border=1)  # Kotak Logo
        logo_path = os.path.join(self.root_path, 'static', 'images', 'Logo Jaya Teknik.png')
        if os.path.exists(logo_path):
            try:
                self.image(logo_path, x=start_x + 2, y=start_y + 2, w=31)
            except Exception:
                pass

        # Judul Dokumen
        self.set_font("helvetica", style="B", size=14)
        self.set_xy(start_x + 35, start_y)
        self.cell(105, 24, "", border=1)
        self.set_xy(start_x + 35, start_y + 12)
        self.cell(105, 8, "REPORT WORK ORDER", align="C")

        # Info Pengendalian Dokumen ISO di Kanan
        self.set_font("helvetica", size=8)
        self.set_xy(start_x + 140, start_y)
        self.cell(20, 6, "No.Dok", border=1)
        self.cell(30, 6, "RP - JT - 26", border=1)

        self.set_xy(start_x + 140, start_y + 6)
        self.cell(20, 6, "Ref.", border=1)
        self.cell(30, 6, "7; 7.1.3 & 7.1.4", border=1)

        self.set_xy(start_x + 140, start_y + 12)
        self.cell(20, 6, "Rev.", border=1)
        self.cell(30, 6, "Original", border=1)

        self.set_xy(start_x + 140, start_y + 18)
        self.cell(20, 6, "Tanggal", border=1)
        printed_date = datetime.now().strftime("%d %b %Y")
        self.cell(30, 6, printed_date, border=1)

        # 2. DETAILS BODY
        self.set_xy(start_x, start_y + 24)
        self.set_font("helvetica", size=9)
        self.cell(190, 24, "", border=1)
        self.set_xy(start_x, start_y + 24)

        form_val = getattr(wo, 'maintenance_type', 'SERVICE') or 'SERVICE'
        nomor_val = wo.code or '-'
        asset_val = f"{wo.asset.name} ({wo.asset.code})" if wo.asset and wo.asset.code else (wo.asset.name if wo.asset else '-')

        assignees_list = list(wo.assignees) if getattr(wo, 'assignees', None) else []
        tech_val = ", ".join([a.name for a in assignees_list]) if assignees_list else "N/A"

        # Responsible is the user who changed status to Completed
        completed_by_user = None
        try:
            logs = wo.logs.all() if hasattr(wo.logs, 'all') else list(wo.logs)
            for log in logs:
                if log.log_text and "status changed to completed" in log.log_text.lower():
                    if log.user and log.user.name:
                        completed_by_user = log.user.name
                        break
        except Exception as e:
            print(f"Error fetching completed_by from logs: {e}")

        resp_val = completed_by_user or tech_val
        proj_val = (wo.asset.project_code if wo.asset and wo.asset.project_code else wo.project_code) or '-'

        loc_val = '-'
        if wo.asset and hasattr(wo.asset, 'location') and wo.asset.location:
            loc_val = wo.asset.location.name if hasattr(wo.asset.location, 'name') else str(wo.asset.location)

        sched_val = f"{self._fmt_dt(wo.suggested_start_date)} s/d {self._fmt_dt(wo.suggested_completion_date)}"
        act_val = f"{self._fmt_dt(wo.start_date)} s/d {self._fmt_dt(wo.end_date)}"

        # Line 1
        self.cell(20, 6, "Form", border=0)
        self.cell(5, 6, ":", border=0)
        self.cell(70, 6, str(form_val)[:35], border=0)
        self.cell(20, 6, "Project", border=0)
        self.cell(5, 6, ":", border=0)
        self.cell(70, 6, str(proj_val)[:35], border=0, ln=1)

        # Line 2
        self.cell(20, 6, "Nomor", border=0)
        self.cell(5, 6, ":", border=0)
        self.cell(70, 6, str(nomor_val)[:35], border=0)
        self.cell(20, 6, "Location", border=0)
        self.cell(5, 6, ":", border=0)
        self.cell(70, 6, str(loc_val)[:35], border=0, ln=1)

        # Line 3
        self.cell(20, 6, "Asset", border=0)
        self.cell(5, 6, ":", border=0)
        self.cell(70, 6, str(asset_val)[:35], border=0)
        self.cell(20, 6, "Schedule", border=0)
        self.cell(5, 6, ":", border=0)
        self.cell(70, 6, str(sched_val)[:40], border=0, ln=1)

        # Line 4
        self.cell(20, 6, "Responsible", border=0)
        self.cell(5, 6, ":", border=0)
        self.cell(70, 6, str(resp_val)[:35], border=0)
        self.cell(20, 6, "Actual Date", border=0)
        self.cell(5, 6, ":", border=0)
        self.cell(70, 6, str(act_val)[:40], border=0, ln=1)

        self.ln(5)

        # 3. TECHNICIAN
        self.set_fill_color(220, 220, 220)
        self.set_font("helvetica", style="B", size=10)
        self.cell(190, 6, "TECHNICIAN", border=1, align="C", fill=True, ln=1)
        self.cell(190, 6, "Name", border=1, align="C", fill=True, ln=1)
        self.set_font("helvetica", size=9)
        tech_str = str(tech_val) if tech_val else "N/A"
        self.multi_cell(190, 5, tech_str, border=1, align="L")
        self.ln(5)

        # 4. CHECKING REPORT
        self.set_fill_color(220, 220, 220)
        self.set_font("helvetica", style="B", size=10)
        self.cell(190, 6, "CHECKING REPORT", border=1, align="C", fill=True, ln=1)

        def print_checking_header():
            self.set_fill_color(220, 220, 220)
            self.set_font("helvetica", style="B", size=8)
            self.cell(75, 8, "Description (Unit Check)", border=1, align="C", fill=True)
            self.cell(25, 8, "Standard", border=1, align="C", fill=True)
            self.cell(25, 8, "Actual", border=1, align="C", fill=True)
            self.cell(25, 8, "Check", border=1, align="C", fill=True)
            self.cell(40, 8, "Note", border=1, align="C", fill=True, ln=1)
            self.set_font("helvetica", size=8)

        print_checking_header()
        line_h = 4.5
        checklist_items = wo.checklist_parameters.all() if hasattr(wo.checklist_parameters, 'all') else list(wo.checklist_parameters)
        for param in checklist_items:
            desc = str(param.parameter or "")
            std_val = str(param.standard) if (param.standard is not None and str(param.standard).strip() != "") else "-"
            actual_val = str(param.value) if (param.value is not None and str(param.value).strip() != "") else "-"
            check_val = "OK" if (actual_val != "-" and str(actual_val).strip() != "") else "-"
            note_val = str(param.note or "")

            lines_desc = calc_num_lines(self, desc, 75)
            lines_std = calc_num_lines(self, std_val, 25)
            lines_act = calc_num_lines(self, actual_val, 25)
            lines_note = calc_num_lines(self, note_val, 40)

            max_lines = max(lines_desc, lines_std, lines_act, lines_note, 1)
            row_height = max(6.0, max_lines * line_h + 1.5)

            if self.get_y() + row_height > 275:
                self.add_page()
                print_checking_header()

            x = 10
            y = self.get_y()

            self.rect(x, y, 75, row_height)
            self.rect(x + 75, y, 25, row_height)
            self.rect(x + 100, y, 25, row_height)
            self.rect(x + 125, y, 25, row_height)
            self.rect(x + 150, y, 40, row_height)

            y_off_desc = y + (row_height - (lines_desc * line_h)) / 2
            self.set_xy(x + 1.5, y_off_desc)
            self.multi_cell(72, line_h, desc, border=0, align="L")

            y_off_std = y + (row_height - (lines_std * line_h)) / 2
            self.set_xy(x + 75 + 1, y_off_std)
            self.multi_cell(23, line_h, std_val, border=0, align="C")

            y_off_act = y + (row_height - (lines_act * line_h)) / 2
            self.set_xy(x + 100 + 1, y_off_act)
            self.multi_cell(23, line_h, actual_val, border=0, align="C")

            self.set_xy(x + 125, y)
            self.cell(25, row_height, check_val, border=0, align="C")

            y_off_note = y + (row_height - (lines_note * line_h)) / 2
            self.set_xy(x + 150 + 1.5, y_off_note)
            self.multi_cell(37, line_h, note_val, border=0, align="L")

            self.set_xy(x, y + row_height)

        self.ln(5)

        # 5. TASKLIST REPORT
        self.set_fill_color(220, 220, 220)
        self.set_font("helvetica", style="B", size=10)
        self.cell(190, 6, "TASKLIST REPORT", border=1, align="C", fill=True, ln=1)

        def print_tasklist_header():
            self.set_fill_color(220, 220, 220)
            self.set_font("helvetica", style="B", size=8)
            self.cell(70, 8, "Step Name", border=1, align="C", fill=True)
            self.cell(90, 8, "Description", border=1, align="C", fill=True)
            self.cell(30, 8, "State", border=1, align="C", fill=True, ln=1)
            self.set_font("helvetica", size=8)

        print_tasklist_header()
        procedures_list = wo.procedures.all() if hasattr(wo.procedures, 'all') else list(wo.procedures)
        for proc in procedures_list:
            step_name = proc.name or ''
            desc = proc.notes or getattr(proc, 'description', '') or ''

            lines_step = calc_num_lines(self, step_name, 70)
            lines_desc = calc_num_lines(self, desc, 90)

            max_lines = max(lines_step, lines_desc, 1)
            row_height = max(6.0, max_lines * 5.0 + 1.5)

            if self.get_y() + row_height > 275:
                self.add_page()
                print_tasklist_header()

            x_start = 10
            y_start = self.get_y()

            self.rect(x_start, y_start, 70, row_height)
            self.rect(x_start + 70, y_start, 90, row_height)
            self.rect(x_start + 160, y_start, 30, row_height)

            y_off_step = y_start + (row_height - (lines_step * 5.0)) / 2
            self.set_xy(x_start + 1.5, y_off_step)
            self.multi_cell(67, 5.0, step_name, border=0)

            y_off_desc = y_start + (row_height - (lines_desc * 5.0)) / 2
            self.set_xy(x_start + 70 + 1.5, y_off_desc)
            self.multi_cell(87, 5.0, desc, border=0)

            self.set_xy(x_start + 160, y_start)
            self.cell(30, row_height, "Done" if getattr(proc, 'is_completed', False) else "Pending", border=0, align="C")

            self.set_xy(x_start, y_start + row_height)

        self.ln(3)

        # 6. NOTE (Tasklist Global Note)
        note_txt = (getattr(wo, 'tasklist_note', None) or '').strip()
        if note_txt:
            lines_note = max(1, int(self.get_string_width(note_txt) / 184) + 1) + note_txt.count('\n')
            note_box_h = max(18.0, lines_note * 4.5 + 6.0)
        else:
            note_box_h = 18.0

        if self.get_y() + 6.0 + note_box_h > 275:
            self.add_page()

        self.set_font("helvetica", style="B", size=9)
        self.set_fill_color(220, 220, 220)
        self.cell(190, 6, "NOTE", border=1, align="C", fill=True, ln=1)

        y_n = self.get_y()
        self.set_draw_color(0, 0, 0)
        self.set_line_width(0.3)
        self.rect(10, y_n, 190, note_box_h)

        self.set_xy(12, y_n + 2)
        self.set_font("helvetica", size=8.5)
        if note_txt:
            self.multi_cell(186, 4.5, note_txt)
        else:
            self.cell(186, 5, "-", ln=1)

        self.set_xy(10, y_n + note_box_h + 3)

        self.ln(3)

        # 7. SIGNATURES
        self.ln(2)
        first_tech = assignees_list[0] if assignees_list else None
        tech_name = first_tech.name if first_tech else "....."
        tech_role = getattr(first_tech, 'role', None) or "....."
        wo_site_name = wo.asset.site.name.upper() if wo.asset and getattr(wo.asset, 'site', None) else self.site_name.upper()

        if self.get_y() > 240:
            self.add_page()

        sig_y = self.get_y()

        c_name_print = getattr(wo, 'customer_name', None) or "....."
        c_title_print = getattr(wo, 'customer_title', None) or "....."

        # Cek Digital Signature
        ds = None
        try:
            from models import DigitalSignature
            ds = DigitalSignature.query.filter_by(work_order_id=wo.id).first()
        except Exception:
            pass

        # Left Column (Pihak Pertama)
        self.set_xy(15, sig_y)
        self.set_font("helvetica", style="B", size=9)
        self.cell(90, 5, "PIHAK PERTAMA,", ln=1)
        self.set_x(15)
        self.cell(90, 5, wo_site_name, ln=1)

        if not ds:
            c_img_path = self._save_temp_image(getattr(wo, 'customer_signature', None))
            if c_img_path:
                try:
                    self.image(c_img_path, x=15, y=sig_y + 12, h=16)
                except Exception:
                    pass

        self.set_xy(15, sig_y + 35)
        self.set_font("helvetica", size=9)
        self.cell(90, 5, f"Nama : {c_name_print}", ln=1)
        self.set_x(15)
        self.cell(90, 5, f"Jabatan : {c_title_print}", ln=1)

        # Right Column (Pihak Kedua)
        self.set_xy(110, sig_y)
        self.set_font("helvetica", style="B", size=9)
        self.cell(85, 5, "PIHAK KEDUA,", ln=1)
        self.set_x(110)
        self.cell(85, 5, "PT JAYA TEKNIK INDONESIA", ln=1)

        if not ds:
            t_img_path = self._save_temp_image(getattr(wo, 'technician_signature', None))
            if t_img_path:
                try:
                    self.image(t_img_path, x=110, y=sig_y + 12, h=16)
                except Exception:
                    pass

        self.set_xy(110, sig_y + 35)
        self.set_font("helvetica", size=9)
        self.cell(85, 5, f"Nama : {tech_name}", ln=1)
        self.set_x(110)
        self.cell(85, 5, f"Jabatan : {tech_role}", ln=1)

        # Center Column (Digital Signature QR)
        if ds:
            try:
                import qrcode
                try:
                    from flask import request
                    url_root = request.url_root.rstrip('/') if request else ''
                except Exception:
                    url_root = ''

                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=10,
                    border=1,
                )
                verify_url = f"{url_root}/verify/doc?id={ds.id}"
                qr.add_data(verify_url)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")

                fd, temp_path = tempfile.mkstemp(suffix='.png')
                with os.fdopen(fd, 'wb') as f:
                    img.save(f)
                self.temp_files_to_clean.append(temp_path)

                self.image(temp_path, x=135, y=sig_y + 10, h=18)

                self.set_xy(125, sig_y + 29)
                self.set_font("helvetica", size=6, style="B")
                self.set_text_color(0, 150, 0)
                self.cell(38, 3, "DIGITALLY SIGNED", ln=1, align="C")
                self.set_xy(125, sig_y + 32)
                self.cell(38, 3, "& VERIFIED", ln=1, align="C")
                self.set_text_color(0, 0, 0)
            except Exception as e:
                print(f"Error rendering digital signature QR: {e}")

        self.set_y(sig_y + 45)

    def render_photo_attachments(self, wo):
        """Merender Halaman Lampiran Foto (Grid 3 foto per baris dengan kotak seksi persis format WO satuan)"""
        photo_groups = []

        # 1. Kumpulkan foto dari prosedur/tasklist
        procedures_list = wo.procedures.all() if hasattr(wo.procedures, 'all') else list(wo.procedures)
        for proc in procedures_list:
            if getattr(proc, 'attachment_path', None):
                paths = [p.strip() for p in proc.attachment_path.split('|') if p.strip()]
                valid_paths = []
                for p in paths:
                    resolved = self._resolve_img_path(p)
                    if resolved:
                        valid_paths.append(resolved)
                if valid_paths:
                    title = proc.name.strip() if proc.name else 'Prosedur'
                    if not title.lower().startswith("lampiran"):
                        title = f"Lampiran {title}"
                    photo_groups.append({'title': title, 'paths': valid_paths})

        # 2. Kumpulkan foto dari lampiran umum
        attachments_list = wo.attachments.all() if hasattr(wo.attachments, 'all') else list(wo.attachments)
        for att in attachments_list:
            if getattr(att, 'file_path', None):
                resolved = self._resolve_img_path(att.file_path)
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

        self.set_auto_page_break(auto=False)
        self.add_page()

        PAGE_BOTTOM_LIMIT = 282
        y_cursor = 10
        img_w = 48
        img_h = 52
        gap_x = 11.5
        gap_y = 6.0

        def _draw_photo_box(p_path, px, py, pw, ph):
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
                    im = im.resize((480, int(480 / target_aspect)))

                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
                    if im.mode != 'RGB':
                        im = im.convert('RGB')
                    im.save(tmp.name, 'JPEG', quality=85)
                    tmp.close()
                    self.temp_files_to_clean.append(tmp.name)

                    self.image(tmp.name, x=px, y=py, w=pw, h=ph)

                    self.set_draw_color(220, 220, 220)
                    self.rect(px, py, pw, ph)
                    self.set_draw_color(0, 0, 0)
                    rendered = True
            except Exception as e:
                print(f"Error processing image {p_path}: {e}")

            if not rendered:
                self.set_fill_color(240, 240, 240)
                self.set_draw_color(200, 200, 200)
                self.rect(px, py, pw, ph, style='FD')
                self.set_font('helvetica', 'I', 7)
                self.set_text_color(150, 150, 150)
                self.set_xy(px, py + ph / 2 - 2)
                self.cell(pw, 4, "[Foto]", align='C')
                self.set_text_color(0, 0, 0)
                self.set_draw_color(0, 0, 0)

        def _calc_title_lines(txt, max_w):
            words = txt.split(' ')
            lines = 1
            cur_line = ''
            for w in words:
                test_line = cur_line + (' ' if cur_line else '') + w
                if self.get_string_width(test_line) <= max_w:
                    cur_line = test_line
                else:
                    lines += 1
                    cur_line = w
            return max(1, lines)

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
                title_font_size = 8.0 if n_items == 3 else 9.0
                self.set_font('helvetica', 'B', title_font_size)

                max_title_lines = 1
                for item in items:
                    lines = _calc_title_lines(item['title'], col_w - 6)
                    if lines > max_title_lines:
                        max_title_lines = lines

                title_text_h = max_title_lines * 4.0
                padding_top = 3.5
                padding_mid = 3.0
                padding_bottom = 4.0
                row_h = padding_top + title_text_h + padding_mid + img_h + padding_bottom

                avail_h = PAGE_BOTTOM_LIMIT - y_cursor
                if avail_h < row_h:
                    self.add_page()
                    y_cursor = 10
                    avail_h = PAGE_BOTTOM_LIMIT - y_cursor

                for i, item in enumerate(items):
                    col_x = 10.0 + i * col_w
                    cur_col_w = col_w if i < n_items - 1 else (200.0 - col_x)

                    # 1. Outer box for this column
                    self.set_draw_color(0, 0, 0)
                    self.set_line_width(0.3)
                    self.rect(col_x, y_cursor, cur_col_w, row_h)

                    # 2. Section Header Title (Centered)
                    self.set_font('helvetica', 'B', title_font_size)
                    self.set_text_color(0, 0, 0)
                    self.set_xy(col_x + 2, y_cursor + padding_top)
                    self.multi_cell(cur_col_w - 4, 4.0, item['title'], align='C')

                    # 3. Photo
                    photo_x = col_x + (cur_col_w - img_w) / 2
                    photo_y = y_cursor + padding_top + title_text_h + padding_mid
                    _draw_photo_box(item['paths'][0], photo_x, photo_y, img_w, img_h)

                y_cursor += row_h
                self.set_xy(10, y_cursor)
            else:
                grp = block['grp']
                group_title = grp['title']
                all_paths = list(grp['paths'])
                is_cont = False

                while all_paths:
                    avail_h = PAGE_BOTTOM_LIMIT - y_cursor
                    self.set_font('helvetica', 'B', 10)
                    curr_title = group_title if not is_cont else f"{group_title} (Lanjutan)"
                    title_lines = max(1, int(self.get_string_width(curr_title) / 180) + 1)
                    title_text_h = title_lines * 4.5
                    title_total_h = 3.5 + title_text_h + 3.5
                    padding_bottom = 5.0

                    min_sec_h = title_total_h + img_h + padding_bottom
                    if avail_h < min_sec_h:
                        self.add_page()
                        y_cursor = 10
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

                    # 1. Section Outer Box
                    self.set_draw_color(0, 0, 0)
                    self.set_line_width(0.3)
                    self.rect(10, y_cursor, 190, section_h)

                    # 2. Section Header Title (Centered)
                    self.set_font('helvetica', 'B', 10)
                    self.set_text_color(0, 0, 0)
                    self.set_xy(10, y_cursor + 3.5)
                    self.multi_cell(190, 4.5, curr_title, align='C')

                    # 3. Grid of Photos
                    y_photo_start = y_cursor + title_total_h
                    for r in range(n_rows):
                        row_paths = chunk[r * 3: (r + 1) * 3]
                        n_in_row = len(row_paths)
                        y_row = y_photo_start + r * (img_h + gap_y)

                        if n_in_row == 3:
                            x_positions = [10 + gap_x + i * (img_w + gap_x) for i in range(3)]
                        elif n_in_row == 2:
                            row_w = 2 * img_w + gap_x
                            start_x = 10 + (190 - row_w) / 2
                            x_positions = [start_x, start_x + img_w + gap_x]
                        else:
                            x_positions = [10 + (190 - img_w) / 2]

                        for c, p in enumerate(row_paths):
                            _draw_photo_box(p, x_positions[c], y_row, img_w, img_h)

                    y_cursor += section_h
                    self.set_xy(10, y_cursor)
                    is_cont = True

        self.set_auto_page_break(auto=True, margin=15)

    def build_pdf(self, work_orders):
        """Membuat seluruh halaman dokumen laporan bulanan gabungan dan mengembalikan bytes data PDF"""
        try:
            # 1. Halaman Cover / Judul (jika diaktifkan)
            if self.include_cover:
                self.draw_cover()

            # 2. Iterasi setiap Work Order: Chiller Details -> REPORT WORK ORDER -> Foto Lampiran
            for wo in work_orders:
                # 2.1 Chiller Details (jika aset merupakan unit chiller)
                self.render_chiller_details(wo)

                # 2.2 REPORT WORK ORDER (halaman lengkap WO: detail, teknisi, checklist, tasklist, note, tanda tangan)
                self.render_work_order(wo)

                # 2.3 Lampiran Foto (grid foto dari prosedur & berkas)
                self.render_photo_attachments(wo)

            try:
                out = self.output(dest='S')
            except TypeError:
                out = self.output()

            pdf_bytes = out.encode('latin-1') if isinstance(out, str) else bytes(out)
            return pdf_bytes
        finally:
            # Bersihkan semua file temporer
            for tf in self.temp_files_to_clean:
                try:
                    if os.path.exists(tf):
                        os.unlink(tf)
                except Exception:
                    pass
            self.temp_files_to_clean.clear()
