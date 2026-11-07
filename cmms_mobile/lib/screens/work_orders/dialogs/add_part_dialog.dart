import 'package:flutter/material.dart';
import '../../../core/constants/app_colors.dart';
import '../../../data/models/part_model.dart';
import '../../../data/repositories/work_order_repository.dart';

class AddPartDialog extends StatefulWidget {
  final int workOrderId;

  const AddPartDialog({Key? key, required this.workOrderId}) : super(key: key);

  @override
  State<AddPartDialog> createState() => _AddPartDialogState();
}

class _AddPartDialogState extends State<AddPartDialog> {
  final WorkOrderRepository _repo = WorkOrderRepository();
  final TextEditingController _searchController = TextEditingController();
  final TextEditingController _qtyController = TextEditingController(text: '1.0');

  List<PartModel> _searchResults = [];
  PartModel? _selectedPart;
  bool _isSearching = false;

  @override
  void initState() {
    super.initState();
    _searchParts('');
  }

  @override
  void dispose() {
    _searchController.dispose();
    _qtyController.dispose();
    super.dispose();
  }

  Future<void> _searchParts(String q) async {
    setState(() => _isSearching = true);
    final results = await _repo.searchParts(q);
    setState(() {
      _searchResults = results;
      _isSearching = false;
    });
  }

  void _submit() {
    if (_selectedPart == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Pilih suku cadang terlebih dahulu.')),
      );
      return;
    }

    final qty = double.tryParse(_qtyController.text) ?? 1.0;
    if (qty <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Jumlah suku cadang harus lebih dari 0.')),
      );
      return;
    }

    Navigator.of(context).pop({
      'part': _selectedPart!,
      'quantity': qty,
    });
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      title: Row(
        children: const [
          Icon(Icons.inventory_2_outlined, color: AppColors.primary, size: 22),
          SizedBox(width: 10),
          Text(
            'Tambah Suku Cadang',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
          ),
        ],
      ),
      content: SizedBox(
        width: double.maxFinite,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Search input
              TextField(
                controller: _searchController,
                onChanged: _searchParts,
                decoration: const InputDecoration(
                  hintText: 'Cari nama atau kode suku cadang...',
                  prefixIcon: Icon(Icons.search, size: 20),
                  contentPadding: EdgeInsets.symmetric(vertical: 10),
                ),
              ),
              const SizedBox(height: 12),

              // Search results list
              Container(
                height: 160,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: AppColors.border),
                ),
                child: _isSearching
                    ? const Center(child: CircularProgressIndicator())
                    : _searchResults.isEmpty
                        ? const Center(
                            child: Text(
                              'Tidak ada suku cadang ditemukan.',
                              style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
                            ),
                          )
                        : ListView.separated(
                            itemCount: _searchResults.length,
                            separatorBuilder: (_, __) => const Divider(height: 1),
                            itemBuilder: (ctx, i) {
                              final p = _searchResults[i];
                              final isSelected = _selectedPart?.id == p.id;

                              return ListTile(
                                dense: true,
                                selected: isSelected,
                                selectedTileColor: AppColors.bgInProgress,
                                title: Text(
                                  p.name,
                                  style: TextStyle(
                                    fontSize: 13,
                                    fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                                    color: isSelected ? AppColors.primary : null,
                                  ),
                                ),
                                subtitle: Text(
                                  'Kode: ${p.code} • Satuan: ${p.unit}',
                                  style: const TextStyle(fontSize: 11),
                                ),
                                trailing: isSelected
                                    ? const Icon(Icons.check_circle, color: AppColors.primary, size: 18)
                                    : null,
                                onTap: () => setState(() => _selectedPart = p),
                              );
                            },
                          ),
              ),
              const SizedBox(height: 16),

              // Quantity Input
              if (_selectedPart != null) ...[
                Row(
                  children: [
                    Expanded(
                      flex: 2,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'Jumlah Terpakai:',
                            style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                          ),
                          const SizedBox(height: 6),
                          TextField(
                            controller: _qtyController,
                            keyboardType: const TextInputType.numberWithOptions(decimal: true),
                            decoration: InputDecoration(
                              suffixText: _selectedPart!.unit,
                              contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(null),
          child: const Text('Batal'),
        ),
        ElevatedButton(
          onPressed: _submit,
          child: const Text('Gunakan'),
        ),
      ],
    );
  }
}
