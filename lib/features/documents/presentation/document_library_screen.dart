import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_failure.dart';
import '../domain/document_record.dart';
import 'documents_providers.dart';

class DocumentLibraryScreen extends ConsumerStatefulWidget {
  const DocumentLibraryScreen({super.key});

  @override
  ConsumerState<DocumentLibraryScreen> createState() =>
      _DocumentLibraryScreenState();
}

class _DocumentLibraryScreenState extends ConsumerState<DocumentLibraryScreen> {
  bool _openingPicker = false;
  final Set<String> _removingDocumentIds = {};

  Future<void> _pickAndUpload() async {
    setState(() => _openingPicker = true);
    try {
      final SelectedPdf? pdf;
      try {
        pdf = await ref.read(pdfPickerProvider).pickPdf();
      } on ApiFailure catch (failure) {
        if (mounted) _showMessage(failure.message);
        return;
      } catch (error, stackTrace) {
        FlutterError.reportError(
          FlutterErrorDetails(
            exception: error,
            stack: stackTrace,
            library: 'document PDF picker',
          ),
        );
        if (mounted) {
          _showMessage('The PDF could not be selected. Please try again.');
        }
        return;
      }
      if (pdf == null || !mounted) return;
      try {
        await ref
            .read(documentsControllerProvider.notifier)
            .uploadPdf(filename: pdf.filename, bytes: pdf.bytes);
      } catch (error, stackTrace) {
        FlutterError.reportError(
          FlutterErrorDetails(
            exception: error,
            stack: stackTrace,
            library: 'document PDF upload',
          ),
        );
        if (mounted) {
          _showMessage('The selected PDF could not be uploaded. Please retry.');
        }
      }
    } finally {
      if (mounted) setState(() => _openingPicker = false);
    }
  }

  Future<void> _retry(DocumentRecord document) async {
    try {
      await ref
          .read(documentsControllerProvider.notifier)
          .retryUpload(document);
    } catch (_) {
      if (mounted) {
        _showMessage(
          'The upload could not be retried. Please select the PDF again.',
        );
      }
    }
  }

  Future<void> _remove(DocumentRecord document) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Remove PDF?'),
        content: Text(
          document.status == DocumentStatus.ready
              ? '“${document.name}” will be removed from this library and its '
                    'indexed content will be deleted.'
              : '“${document.name}” will be removed from this device library.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Remove'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _removingDocumentIds.add(document.id));
    try {
      await ref
          .read(documentsControllerProvider.notifier)
          .removeDocument(document);
      if (mounted) _showMessage('Removed ${document.name}.');
    } catch (error, stackTrace) {
      FlutterError.reportError(
        FlutterErrorDetails(
          exception: error,
          stack: stackTrace,
          library: 'document removal',
        ),
      );
      if (mounted) {
        _showMessage('Could not remove ${document.name}. Please try again.');
      }
    } finally {
      if (mounted) setState(() => _removingDocumentIds.remove(document.id));
    }
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final colorScheme = Theme.of(context).colorScheme;
    final library = ref.watch(documentsControllerProvider);
    final isUploading =
        library.value?.any(
          (document) => document.status == DocumentStatus.uploading,
        ) ??
        false;

    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 920),
        child: ListView(
          padding: const EdgeInsets.fromLTRB(24, 28, 24, 36),
          children: [
            Text(
              'YOUR WORKSPACE',
              style: textTheme.labelMedium?.copyWith(
                color: colorScheme.primary,
                fontWeight: FontWeight.w700,
                letterSpacing: 1.2,
              ),
            ),
            const SizedBox(height: 10),
            Text(
              'Documents',
              style: textTheme.headlineMedium?.copyWith(
                fontWeight: FontWeight.w700,
                letterSpacing: -0.7,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Upload a PDF, then ask questions grounded in its pages.',
              style: textTheme.bodyLarge?.copyWith(color: Colors.black54),
            ),
            const SizedBox(height: 22),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(18),
                child: Row(
                  children: [
                    Icon(Icons.phone_android, color: colorScheme.primary),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        'Your library is saved on this device. The current API '
                        'does not yet provide server-side library sync.',
                        style: textTheme.bodySmall,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 22),
            Row(
              children: [
                Expanded(
                  child: Text(
                    'Your library',
                    style: textTheme.titleLarge?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                IconButton(
                  tooltip: 'Refresh library',
                  onPressed: isUploading
                      ? null
                      : () => ref.invalidate(documentsControllerProvider),
                  icon: const Icon(Icons.refresh),
                ),
                FilledButton.icon(
                  onPressed: _openingPicker ? null : _pickAndUpload,
                  icon: _openingPicker
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.add),
                  label: const Text('Add PDF'),
                ),
              ],
            ),
            const SizedBox(height: 12),
            library.when(
              data: (documents) {
                if (documents.isEmpty) return _emptyLibrary(context);
                return Column(
                  children: [
                    for (final document in documents)
                      _DocumentCard(
                        document: document,
                        onRetry: () => _retry(document),
                        onRemove: () => _remove(document),
                        isRemoving: _removingDocumentIds.contains(document.id),
                      ),
                  ],
                );
              },
              loading: () => const Padding(
                padding: EdgeInsets.all(48),
                child: Center(child: CircularProgressIndicator()),
              ),
              error: (error, _) => Card(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    children: [
                      const Icon(Icons.cloud_off_outlined, size: 34),
                      const SizedBox(height: 12),
                      const Text('The on-device library could not be loaded.'),
                      const SizedBox(height: 12),
                      OutlinedButton.icon(
                        onPressed: () =>
                            ref.invalidate(documentsControllerProvider),
                        icon: const Icon(Icons.refresh),
                        label: const Text('Try again'),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _emptyLibrary(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final colorScheme = Theme.of(context).colorScheme;
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 42),
        child: Column(
          children: [
            Container(
              width: 64,
              height: 64,
              decoration: BoxDecoration(
                color: colorScheme.primaryContainer.withValues(alpha: 0.65),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Icon(
                Icons.description_outlined,
                color: colorScheme.primary,
                size: 30,
              ),
            ),
            const SizedBox(height: 18),
            Text(
              'Your library is ready',
              style: textTheme.titleLarge?.copyWith(
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Choose a PDF to start building your document library.',
              textAlign: TextAlign.center,
              style: textTheme.bodyMedium?.copyWith(color: Colors.black54),
            ),
          ],
        ),
      ),
    );
  }
}

class _DocumentCard extends StatelessWidget {
  const _DocumentCard({
    required this.document,
    required this.onRetry,
    required this.onRemove,
    required this.isRemoving,
  });

  final DocumentRecord document;
  final VoidCallback onRetry;
  final VoidCallback onRemove;
  final bool isRemoving;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final colorScheme = Theme.of(context).colorScheme;
    final isReady = document.status == DocumentStatus.ready;
    final isFailed = document.status == DocumentStatus.failed;
    final statusColor = isReady
        ? colorScheme.primary
        : isFailed
        ? colorScheme.error
        : colorScheme.tertiary;

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    color: colorScheme.primaryContainer.withValues(alpha: 0.55),
                    borderRadius: BorderRadius.circular(13),
                  ),
                  child: Icon(
                    Icons.picture_as_pdf_outlined,
                    color: colorScheme.primary,
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        document.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        '${_formatBytes(document.sizeBytes)} · '
                        '${_formatDate(document.uploadedAt)}'
                        '${document.pageCount == null ? '' : ' · ${document.pageCount} pages'}',
                        style: textTheme.bodySmall?.copyWith(
                          color: Colors.black54,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                _StatusLabel(
                  label: switch (document.status) {
                    DocumentStatus.uploading => 'Processing',
                    DocumentStatus.ready => 'Ready',
                    DocumentStatus.failed => 'Failed',
                  },
                  color: statusColor,
                  isLoading: document.status == DocumentStatus.uploading,
                ),
                const SizedBox(width: 4),
                IconButton(
                  tooltip: 'Remove ${document.name} from library',
                  onPressed:
                      isRemoving || document.status == DocumentStatus.uploading
                      ? null
                      : onRemove,
                  icon: isRemoving
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.delete_outline),
                ),
              ],
            ),
            if (document.status == DocumentStatus.uploading) ...[
              const SizedBox(height: 16),
              LinearProgressIndicator(value: document.progress),
              const SizedBox(height: 6),
              Text(
                'Uploading and processing PDF…',
                style: textTheme.bodySmall?.copyWith(color: Colors.black54),
              ),
            ],
            if (isFailed) ...[
              const SizedBox(height: 14),
              Text(
                document.errorMessage ?? 'Upload failed. Please try again.',
                style: textTheme.bodyMedium?.copyWith(color: colorScheme.error),
              ),
              if (document.retryBytes != null) ...[
                const SizedBox(height: 10),
                Align(
                  alignment: Alignment.centerRight,
                  child: TextButton.icon(
                    onPressed: onRetry,
                    icon: const Icon(Icons.refresh),
                    label: const Text('Retry upload'),
                  ),
                ),
              ],
            ],
          ],
        ),
      ),
    );
  }

  static String _formatBytes(int bytes) {
    if (bytes < 1024 * 1024) return '${(bytes / 1024).ceil()} KB';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }

  static String _formatDate(DateTime date) {
    final local = date.toLocal();
    return '${local.day}/${local.month}/${local.year}';
  }
}

class _StatusLabel extends StatelessWidget {
  const _StatusLabel({
    required this.label,
    required this.color,
    required this.isLoading,
  });

  final String label;
  final Color color;
  final bool isLoading;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (isLoading) ...[
              SizedBox(
                width: 12,
                height: 12,
                child: CircularProgressIndicator(strokeWidth: 2, color: color),
              ),
              const SizedBox(width: 6),
            ],
            Text(
              label,
              style: Theme.of(context).textTheme.labelSmall
                  ?.copyWith(color: color, fontWeight: FontWeight.w700),
            ),
          ],
        ),
      ),
    );
  }
}
