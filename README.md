# BNK-Tools
A command-line utility for working with Wwise soundbank (`.bnk`) files - a common audio middleware format used in game development.

## Features
- Extract individual or all audio files from soundbanks
- Replace audio files within soundbanks
- Inspect soundbank contents and metadata
- Analyze event-to-audio relationships and hierarchies

## Installation

Download the latest release from the [Releases](../../releases) page, or run the Python scripts directly if you have Python 3.7+ installed.

## Usage

### Info
Displays the IDs of the audio files in the `.bnk` file.

**Example Usage:**
```bash
SoundBankPatcher.exe info YourBNKFileName.bnk
```

| Option | Description | Example Usage |
|--------|-------------|----------------|
| `--export-catalog` | Exports info (IDs and file sizes) to a JSON file | ```bash SoundBankPatcher.exe info --export-catalog YourJSONFileName.json YourBNKFileName.bnk``` |

---

### Extract
Extracts a specific `.wem` audio file from a `.bnk` file.

**Example Usage:**
```bash
SoundBankPatcher.exe extract YourBNKFileName.bnk audioID
```

| Option | Description | Example Usage |
|--------|-------------|----------------|
| `--output` | Specifies output directory and filename | ```bash SoundBankPatcher.exe extract YourBNKFileName.bnk audioID --output YourExtractedAudio.wem``` |

---

### Extract-All
Extracts **all** `.wem` audio files from a `.bnk` file.

**Example Usage:**
```bash
SoundBankPatcher.exe extract-all YourBNKFileName.bnk OutputDirectory
```

---

### Replace-One
Replaces a single `.wem` audio in a specified `.bnk` file.

**Example Usage:**
```bash
SoundBankPatcher.exe replace-one YourBNKFileName.bnk audioID YourReplacingWemFile.wem --output OutputBNK.bnk
```

---

### Patch
Replaces **multiple** `.wem` audio files in a `.bnk` file using a JSON map.

**JSON Structure:**
```json
{
    "IDFromBNKFile1": "AudioToReplaceWith1.wem",
    "IDFromBNKFile2": "AudioToReplaceWith2.wem"
}
```

**Example Usage:**
```bash
SoundBankPatcher.exe patch YourBNKFileName.bnk YourJson.json -w Path/To/Your/WEM/FILES --output OutputBNK.bnk
```

| Option | Description | Example Usage |
|--------|-------------|----------------|
| `--big-endian` | Uses big-endian instead of little-endian | ```bash SoundBankPatcher.exe patch YourBNKFileName.bnk YourJson.json -w Path/To/Your/WEM/Files --output OutputBNK.bnk --big-endian``` |

---

## Additional Tools

### Event Parser
Analyzes the relationship between events, actions, containers, and audio files within a soundbank. This tool helps you understand which audio files are triggered by specific events, including complex hierarchies with containers and playlists.

**Features:**
- Maps event IDs to their associated audio file IDs
- Resolves complex container hierarchies and playlists
- Handles recursive sound structures
- Supports multiple Wwise versions

**Example Usage:**
```bash
python event_parser.py YourBNKFileName.bnk
```

**With JSON output:**
```bash
python event_parser.py YourBNKFileName.bnk --json_output event_mapping.json
```

**Output format options:**
```bash
# Decimal IDs (default: hexadecimal)
python event_parser.py YourBNKFileName.bnk --format dec
```

**Sample Output:**
```
Event ID: 0x12345678
Action IDs: [0x11111111, 0x22222222]
Associated Audio File IDs: [0xAAAAAAAA, 0xBBBBBBBB]
```

The JSON output provides a clean mapping structure:
```json
{
    "305419896": [2952748896, 2952748897],
    "305419897": [2952748898]
}
```

---

## Technical Details

This tool parses Wwise soundbank binary format, including:
- BKHD (Bank Header) sections
- DIDX (Data Index) sections containing audio file references
- DATA sections containing the actual audio data
- HIRC (Hierarchy) sections for event/action/sound relationships

The event parser additionally handles:
- Event → Action → Sound/Container relationships
- Recursive container hierarchies
- Playlist resolution
- Multiple Wwise format versions (pre and post v89, v122, etc.)

## Use Cases
- Game modding and audio customization
- Audio analysis and research
- Working with Wwise audio pipelines
- Understanding game audio event structures
- Batch audio replacement workflows

## Requirements
- Python 3.7+ (if running scripts directly)
- No external dependencies for core functionality
- PyYAML for YAML config support (optional)

## License
MIT License
