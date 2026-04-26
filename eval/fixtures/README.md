# Test Fixtures

This directory contains mock hardware and test data for evaluation.

## Structure

- `scenario.json` — Test scenario definitions (input/expected output pairs)
- `capture.png` — Sample images for face recognition tests
- `record.wav` — Sample audio clips for voice recognition tests
- `enrollments/` — Biometric enrollment data (faces, voiceprints)

## Usage

Test fixtures are used to:
1. Standardize inputs across evaluation runs
2. Ensure reproducible results
3. Test without requiring actual hardware

## Adding Fixtures

1. Create a new file in appropriate subdirectory
2. Name with descriptive label (e.g., `chinese_voice_001.wav`)
3. Update `manifest.json` with metadata
4. Document the fixture in this README

## Notes

- Audio files should be WAV format, 16kHz, mono, 16-bit
- Images should be JPEG or PNG, 640x480 minimum
- JSON files should follow schema in `eval/cases/core/*.yaml`
