import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../documents/domain/document_record.dart';
import '../../documents/presentation/documents_providers.dart';
import '../domain/question_answer.dart';
import 'questions_providers.dart';

class ChatScreen extends ConsumerStatefulWidget {
  const ChatScreen({super.key});

  @override
  ConsumerState<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends ConsumerState<ChatScreen> {
  final _questionController = TextEditingController();
  String? _selectedDocumentId;

  @override
  void dispose() {
    _questionController.dispose();
    super.dispose();
  }

  Future<void> _submit(String documentId) async {
    final question = _questionController.text;
    if (question.trim().isEmpty) return;
    await ref
        .read(questionControllerProvider.notifier)
        .ask(documentId: documentId, question: question);
    _questionController.clear();
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final documentsState = ref.watch(documentsControllerProvider);
    final chat = ref.watch(questionControllerProvider);
    final readyDocuments =
        documentsState.value
            ?.where((document) => document.status == DocumentStatus.ready)
            .toList() ??
        const <DocumentRecord>[];
    final selectedDocument = readyDocuments
        .where((document) => document.id == _selectedDocumentId)
        .firstOrNull;
    final activeDocument =
        selectedDocument ??
        readyDocuments
            .where((document) => document.id == chat.documentId)
            .firstOrNull ??
        (readyDocuments.isEmpty ? null : readyDocuments.first);

    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 920),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 24, 24, 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'QUESTIONS',
                style: textTheme.labelMedium?.copyWith(
                  color: Theme.of(context).colorScheme.primary,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1.2,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'Chat with your documents',
                style: textTheme.headlineMedium?.copyWith(
                  fontWeight: FontWeight.w700,
                  letterSpacing: -0.7,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                'Answers are grounded in retrieved pages from your PDF.',
                style: textTheme.bodyLarge?.copyWith(color: Colors.black54),
              ),
              const SizedBox(height: 18),
              if (documentsState.isLoading)
                const Expanded(
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (documentsState.hasError)
                Expanded(
                  child: _MessagePanel(
                    icon: Icons.cloud_off_outlined,
                    title: 'Your library could not be loaded',
                    description: 'Refresh the library and try again.',
                    actionLabel: 'Refresh library',
                    onAction: () => ref.invalidate(documentsControllerProvider),
                  ),
                )
              else if (activeDocument == null)
                Expanded(
                  child: _MessagePanel(
                    icon: Icons.menu_book_outlined,
                    title: 'Add a PDF to start chatting',
                    description:
                        'Upload a document first. Once processing succeeds, '
                        'you can ask questions and review its source pages.',
                    actionLabel: 'Open library',
                    onAction: () => context.go('/documents'),
                  ),
                )
              else ...[
                _DocumentSelector(
                  documents: readyDocuments,
                  selected: activeDocument,
                  onChanged: (document) {
                    if (document == null) return;
                    setState(() => _selectedDocumentId = document.id);
                    ref
                        .read(questionControllerProvider.notifier)
                        .selectDocument(document.id);
                  },
                ),
                const SizedBox(height: 12),
                Expanded(
                  child: chat.turns.isEmpty
                      ? _MessagePanel(
                          icon: Icons.forum_outlined,
                          title: 'Ask about ${activeDocument.name}',
                          description:
                              'Try a summary, find a key detail, or ask for '
                              'evidence from a specific page.',
                        )
                      : ListView.builder(
                          itemCount: chat.turns.length,
                          itemBuilder: (context, index) => _TurnView(
                            turn: chat.turns[index],
                            onRetry: chat.isSending
                                ? null
                                : () => ref
                                      .read(questionControllerProvider.notifier)
                                      .retryLast(),
                          ),
                        ),
                ),
                const SizedBox(height: 12),
                _QuestionComposer(
                  controller: _questionController,
                  enabled: !chat.isSending,
                  onSubmit: () => _submit(activeDocument.id),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _DocumentSelector extends StatelessWidget {
  const _DocumentSelector({
    required this.documents,
    required this.selected,
    required this.onChanged,
  });

  final List<DocumentRecord> documents;
  final DocumentRecord selected;
  final ValueChanged<DocumentRecord?> onChanged;

  @override
  Widget build(BuildContext context) {
    return DropdownButtonFormField<String>(
      initialValue: selected.id,
      decoration: const InputDecoration(
        labelText: 'Ask about',
        prefixIcon: Icon(Icons.picture_as_pdf_outlined),
        border: OutlineInputBorder(),
      ),
      items: [
        for (final document in documents)
          DropdownMenuItem(
            value: document.id,
            child: Text(document.name, overflow: TextOverflow.ellipsis),
          ),
      ],
      onChanged: (id) => onChanged(
        documents.where((document) => document.id == id).firstOrNull,
      ),
    );
  }
}

class _MessagePanel extends StatelessWidget {
  const _MessagePanel({
    required this.icon,
    required this.title,
    required this.description,
    this.actionLabel,
    this.onAction,
  });

  final IconData icon;
  final String title;
  final String description;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    return SingleChildScrollView(
      child: Center(
        child: Card(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 34),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(icon, size: 38, color: colors.primary),
                const SizedBox(height: 14),
                Text(
                  title,
                  textAlign: TextAlign.center,
                  style: textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  description,
                  textAlign: TextAlign.center,
                  style: textTheme.bodyMedium?.copyWith(color: Colors.black54),
                ),
                if (actionLabel != null) ...[
                  const SizedBox(height: 18),
                  FilledButton.tonal(
                    onPressed: onAction,
                    child: Text(actionLabel!),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _TurnView extends StatelessWidget {
  const _TurnView({required this.turn, required this.onRetry});

  final ChatTurn turn;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Align(
            alignment: Alignment.centerRight,
            child: Container(
              constraints: const BoxConstraints(maxWidth: 620),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: BoxDecoration(
                color: colors.primary,
                borderRadius: BorderRadius.circular(18),
              ),
              child: Text(
                turn.question,
                style: textTheme.bodyLarge?.copyWith(color: colors.onPrimary),
              ),
            ),
          ),
          const SizedBox(height: 10),
          if (turn.isLoading)
            const Card(
              child: Padding(
                padding: EdgeInsets.all(18),
                child: Row(
                  children: [
                    SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                    SizedBox(width: 12),
                    Text('Searching this document and preparing an answer…'),
                  ],
                ),
              ),
            )
          else if (turn.errorMessage != null)
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      turn.errorMessage!,
                      style: textTheme.bodyMedium?.copyWith(
                        color: colors.error,
                      ),
                    ),
                    const SizedBox(height: 8),
                    TextButton.icon(
                      onPressed: onRetry,
                      icon: const Icon(Icons.refresh),
                      label: const Text('Retry question'),
                    ),
                  ],
                ),
              ),
            )
          else if (turn.answer case final answer?)
            _AnswerCard(answer: answer),
        ],
      ),
    );
  }
}

class _AnswerCard extends StatelessWidget {
  const _AnswerCard({required this.answer});

  final QuestionAnswer answer;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    final insufficient = answer.hasInsufficientEvidence;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  insufficient ? Icons.info_outline : Icons.auto_awesome,
                  size: 19,
                  color: insufficient ? colors.tertiary : colors.primary,
                ),
                const SizedBox(width: 8),
                Text(
                  insufficient ? 'Not enough evidence' : 'Answer',
                  style: textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.w700,
                    color: insufficient ? colors.tertiary : colors.primary,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Text(answer.answer, style: textTheme.bodyLarge),
            if (answer.citations.isNotEmpty) ...[
              const SizedBox(height: 16),
              const Divider(),
              const SizedBox(height: 8),
              Text(
                'SOURCES',
                style: textTheme.labelSmall?.copyWith(
                  letterSpacing: 1,
                  fontWeight: FontWeight.w700,
                  color: colors.primary,
                ),
              ),
              const SizedBox(height: 8),
              for (final citation in answer.citations)
                _CitationView(citation: citation),
            ],
          ],
        ),
      ),
    );
  }
}

class _CitationView extends StatelessWidget {
  const _CitationView({required this.citation});

  final Citation citation;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(top: 6),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: colors.surfaceContainerHighest.withValues(alpha: 0.55),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Page ${citation.pageNumber}',
            style: Theme.of(context).textTheme.labelMedium
                ?.copyWith(fontWeight: FontWeight.w700, color: colors.primary),
          ),
          const SizedBox(height: 4),
          Text(
            '“${citation.excerpt}”',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}

class _QuestionComposer extends StatelessWidget {
  const _QuestionComposer({
    required this.controller,
    required this.enabled,
    required this.onSubmit,
  });

  final TextEditingController controller;
  final bool enabled;
  final VoidCallback onSubmit;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 8, 8, 8),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: TextField(
                controller: controller,
                enabled: enabled,
                minLines: 1,
                maxLines: 4,
                maxLength: 2000,
                textCapitalization: TextCapitalization.sentences,
                decoration: const InputDecoration(
                  hintText: 'Ask a question about this PDF…',
                  border: InputBorder.none,
                  counterText: '',
                ),
                onSubmitted: enabled ? (_) => onSubmit() : null,
              ),
            ),
            const SizedBox(width: 8),
            IconButton.filled(
              tooltip: 'Send question',
              onPressed: enabled ? onSubmit : null,
              icon: const Icon(Icons.arrow_upward),
            ),
          ],
        ),
      ),
    );
  }
}
