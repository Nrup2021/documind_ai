import 'dart:typed_data';

import 'document_record.dart';

abstract interface class DocumentsRepository {
  Future<List<DocumentRecord>> loadLibrary();

  Future<DocumentRecord> uploadPdf({
    required String filename,
    required Uint8List bytes,
    required void Function(double progress) onProgress,
  });
}
