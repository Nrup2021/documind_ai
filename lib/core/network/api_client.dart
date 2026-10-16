import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

const _configuredApiBaseUrl = String.fromEnvironment('DOCUMIND_API_BASE_URL');

// Web can reach a backend on the same computer through loopback; Android
// emulators must use 10.0.2.2, the emulator's host-machine address.
final apiBaseUrl = _configuredApiBaseUrl.isNotEmpty
    ? _configuredApiBaseUrl
    : kIsWeb
    ? 'http://127.0.0.1:8000'
    : 'http://10.0.2.2:8000';

final apiClientProvider = Provider<Dio>((ref) {
  final client = Dio(
    BaseOptions(
      baseUrl: apiBaseUrl,
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(minutes: 2),
      sendTimeout: const Duration(minutes: 2),
    ),
  );
  ref.onDispose(client.close);
  return client;
});
