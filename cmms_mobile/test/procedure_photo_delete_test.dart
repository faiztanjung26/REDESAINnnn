import 'package:flutter_test/flutter_test.dart';
import 'package:cmms_mobile/data/models/procedure_model.dart';

void main() {
  group('ProcedureModel Photo Management Tests', () {
    test('totalPhotosCount counts both local and server photos', () {
      final proc = ProcedureModel(
        id: 1,
        workOrderId: 10,
        name: 'Check Pump Pressure',
        minPhotos: 2,
        requiresAttachment: true,
        photos: ['uploads/photo1.jpg'],
        localPhotoPaths: ['/local/cache/photo2.jpg'],
      );

      expect(proc.totalPhotosCount, 2);
      expect(proc.satisfiesAttachmentRequirement, true);

      // Simulate deleting the wrong local photo
      proc.localPhotoPaths.remove('/local/cache/photo2.jpg');
      expect(proc.totalPhotosCount, 1);
      // Below minPhotos requirement of 2
      expect(proc.satisfiesAttachmentRequirement, false);
    });

    test('toDbMap and fromDb preserve photos and localPhotoPaths correctly after deletion', () {
      final proc = ProcedureModel(
        id: 2,
        workOrderId: 10,
        name: 'Grease Bearings',
        minPhotos: 1,
        requiresAttachment: true,
        attachmentPath: 'uploads/old_wrong_photo.jpg|uploads/correct_photo.jpg',
        photos: ['uploads/old_wrong_photo.jpg', 'uploads/correct_photo.jpg'],
        localPhotoPaths: ['/data/temp/extra.jpg'],
      );

      expect(proc.totalPhotosCount, 3);

      // Simulate user deleting wrong photo
      proc.photos.remove('uploads/old_wrong_photo.jpg');
      final updatedAttachments = proc.attachmentPath
          .split('|')
          .where((p) => p != 'uploads/old_wrong_photo.jpg')
          .join('|');
      proc.attachmentPath = updatedAttachments;

      final dbMap = proc.toDbMap();
      expect(dbMap['attachment_path'], 'uploads/correct_photo.jpg');

      final restored = ProcedureModel.fromDb(dbMap);
      expect(restored.photos.length, 1);
      expect(restored.photos.first, 'uploads/correct_photo.jpg');
      expect(restored.totalPhotosCount, 2); // 1 server + 1 local
    });

    test('satisfiesAttachmentRequirement works with zero minPhotos and requiresAttachment false', () {
      final proc = ProcedureModel(
        id: 3,
        workOrderId: 10,
        name: 'Visual Inspection',
        minPhotos: 0,
        requiresAttachment: false,
      );

      expect(proc.satisfiesAttachmentRequirement, true);
    });
  });
}
