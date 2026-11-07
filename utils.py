from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'Admin':
            flash('Access denied. Administrator privileges required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def supervisor_or_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['Admin', 'Supervisor']:
            flash('Access denied. Supervisor or Administrator privileges required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function
def send_whatsapp_notification(phone, message):
    import requests
    import os
    
    token = os.getenv('FONNTE_TOKEN')
    api_url = os.getenv('FONNTE_API_URL', 'https://api.fonnte.com/send')
    
    if not token or not phone:
        print(f"Skipping WA: Token or phone missing. Phone: {phone}")
        return False
        
    payload = {
        'target': phone,
        'message': message,
        'countryCode': '62', # Default Indonesia
    }
    headers = {
        'Authorization': token
    }
    
    try:
        response = requests.post(api_url, data=payload, headers=headers)
        print(f"WA Notification sent to {phone}. Response: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending WA notification: {e}")
        return False

def save_optimized_image(uploaded_file, target_path, max_dim=1920, quality=80):
    """
    Saves an uploaded image, auto-orienting EXIF, resizing if exceeding max_dim,
    and compressing with Pillow JPEG quality.
    If the file is not an image (e.g. PDF), it saves it directly.
    """
    import os
    from PIL import Image, ImageOps

    ext = os.path.splitext(target_path)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.webp']:
        uploaded_file.save(target_path)
        return

    try:
        uploaded_file.seek(0)
        img = Image.open(uploaded_file)
        img = ImageOps.exif_transpose(img)

        # Convert RGBA / P to RGB with white background
        if img.mode in ('RGBA', 'LA', 'P'):
            bg = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            mask = img.split()[3] if len(img.split()) > 3 else None
            bg.paste(img, mask=mask)
            img = bg
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        w, h = img.size
        if max(w, h) > max_dim:
            if w > h:
                new_w = max_dim
                new_h = int(h * (max_dim / w))
            else:
                new_h = max_dim
                new_w = int(w * (max_dim / h))
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        img.save(target_path, 'JPEG', quality=quality, optimize=True)
    except Exception as e:
        print(f"Pillow optimization warning: {e}, saving original file.")
        try:
            uploaded_file.seek(0)
            uploaded_file.save(target_path)
        except Exception:
            pass




def get_wo_chiller_details(asset):
    """
    Retrieves chiller details for a Work Order's asset if it is a chiller.
    Returns a dict with site_name, chiller_num, image_filename, and details_to_show,
    or None if the asset is not a chiller.
    """
    if not asset:
        return None

    is_chiller = (
        getattr(asset, 'is_chiller', False) or 
        bool(getattr(asset, 'api_chiller_id', None)) or 
        'chiller' in (asset.name or '').lower() or
        (getattr(asset, 'category', None) and 'chiller' in (asset.category.name or '').lower())
    )
    if not is_chiller:
        return None

    import re
    site_name = asset.site.name if getattr(asset, 'site', None) else 'Unknown Site'
    raw_name = asset.name or 'Chiller'

    # Try extracting chiller number from name (e.g. "Chiller 2" -> "2", "Chiller No. 1 (1000 TR)" -> "1")
    num_match = re.search(r'(?:No\.?\s*|Chiller\s*[-#]?\s*)(\d+)', raw_name, re.IGNORECASE)
    chiller_num = num_match.group(1) if num_match else raw_name

    ton_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:TR|Ton)', raw_name, re.IGNORECASE)
    default_ton = f"{float(ton_match.group(1)):.1f}" if ton_match else None

    serial_no = asset.serial_number or '-'
    model_no = asset.model or '-'
    comp_model = asset.make or '-'
    ton_val = default_ton or '-'
    image_file = 'chiller.png'

    # Try querying IoT API
    target_id = getattr(asset, 'api_chiller_id', None)
    if not target_id and getattr(asset, 'site', None):
        site_str = (asset.site.api_site_id or asset.site.name or '').lower()
        if 'pakubuwono' in site_str and num_match:
            target_id = f'pakubuwono_{num_match.group(1)}'
        elif ('bxc2' in site_str or 'bintaro xchange 2' in site_str) and num_match:
            target_id = f'bxc2_sqc_{num_match.group(1)}'
        elif 'btpn' in site_str and num_match:
            target_id = f'menara_btpn_{num_match.group(1)}'

    if target_id:
        try:
            import requests
            chiller_api_base = os.environ.get('CHILLER_API_BASE_URL', 'http://127.0.0.1:8000')
            resp = requests.get(f'{chiller_api_base}/chillers/{target_id}', timeout=2.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('serial_number'):
                    serial_no = data.get('serial_number')
                if data.get('model_number'):
                    model_no = data.get('model_number')
                if data.get('compressor_model'):
                    comp_model = data.get('compressor_model')
                if data.get('ton_of_refrigeration'):
                    try:
                        ton_val = f"{float(data.get('ton_of_refrigeration')):.1f}"
                    except:
                        ton_val = str(data.get('ton_of_refrigeration'))
                if data.get('chiller_num'):
                    chiller_num = str(data.get('chiller_num'))
                if data.get('image_name'):
                    image_file = data.get('image_name')
        except Exception:
            pass

    details_to_show = {
        'Serial Number': serial_no,
        'Model Number': model_no,
        'Compressor Model': comp_model,
        'Ton of Refrigeration': ton_val
    }

    return {
        'site_name': site_name,
        'chiller_num': chiller_num,
        'image_filename': image_file,
        'details_to_show': details_to_show
    }
