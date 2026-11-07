/**
 * Photo Auto-Compressor for CMMS
 * Otomatis me-resize dan mengompres foto langsung di browser teknisi sebelum upload.
 * Mempercepat upload hingga 10x - 30x lebih cepat serta hemat kuota mobile data.
 */

(function (window) {
    'use strict';

    const PhotoCompressor = {
        config: {
            maxWidth: 1600,
            maxHeight: 1600,
            quality: 0.75, // Kualitas optimal: jernih untuk teks/nomor seri, ukuran ~150KB - 300KB
            minSizeToCompress: 200 * 1024 // Jika < 200KB & JPEG, tidak perlu re-compress
        },

        // Buat atau dapatkan elemen Overlay Loading
        getOverlay: function () {
            let overlay = document.getElementById('photoCompressorOverlay');
            if (!overlay) {
                overlay = document.createElement('div');
                overlay.id = 'photoCompressorOverlay';
                overlay.style.cssText = 'position:fixed; top:0; left:0; width:100vw; height:100vh; z-index:999999; background:rgba(15,23,42,0.75); backdrop-filter:blur(6px); display:none; align-items:center; justify-content:center; flex-direction:column; font-family:Inter,system-ui,-apple-system,sans-serif; text-align:center; padding:20px;';
                overlay.innerHTML = `
                    <div style="background:#ffffff; color:#0f172a; padding:28px 24px; border-radius:20px; max-width:340px; width:90%; box-shadow:0 25px 50px -12px rgba(0,0,0,0.35); text-align:center;">
                        <div class="spinner-border text-primary mb-3" role="status" style="width:3.2rem; height:3.2rem; border-width:0.3rem;">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                        <h6 id="photoCompressorTitle" style="font-weight:700; margin-bottom:6px; font-size:1.05rem; color:#0f172a;">⚡ Mengompresi Foto...</h6>
                        <p id="photoCompressorSubtitle" style="font-size:0.83rem; color:#64748b; margin-bottom:0; line-height:1.45;">Mengoptimasi ukuran foto agar upload kilat & hemat kuota.</p>
                    </div>
                `;
                document.body.appendChild(overlay);
            }
            return overlay;
        },

        showOverlay: function (title, subtitle) {
            const overlay = this.getOverlay();
            if (title) {
                const titleEl = document.getElementById('photoCompressorTitle');
                if (titleEl) titleEl.innerText = title;
            }
            if (subtitle) {
                const subEl = document.getElementById('photoCompressorSubtitle');
                if (subEl) subEl.innerText = subtitle;
            }
            overlay.style.display = 'flex';
        },

        updateOverlay: function (title, subtitle) {
            if (title) {
                const titleEl = document.getElementById('photoCompressorTitle');
                if (titleEl) titleEl.innerText = title;
            }
            if (subtitle) {
                const subEl = document.getElementById('photoCompressorSubtitle');
                if (subEl) subEl.innerText = subtitle;
            }
        },

        hideOverlay: function () {
            const overlay = document.getElementById('photoCompressorOverlay');
            if (overlay) overlay.style.display = 'none';
        },

        // Kompresi single image file menggunakan HTML5 Canvas
        compressImage: function (file, customOptions) {
            const opts = Object.assign({}, this.config, customOptions || {});
            
            // Lewati jika bukan image (misal PDF atau dokumen lain)
            if (!file || !file.type || !file.type.startsWith('image/')) {
                return Promise.resolve(file);
            }

            // Jika ukuran sudah kecil dan format jpeg, lewati kompresi
            if (file.size <= opts.minSizeToCompress && file.type === 'image/jpeg') {
                return Promise.resolve(file);
            }

            return new Promise((resolve) => {
                const reader = new FileReader();
                reader.onload = function (e) {
                    const img = new Image();
                    img.onload = function () {
                        let width = img.naturalWidth || img.width;
                        let height = img.naturalHeight || img.height;

                        // Perhitungan aspect ratio jika melebihi maxWidth/maxHeight
                        if (width > opts.maxWidth || height > opts.maxHeight) {
                            if (width / opts.maxWidth > height / opts.maxHeight) {
                                height = Math.round((height * opts.maxWidth) / width);
                                width = opts.maxWidth;
                            } else {
                                width = Math.round((width * opts.maxHeight) / height);
                                height = opts.maxHeight;
                            }
                        }

                        const canvas = document.createElement('canvas');
                        canvas.width = width;
                        canvas.height = height;
                        const ctx = canvas.getContext('2d');

                        // Background putih jika transparan
                        ctx.fillStyle = '#FFFFFF';
                        ctx.fillRect(0, 0, width, height);

                        ctx.drawImage(img, 0, 0, width, height);

                        canvas.toBlob(function (blob) {
                            if (!blob) {
                                resolve(file); // Fallback ke file asli jika gagal
                                return;
                            }

                            // Jika hasil kompresi malah lebih besar dari file asli JPEG
                            if (blob.size >= file.size && file.type === 'image/jpeg') {
                                resolve(file);
                                return;
                            }

                            // Buat nama file baru dengan ekstensi .jpg
                            const originalName = file.name || 'photo.jpg';
                            const baseName = originalName.lastIndexOf('.') !== -1 
                                ? originalName.substring(0, originalName.lastIndexOf('.'))
                                : originalName;
                            const newFileName = baseName + '.jpg';

                            const compressedFile = new File([blob], newFileName, {
                                type: 'image/jpeg',
                                lastModified: Date.now()
                            });

                            console.log(`[PhotoCompressor] ${file.name} compressed: ${(file.size / 1024).toFixed(0)}KB -> ${(compressedFile.size / 1024).toFixed(0)}KB (-${(100 - (compressedFile.size / file.size * 100)).toFixed(0)}%)`);
                            resolve(compressedFile);
                        }, 'image/jpeg', opts.quality);
                    };

                    img.onerror = function () {
                        resolve(file);
                    };
                    img.src = e.target.result;
                };

                reader.onerror = function () {
                    resolve(file);
                };
                reader.readAsDataURL(file);
            });
        },

        // Kompres array of files
        compressFiles: async function (files, onProgress) {
            const results = [];
            for (let i = 0; i < files.length; i++) {
                if (typeof onProgress === 'function') {
                    onProgress(i + 1, files.length, files[i]);
                }
                const compressed = await this.compressImage(files[i]);
                results.push(compressed);
            }
            return results;
        },

        // Kompres input file saat dipilih & langsung submit form (untuk Camera / Gallery modal)
        handleUpload: async function (inputElement, customOptions) {
            if (!inputElement || !inputElement.files || inputElement.files.length === 0) {
                return;
            }

            const files = Array.from(inputElement.files);
            const form = inputElement.form;
            if (!form) return;

            this.showOverlay('⚡ Mengompresi Foto...', `Memproses ${files.length} foto...`);

            try {
                const compressedFiles = await this.compressFiles(files, (curr, total, f) => {
                    this.updateOverlay(
                        `⚡ Mengompresi Foto (${curr}/${total})...`,
                        `Mengoptimalkan foto agar upload kilat...`
                    );
                });

                const isAjax = inputElement.dataset.ajax === 'true' || 
                               (form && form.dataset.ajax === 'true') || 
                               (customOptions && customOptions.ajax);

                if (isAjax) {
                    this.updateOverlay('🚀 Mengunggah Foto...', 'Sedang mengirim ke server...');
                    const formData = new FormData(form);
                    formData.delete(inputElement.name);
                    compressedFiles.forEach(f => formData.append(inputElement.name, f));
                    formData.append('is_ajax', '1');

                    try {
                        const actionUrl = form.getAttribute('action') || (typeof form.action === 'string' ? form.action : '');
                const response = await fetch(actionUrl, {
                            method: form.method || 'POST',
                            headers: {
                                'X-Requested-With': 'XMLHttpRequest'
                            },
                            body: formData
                        });

                        const data = await response.json();
                        this.hideOverlay();
                        inputElement.value = '';

                        if (typeof window.handleProcedureAjaxResponse === 'function') {
                            window.handleProcedureAjaxResponse(data);
                        } else if (typeof customOptions?.onSuccess === 'function') {
                            customOptions.onSuccess(data);
                        } else {
                            window.location.reload();
                        }
                    } catch (netErr) {
                        this.hideOverlay();
                        console.error('[PhotoCompressor] Upload failed:', netErr);
                        alert('Gagal mengunggah foto. Silakan periksa koneksi internet Anda.');
                    }
                    return;
                }

                // Coba gunakan DataTransfer untuk mengisi input element
                let dataTransferSuccess = false;
                try {
                    const dt = new DataTransfer();
                    compressedFiles.forEach(f => dt.items.add(f));
                    inputElement.files = dt.files;
                    dataTransferSuccess = true;
                } catch (dtError) {
                    console.warn('[PhotoCompressor] DataTransfer failed, using FormData fallback:', dtError);
                    dataTransferSuccess = false;
                }

                this.updateOverlay('🚀 Mengunggah Foto...', 'Sedang mengirim ke server...');

                if (dataTransferSuccess) {
                    form.submit();
                } else {
                    // Fallback FormData submit
                    const formData = new FormData(form);
                    formData.delete(inputElement.name);
                    compressedFiles.forEach(f => formData.append(inputElement.name, f));

                    const actionUrl = form.getAttribute('action') || (typeof form.action === 'string' ? form.action : '');
                const response = await fetch(actionUrl, {
                        method: form.method || 'POST',
                        body: formData
                    });

                    if (response.redirected) {
                        window.location.href = response.url;
                    } else {
                        window.location.reload();
                    }
                }
            } catch (error) {
                console.error('[PhotoCompressor] Upload error:', error);
                this.updateOverlay('🚀 Mengunggah Foto Asli...', 'Kompresi dilewati.');
                form.submit();
            }
        },

        // Kompres file in-place pada input standar tanpa langsung submit form
        autoCompressInput: async function (inputElement, badgeContainerId) {
            if (!inputElement || !inputElement.files || inputElement.files.length === 0) return;

            const files = Array.from(inputElement.files);
            // Cek apakah ada image file
            const hasImage = files.some(f => f.type && f.type.startsWith('image/'));
            if (!hasImage) return;

            const originalTotalSize = files.reduce((acc, f) => acc + f.size, 0);

            try {
                // Jangan blokir layar penuh untuk input form biasa, cukup proses cepat
                const compressedFiles = await this.compressFiles(files);
                const newTotalSize = compressedFiles.reduce((acc, f) => acc + f.size, 0);

                try {
                    const dt = new DataTransfer();
                    compressedFiles.forEach(f => dt.items.add(f));
                    inputElement.files = dt.files;
                } catch (e) {
                    console.warn('[PhotoCompressor] DataTransfer not supported for in-place edit:', e);
                }

                // Tampilkan info jika ada badge container
                if (badgeContainerId) {
                    const el = document.getElementById(badgeContainerId);
                    if (el) {
                        const savedPercent = (100 - (newTotalSize / originalTotalSize * 100)).toFixed(0);
                        el.innerHTML = `<span class="badge bg-success-subtle text-success border border-success-subtle"><i class="bi bi-lightning-charge-fill me-1"></i>Foto dioptimasi: ${(newTotalSize / 1024).toFixed(0)} KB (-${savedPercent}%)</span>`;
                    }
                }
            } catch (err) {
                console.error('[PhotoCompressor] autoCompressInput error:', err);
            }
        }
    };

    // Global helper shortcuts
    window.PhotoCompressor = PhotoCompressor;
    window.handleCompressedPhotoUpload = function (inputElement, opts) {
        return PhotoCompressor.handleUpload(inputElement, opts);
    };
    window.autoCompressFileInput = function (inputElement, badgeId) {
        return PhotoCompressor.autoCompressInput(inputElement, badgeId);
    };

})(window);
