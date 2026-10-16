import 'dart:typed_data';

import 'package:dio/dio.dart';

import '../../../core/network/api_failure.dart';
import '../domain/document_record.dart';
import '../domain/documents_repository.dart';
import 'document_library_store.dart';

class ApiDocumentsRepository implements DocumentsRepository {
  ApiDocumentsRepository({required this._client, required this._libraryStore});

  final Dio _client;
  final DocumentLibraryStore _libraryStore;

  @override
  Future<List<DocumentRecord>> loadLibrary() => _libraryStore.load();

  @override
  Future<DocumentRecord> uploadPdf({
    required String filename,
    required Uint8List bytes,
    required void Function(double progress) onProgress,
  }) async {
    final form = FormData.fromMap({
      'file': MultipartFile.fromBytes(bytes, filename: filename),
    });

    try {
      final response = await _client.post<Map<String, dynamic>>(
        '/v1/documents',
        data: form,
        onSendProgress: (sent, total) {
          if (total > 0) onProgress((sent / total).clamp(0, 1).toDouble());
        },
      );
      final body = response.data;
      final id = body?['document_id'];
      final pages = body?['page_count'];
      final chunks = body?['chunk_count'];
      if (id is! String || pages is! int || chunks is! int) {
        throw const ApiFailure(
          code: 'invalid_response',
          message: 'The API returned an invalid upload response.',
        );
      }

      final document = DocumentRecord(
        id: id,
        name: filename,
        sizeBytes: bytes.length,
        uploadedAt: DateTime.now(),
        status: DocumentStatus.ready,
        pageCount: pages,
        chunkCount: chunks,
      );
      await _libraryStore.save(document);
      return document;
    } on DioException catch (error) {
      throw ApiFailure.fromDio(error);
    }
  }
}
