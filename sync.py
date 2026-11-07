from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from models import db, WorkOrder, WorkOrderProcedure, WorkOrderChecklistParameter
from werkzeug.utils import secure_filename
import os
import json
from datetime import datetime, timezone

sync_bp = Blueprint('sync', __name__, url_prefix='/sync')

@sync_bp.route('/api/download-assigned-wo', methods=['GET'])
@login_required
def download_assigned_wo():
    """
    Download Work Orders assigned to the currently logged in user (or all active for Admin)
    for offline execution.
    """
    try:
        all_wos = WorkOrder.query.all()
        wos = []

        for wo in all_wos:
            # Skip closed work orders
            if wo.current_status and wo.current_status.control_type == 'Closed':
                continue

            if current_user.role in ['Admin', 'Supervisor']:
                wos.append(wo)
            else:
                is_assigned = (wo.assigned_to == current_user.id) or (current_user in getattr(wo, 'assignees', []))
                if is_assigned:
                    wos.append(wo)

        wo_list = []
        proc_list = []
        chk_list = []

        for wo in wos:
            # Safely get location & asset names
            location_name = ''
            asset_name = ''
            if getattr(wo, 'asset', None):
                asset_name = wo.asset.name or ''
                if getattr(wo.asset, 'location', None):
                    location_name = wo.asset.location.name or ''
                elif getattr(wo.asset, 'site', None):
                    location_name = wo.asset.site.name or ''

            status_str = wo.current_status.name if getattr(wo, 'current_status', None) else 'Active'

            wo_list.append({
                'id': wo.id,
                'wo_number': getattr(wo, 'code', f'WO-{wo.id}'),
                'description': wo.description or '',
                'priority': wo.priority or 'Medium',
                'status': status_str,
                'location': location_name,
                'asset_name': asset_name
            })

            # Procedures
            for proc in wo.procedures:
                proc_list.append({
                    'id': proc.id,
                    'work_order_id': proc.work_order_id,
                    'name': proc.name,
                    'requires_attachment': bool(proc.requires_attachment),
                    'min_photos': int(getattr(proc, 'min_photos', 0) or 0),
                    'estimated_minutes': int(getattr(proc, 'estimated_minutes', 0) or 0),
                    'is_completed': bool(proc.is_completed),
                    'status': proc.status or 'Pending',
                    'notes': proc.notes or '',
                    'attachment_path': proc.attachment_path or '',
                    'synced': True
                })

            # Checklists
            for chk in wo.checklist_parameters:
                chk_list.append({
                    'id': chk.id,
                    'work_order_id': chk.work_order_id,
                    'parameter': chk.parameter,
                    'standard': chk.standard or '',
                    'value': chk.value or '',
                    'synced': True
                })

        return jsonify({
            'status': 'success',
            'count': len(wo_list),
            'work_orders': wo_list,
            'procedures': proc_list,
            'checklists': chk_list
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@sync_bp.route('/api/upload-offline-batch', methods=['POST'])
@login_required
def upload_offline_batch():
    """
    Process batch updates uploaded from client IndexedDB outbox when re-connected.
    """
    try:
        procedures_raw = request.form.get('procedures', '[]')
        checklists_raw = request.form.get('checklists', '[]')

        procedures_data = json.loads(procedures_raw)
        checklists_data = json.loads(checklists_raw)

        updated_procs_count = 0
        updated_chks_count = 0

        # Update Procedures
        for item in procedures_data:
            proc_id = item.get('id')
            if not proc_id:
                continue
            proc = WorkOrderProcedure.query.get(proc_id)
            if proc:
                proc.is_completed = item.get('is_completed', True)
                proc.status = item.get('status', 'Done')
                proc.notes = item.get('notes', proc.notes)
                proc.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                proc.completed_by_id = current_user.id
                updated_procs_count += 1

        # Update Checklists
        for chk_item in checklists_data:
            chk_id = chk_item.get('id')
            if not chk_id:
                continue
            chk = WorkOrderChecklistParameter.query.get(chk_id)
            if chk:
                chk.value = chk_item.get('value')
                updated_chks_count += 1

        # Process uploaded photo files from FormData
        for key, file in request.files.items():
            if key.startswith('file_') and file and file.filename != '':
                parts = key.split('_')
                if len(parts) >= 2:
                    try:
                        proc_id = int(parts[1])
                        proc = WorkOrderProcedure.query.get(proc_id)
                        if proc:
                            filename = secure_filename(f"wo{proc.work_order_id}_proc{proc.id}_offline_{file.filename}")
                            uploads_dir = os.path.join(current_app.root_path, 'static', 'uploads')
                            os.makedirs(uploads_dir, exist_ok=True)
                            file_sys_path = os.path.join(uploads_dir, filename)
                            file.save(file_sys_path)

                            rel_path = f'uploads/{filename}'
                            curr = [p.strip() for p in (proc.attachment_path or '').split('|') if p.strip()]
                            if rel_path not in curr:
                                curr.append(rel_path)
                            proc.attachment_path = '|'.join(curr)
                    except Exception as ex:
                        print(f"[Sync] Error processing photo file {key}: {ex}")

        db.session.commit()

        return jsonify({
            'status': 'success',
            'updated_procedures': updated_procs_count,
            'updated_checklists': updated_chks_count
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 400
