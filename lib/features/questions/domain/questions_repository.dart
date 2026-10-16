import 'question_answer.dart';

abstract interface class QuestionsRepository {
  Future<QuestionAnswer> ask({
    required String documentId,
    required String question,
  });
}
