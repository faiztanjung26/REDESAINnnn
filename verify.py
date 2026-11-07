from flask import Blueprint, render_template, request, abort
from models import DigitalSignature, WorkOrder
from datetime import timedelta

verify_bp = Blueprint('verify', __name__, url_prefix='/verify')

@verify_bp.route('/doc')
def verify_doc():
    doc_id = request.args.get('id')
    if not doc_id:
        abort(400, "Missing document ID")
        
    sig = DigitalSignature.query.filter_by(id=doc_id).first()
    if not sig:
        return render_template('verify.html', status='not_found')
        
    wo = WorkOrder.query.get(sig.work_order_id)
    if not wo:
        return render_template('verify.html', status='not_found')

    if sig.status != 'Valid':
        return render_template('verify.html', status='revoked', sig=sig, wo=wo)

    # Convert UTC to WIB for display
    wib_time = sig.signed_at + timedelta(hours=7) if sig.signed_at else None

    return render_template('verify.html', status='valid', sig=sig, wo=wo, wib_time=wib_time)
