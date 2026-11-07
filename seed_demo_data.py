"""
Script Seeder Data Demo CMMS untuk Redesign & Development.
Menghasilkan data mockup realistis tanpa data pribadi atau sensitif.
"""

import os
from datetime import datetime, timedelta
from app import create_app
from models import (
    db, User, Site, Team, Location, Category, SubCategory, Asset,
    WorkOrderStatus, WorkOrder, WorkOrderProcedure, WorkOrderChecklistParameter,
    WorkOrderLog, Part, StockLevel, Vendor, HelpdeskModule, HelpdeskLocation,
    HelpdeskTicket, HelpdeskProcedure, HelpdeskChecklistParameter,
    Tasklist, TasklistProcedure, Checklist, ChecklistParameterTemplate,
    SystemSetting, Customer, ProjectCode
)

def seed_all():
    app = create_app()
    with app.app_context():
        print("[1/9] Inisialisasi Database Schema...")
        db.create_all()

        print("[2/9] Membuat Work Order Statuses...")
        statuses = [
            ('Draft', 'Draft'),
            ('Assigned', 'Pending'),
            ('Confirmed', 'Pending'),
            ('In Progress', 'Active'),
            ('Hold', 'Pending'),
            ('Solved', 'Active'),
            ('Completed', 'Closed'),
            ('Closed', 'Closed'),
            ('Incompleted', 'Closed')
        ]
        status_map = {}
        for name, control in statuses:
            st = WorkOrderStatus.query.filter_by(name=name).first()
            if not st:
                st = WorkOrderStatus(name=name, control_type=control)
                db.session.add(st)
                db.session.flush()
            status_map[name] = st

        print("[3/9] Membuat Master Sites, Teams, & Locations...")
        site1 = Site.query.filter_by(name="Menara Jaya Sudirman (HQ)").first()
        if not site1:
            site1 = Site(name="Menara Jaya Sudirman (HQ)", project_code="PRJ-HQ-01", address="Jl. Jend. Sudirman Kav. 21, Jakarta Selatan")
            db.session.add(site1)
            db.session.flush()

        site2 = Site.query.filter_by(name="Pabrik Cikarang Sentra").first()
        if not site2:
            site2 = Site(name="Pabrik Cikarang Sentra", project_code="PRJ-CKR-02", address="Kawasan Industri MM2100 Blok C, Cikarang")
            db.session.add(site2)
            db.session.flush()

        # Project codes
        for code, desc in [("PRJ-HQ-01", "Proyek Gedung HQ Sudirman"), ("PRJ-CKR-02", "Proyek Pabrik Cikarang")]:
            if not ProjectCode.query.filter_by(code=code).first():
                db.session.add(ProjectCode(code=code, description=desc))

        team_mech = Team.query.filter_by(name="Tim Mekanikal & HVAC", site_id=site1.id).first()
        if not team_mech:
            team_mech = Team(name="Tim Mekanikal & HVAC", site_id=site1.id)
            db.session.add(team_mech)

        team_elec = Team.query.filter_by(name="Tim Elektrikal & Otomasi", site_id=site1.id).first()
        if not team_elec:
            team_elec = Team(name="Tim Elektrikal & Otomasi", site_id=site1.id)
            db.session.add(team_elec)

        team_plant = Team.query.filter_by(name="Tim Pemeliharaan Fasilitas", site_id=site2.id).first()
        if not team_plant:
            team_plant = Team(name="Tim Pemeliharaan Fasilitas", site_id=site2.id)
            db.session.add(team_plant)
        db.session.flush()

        # Locations
        locs_data = [
            (site1.id, "Lantai Semi-Basement (Plant Room)"),
            (site1.id, "Lantai 1 - Lobby & Front Office"),
            (site1.id, "Lantai 5 - Ruang Server & IT"),
            (site1.id, "Rooftop - Chiller & Cooling Tower Area"),
            (site2.id, "Gedung Produksi Utama"),
            (site2.id, "Gudang Sentral Sparepart")
        ]
        loc_map = {}
        for s_id, loc_name in locs_data:
            loc = Location.query.filter_by(name=loc_name, site_id=s_id).first()
            if not loc:
                loc = Location(name=loc_name, site_id=s_id)
                db.session.add(loc)
                db.session.flush()
            loc_map[loc_name] = loc

        print("[4/9] Membuat User Akun Login Demo...")
        users_to_seed = [
            {
                "nrp": "admin",
                "name": "Super Administrator",
                "role": "Admin",
                "password": "admin123",
                "phone": "081200000001",
                "site_id": None,
                "team_id": None
            },
            {
                "nrp": "supervisor",
                "name": "Supervisor Teknik",
                "role": "Supervisor",
                "password": "supervisor123",
                "phone": "081200000002",
                "site_id": site1.id,
                "team_id": team_mech.id
            },
            {
                "nrp": "TK001",
                "name": "Budi Santoso (Teknisi HVAC)",
                "role": "Technician",
                "password": "technician123",
                "phone": "081200000003",
                "site_id": site1.id,
                "team_id": team_mech.id
            },
            {
                "nrp": "TK002",
                "name": "Rian Hidayat (Teknisi Listrik)",
                "role": "Technician",
                "password": "technician123",
                "phone": "081200000004",
                "site_id": site1.id,
                "team_id": team_elec.id
            },
            {
                "nrp": "client01",
                "name": "Tenant Representative",
                "role": "User",
                "password": "user123",
                "phone": "081200000005",
                "site_id": site1.id,
                "team_id": None
            }
        ]

        user_map = {}
        for uinfo in users_to_seed:
            u = User.query.filter_by(nrp=uinfo["nrp"]).first()
            if not u:
                u = User(
                    nrp=uinfo["nrp"],
                    name=uinfo["name"],
                    role=uinfo["role"],
                    phone_number=uinfo["phone"],
                    is_approved=True,
                    site_id=uinfo["site_id"],
                    team_id=uinfo["team_id"]
                )
                u.set_password(uinfo["password"])
                db.session.add(u)
                db.session.flush()
            else:
                u.is_approved = True
                u.set_password(uinfo["password"])
            user_map[uinfo["nrp"]] = u

        print("[5/9] Membuat Kategori & Aset Mesin...")
        cat_hvac = Category.query.filter_by(name="HVAC & Cooling").first()
        if not cat_hvac:
            cat_hvac = Category(name="HVAC & Cooling")
            db.session.add(cat_hvac)
            db.session.flush()

        cat_elec = Category.query.filter_by(name="Sistem Elektrikal").first()
        if not cat_elec:
            cat_elec = Category(name="Sistem Elektrikal")
            db.session.add(cat_elec)
            db.session.flush()

        cat_plumb = Category.query.filter_by(name="Plumbing & Pompa").first()
        if not cat_plumb:
            cat_plumb = Category(name="Plumbing & Pompa")
            db.session.add(cat_plumb)
            db.session.flush()

        # Subcategories
        subcat_chl = SubCategory.query.filter_by(name="Chiller Unit", category_id=cat_hvac.id).first()
        if not subcat_chl:
            subcat_chl = SubCategory(name="Chiller Unit", category_id=cat_hvac.id)
            db.session.add(subcat_chl)
            db.session.flush()

        subcat_ahu = SubCategory.query.filter_by(name="Air Handling Unit (AHU)", category_id=cat_hvac.id).first()
        if not subcat_ahu:
            subcat_ahu = SubCategory(name="Air Handling Unit (AHU)", category_id=cat_hvac.id)
            db.session.add(subcat_ahu)
            db.session.flush()

        subcat_gen = SubCategory.query.filter_by(name="Genset & Power Backup", category_id=cat_elec.id).first()
        if not subcat_gen:
            subcat_gen = SubCategory(name="Genset & Power Backup", category_id=cat_elec.id)
            db.session.add(subcat_gen)
            db.session.flush()

        subcat_pmp = SubCategory.query.filter_by(name="Pompa Air Bersih / Chilled", category_id=cat_plumb.id).first()
        if not subcat_pmp:
            subcat_pmp = SubCategory(name="Pompa Air Bersih / Chilled", category_id=cat_plumb.id)
            db.session.add(subcat_pmp)
            db.session.flush()

        # Assets
        assets_data = [
            {
                "code": "CHL-001",
                "name": "Chiller Centrifugal Carrier 400TR #01",
                "site_id": site1.id,
                "category_id": cat_hvac.id,
                "subcategory_id": subcat_chl.id,
                "location_id": loc_map["Rooftop - Chiller & Cooling Tower Area"].id,
                "status": "Online",
                "criticality": "High",
                "make": "Carrier",
                "model": "19XR-400TR",
                "serial_number": "SN-CRR-2024-001",
                "description": "Unit pendingin utama gedung sayap timur."
            },
            {
                "code": "CHL-002",
                "name": "Chiller Centrifugal York 450TR #02",
                "site_id": site1.id,
                "category_id": cat_hvac.id,
                "subcategory_id": subcat_chl.id,
                "location_id": loc_map["Rooftop - Chiller & Cooling Tower Area"].id,
                "status": "Online",
                "criticality": "High",
                "make": "York",
                "model": "YK-450-MAX",
                "serial_number": "SN-YRK-2023-882",
                "description": "Unit pendingin utama gedung sayap barat."
            },
            {
                "code": "AHU-LT5-01",
                "name": "AHU Lantai 5 Server Room",
                "site_id": site1.id,
                "category_id": cat_hvac.id,
                "subcategory_id": subcat_ahu.id,
                "location_id": loc_map["Lantai 5 - Ruang Server & IT"].id,
                "status": "Online",
                "criticality": "High",
                "make": "Daikin",
                "model": "AHU-DAIK-500",
                "serial_number": "SN-DKN-5011",
                "description": "Pengatur sirkulasi suhu stabil 20°C untuk server IT."
            },
            {
                "code": "GEN-001",
                "name": "Emergency Diesel Genset 1000 kVA",
                "site_id": site1.id,
                "category_id": cat_elec.id,
                "subcategory_id": subcat_gen.id,
                "location_id": loc_map["Lantai Semi-Basement (Plant Room)"].id,
                "status": "Online",
                "criticality": "High",
                "make": "Cummins",
                "model": "QST30-G4",
                "serial_number": "SN-CUM-9910",
                "description": "Pembangkit listrik darurat cadangan seluruh gedung."
            },
            {
                "code": "PMP-CHW-01",
                "name": "Chilled Water Primary Pump #01",
                "site_id": site1.id,
                "category_id": cat_plumb.id,
                "subcategory_id": subcat_pmp.id,
                "location_id": loc_map["Lantai Semi-Basement (Plant Room)"].id,
                "status": "Online",
                "criticality": "Medium",
                "make": "Grundfos",
                "model": "NB-80-250",
                "serial_number": "SN-GRF-11029",
                "description": "Pompa sirkulasi air dingin chiller ke gedung."
            },
            {
                "code": "AHU-PROD-01",
                "name": "AHU Area Produksi Cleanroom Cikarang",
                "site_id": site2.id,
                "category_id": cat_hvac.id,
                "subcategory_id": subcat_ahu.id,
                "location_id": loc_map["Gedung Produksi Utama"].id,
                "status": "Online",
                "criticality": "High",
                "make": "Trane",
                "model": "CLCP-080",
                "serial_number": "SN-TRN-88231",
                "description": "Unit tata udara ruang produksi berstandar higienis."
            }
        ]

        asset_map = {}
        for adata in assets_data:
            ast = Asset.query.filter_by(code=adata["code"]).first()
            if not ast:
                ast = Asset(**adata)
                db.session.add(ast)
                db.session.flush()
            asset_map[adata["code"]] = ast

        print("[6/9] Membuat Spare Parts Gudang & Inventory...")
        vendor1 = Vendor.query.filter_by(name="PT Mitra Teknik Makmur").first()
        if not vendor1:
            vendor1 = Vendor(name="PT Mitra Teknik Makmur")
            db.session.add(vendor1)
            db.session.flush()

        parts_data = [
            ("FLT-PRE-24", "Pre-Filter AHU 24x24x2 inch", "Pcs", 120000, 45, 10),
            ("FLT-HEP-24", "HEPA Filter Cleanroom Grade H14", "Pcs", 850000, 12, 4),
            ("VBLT-B52", "V-Belt Mitsuboshi Grade B52", "Pcs", 85000, 30, 8),
            ("OIL-REF-68", "Oli Kompresor Chiller ISO VG 68", "Liter", 275000, 60, 15),
            ("MCB-3P-63A", "MCB 3-Pole 63 Ampere Schneider", "Pcs", 340000, 20, 5),
            ("SEAL-MECH-80", "Mechanical Seal Pompa Grundfos NB80", "Set", 650000, 8, 2)
        ]
        for pcode, pname, punit, pprice, pqty, pmin in parts_data:
            part = Part.query.filter_by(code=pcode).first()
            if not part:
                part = Part(name=pname, code=pcode, unit=punit, price=pprice)
                db.session.add(part)
                db.session.flush()
                # Stock level
                sl = StockLevel(part_id=part.id, site_id=site1.id, qty_on_hand=pqty, min_qty=pmin)
                db.session.add(sl)

        print("[7/9] Membuat Work Orders & Prosedur Demo...")
        now = datetime.utcnow()
        tech1 = user_map["TK001"]
        tech2 = user_map["TK002"]

        wo_samples = [
            {
                "code": "WO-2026-0001",
                "description": "Perawatan Rutin Bulanan Chiller Centrifugal Carrier #01",
                "status": "In Progress",
                "priority": "High",
                "maint_type": "Preventive",
                "date_created": now - timedelta(days=2),
                "suggested_start": now - timedelta(hours=3),
                "suggested_comp": now + timedelta(hours=5),
                "start_date": now - timedelta(hours=2),
                "asset": asset_map["CHL-001"],
                "tech": tech1,
                "team": team_mech,
                "instructions": "Ikuti SOP K3. Lakukan LOTO sebelum membuka panel kontrol kompresor."
            },
            {
                "code": "WO-2026-0002",
                "description": "Penggantian V-Belt Motor Blower AHU Lantai 5 IT Server Room",
                "status": "Assigned",
                "priority": "Medium",
                "maint_type": "Corrective",
                "date_created": now - timedelta(hours=5),
                "suggested_start": now + timedelta(hours=1),
                "suggested_comp": now + timedelta(days=1),
                "start_date": None,
                "asset": asset_map["AHU-LT5-01"],
                "tech": tech1,
                "team": team_mech,
                "instructions": "Ambil suku cadang V-Belt B52 dari gudang. Cek ketegangan belt setelah pemasangan."
            },
            {
                "code": "WO-2026-0003",
                "description": "Uji Beban & Pemanasan Mingguan Genset Cummins 1000 kVA",
                "status": "Completed",
                "priority": "High",
                "maint_type": "Preventive",
                "date_created": now - timedelta(days=5),
                "suggested_start": now - timedelta(days=4),
                "suggested_comp": now - timedelta(days=4, hours=-2),
                "start_date": now - timedelta(days=4),
                "asset": asset_map["GEN-001"],
                "tech": tech2,
                "team": team_elec,
                "instructions": "Running test tanpa beban 15 menit, running test dengan beban ATS 30 menit."
            },
            {
                "code": "WO-2026-0004",
                "description": "Pemeriksaan Kebocoran Mechanical Seal Pompa Chilled Water #01",
                "status": "Hold",
                "priority": "Highest",
                "maint_type": "Corrective",
                "date_created": now - timedelta(days=4),
                "suggested_start": now - timedelta(days=3),
                "suggested_comp": now - timedelta(days=1),
                "start_date": now - timedelta(days=3),
                "asset": asset_map["PMP-CHW-01"],
                "tech": tech1,
                "team": team_mech,
                "instructions": "Menunggu part pengganti Seal Kit tiba dari vendor."
            },
            {
                "code": "WO-2026-0005",
                "description": "Draft Pengecekan Suhu Operasional Chiller York #02",
                "status": "Draft",
                "priority": "Low",
                "maint_type": "Inspection",
                "date_created": now,
                "suggested_start": now + timedelta(days=2),
                "suggested_comp": now + timedelta(days=3),
                "start_date": None,
                "asset": asset_map["CHL-002"],
                "tech": tech1,
                "team": team_mech,
                "instructions": "Review logsheet suhu masuk/keluar chiller."
            }
        ]

        for wdata in wo_samples:
            wo = WorkOrder.query.filter_by(code=wdata["code"]).first()
            if not wo:
                wo = WorkOrder(
                    code=wdata["code"],
                    description=wdata["description"],
                    status_id=status_map[wdata["status"]].id,
                    priority=wdata["priority"],
                    maintenance_type=wdata["maint_type"],
                    date_created=wdata["date_created"],
                    suggested_start_date=wdata["suggested_start"],
                    suggested_completion_date=wdata["suggested_comp"],
                    start_date=wdata["start_date"],
                    asset_id=wdata["asset"].id,
                    assigned_to=wdata["tech"].id,
                    team_id=wdata["team"].id,
                    work_instructions=wdata["instructions"]
                )
                wo.assignees.append(wdata["tech"])
                db.session.add(wo)
                db.session.flush()

                # Add sample procedures
                p1 = WorkOrderProcedure(
                    work_order_id=wo.id,
                    tasklist_name="Pemeriksaan Standard",
                    name="Inspeksi visual komponen dan periksa getaran abnormal",
                    requires_attachment=True,
                    min_photos=1,
                    estimated_minutes=20,
                    is_completed=(wdata["status"] in ["In Progress", "Completed"]),
                    status="Done" if (wdata["status"] in ["In Progress", "Completed"]) else "Pending",
                    notes="Pemeriksaan visual telah dilakukan, kondisi fisik normal." if (wdata["status"] in ["In Progress", "Completed"]) else ""
                )
                p2 = WorkOrderProcedure(
                    work_order_id=wo.id,
                    tasklist_name="Pemeriksaan Standard",
                    name="Pembersihan unit & pengecekan baut pengikat fondasi",
                    requires_attachment=False,
                    min_photos=0,
                    estimated_minutes=15,
                    is_completed=(wdata["status"] == "Completed"),
                    status="Done" if (wdata["status"] == "Completed") else "Pending",
                    notes=""
                )
                db.session.add_all([p1, p2])

                # Add sample checklists
                c1 = WorkOrderChecklistParameter(
                    work_order_id=wo.id,
                    parameter="Tegangan Listrik 3-Phase (Volt)",
                    standard="380 - 400 V",
                    value="392" if (wdata["status"] in ["In Progress", "Completed"]) else ""
                )
                c2 = WorkOrderChecklistParameter(
                    work_order_id=wo.id,
                    parameter="Arus Listrik Motor (Ampere)",
                    standard="120 - 150 A",
                    value="132" if (wdata["status"] == "Completed") else ""
                )
                db.session.add_all([c1, c2])

                # Add sample log
                log = WorkOrderLog(
                    work_order_id=wo.id,
                    user_id=wdata["tech"].id,
                    log_text=f"Status WO diatur ke {wdata['status']}. Pekerjaan diproses oleh {wdata['tech'].name}."
                )
                db.session.add(log)

        print("[8/9] Membuat Data Master Helpdesk & Tiket...")
        modules = ["Sistem Tata Udara (AC)", "Kelistrikan & Penerangan", "Plumbing & Toilet", "Fasilitas Kantor"]
        mod_map = {}
        for m_name in modules:
            m = HelpdeskModule.query.filter_by(name=m_name).first()
            if not m:
                m = HelpdeskModule(name=m_name)
                db.session.add(m)
                db.session.flush()
            mod_map[m_name] = m

        hd_locs = ["Ruang Rapat Lt. 3", "Kantin & Pantry Lt. 2", "Lobby Utama", "Ruang Server Lt. 5"]
        hd_loc_map = {}
        for hl_name in hd_locs:
            hl = HelpdeskLocation.query.filter_by(name=hl_name).first()
            if not hl:
                hl = HelpdeskLocation(name=hl_name)
                db.session.add(hl)
                db.session.flush()
            hd_loc_map[hl_name] = hl

        # Customers
        cust = Customer.query.filter_by(partner_organization="PT Sentosa Tenant Mandiri").first()
        if not cust:
            cust = Customer(
                partner_organization="PT Sentosa Tenant Mandiri",
                point_of_contact="Ibu Ratna Dewi",
                mobile_number="081399887766",
                email="ratna.dewi@sentosagroup.com"
            )
            db.session.add(cust)
            db.session.flush()

        # Helpdesk Tickets
        tickets_data = [
            {
                "ticket_code": "HD-2026-001",
                "subject": "Keluhan AC Ruang Rapat Lt. 3 Kurang Dingin",
                "person_name": "Ibu Ratna Dewi (Tenant Lt. 3)",
                "mobile": "081399887766",
                "complain_type": "Suhu Ruangan Panas",
                "description": "AC di ruang rapat utama lantai 3 tidak terasa dingin sejak pagi hari.",
                "status": "WIP",
                "priority": "High",
                "modul": "Sistem Tata Udara (AC)",
                "location_subject": "Ruang Rapat Lt. 3",
                "assigned_user_id": tech1.id
            },
            {
                "ticket_code": "HD-2026-002",
                "subject": "Lampu Downlight Berkedip di Pantry",
                "person_name": "Pak Hendra (Pantry)",
                "mobile": "081233445566",
                "complain_type": "Lampu Downlight Redup / Berkedip",
                "description": "Lampu LED di pantry lantai 2 berkedip terus-menerus.",
                "status": "Action Plan",
                "priority": "Medium",
                "modul": "Kelistrikan & Penerangan",
                "location_subject": "Kantin & Pantry Lt. 2",
                "assigned_user_id": tech2.id
            },
            {
                "ticket_code": "HD-2026-003",
                "subject": "Kran Wastafel Toilet Lobby Bocor",
                "person_name": "Resepsionis Gedung",
                "mobile": "081299881122",
                "complain_type": "Kran Wastafel Bocor",
                "description": "Kran air toilet lobby menetes terus menerus.",
                "status": "Done",
                "priority": "Low",
                "modul": "Plumbing & Toilet",
                "location_subject": "Lobby Utama",
                "assigned_user_id": tech1.id
            }
        ]

        for tdata in tickets_data:
            t = HelpdeskTicket.query.filter_by(ticket_code=tdata["ticket_code"]).first()
            if not t:
                t = HelpdeskTicket(**tdata)
                db.session.add(t)

        print("[9/9] Mengatur System Settings...")
        settings_defaults = [
            ("APP_NAME", "CMMS - Maintenance Management System"),
            ("COMPANY_NAME", "PT Demo Solusi Engineering"),
            ("DEFAULT_PAGE_SIZE", "20"),
            ("THEME_COLOR", "primary")
        ]
        for key, val in settings_defaults:
            setting = SystemSetting.query.filter_by(setting_key=key).first()
            if not setting:
                db.session.add(SystemSetting(setting_key=key, setting_value=val))

        db.session.commit()
        print("\n=======================================================")
        print(" SEMUA DATA DEMO BERHASIL DIBUAT KE cmms.db!")
        print(" Akun Login Demo:")
        print("   - Admin:      NRP: admin      | Password: admin123")
        print("   - Supervisor: NRP: supervisor | Password: supervisor123")
        print("   - Teknisi 1:  NRP: TK001      | Password: technician123")
        print("   - Teknisi 2:  NRP: TK002      | Password: technician123")
        print("   - Tenant:     NRP: client01   | Password: user123")
        print("=======================================================\n")

if __name__ == '__main__':
    seed_all()
