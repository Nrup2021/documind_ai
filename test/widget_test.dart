import 'package:documind_ai/app/app.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Future<void> pumpApp(WidgetTester tester) {
    return tester.pumpWidget(const ProviderScope(child: DocuMindApp()));
  }

  testWidgets('opens the document library by default', (tester) async {
    await pumpApp(tester);

    expect(find.text('Documents'), findsOneWidget);
    expect(find.text('Your library is ready'), findsOneWidget);
    expect(find.text('Library'), findsOneWidget);
    expect(find.text('Chat'), findsOneWidget);
  });

  testWidgets('navigates to chat and back to the library', (tester) async {
    await pumpApp(tester);

    await tester.tap(find.text('Chat').last);
    await tester.pumpAndSettle();

    expect(find.text('Chat with your documents'), findsOneWidget);
    expect(
      find.text('Your document conversations will appear here.'),
      findsOneWidget,
    );

    await tester.tap(find.text('Library').last);
    await tester.pumpAndSettle();

    expect(find.text('Your library is ready'), findsOneWidget);
  });

  testWidgets('shows a navigation rail on wide layouts', (tester) async {
    tester.view.physicalSize = const Size(1200, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await pumpApp(tester);

    expect(find.byType(NavigationRail), findsOneWidget);
    expect(find.byType(NavigationBar), findsNothing);
  });
}
