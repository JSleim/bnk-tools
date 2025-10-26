# BNK-Tools
   A command-line utility for working with Wwise soundbank (`.bnk`) files - a common audio middleware format used in game development.
   
   ## Features
   - Extract individual or all audio files from soundbanks
   - Replace audio files within soundbanks
   - Inspect soundbank contents and metadata
   
# Usage

## Info

Displays the IDs of the audio files in the `.bnk` file.

**Example Usage:**
```bash
SoundBankPatcher.exe info YourBNKFileName.bnk
```

| Option | Description | Example Usage |
|--------|-------------|----------------|
| `--export-catalog` | Exports info (IDs and file sizes) to a JSON file | ```bash SoundBankPatcher.exe info --export-catalog YourJSONFileName.json YourBNKFileName.bnk``` |

---

## Extract

Extracts a specific `.wem` audio file from a `.bnk` file.

**Example Usage:**
```bash
SoundBankPatcher.exe extract YourBNKFileName.bnk audioID
```

| Option | Description | Example Usage |
|--------|-------------|----------------|
| `--output` | Specifies output directory and filename | ```SoundBankPatcher.exe extract YourBNKFileName.bnk audioID --output YourExtractedAudio.wem``` |

---

## Extract-All

Extracts **all** `.wem` audio files from a `.bnk` file.

**Example Usage:**
```bash
SoundBankPatcher.exe extract-all YourBNKFileName.bnk OutputDirectory
```

---

## Replace-One

Replaces a single `.wem` audio in a specified `.bnk` file.

**Example Usage:**
```bash
SoundBankPatcher.exe replace-one YourBNKFileName.bnk audioID YourReplacingWemFile.wem --output OutputBNK.bnk
```

---

## Patch

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
| `--big-endian` | Uses big-endian instead of little-endian | ```SoundBankPatcher.exe patch YourBNKFileName.bnk YourJson.json -w Path/To/Your/WEM/Files --output OutputBNK.bnk --big-endian``` |


