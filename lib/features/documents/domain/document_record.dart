import 'dart:typed_data';

enum DocumentStatus { uploading, ready, failed }

class DocumentRecord {
  const DocumentRecord({
    required this.id,
    required this.name,
    required this.sizeBytes,
    required this.uploadedAt,
    required this.status,
    this.pageCount,
    this.chunkCount,
    this.progress,
    this.errorMessage,
    this.retryBytes,
  });

  final String id;
  final String name;
  final int sizeBytes;
  final DateTime uploadedAt;
  final DocumentStatus status;
  final int? pageCount;
  final int? chunkCount;
  final double? progress;
  final String? errorMessage;
  final Uint8List? retryBytes;

  DocumentRecord copyWith({
    String? id,
    DocumentStatus? status,
    int? pageCount,
    int? chunkCount,
    double? progress,
    String? errorMessage,
    bool clearError = false,
    Uint8List? retryBytes,
  }) {
    return DocumentRecord(
      id: id ?? this.id,
      name: name,
      sizeBytes: sizeBytes,
      uploadedAt: uploadedAt,
      status: status ?? this.status,
      pageCount: pageCount ?? this.pageCount,
      chunkCount: chunkCount ?? this.chunkCount,
      progress: progress ?? this.progress,
      errorMessage: clearError ? null : errorMessage ?? this.errorMessage,
      retryBytes: retryBytes ?? this.retryBytes,
    );
  }

  Map<String, Object?> toJson() => {
    'id': id,
    'name': name,
    'size_bytes': sizeBytes,
    'uploaded_at': uploadedAt.toIso8601String(),
    'page_count': pageCount,
    'chunk_count': chunkCount,
  };

  factory DocumentRecord.fromJson(Map<String, Object?> json) {
    return DocumentRecord(
      id: json['id']! as String,
      name: json['name']! as String,
      sizeBytes: json['size_bytes']! as int,
      uploadedAt: DateTime.parse(json['uploaded_at']! as String),
      status: DocumentStatus.ready,
      pageCount: json['page_count'] as int?,
      chunkCount: json['chunk_count'] as int?,
    );
  }
}
