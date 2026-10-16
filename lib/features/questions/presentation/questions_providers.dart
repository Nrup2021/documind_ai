import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/api_failure.dart';
import '../data/api_questions_repository.dart';
import '../domain/question_answer.dart';
import '../domain/questions_repository.dart';

final questionsRepositoryProvider = Provider<QuestionsRepository>((ref) {
  return ApiQuestionsRepository(ref.watch(apiClientProvider));
});

final questionControllerProvider =
    NotifierProvider<QuestionController, QuestionState>(QuestionController.new);

class ChatTurn {
  const ChatTurn({
    required this.question,
    this.answer,
    this.errorMessage,
    this.isLoading = false,
  });

  final String question;
  final QuestionAnswer? answer;
  final String? errorMessage;
  final bool isLoading;

  ChatTurn copyWith({
    QuestionAnswer? answer,
    String? errorMessage,
    bool clearError = false,
    bool? isLoading,
  }) {
    return ChatTurn(
      question: question,
      answer: answer ?? this.answer,
      errorMessage: clearError ? null : errorMessage ?? this.errorMessage,
      isLoading: isLoading ?? this.isLoading,
    );
  }
}

class QuestionState {
  const QuestionState({
    this.documentId,
    this.turns = const [],
    this.isSending = false,
  });

  final String? documentId;
  final List<ChatTurn> turns;
  final bool isSending;
}

class QuestionController extends Notifier<QuestionState> {
  @override
  QuestionState build() => const QuestionState();

  void selectDocument(String? documentId) {
    if (state.documentId == documentId) return;
    state = QuestionState(documentId: documentId);
  }

  Future<void> ask({
    required String documentId,
    required String question,
  }) async {
    final normalized = question.trim();
    if (normalized.isEmpty) {
      throw const ApiFailure(
        code: 'validation_error',
        message: 'Enter a question first.',
      );
    }
    if (normalized.length > 2000) {
      throw const ApiFailure(
        code: 'validation_error',
        message: 'Questions must be 2,000 characters or fewer.',
      );
    }
    if (state.isSending) return;

    final previousTurns = state.documentId == documentId ? state.turns : [];
    final turnIndex = previousTurns.length;
    state = QuestionState(
      documentId: documentId,
      turns: [
        ...previousTurns,
        ChatTurn(question: normalized, isLoading: true),
      ],
      isSending: true,
    );
    await _send(documentId, normalized, turnIndex);
  }

  Future<void> retryLast() async {
    final documentId = state.documentId;
    if (state.isSending || documentId == null || state.turns.isEmpty) return;
    final index = state.turns.length - 1;
    final failed = state.turns[index];
    state = QuestionState(
      documentId: documentId,
      turns: [
        ...state.turns.take(index),
        ChatTurn(question: failed.question, isLoading: true),
      ],
      isSending: true,
    );
    await _send(documentId, failed.question, index);
  }

  Future<void> _send(String documentId, String question, int index) async {
    try {
      final answer = await ref.read(questionsRepositoryProvider).ask(
        documentId: documentId,
        question: question,
      );
      _replaceTurn(index, (turn) => turn.copyWith(answer: answer, isLoading: false));
    } on ApiFailure catch (failure) {
      _replaceTurn(
        index,
        (turn) => turn.copyWith(
          errorMessage: failure.message,
          isLoading: false,
        ),
      );
    } catch (error, stackTrace) {
      _replaceTurn(
        index,
        (turn) => turn.copyWith(
          errorMessage: 'The answer could not be loaded. Please retry.',
          isLoading: false,
        ),
      );
      Error.throwWithStackTrace(error, stackTrace);
    } finally {
      state = QuestionState(
        documentId: state.documentId,
        turns: state.turns,
        isSending: false,
      );
    }
  }

  void _replaceTurn(int index, ChatTurn Function(ChatTurn) update) {
    if (index >= state.turns.length) return;
    final turns = [...state.turns];
    turns[index] = update(turns[index]);
    state = QuestionState(
      documentId: state.documentId,
      turns: turns,
      isSending: state.isSending,
    );
  }
}
