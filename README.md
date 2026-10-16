# DocuMind

DocuMind is a Flutter app foundation for exploring a personal document library
and document-focused chat, with a separate Python backend foundation.

## Current scope

- Riverpod app bootstrap and GoRouter navigation.
- Responsive library and chat shell with presentation-only empty states.
- FastAPI backend with a health endpoint and typed API contracts.
- No document processing or AI functionality is implemented yet.

## Development

Run the app with `flutter run`. Format and verify changes with:

```sh
dart format .
flutter analyze
flutter test
```

For backend setup and API details, see the [backend README](./backend/README.md).
