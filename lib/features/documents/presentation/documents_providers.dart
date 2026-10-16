import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/api_failure.dart';
import '../data/api_documents_repository.dart';
import '../data/document_library_store.dart';
import '../domain/document_record.dart';
import '../domain/documents_repository.dart';

final documentLibraryStoreProvider = Provider<DocumentLibraryStore>(
  (ref) => SharedPreferencesDocumentLibraryStore(),
);

final documentsRepositoryProvider = Provider<DocumentsRepository>((ref) {
  return ApiDocumentsRepository(
    client: ref.watch(apiClientProvider),
    libraryStore: ref.watch(documentLibraryStoreProvider),
  );
});

final documentsControllerProvider =
    AsyncNotifierProvider<DocumentsController, List<DocumentRecord>>(
      DocumentsController.new,
    );

class DocumentsController extends AsyncNotifier<List<DocumentRecord>> {
  @override
  Future<List<DocumentRecord>> build() {
    return ref.watch(documentsRepositoryProvider).loadLibrary();
  }

  Future<void> uploadPdf({
    required String filename,
    required Uint8List bytes,
  }) async {
    final pending = DocumentRecord(
      id: 'upload-${DateTime.now().microsecondsSinceEpoch}',
      name: filename,
      sizeBytes: bytes.length,
      uploadedAt: DateTime.now(),
      status: DocumentStatus.uploading,
      progress: 0,
      retryBytes: bytes,
    );
    state = AsyncData([pending, ...(state.value ?? const <DocumentRecord>[])]);
    await _upload(pending);
  }

  Future<void> retryUpload(DocumentRecord document) async {
    final bytes = document.retryBytes;
    if (bytes == null) {
      throw const ApiFailure(
        code: 'retry_unavailable',
        message: 'Select the PDF again to retry this upload.',
      );
    }
    final pending = document.copyWith(
      status: DocumentStatus.uploading,
      progress: 0,
      clearError: true,
    );
    _replace(document.id, pending);
    await _upload(pending);
  }

  Future<void> removeDocument(DocumentRecord document) async {
    if (document.status == DocumentStatus.uploading) {
      throw const ApiFailure(
        code: 'upload_in_progress',
        message: 'Wait for the upload to finish before removing this PDF.',
      );
    }
    await ref.read(documentsRepositoryProvider).remove(document);
    state = AsyncData([
      for (final item in state.value ?? const <DocumentRecord>[])
        if (item.id != document.id) item,
    ]);
  }

  Future<void> _upload(DocumentRecord pending) async {
    try {
      final uploaded = await ref
          .read(documentsRepositoryProvider)
          .uploadPdf(
            filename: pending.name,
            bytes: pending.retryBytes!,
            onProgress: (progress) {
              final current = _find(pending.id);
              if (current != null) {
                _replace(pending.id, current.copyWith(progress: progress));
              }
            },
          );
      _replace(pending.id, uploaded);
    } on ApiFailure catch (failure) {
      _replace(
        pending.id,
        pending.copyWith(
          status: DocumentStatus.failed,
          progress: null,
          errorMessage: failure.message,
        ),
      );
    } catch (error, stackTrace) {
      _replace(
        pending.id,
        pending.copyWith(
          status: DocumentStatus.failed,
          progress: null,
          errorMessage: 'Upload failed unexpectedly. Please retry.',
        ),
      );
      Error.throwWithStackTrace(error, stackTrace);
    }
  }

  DocumentRecord? _find(String id) {
    return state.value?.where((document) => document.id == id).firstOrNull;
  }

  void _replace(String id, DocumentRecord replacement) {
    final documents = state.value ?? const <DocumentRecord>[];
    state = AsyncData([
      for (final document in documents)
        if (document.id == id) replacement else document,
    ]);
  }
}

final pdfPickerProvider = Provider<PdfPicker>((ref) => const PdfPicker());

class SelectedPdf {
  const SelectedPdf({required this.filename, required this.bytes});

  final String filename;
  final Uint8List bytes;
}

class PdfPicker {
  const PdfPicker();

  static const maxUploadBytes = 25 * 1024 * 1024;

  Future<SelectedPdf?> pickPdf() async {
    final file = await FilePicker.pickFile(
      type: FileType.custom,
      allowedExtensions: const ['pdf'],
    );
    if (file == null) return null;
    if (file.extension?.toLowerCase() != 'pdf') {
      throw const ApiFailure(
        code: 'invalid_file_type',
        message: 'Choose a file with the .pdf extension.',
      );
    }
    final fileSize = await file.length();
    if (fileSize == null) {
      throw const ApiFailure(
        code: 'file_read_error',
        message:
            'The selected PDF size could not be read. Please choose it again.',
      );
    }
    if (fileSize > maxUploadBytes) {
      throw const ApiFailure(
        code: 'upload_too_large',
        message: 'The PDF exceeds the 25 MiB upload limit.',
      );
    }
    final bytes = await file.readAsBytes();
    if (bytes.isEmpty) {
      throw const ApiFailure(
        code: 'empty_upload',
        message: 'The selected PDF could not be read. Please choose it again.',
      );
    }
    if (bytes.length > maxUploadBytes) {
      throw const ApiFailure(
        code: 'upload_too_large',
        message: 'The PDF exceeds the 25 MiB upload limit.',
      );
    }
    return SelectedPdf(filename: file.name, bytes: bytes);
  }
}
