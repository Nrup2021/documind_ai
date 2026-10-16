import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:documind_ai/core/network/api_failure.dart';
import 'package:documind_ai/features/documents/data/api_documents_repository.dart';
import 'package:documind_ai/features/documents/data/document_library_store.dart';
import 'package:documind_ai/features/documents/domain/document_record.dart';
import 'package:documind_ai/features/questions/data/api_questions_repository.dart';
import 'package:flutter_test/flutter_test.dart';

class FakeLibraryStore implements DocumentLibraryStore {
  final saved = <DocumentRecord>[];

  @override
  Future<List<DocumentRecord>> load() async => List.of(saved);

  @override
  Future<void> save(DocumentRecord document) async {
    saved.removeWhere((existing) => existing.id == document.id);
    saved.insert(0, document);
  }

  @override
  Future<void> remove(String documentId) async {
    saved.removeWhere((document) => document.id == documentId);
  }
}

void main() {
  late HttpServer server;
  late StreamSubscription<HttpRequest> subscription;
  late Dio client;

  Future<void> startServer(
    Future<void> Function(HttpRequest request) handler,
  ) async {
    server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    subscription = server.listen(handler);
    client = Dio(BaseOptions(baseUrl: 'http://127.0.0.1:${server.port}'));
  }

  tearDown(() async {
    client.close(force: true);
    await subscription.cancel();
    await server.close(force: true);
  });

  test(
    'uploads multipart field file and parses the backend upload response',
    () async {
      late String path;
      late String contentType;
      late String body;
      await startServer((request) async {
        path = request.uri.path;
        contentType = request.headers.value(HttpHeaders.contentTypeHeader)!;
        final bytes = await request.fold<List<int>>(
          [],
          (buffer, chunk) => buffer..addAll(chunk),
        );
        body = latin1.decode(bytes);
        request.response.statusCode = HttpStatus.created;
        request.response.headers.contentType = ContentType.json;
        request.response.write(
          jsonEncode({
            'document_id': 'doc-123',
            'page_count': 3,
            'chunk_count': 4,
          }),
        );
        await request.response.close();
      });

      final store = FakeLibraryStore();
      final repository = ApiDocumentsRepository(
        client: client,
        libraryStore: store,
      );
      final document = await repository.uploadPdf(
        filename: 'research.pdf',
        bytes: Uint8List.fromList(utf8.encode('%PDF-1.7\nfixture')),
        onProgress: (_) {},
      );

      expect(path, '/v1/documents');
      expect(contentType, startsWith('multipart/form-data;'));
      expect(body, contains('name="file"; filename="research.pdf"'));
      expect(document.id, 'doc-123');
      expect(document.pageCount, 3);
      expect(document.chunkCount, 4);
      expect(store.saved.single.name, 'research.pdf');
    },
  );

  test(
    'asks the document-scoped question route with the backend JSON shape',
    () async {
      late String path;
      late Map<String, dynamic> requestBody;
      await startServer((request) async {
        path = request.uri.path;
        requestBody = jsonDecode(
          await utf8.decoder.bind(request).join(),
        ) as Map<String, dynamic>;
        request.response.headers.contentType = ContentType.json;
        request.response.write(
          jsonEncode({
            'outcome': 'answered',
            'answer': 'The report highlights user retention.',
            'citations': [
              {'page_number': 2, 'excerpt': 'Retention increased in Q3.'},
            ],
          }),
        );
        await request.response.close();
      });

      final answer = await ApiQuestionsRepository(
        client,
      ).ask(documentId: 'doc-123', question: 'What does the report highlight?');

      expect(path, '/v1/documents/doc-123/questions');
      expect(requestBody, {'question': 'What does the report highlight?'});
      expect(answer.outcome, 'answered');
      expect(answer.citations.single.pageNumber, 2);
      expect(answer.citations.single.excerpt, 'Retention increased in Q3.');
    },
  );

  test('preserves structured backend errors for an invalid PDF', () async {
    await startServer((request) async {
      await request.drain<void>();
      request.response.statusCode = HttpStatus.badRequest;
      request.response.headers.contentType = ContentType.json;
      request.response.write(
        jsonEncode({
          'error': {
            'code': 'invalid_pdf',
            'message': 'The uploaded file is not a valid PDF.',
          },
        }),
      );
      await request.response.close();
    });

    final repository = ApiDocumentsRepository(
      client: client,
      libraryStore: FakeLibraryStore(),
    );
    await expectLater(
      repository.uploadPdf(
        filename: 'broken.pdf',
        bytes: Uint8List.fromList(utf8.encode('not a pdf')),
        onProgress: (_) {},
      ),
      throwsA(
        isA<ApiFailure>()
            .having((failure) => failure.code, 'code', 'invalid_pdf')
            .having(
              (failure) => failure.message,
              'message',
              'The uploaded file is not a valid PDF.',
            ),
      ),
    );
  });

  test(
    'deletes an indexed PDF before removing its local library entry',
    () async {
      late String path;
      await startServer((request) async {
        path = request.uri.path;
        request.response.statusCode = HttpStatus.noContent;
        await request.response.close();
      });
      final store = FakeLibraryStore()
        ..saved.add(
          DocumentRecord(
            id: 'doc-123',
            name: 'research.pdf',
            sizeBytes: 123,
            uploadedAt: DateTime(2026),
            status: DocumentStatus.ready,
          ),
        );
      final repository = ApiDocumentsRepository(
        client: client,
        libraryStore: store,
      );

      await repository.remove(store.saved.single);

      expect(path, '/v1/documents/doc-123');
      expect(store.saved, isEmpty);
    },
  );
}
