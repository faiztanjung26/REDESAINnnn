import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../../core/constants/app_colors.dart';
import '../../core/utils/formatters.dart';
import '../../data/models/work_order_model.dart';
import '../../data/models/procedure_model.dart';
import '../../data/models/part_model.dart';
import '../../data/repositories/work_order_repository.dart';
import '../../widgets/status_badge.dart';
import '../../widgets/priority_badge.dart';
import 'dialogs/hold_reason_dialog.dart';
import 'dialogs/add_part_dialog.dart';
import 'dialogs/add_log_dialog.dart';
import 'dialogs/signature_dialog.dart';
import '../../core/network/api_service.dart';
import '../../core/constants/api_constants.dart';

class WorkOrderDetailScreen extends StatefulWidget {
  final int workOrderId;

  const WorkOrderDetailScreen({Key? key, required this.workOrderId}) : super(key: key);

  @override
  State<WorkOrderDetailScreen> createState() => _WorkOrderDetailScreenState();
}

class _WorkOrderDetailScreenState extends State<WorkOrderDetailScreen> with SingleTickerProviderStateMixin {
  final WorkOrderRepository _repo = WorkOrderRepository();
  final ImagePicker _picker = ImagePicker();

  late TabController _tabController;
  WorkOrderModel? _wo;
  bool _isLoading = true;
  String? _errorMessage;
  String _baseUrl = '';

  // Controllers for checklists
  final Map<int, TextEditingController> _checklistControllers = {};

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 6, vsync: this);
    _loadDetail();
  }

  @override
  void dispose() {
    _tabController.dispose();
    for (var c in _checklistControllers.values) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _loadDetail() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      try {
        _baseUrl = await ApiService.instance.getBaseUrl();
      } catch (_) {}
      final wo = await _repo.getWorkOrderDetail(widget.workOrderId);
      for (var chk in wo.checklists) {
        _checklistControllers[chk.id] = TextEditingController(text: chk.value);
      }
      setState(() {
        _wo = wo;
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _errorMessage = 'Gagal memuat detail Work Order: $e';
        _isLoading = false;
      });
    }
  }

  // --- Actions ---

  Future<void> _handleStart() async {
    try {
      await _repo.updateStatus(widget.workOrderId, 'start');
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Pekerjaan dimulai! Status diperbarui menjadi Sedang Dikerjakan.'),
          backgroundColor: AppColors.statusInProgress,
        ),
      );
      _loadDetail();
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Gagal memulai WO: $e')));
    }
  }

  Future<void> _handleHold() async {
    final reason = await showDialog<String>(
      context: context,
      builder: (_) => const HoldReasonDialog(),
    );
    if (reason != null && reason.isNotEmpty) {
      try {
        await _repo.updateStatus(widget.workOrderId, 'hold', reason: reason);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Work Order berhasil ditunda (Hold).'),
            backgroundColor: AppColors.statusHold,
          ),
        );
        _loadDetail();
      } catch (e) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Gagal menunda WO: $e')));
      }
    }
  }

  Future<void> _handleResume() async {
    try {
      await _repo.updateStatus(widget.workOrderId, 'resume');
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Pekerjaan dilanjutkan kembali!'),
          backgroundColor: AppColors.statusInProgress,
        ),
      );
      _loadDetail();
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Gagal melanjutkan WO: $e')));
    }
  }

  Future<void> _handleSolve() async {
    if (_wo == null) return;

    // 1. Validasi Prosedur Selesai & Foto Bukti
    List<String> missingProcs = [];
    for (var proc in _wo!.procedures) {
      if (!proc.isCompleted) {
        missingProcs.add('${proc.name} (Belum dicentang)');
      } else if (!proc.satisfiesAttachmentRequirement) {
        missingProcs.add('${proc.name} (Foto bukti kurang, butuh min ${proc.minPhotos > 0 ? proc.minPhotos : 1} foto)');
      }
    }

    if (missingProcs.isNotEmpty) {
      _showValidationDialog(
        title: 'Prosedur Belum Lengkap',
        message: 'Lengkapi prosedur berikut sebelum menyelesaikan Work Order:\n\n• ' + missingProcs.join('\n• '),
        tabIndexToGo: 1, // Prosedur Tab
      );
      return;
    }

    // 2. Validasi Parameter Checklist
    List<String> missingChks = [];
    for (var chk in _wo!.checklists) {
      final ctrl = _checklistControllers[chk.id];
      final val = ctrl?.text.trim() ?? chk.value.trim();
      if (val.isEmpty) {
        missingChks.add(chk.parameter);
      }
    }

    if (missingChks.isNotEmpty) {
      _showValidationDialog(
        title: 'Parameter Checklist Kosong',
        message: 'Parameter berikut wajib diisi nilainya:\n\n• ' + missingChks.join('\n• '),
        tabIndexToGo: 2, // Checklist Tab
      );
      return;
    }

    // 3. Konfirmasi Penyelesaian
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: const Text('Selesaikan Work Order?'),
        content: const Text(
          'Semua prosedur telah selesai dan checklist telah diisi. Pastikan Anda telah melengkapi tanda tangan teknisi / pelanggan sebelum menyimpan.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('Periksa Kembali')),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: AppColors.statusSolved),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Ya, Selesaikan', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );

    if (confirm == true) {
      try {
        await _repo.updateStatus(widget.workOrderId, 'solve');
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Selamat! Work Order berhasil diselesaikan.'),
            backgroundColor: AppColors.statusSolved,
          ),
        );
        _loadDetail();
      } catch (e) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Gagal menyelesaikan WO: $e')));
      }
    }
  }

  void _showValidationDialog({required String title, required String message, int? tabIndexToGo}) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: Row(
          children: [
            const Icon(Icons.warning_amber_rounded, color: AppColors.statusOverdue),
            const SizedBox(width: 8),
            Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
          ],
        ),
        content: Text(message, style: const TextStyle(fontSize: 13, height: 1.4)),
        actions: [
          ElevatedButton(
            onPressed: () {
              Navigator.of(ctx).pop();
              if (tabIndexToGo != null) {
                _tabController.animateTo(tabIndexToGo);
              }
            },
            child: const Text('Buka Formulir'),
          ),
        ],
      ),
    );
  }

  Future<void> _capturePhotoForProcedure(ProcedureModel proc, ImageSource source) async {
    try {
      final XFile? image = await _picker.pickImage(
        source: source,
        imageQuality: 75,
        maxWidth: 1200,
      );

      if (image != null) {
        await _repo.updateProcedure(
          workOrderId: widget.workOrderId,
          procedureId: proc.id,
          isCompleted: proc.isCompleted,
          notes: proc.notes,
          newLocalPhotos: [image.path],
        );
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Foto bukti berhasil disimpan di perangkat.')),
        );
        _loadDetail();
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Gagal mengambil foto: $e')),
      );
    }
  }

  Future<void> _confirmDeletePhoto(ProcedureModel proc, {String? localPath, String? photoUrlOrPath}) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Row(
          children: [
            Icon(Icons.delete_outline, color: AppColors.statusOverdue),
            SizedBox(width: 8),
            Text('Hapus Foto?'),
          ],
        ),
        content: const Text(
          'Apakah Anda yakin ingin menghapus foto bukti ini? Jika salah upload, Anda bisa mengambil foto baru setelah menghapusnya.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Batal'),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.statusOverdue,
              foregroundColor: Colors.white,
            ),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Hapus'),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      try {
        await _repo.deleteProcedurePhoto(
          workOrderId: widget.workOrderId,
          procedureId: proc.id,
          localPath: localPath,
          photoUrlOrPath: photoUrlOrPath,
        );
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Foto bukti berhasil dihapus.'),
              backgroundColor: AppColors.statusCompleted,
            ),
          );
          _loadDetail();
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Gagal menghapus foto: $e'),
              backgroundColor: AppColors.statusOverdue,
            ),
          );
        }
      }
    }
  }

  void _showPhotoPreviewDialog(ProcedureModel proc, {String? localPath, String? photoUrlOrPath}) {
    final isLocal = localPath != null;
    showDialog(
      context: context,
      builder: (ctx) => Dialog(
        backgroundColor: Colors.transparent,
        insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
        child: Container(
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(16),
          ),
          clipBehavior: Clip.antiAlias,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                color: Colors.grey.shade100,
                child: Row(
                  children: [
                    const Icon(Icons.photo_outlined, size: 20, color: AppColors.primary),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        proc.name,
                        style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    IconButton(
                      icon: const Icon(Icons.close, size: 20),
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(),
                      onPressed: () => Navigator.pop(ctx),
                    ),
                  ],
                ),
              ),
              Flexible(
                child: Container(
                  constraints: const BoxConstraints(maxHeight: 380),
                  width: double.infinity,
                  color: Colors.black,
                  child: Center(
                    child: isLocal
                        ? (!kIsWeb
                            ? Image.file(
                                File(localPath),
                                fit: BoxFit.contain,
                                errorBuilder: (_, __, ___) => const Center(
                                  child: Icon(Icons.broken_image, color: Colors.white54, size: 48),
                                ),
                              )
                            : const Icon(Icons.image, color: Colors.white54, size: 48))
                        : _buildNetworkImage(photoUrlOrPath!, fit: BoxFit.contain),
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.all(12),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    TextButton(
                      onPressed: () => Navigator.pop(ctx),
                      child: const Text('Tutup'),
                    ),
                    ElevatedButton.icon(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppColors.statusOverdue,
                        foregroundColor: Colors.white,
                      ),
                      icon: const Icon(Icons.delete_outline, size: 18),
                      label: const Text('Hapus Foto'),
                      onPressed: () {
                        Navigator.pop(ctx);
                        _confirmDeletePhoto(
                          proc,
                          localPath: localPath,
                          photoUrlOrPath: photoUrlOrPath,
                        );
                      },
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildNetworkImage(String photoUrl, {BoxFit fit = BoxFit.cover}) {
    String fullUrl = photoUrl;
    if (!photoUrl.startsWith('http')) {
      final base = _baseUrl.isNotEmpty ? _baseUrl : ApiConstants.defaultBaseUrl;
      final cleanBase = base.replaceAll(RegExp(r'/+$'), '');
      final cleanPath = photoUrl.startsWith('/') ? photoUrl : '/$photoUrl';
      fullUrl = '$cleanBase$cleanPath';
    }
    return Image.network(
      fullUrl,
      fit: fit,
      errorBuilder: (_, __, ___) => const Center(
        child: Icon(Icons.image, color: AppColors.primary),
      ),
    );
  }

  Widget _buildPhotoThumbnail({
    required ProcedureModel proc,
    String? localPath,
    String? photoUrlOrPath,
  }) {
    final isLocal = localPath != null;
    return Stack(
      clipBehavior: Clip.none,
      children: [
        GestureDetector(
          onTap: () => _showPhotoPreviewDialog(
            proc,
            localPath: localPath,
            photoUrlOrPath: photoUrlOrPath,
          ),
          child: Container(
            width: 70,
            height: 70,
            margin: const EdgeInsets.only(right: 10, top: 4),
            decoration: BoxDecoration(
              color: Colors.grey.shade200,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: AppColors.border),
            ),
            clipBehavior: Clip.antiAlias,
            child: isLocal
                ? (!kIsWeb
                    ? Image.file(
                        File(localPath),
                        fit: BoxFit.cover,
                        errorBuilder: (_, __, ___) => const Icon(Icons.broken_image, color: AppColors.textSecondary),
                      )
                    : const Icon(Icons.image, color: AppColors.textSecondary))
                : _buildNetworkImage(photoUrlOrPath!),
          ),
        ),
        Positioned(
          top: 0,
          right: 6,
          child: GestureDetector(
            onTap: () => _confirmDeletePhoto(
              proc,
              localPath: localPath,
              photoUrlOrPath: photoUrlOrPath,
            ),
            child: Container(
              padding: const EdgeInsets.all(3),
              decoration: BoxDecoration(
                color: Colors.red.shade600,
                shape: BoxShape.circle,
                boxShadow: const [
                  BoxShadow(color: Colors.black26, blurRadius: 3, offset: Offset(0, 1)),
                ],
              ),
              child: const Icon(Icons.close, size: 13, color: Colors.white),
            ),
          ),
        ),
      ],
    );
  }

  Future<void> _saveAllChecklists() async {
    if (_wo == null) return;
    List<Map<String, dynamic>> items = [];

    for (var chk in _wo!.checklists) {
      final ctrl = _checklistControllers[chk.id];
      final val = ctrl?.text.trim() ?? chk.value;
      items.add({'id': chk.id, 'value': val});
    }

    try {
      await _repo.saveChecklists(workOrderId: widget.workOrderId, items: items);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Parameter checklist berhasil disimpan!'),
          backgroundColor: AppColors.statusCompleted,
        ),
      );
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Gagal menyimpan checklist: $e')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    if (_isLoading) {
      return Scaffold(
        appBar: AppBar(title: const Text('Detail Work Order')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    if (_wo == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Detail Work Order')),
        body: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(_errorMessage ?? 'Data tidak ditemukan'),
              const SizedBox(height: 12),
              ElevatedButton(onPressed: _loadDetail, child: const Text('Coba Lagi')),
            ],
          ),
        ),
      );
    }

    final wo = _wo!;

    return Scaffold(
      appBar: AppBar(
        title: Text(wo.code),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadDetail,
            tooltip: 'Segarkan',
          ),
        ],
        bottom: TabBar(
          controller: _tabController,
          isScrollable: true,
          tabAlignment: TabAlignment.start,
          indicatorColor: AppColors.primary,
          labelColor: AppColors.primary,
          unselectedLabelColor: isDark ? AppColors.darkTextSecondary : AppColors.textSecondary,
          labelStyle: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
          unselectedLabelStyle: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500),
          tabs: [
            const Tab(text: 'Informasi'),
            Tab(text: 'Prosedur (${wo.proceduresCompletedCount}/${wo.proceduresCount})'),
            Tab(text: 'Parameter (${wo.checklists.length})'),
            Tab(text: 'Suku Cadang (${wo.partsUsed.length})'),
            Tab(text: 'Log (${wo.logs.length})'),
            const Tab(text: 'Tanda Tangan'),
          ],
        ),
      ),
      body: Column(
        children: [
          // Top Action Banner / Status Bar
          _buildActionBanner(wo),

          // Tab Views
          Expanded(
            child: TabBarView(
              controller: _tabController,
              children: [
                _buildInfoTab(wo),
                _buildProceduresTab(wo),
                _buildChecklistTab(wo),
                _buildPartsTab(wo),
                _buildLogsTab(wo),
                _buildSignaturesTab(wo),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // --- WIDGET BUILDERS ---

  Widget _buildActionBanner(WorkOrderModel wo) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: Theme.of(context).cardColor,
        border: const Border(bottom: BorderSide(color: AppColors.border, width: 1)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  StatusBadge(status: wo.status),
                  const SizedBox(width: 8),
                  PriorityBadge(priority: wo.priority),
                ],
              ),
              // Action Buttons
              Row(
                children: [
                  if (wo.canStart)
                    ElevatedButton.icon(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppColors.primary,
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                      ),
                      onPressed: _handleStart,
                      icon: const Icon(Icons.play_arrow_rounded, size: 18),
                      label: const Text('Mulai'),
                    ),
                  if (wo.canHold) ...[
                    OutlinedButton.icon(
                      style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                        foregroundColor: AppColors.statusHold,
                        side: const BorderSide(color: AppColors.statusHold),
                      ),
                      onPressed: _handleHold,
                      icon: const Icon(Icons.pause, size: 16),
                      label: const Text('Tunda'),
                    ),
                    const SizedBox(width: 8),
                    ElevatedButton.icon(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppColors.statusSolved,
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                      ),
                      onPressed: _handleSolve,
                      icon: const Icon(Icons.check_circle_outline, size: 18),
                      label: const Text('Selesai'),
                    ),
                  ],
                  if (wo.canResume)
                    ElevatedButton.icon(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppColors.statusInProgress,
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                      ),
                      onPressed: _handleResume,
                      icon: const Icon(Icons.play_arrow, size: 18),
                      label: const Text('Lanjutkan'),
                    ),
                ],
              ),
            ],
          ),
          if (wo.delayReason.isNotEmpty && wo.status == 'Hold') ...[
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: AppColors.bgHold,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                children: [
                  const Icon(Icons.info_outline, size: 16, color: Color(0xFFB45309)),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      'Alasan Hold: ${wo.delayReason}',
                      style: const TextStyle(fontSize: 12, color: Color(0xFFB45309), fontWeight: FontWeight.w600),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  // --- TAB 1: INFORMASI ---
  Widget _buildInfoTab(WorkOrderModel wo) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Description Card
          _buildSectionCard(
            title: 'Deskripsi Pekerjaan',
            icon: Icons.description_outlined,
            content: Text(
              wo.description,
              style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w500, height: 1.4),
            ),
          ),
          const SizedBox(height: 14),

          // Work Instructions Card
          if (wo.workInstructions.isNotEmpty) ...[
            _buildSectionCard(
              title: 'Petunjuk & Instruksi Kerja (SOP)',
              icon: Icons.menu_book_outlined,
              content: Text(
                wo.workInstructions,
                style: const TextStyle(fontSize: 13, height: 1.4),
              ),
            ),
            const SizedBox(height: 14),
          ],

          // Asset Details Card
          _buildSectionCard(
            title: 'Informasi Aset & Lokasi',
            icon: Icons.precision_manufacturing_outlined,
            content: Column(
              children: [
                _buildInfoRow('Nama Aset', wo.assetName),
                _buildInfoRow('Kode Aset', wo.assetCode),
                _buildInfoRow('Lokasi', wo.assetLocation),
                _buildInfoRow('Site / Gedung', wo.assetSite),
                _buildInfoRow('Tipe Pemeliharaan', wo.maintenanceType),
              ],
            ),
          ),
          const SizedBox(height: 14),

          // Schedule & Timing Card
          _buildSectionCard(
            title: 'Jadwal & Waktu Pengerjaan',
            icon: Icons.access_time_rounded,
            content: Column(
              children: [
                _buildInfoRow('Target Selesai', Formatters.formatDate(wo.suggestedCompletionDate)),
                _buildInfoRow('Mulai Dikerjakan', Formatters.formatDate(wo.startDate)),
                _buildInfoRow('Selesai Dikerjakan', Formatters.formatDate(wo.endDate)),
                _buildInfoRow('Tim Pelaksana', wo.team),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // --- TAB 2: PROSEDUR ---
  Widget _buildProceduresTab(WorkOrderModel wo) {
    if (wo.procedures.isEmpty) {
      return const Center(child: Text('Tidak ada prosedur kerja untuk WO ini.'));
    }

    return ListView.separated(
      padding: const EdgeInsets.all(16),
      itemCount: wo.procedures.length,
      separatorBuilder: (_, __) => const SizedBox(height: 12),
      itemBuilder: (ctx, index) {
        final proc = wo.procedures[index];
        final totalPhotos = proc.totalPhotosCount;

        return Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Top row: Checkbox, Name, Estimated time
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Checkbox(
                      value: proc.isCompleted,
                      activeColor: AppColors.statusCompleted,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(5)),
                      onChanged: (val) async {
                        setState(() => proc.isCompleted = val ?? false);
                        await _repo.updateProcedure(
                          workOrderId: wo.id,
                          procedureId: proc.id,
                          isCompleted: proc.isCompleted,
                          notes: proc.notes,
                        );
                      },
                    ),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            proc.name,
                            style: TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.w700,
                              decoration: proc.isCompleted ? TextDecoration.lineThrough : null,
                            ),
                          ),
                          if (proc.estimatedMinutes > 0)
                            Text(
                              'Estimasi: ${proc.estimatedMinutes} menit',
                              style: const TextStyle(fontSize: 11, color: AppColors.textSecondary),
                            ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 10),

                // Photo requirement tag
                if (proc.requiresAttachment || proc.minPhotos > 0) ...[
                  Row(
                    children: [
                      Icon(
                        proc.satisfiesAttachmentRequirement ? Icons.check_circle : Icons.camera_alt_outlined,
                        size: 14,
                        color: proc.satisfiesAttachmentRequirement ? AppColors.statusCompleted : AppColors.statusHold,
                      ),
                      const SizedBox(width: 6),
                      Text(
                        'Foto Bukti: $totalPhotos foto tersimpan (Min. ${proc.minPhotos > 0 ? proc.minPhotos : 1})',
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          color: proc.satisfiesAttachmentRequirement ? AppColors.statusCompleted : const Color(0xFFB45309),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                ],

                // Photos Preview Row (Local paths & online paths) with delete action
                if (proc.photos.isNotEmpty || proc.localPhotoPaths.isNotEmpty) ...[
                  SizedBox(
                    height: 75,
                    child: ListView(
                      scrollDirection: Axis.horizontal,
                      children: [
                        ...proc.localPhotoPaths.map((p) {
                          return _buildPhotoThumbnail(
                            proc: proc,
                            localPath: p,
                          );
                        }),
                        ...proc.photos.map((p) {
                          return _buildPhotoThumbnail(
                            proc: proc,
                            photoUrlOrPath: p,
                          );
                        }),
                      ],
                    ),
                  ),
                  const SizedBox(height: 10),
                ],

                // Action Buttons: Camera & Notes
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Row(
                      children: [
                        IconButton(
                          icon: const Icon(Icons.camera_alt_rounded, size: 20, color: AppColors.primary),
                          tooltip: 'Ambil Foto Bukti Kamera',
                          onPressed: () => _capturePhotoForProcedure(proc, ImageSource.camera),
                        ),
                        IconButton(
                          icon: const Icon(Icons.photo_library_outlined, size: 20, color: AppColors.secondary),
                          tooltip: 'Pilih dari Galeri',
                          onPressed: () => _capturePhotoForProcedure(proc, ImageSource.gallery),
                        ),
                      ],
                    ),
                    TextButton.icon(
                      icon: const Icon(Icons.edit_note, size: 18),
                      label: Text(proc.notes.isEmpty ? 'Tambah Catatan' : 'Ubah Catatan'),
                      onPressed: () => _showProcedureNotesDialog(proc),
                    ),
                  ],
                ),

                if (proc.notes.isNotEmpty) ...[
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: AppColors.surfaceVariant,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      'Catatan: ${proc.notes}',
                      style: const TextStyle(fontSize: 12, color: AppColors.textPrimary),
                    ),
                  ),
                ],
              ],
            ),
          ),
        );
      },
    );
  }

  void _showProcedureNotesDialog(ProcedureModel proc) {
    final ctrl = TextEditingController(text: proc.notes);
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Catatan Prosedur', style: TextStyle(fontSize: 16)),
        content: TextField(
          controller: ctrl,
          maxLines: 3,
          decoration: const InputDecoration(hintText: 'Tulis temuan atau catatan pengerjaan...'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('Batal')),
          ElevatedButton(
            onPressed: () async {
              final newNotes = ctrl.text.trim();
              setState(() => proc.notes = newNotes);
              Navigator.of(ctx).pop();
              await _repo.updateProcedure(
                workOrderId: widget.workOrderId,
                procedureId: proc.id,
                isCompleted: proc.isCompleted,
                notes: newNotes,
              );
            },
            child: const Text('Simpan'),
          ),
        ],
      ),
    );
  }

  // --- TAB 3: PARAMETER CHECKLIST ---
  Widget _buildChecklistTab(WorkOrderModel wo) {
    if (wo.checklists.isEmpty) {
      return const Center(child: Text('Tidak ada parameter checklist teknis.'));
    }

    return Column(
      children: [
        Expanded(
          child: ListView.separated(
            padding: const EdgeInsets.all(16),
            itemCount: wo.checklists.length,
            separatorBuilder: (_, __) => const SizedBox(height: 12),
            itemBuilder: (ctx, i) {
              final chk = wo.checklists[i];
              final ctrl = _checklistControllers[chk.id];

              return Card(
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        chk.parameter,
                        style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
                      ),
                      const SizedBox(height: 4),
                      if (chk.standard.isNotEmpty)
                        Text(
                          'Standar Acuan: ${chk.standard}',
                          style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
                        ),
                      const SizedBox(height: 10),
                      TextField(
                        controller: ctrl,
                        decoration: InputDecoration(
                          hintText: 'Masukkan nilai hasil inspeksi...',
                          labelText: 'Nilai Aktual',
                          contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                          suffixIcon: ctrl != null && ctrl.text.isNotEmpty
                              ? const Icon(Icons.check, color: AppColors.statusCompleted)
                              : null,
                        ),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
        Container(
          padding: const EdgeInsets.all(16),
          color: Theme.of(context).cardColor,
          child: SizedBox(
            width: double.infinity,
            child: ElevatedButton.icon(
              onPressed: _saveAllChecklists,
              icon: const Icon(Icons.save_outlined),
              label: const Text('Simpan Semua Parameter'),
            ),
          ),
        ),
      ],
    );
  }

  // --- TAB 4: SUKU CADANG ---
  Widget _buildPartsTab(WorkOrderModel wo) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'Suku Cadang Digunakan',
                style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
              ),
              ElevatedButton.icon(
                icon: const Icon(Icons.add, size: 16),
                label: const Text('Tambah Part'),
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                ),
                onPressed: () async {
                  final result = await showDialog<Map<String, dynamic>>(
                    context: context,
                    builder: (_) => AddPartDialog(workOrderId: wo.id),
                  );
                  if (result != null) {
                    final part = result['part'] as PartModel;
                    final qty = result['quantity'] as double;
                    await _repo.addUsedPart(
                      workOrderId: wo.id,
                      partId: part.id,
                      partName: part.name,
                      partCode: part.code,
                      quantity: qty,
                      unit: part.unit,
                    );
                    _loadDetail();
                  }
                },
              ),
            ],
          ),
        ),
        const Divider(height: 1),
        Expanded(
          child: wo.partsUsed.isEmpty
              ? const Center(child: Text('Belum ada suku cadang yang dicatat untuk WO ini.'))
              : ListView.separated(
                  padding: const EdgeInsets.all(16),
                  itemCount: wo.partsUsed.length,
                  separatorBuilder: (_, __) => const SizedBox(height: 10),
                  itemBuilder: (ctx, i) {
                    final p = wo.partsUsed[i];
                    return Card(
                      child: ListTile(
                        leading: Container(
                          padding: const EdgeInsets.all(8),
                          decoration: BoxDecoration(
                            color: AppColors.bgInProgress,
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: const Icon(Icons.build, color: AppColors.primary, size: 20),
                        ),
                        title: Text(p.partName, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
                        subtitle: Text('Kode: ${p.partCode} • Ditambahkan: ${Formatters.formatDateShort(p.dateAdded)}'),
                        trailing: Text(
                          '${p.quantityUsed} ${p.unit}',
                          style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w800, color: AppColors.primary),
                        ),
                      ),
                    );
                  },
                ),
        ),
      ],
    );
  }

  // --- TAB 5: LOG & CATATAN ---
  Widget _buildLogsTab(WorkOrderModel wo) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'Riwayat Aktivitas & Progres',
                style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
              ),
              ElevatedButton.icon(
                icon: const Icon(Icons.add_comment_outlined, size: 16),
                label: const Text('Tambah Catatan'),
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                ),
                onPressed: () async {
                  final text = await showDialog<String>(
                    context: context,
                    builder: (_) => const AddLogDialog(),
                  );
                  if (text != null && text.isNotEmpty) {
                    await _repo.addWorkLog(
                      workOrderId: wo.id,
                      text: text,
                      userName: 'Teknisi',
                    );
                    _loadDetail();
                  }
                },
              ),
            ],
          ),
        ),
        const Divider(height: 1),
        Expanded(
          child: wo.logs.isEmpty
              ? const Center(child: Text('Belum ada log catatan aktivitas.'))
              : ListView.separated(
                  padding: const EdgeInsets.all(16),
                  itemCount: wo.logs.length,
                  separatorBuilder: (_, __) => const SizedBox(height: 12),
                  itemBuilder: (ctx, i) {
                    final log = wo.logs[i];
                    return Card(
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Text(
                                  log.userName,
                                  style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: AppColors.primary),
                                ),
                                Text(
                                  Formatters.timeAgo(log.createdAt),
                                  style: const TextStyle(fontSize: 11, color: AppColors.textMuted),
                                ),
                              ],
                            ),
                            const SizedBox(height: 8),
                            Text(
                              log.logText,
                              style: const TextStyle(fontSize: 13, height: 1.3),
                            ),
                          ],
                        ),
                      ),
                    );
                  },
                ),
        ),
      ],
    );
  }

  // --- TAB 6: TANDA TANGAN ---
  Widget _buildSignaturesTab(WorkOrderModel wo) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Technician Signature Card
          _buildSignatureBox(
            title: 'Tanda Tangan Teknisi Pelaksana',
            signerName: 'Teknisi',
            signerTitle: 'Teknisi Jaya Teknik',
            signatureBase64: wo.technicianSignature,
            onSign: () async {
              final result = await showDialog<Map<String, String>>(
                context: context,
                builder: (_) => const SignatureDialog(
                  title: 'Tanda Tangan Teknisi',
                  showNameFields: false,
                ),
              );
              if (result != null && result['signature'] != null) {
                await _repo.saveSignatures(
                  workOrderId: wo.id,
                  technicianSignature: result['signature'],
                );
                _loadDetail();
              }
            },
          ),
          const SizedBox(height: 20),

          // Customer / PIC Signature Card
          _buildSignatureBox(
            title: 'Tanda Tangan Pelanggan / PIC Lapangan',
            signerName: wo.customerName.isNotEmpty ? wo.customerName : 'PIC Gedung',
            signerTitle: wo.customerTitle.isNotEmpty ? wo.customerTitle : 'Pengawas Lokasi',
            signatureBase64: wo.customerSignature,
            showTitle: true,
            onSign: () async {
              final result = await showDialog<Map<String, String>>(
                context: context,
                builder: (_) => SignatureDialog(
                  title: 'Tanda Tangan Pelanggan',
                  showNameFields: true,
                  initialName: wo.customerName,
                  initialTitle: wo.customerTitle,
                ),
              );
              if (result != null && result['signature'] != null) {
                await _repo.saveSignatures(
                  workOrderId: wo.id,
                  customerSignature: result['signature'],
                  customerName: result['name'],
                  customerTitle: result['title'],
                );
                _loadDetail();
              }
            },
          ),
        ],
      ),
    );
  }

  Widget _buildSignatureBox({
    required String title,
    required String signerName,
    required String signerTitle,
    required String signatureBase64,
    required VoidCallback onSign,
    bool showTitle = false,
  }) {
    final hasSig = signatureBase64.isNotEmpty;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
            const SizedBox(height: 10),
            Container(
              height: 140,
              width: double.infinity,
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: AppColors.border, width: 1.5),
              ),
              child: hasSig
                  ? ClipRRect(
                      borderRadius: BorderRadius.circular(12),
                      child: signatureBase64.startsWith('data:image')
                          ? Image.memory(
                              base64Decode(signatureBase64.split(',')[1]),
                              fit: BoxFit.contain,
                            )
                          : const Center(child: Text('Tanda Tangan Tersimpan')),
                    )
                  : Center(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: const [
                          Icon(Icons.draw_outlined, size: 36, color: AppColors.textMuted),
                          SizedBox(height: 6),
                          Text('Belum ada tanda tangan', style: TextStyle(fontSize: 12, color: AppColors.textMuted)),
                        ],
                      ),
                    ),
            ),
            const SizedBox(height: 12),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(signerName, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
                    Text(signerTitle, style: const TextStyle(fontSize: 11, color: AppColors.textSecondary)),
                  ],
                ),
                ElevatedButton.icon(
                  onPressed: onSign,
                  icon: Icon(hasSig ? Icons.edit : Icons.draw, size: 16),
                  label: Text(hasSig ? 'Ubah' : 'Tanda Tangani'),
                  style: ElevatedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSectionCard({
    required String title,
    required IconData icon,
    required Widget content,
  }) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, size: 18, color: AppColors.primary),
                const SizedBox(width: 8),
                Text(
                  title,
                  style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700, letterSpacing: -0.2),
                ),
              ],
            ),
            const SizedBox(height: 12),
            content,
          ],
        ),
      ),
    );
  }

  Widget _buildInfoRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 120,
            child: Text(
              label,
              style: const TextStyle(fontSize: 12, color: AppColors.textSecondary, fontWeight: FontWeight.w500),
            ),
          ),
          Expanded(
            child: Text(
              value.isNotEmpty ? value : '-',
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
  }
}
