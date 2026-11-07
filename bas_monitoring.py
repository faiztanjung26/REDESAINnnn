from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, BasFrame, Site

bas_monitoring_bp = Blueprint('bas_monitoring', __name__, url_prefix='/bas_monitoring')

@bas_monitoring_bp.route('/')
@login_required
def index():
    if current_user.role == 'Admin':
        frames = BasFrame.query.order_by(BasFrame.created_at.desc()).all()
    else:
        # User only sees frames for their site, or global frames (site_id is null)
        frames = BasFrame.query.filter(
            db.or_(BasFrame.site_id == current_user.site_id, BasFrame.site_id == None)
        ).order_by(BasFrame.created_at.desc()).all()
        
    sites = Site.query.order_by(Site.name).all()
    return render_template('bas_monitoring.html', frames=frames, sites=sites)

@bas_monitoring_bp.route('/add', methods=['POST'])
@login_required
def add_frame():
    if current_user.role != 'Admin':
        flash('Hanya Admin yang dapat menambahkan frame.', 'danger')
        return redirect(url_for('bas_monitoring.index'))
        
    name = request.form.get('name')
    url = request.form.get('url')
    site_id = request.form.get('site_id')
    
    if site_id == '':
        site_id = None
    
    if name and url:
        new_frame = BasFrame(name=name, url=url, site_id=site_id)
        db.session.add(new_frame)
        db.session.commit()
        flash('Frame berhasil ditambahkan', 'success')
    else:
        flash('Nama dan URL harus diisi', 'danger')
        
    return redirect(url_for('bas_monitoring.index'))

@bas_monitoring_bp.route('/edit/<int:frame_id>', methods=['POST'])
@login_required
def edit_frame(frame_id):
    if current_user.role != 'Admin':
        flash('Hanya Admin yang dapat mengedit frame.', 'danger')
        return redirect(url_for('bas_monitoring.index'))
        
    frame = BasFrame.query.get_or_404(frame_id)
    name = request.form.get('name')
    url = request.form.get('url')
    site_id = request.form.get('site_id')
    
    if site_id == '':
        site_id = None
        
    if name and url:
        frame.name = name
        frame.url = url
        frame.site_id = site_id
        db.session.commit()
        flash('Frame berhasil diperbarui', 'success')
    else:
        flash('Nama dan URL harus diisi', 'danger')
        
    return redirect(url_for('bas_monitoring.index'))

@bas_monitoring_bp.route('/delete/<int:frame_id>', methods=['POST'])
@login_required
def delete_frame(frame_id):
    if current_user.role != 'Admin':
        flash('Hanya Admin yang dapat menghapus frame.', 'danger')
        return redirect(url_for('bas_monitoring.index'))
        
    frame = BasFrame.query.get_or_404(frame_id)
    db.session.delete(frame)
    db.session.commit()
    flash('Frame berhasil dihapus', 'success')
    return redirect(url_for('bas_monitoring.index'))

@bas_monitoring_bp.route('/view/<int:frame_id>')
@login_required
def view_frame(frame_id):
    frame = BasFrame.query.get_or_404(frame_id)
    # Check access
    if current_user.role != 'Admin' and frame.site_id is not None and frame.site_id != current_user.site_id:
        flash('Anda tidak memiliki akses ke monitor ini.', 'danger')
        return redirect(url_for('bas_monitoring.index'))
        
    return render_template('bas_monitoring_view.html', frame=frame)
