import 'dart:typed_data';

import 'package:documind_ai/app/app.dart';
import 'package:documind_ai/core/network/api_failure.dart';
import 'package:documind_ai/features/documents/domain/document_record.dart';
import 'package:documind_ai/features/documents/domain/documents_repository.dart';
import 'package:documind_ai/features/documents/presentation/documents_providers.dart';
import 'package:documind_ai/features/questions/domain/question_answer.dart';
import 'package:documind_ai/features/questions/domain/questions_repository.dart';
import 'package:documind_ai/features/questions/presentation/questions_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

class FakeDocumentsRepository implements DocumentsRepository {
  final documents = <DocumentRecord>[];
  bool failNextUpload = false;

  @override
  Future<List<DocumentRecord>> loadLibrary() async => List.of(documents);

  @override
  Future<DocumentRecord> uploadPdf({
    required String filename,
    required Uint8List bytes,
    required void Function(double progress) onProgress,
  }) async {
    onProgress(0.5);
    if (failNextUpload) {
      failNextUpload = false;
      throw const ApiFailure(
        code: 'invalid_pdf',
        message: 'The selected file is not a valid PDF.',
      );
    }
    final document = DocumentRecord(
      id: 'document-${documents.length + 1}',
      name: filename,
      sizeBytes: bytes.length,
      uploadedAt: DateTime(2026, 1, 1),
      status: DocumentStatus.ready,
      pageCount: 4,
      chunkCount: 6,
    );
    documents.insert(0, document);
    onProgress(1);
    return document;
  }
}

class FakeQuestionsRepository implements QuestionsRepository {
  @override
  Future<QuestionAnswer> ask({
    required String documentId,
    required String question,
  }) async {
    return const QuestionAnswer(
      outcome: 'answered',
      answer: 'The document describes a steady increase.',
      citations: [
        Citation(pageNumber: 2, excerpt: 'The measure increased steadily.'),
      ],
    );
  }
}

class FakePdfPicker extends PdfPicker {
  FakePdfPicker();

  @override
  Future<SelectedPdf?> pickPdf() async => SelectedPdf(
    filename: 'research.pdf',
    bytes: Uint8List.fromList([37, 80, 68, 70]),
  );
}

void main() {
  late FakeDocumentsRepository documentsRepository;

  Future<void> pumpApp(WidgetTester tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          documentsRepositoryProvider.overrideWithValue(documentsRepository),
          questionsRepositoryProvider.overrideWithValue(
            FakeQuestionsRepository(),
          ),
          pdfPickerProvider.overrideWith((ref) => FakePdfPicker()),
        ],
        child: const DocuMindApp(),
      ),
    );
    await tester.pumpAndSettle();
  }

  setUp(() {
    documentsRepository = FakeDocumentsRepository();
  });

  testWidgets('opens the local document library by default', (tester) async {
    await pumpApp(tester);

    expect(find.text('Documents'), findsOneWidget);
    expect(find.text('Your library is ready'), findsOneWidget);
    expect(find.text('Library'), findsOneWidget);
    expect(find.text('Chat'), findsOneWidget);
  });

  testWidgets(
    'selects a PDF, retries an upload error, and asks with citations',
    (tester) async {
      documentsRepository.failNextUpload = true;
      await pumpApp(tester);

      await tester.tap(find.text('Add PDF'));
      await tester.pumpAndSettle();

      expect(
        find.text('The selected file is not a valid PDF.'),
        findsOneWidget,
      );
      expect(find.text('Retry upload'), findsOneWidget);
      await tester.tap(find.text('Retry upload'));
      await tester.pumpAndSettle();

      expect(find.text('research.pdf'), findsOneWidget);
      expect(find.text('Ready'), findsOneWidget);
      await tester.tap(find.text('Chat').last);
      await tester.pumpAndSettle();

      expect(find.text('Ask about research.pdf'), findsOneWidget);
      await tester.enterText(
        find.byType(TextField),
        'What changed in the document?',
      );
      await tester.tap(find.byTooltip('Send question'));
      await tester.pumpAndSettle();

      expect(
        find.text('The document describes a steady increase.'),
        findsOneWidget,
      );
      expect(find.text('Page 2'), findsOneWidget);
      expect(find.text('“The measure increased steadily.”'), findsOneWidget);
    },
  );

  testWidgets('shows a navigation rail on wide layouts', (tester) async {
    tester.view.physicalSize = const Size(1200, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await pumpApp(tester);

    expect(find.byType(NavigationRail), findsOneWidget);
    expect(find.byType(NavigationBar), findsNothing);
  });
}
