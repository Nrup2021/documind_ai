import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../domain/document_record.dart';

abstract interface class DocumentLibraryStore {
  Future<List<DocumentRecord>> load();

  Future<void> save(DocumentRecord document);
}

class SharedPreferencesDocumentLibraryStore implements DocumentLibraryStore {
  static const _key = 'documind.document_library.v1';

  @override
  Future<List<DocumentRecord>> load() async {
    final preferences = await SharedPreferences.getInstance();
    final serialized = preferences.getString(_key);
    if (serialized == null) return [];

    final decoded = jsonDecode(serialized);
    if (decoded is! List) {
      throw const FormatException('Saved document library is not a list.');
    }
    return decoded.map((item) {
      if (item is! Map) {
        throw const FormatException('Saved document entry is invalid.');
      }
      return DocumentRecord.fromJson(Map<String, Object?>.from(item));
    }).toList();
  }

  @override
  Future<void> save(DocumentRecord document) async {
    final preferences = await SharedPreferences.getInstance();
    final documents = await load();
    final updated = [
      document,
      ...documents.where((existing) => existing.id != document.id),
    ];
    final saved = await preferences.setString(
      _key,
      jsonEncode(updated.map((item) => item.toJson()).toList()),
    );
    if (!saved) {
      throw StateError('The document library could not be saved on this device.');
    }
  }
}
