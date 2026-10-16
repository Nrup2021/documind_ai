import 'package:documind_ai/features/documents/data/document_library_store.dart';
import 'package:documind_ai/features/documents/domain/document_record.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('persists completed document metadata for the local library', () async {
    SharedPreferences.setMockInitialValues({});
    final store = SharedPreferencesDocumentLibraryStore();
    final document = DocumentRecord(
      id: 'doc-123',
      name: 'research.pdf',
      sizeBytes: 4096,
      uploadedAt: DateTime.utc(2026, 10, 16),
      status: DocumentStatus.ready,
      pageCount: 5,
      chunkCount: 8,
    );

    await store.save(document);
    final restored = await store.load();

    expect(restored, hasLength(1));
    expect(restored.single.id, document.id);
    expect(restored.single.name, document.name);
    expect(restored.single.sizeBytes, document.sizeBytes);
    expect(restored.single.uploadedAt, document.uploadedAt);
    expect(restored.single.status, DocumentStatus.ready);
    expect(restored.single.pageCount, 5);
    expect(restored.single.chunkCount, 8);
  });
}
