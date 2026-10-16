class Citation {
  const Citation({required this.pageNumber, required this.excerpt});

  final int pageNumber;
  final String excerpt;
}

class QuestionAnswer {
  const QuestionAnswer({
    required this.outcome,
    required this.answer,
    required this.citations,
  });

  final String outcome;
  final String answer;
  final List<Citation> citations;

  bool get hasInsufficientEvidence => outcome == 'insufficient_evidence';
}
