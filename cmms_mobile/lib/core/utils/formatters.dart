import 'package:intl/intl.dart';

class Formatters {
  static final NumberFormat currencyFormatter = NumberFormat.currency(
    locale: 'id_ID',
    symbol: 'Rp ',
    decimalDigits: 0,
  );

  static String formatDate(String? dateStr) {
    if (dateStr == null || dateStr.isEmpty) return '-';
    try {
      final dt = DateTime.parse(dateStr);
      return DateFormat('dd MMM yyyy, HH:mm', 'id_ID').format(dt) + ' WIB';
    } catch (_) {
      return dateStr;
    }
  }

  static String formatDateShort(String? dateStr) {
    if (dateStr == null || dateStr.isEmpty) return '-';
    try {
      final dt = DateTime.parse(dateStr);
      return DateFormat('dd MMM yyyy', 'id_ID').format(dt);
    } catch (_) {
      return dateStr;
    }
  }

  static String formatCurrency(num amount) {
    return currencyFormatter.format(amount);
  }

  static String timeAgo(String? dateStr) {
    if (dateStr == null || dateStr.isEmpty) return '';
    try {
      final dt = DateTime.parse(dateStr);
      final diff = DateTime.now().difference(dt);

      if (diff.inDays > 7) {
        return DateFormat('dd MMM yyyy', 'id_ID').format(dt);
      } else if (diff.inDays >= 1) {
        return '${diff.inDays} hari yang lalu';
      } else if (diff.inHours >= 1) {
        return '${diff.inHours} jam yang lalu';
      } else if (diff.inMinutes >= 1) {
        return '${diff.inMinutes} menit yang lalu';
      } else {
        return 'Baru saja';
      }
    } catch (_) {
      return dateStr;
    }
  }
}
