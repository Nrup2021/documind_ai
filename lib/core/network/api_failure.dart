import 'package:dio/dio.dart';

class ApiFailure implements Exception {
  const ApiFailure({
    required this.code,
    required this.message,
    this.statusCode,
  });

  final String code;
  final String message;
  final int? statusCode;

  factory ApiFailure.fromDio(DioException exception) {
    final responseData = exception.response?.data;
    if (responseData is Map) {
      final error = responseData['error'];
      if (error is Map) {
        final code = error['code'];
        final message = error['message'];
        if (code is String && message is String) {
          return ApiFailure(
            code: code,
            message: message,
            statusCode: exception.response?.statusCode,
          );
        }
      }
    }

    if (exception.response == null) {
      return const ApiFailure(
        code: 'network_error',
        message:
            'Unable to reach DocuMind. Check your connection and API address, then retry.',
      );
    }

    return ApiFailure(
      code: 'request_failed',
      message:
          'The server could not complete this request. Please retry in a moment.',
      statusCode: exception.response?.statusCode,
    );
  }

  @override
  String toString() => message;
}
