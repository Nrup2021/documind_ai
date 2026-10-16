import 'package:dio/dio.dart';

import '../../../core/network/api_failure.dart';
import '../domain/question_answer.dart';
import '../domain/questions_repository.dart';

class ApiQuestionsRepository implements QuestionsRepository {
  const ApiQuestionsRepository(this._client);

  final Dio _client;

  @override
  Future<QuestionAnswer> ask({
    required String documentId,
    required String question,
  }) async {
    try {
      final response = await _client.post<Map<String, dynamic>>(
        '/v1/documents/$documentId/questions',
        data: {'question': question},
      );
      final body = response.data;
      final outcome = body?['outcome'];
      final answer = body?['answer'];
      final rawCitations = body?['citations'];
      if ((outcome != 'answered' && outcome != 'insufficient_evidence') ||
          answer is! String ||
          rawCitations is! List) {
        throw const ApiFailure(
          code: 'invalid_response',
          message: 'The API returned an invalid answer response.',
        );
      }

      final citations = <Citation>[];
      for (final item in rawCitations) {
        if (item is! Map ||
            item['page_number'] is! int ||
            item['excerpt'] is! String ||
            (item['page_number'] as int) <= 0 ||
            (item['excerpt'] as String).isEmpty) {
          throw const ApiFailure(
            code: 'invalid_response',
            message: 'The API returned an invalid source citation.',
          );
        }
        citations.add(
          Citation(
            pageNumber: item['page_number'] as int,
            excerpt: item['excerpt'] as String,
          ),
        );
      }
      return QuestionAnswer(
        outcome: outcome as String,
        answer: answer,
        citations: citations,
      );
    } on DioException catch (error) {
      throw ApiFailure.fromDio(error);
    }
  }
}
