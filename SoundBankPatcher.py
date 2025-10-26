import struct
import json
import yaml
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Union
import argparse
import sys
import logging
from contextlib import contextmanager


@dataclass
class AudioEntry:
    id: int
    offset: int
    size: int
    data: Optional[bytes] = None
    replacement_path: Optional[Path] = None

    @property
    def final_size(self) -> int:
        if self.replacement_path:
            return self.replacement_path.stat().st_size
        return self.size


class SoundbankSection:
    def __init__(self, magic: str, data: bytes):
        self.magic = magic
        self.data = data

    def serialize(self, endian: str = '<') -> bytes:
        header = self.magic.encode('ascii')
        length = struct.pack(f'{endian}I', len(self.data))
        return header + length + self.data


class WwiseSoundbank:

    def __init__(self, file_path: Path, endian: str = '<'):
        self.file_path = file_path
        self.endian = endian
        self.sections: Dict[str, SoundbankSection] = {}
        self.audio_entries: List[AudioEntry] = []
        self.metadata = {}

        self.logger = logging.getLogger(__name__)
        self._load_soundbank()

    def _load_soundbank(self):
        self.logger.info(f"Loading soundbank: {self.file_path}")

        with open(self.file_path, 'rb') as stream:
            self._parse_sections(stream)
            self._extract_audio_catalog(stream)
            self._preload_audio_data(stream)

    def _parse_sections(self, stream):
        while True:
            magic_bytes = stream.read(4)
            if len(magic_bytes) < 4:
                break

            magic = magic_bytes.decode('ascii', errors='ignore')
            if magic not in ['BKHD', 'DIDX', 'DATA']:

                stream.seek(-4, 1)
                break

            size = struct.unpack(f'{self.endian}I', stream.read(4))[0]

            if magic == 'DATA':

                self._data_offset = stream.tell()
                self._data_size = size
                stream.seek(size, 1)
                break
            else:
                data = stream.read(size)
                self.sections[magic] = SoundbankSection(magic, data)

        self._trailing_data = stream.read()

    def _extract_audio_catalog(self, stream):
        if 'DIDX' not in self.sections:
            raise ValueError("No audio index (DIDX) found in soundbank")

        didx_data = self.sections['DIDX'].data
        entry_count = len(didx_data) // 12

        self.logger.info(f"Found {entry_count} audio entries")

        for i in range(entry_count):
            offset = i * 12
            audio_id, file_offset, file_size = struct.unpack(
                f'{self.endian}III', didx_data[offset:offset + 12]
            )

            entry = AudioEntry(
                id=audio_id,
                offset=file_offset,
                size=file_size
            )
            self.audio_entries.append(entry)

    def _preload_audio_data(self, stream):
        self.logger.info("Preloading audio data...")

        for entry in self.audio_entries:
            stream.seek(self._data_offset + entry.offset)
            entry.data = stream.read(entry.size)

    @contextmanager
    def batch_operation(self):
        self.logger.info("Starting batch operation")
        try:
            yield self
        finally:
            self.logger.info("Batch operation completed")

    def replace_audio(self, audio_id: int, replacement_file: Path):
        entry = self.find_audio_entry(audio_id)
        if not entry:
            raise KeyError(f"Audio ID {audio_id} not found in soundbank")

        if not replacement_file.exists():
            raise FileNotFoundError(f"Replacement file not found: {replacement_file}")

        entry.replacement_path = replacement_file
        self.logger.debug(f"Queued replacement: ID {audio_id} -> {replacement_file}")

    def find_audio_entry(self, audio_id: int) -> Optional[AudioEntry]:
        return next((entry for entry in self.audio_entries if entry.id == audio_id), None)

    def get_audio_catalog(self) -> Dict[int, int]:
        return {entry.id: entry.size for entry in self.audio_entries}

    def export_audio(self, audio_id: int, output_path: Path):
        entry = self.find_audio_entry(audio_id)
        if not entry:
            raise KeyError(f"Audio ID {audio_id} not found")

        with open(output_path, 'wb') as f:
            f.write(entry.data)

        self.logger.info(f"Exported audio ID {audio_id} to {output_path}")

    def _rebuild_audio_index(self) -> bytes:
        didx_data = bytearray()
        current_offset = 0

        for entry in self.audio_entries:
            didx_data.extend(struct.pack(f'{self.endian}III',
                                         entry.id, current_offset, entry.final_size))
            current_offset += entry.final_size

        return bytes(didx_data)

    def _serialize_audio_data(self) -> bytes:
        audio_stream = bytearray()

        for entry in self.audio_entries:
            if entry.replacement_path:

                with open(entry.replacement_path, 'rb') as f:
                    audio_stream.extend(f.read())
            else:

                audio_stream.extend(entry.data)

        return bytes(audio_stream)

    def save(self, output_path: Path):
        self.logger.info(f"Saving modified soundbank to: {output_path}")

        with open(output_path, 'wb') as f:

            if 'BKHD' in self.sections:
                f.write(self.sections['BKHD'].serialize(self.endian))


            updated_didx = self._rebuild_audio_index()
            didx_section = SoundbankSection('DIDX', updated_didx)
            f.write(didx_section.serialize(self.endian))


            audio_data = self._serialize_audio_data()
            data_section = SoundbankSection('DATA', audio_data)
            f.write(data_section.serialize(self.endian))


            f.write(self._trailing_data)

        self.logger.info("Soundbank saved successfully")

    def get_statistics(self) -> Dict:
        replacements = sum(1 for entry in self.audio_entries if entry.replacement_path)
        original_size = sum(entry.size for entry in self.audio_entries)
        new_size = sum(entry.final_size for entry in self.audio_entries)

        return {
            'total_audio_files': len(self.audio_entries),
            'replacements_queued': replacements,
            'original_data_size': original_size,
            'new_data_size': new_size,
            'size_change': new_size - original_size
        }

    def export_all_audio(self, output_dir: Path):
        output_dir.mkdir(parents=True, exist_ok=True)
        for entry in self.audio_entries:
            output_path = output_dir / f"{entry.id}.wem"
            with open(output_path, 'wb') as f:
                f.write(entry.data)
            self.logger.info(f"Exported audio ID {entry.id} to {output_path}")


class ConfigurationLoader:

    @staticmethod
    def load_replacements(config_file: Path, wem_directory: Optional[Path] = None) -> Dict[int, Path]:
        suffix = config_file.suffix.lower()

        with open(config_file, 'r') as f:
            if suffix == '.json':
                data = json.load(f)
            elif suffix in ['.yml', '.yaml']:
                data = yaml.safe_load(f)
            else:
                raise ValueError(f"Unsupported config format: {suffix}")

        replacements = {}
        for k, v in data.items():
            audio_id = int(k)
            
            if isinstance(v, (int, float)):
                
                file_path_str = f"{int(v)}.wem"
                logging.warning(f"Coercing numeric value '{v}' for ID {audio_id} to file path '{file_path_str}'. "
                                "It's recommended to provide string paths in the config.")
            elif isinstance(v, str):
                file_path_str = v
            else:
                raise TypeError(f"Value for audio ID {audio_id} must be a string file path or numeric ID, but got {type(v).__name__}: {v}")

            file_path = Path(file_path_str)


            
            if not file_path.is_absolute():
                if wem_directory and (wem_directory / file_path).exists():
                    file_path = wem_directory / file_path
                elif (config_file.parent / file_path).exists():
                    file_path = config_file.parent / file_path
                else:
                    if wem_directory:
                        file_path = wem_directory / file_path
                    else:
                        file_path = config_file.parent / file_path

            replacements[audio_id] = file_path

        return replacements

    @staticmethod
    def convert_json_to_yaml(input_path: Path, output_path: Path):
        logging.info(f"Converting JSON '{input_path}' to YAML '{output_path}'")
        with open(input_path, 'r') as json_file:
            data = json.load(json_file)

        processed_data = {}
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, (int, float)):
                    
                    processed_data[str(k)] = f"{int(v)}.wem"
                else:
                    processed_data[str(k)] = str(v) 
        else:
            processed_data = data 

        with open(output_path, 'w') as yaml_file:
            yaml.safe_dump(processed_data, yaml_file, indent=2, sort_keys=False)
        logging.info("Conversion complete.")

    @staticmethod
    def convert_yaml_to_json(input_path: Path, output_path: Path):
        logging.info(f"Converting YAML '{input_path}' to JSON '{output_path}'")
        with open(input_path, 'r') as yaml_file:
            data = yaml.safe_load(yaml_file) 
        
        processed_data = {}
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, (int, float)):
                    
                    processed_data[str(k)] = f"{int(v)}.wem"
                else:
                    processed_data[str(k)] = str(v) 
        else:
            processed_data = data 

        with open(output_path, 'w') as json_file:
            json.dump(processed_data, json_file, indent=2)
        logging.info("Conversion complete.")


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(levelname)s: %(message)s'
    )


def patch_soundbank(bnk_file: Path, config_file: Path, output_file: Path, wem_directory: Optional[Path] = None, **kwargs):

    logging.info(f"Patching soundbank: {bnk_file} with config: {config_file}")
    replacements = ConfigurationLoader.load_replacements(config_file, wem_directory)


    missing_files = []
    for audio_id, replacement_path in replacements.items():
        if not replacement_path.exists():
            missing_files.append(f"Audio ID {audio_id}: {replacement_path}")

    if missing_files:
        print("WARNING: The following replacement files were not found:")
        for missing in missing_files:
            print(f"  - {missing}")

        response = input("Continue anyway? (y/N): ").lower()
        if response != 'y':
            print("Operation cancelled.")
            return


    soundbank = WwiseSoundbank(bnk_file, endian='<' if not kwargs.get('big_endian') else '>')


    with soundbank.batch_operation():
        successful_replacements = 0
        for audio_id, replacement_path in replacements.items():
            try:
                if replacement_path.exists():
                    soundbank.replace_audio(audio_id, replacement_path)
                    successful_replacements += 1
                else:
                    print(f"Skipping Audio ID {audio_id}: File not found - {replacement_path}")
            except Exception as e:
                print(f"Error replacing Audio ID {audio_id}: {e}")


    stats = soundbank.get_statistics()
    print(f"\nSoundbank Statistics:")
    print(f"  Total audio files: {stats['total_audio_files']}")
    print(f"  Files being replaced: {stats['replacements_queued']}")
    print(f"  Successful replacements: {successful_replacements}")
    print(f"  Size change: {stats['size_change']:+d} bytes")

    if wem_directory:
        print(f"  WEM directory used: {wem_directory}")


    soundbank.save(output_file)


def main():
    parser = argparse.ArgumentParser(
        description='Wwise BNK Patcher',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')


    patch_parser = subparsers.add_parser('patch', help='Apply audio replacements')
    patch_parser.add_argument('bnk_file', type=Path, help='Input BNK soundbank file')
    patch_parser.add_argument('config_file', type=Path, help='Replacement config (JSON/YAML)')
    patch_parser.add_argument('-o', '--output', type=Path, help='Output file path')
    patch_parser.add_argument('-w', '--wem-dir', type=Path, help='Directory containing WEM replacement files')
    patch_parser.add_argument('--big-endian', action='store_true', help='Use big-endian byte order')


    info_parser = subparsers.add_parser('info', help='Show soundbank information')
    info_parser.add_argument('bnk_file', type=Path, help='BNK soundbank file')
    info_parser.add_argument('--export-catalog', type=Path, help='Export audio catalog to JSON')


    extract_parser = subparsers.add_parser('extract', help='Extract audio files')
    extract_parser.add_argument('bnk_file', type=Path, help='BNK soundbank file')
    extract_parser.add_argument('audio_id', type=int, help='Audio ID to extract')
    extract_parser.add_argument('-o', '--output', type=Path, required=False, help='Output file path (defaults to {audio_id}.wem)')

    extract_all_parser = subparsers.add_parser('extract-all', help='Extract all audio files')
    extract_all_parser.add_argument('bnk_file', type=Path, help='BNK soundbank file')
    extract_all_parser.add_argument('output_dir', type=Path, help='Directory to extract all audio files to')

    replace_one_parser = subparsers.add_parser('replace-one', help='Replace a single audio entry')
    replace_one_parser.add_argument('bnk_file', type=Path, help='Input BNK soundbank file')
    replace_one_parser.add_argument('audio_id', type=int, help='Audio ID to replace')
    replace_one_parser.add_argument('wem_file', type=Path, help='Replacement WEM file')
    replace_one_parser.add_argument('-o', '--output', type=Path, help='Output file path')

    
    json_to_yaml_parser = subparsers.add_parser('json-to-yaml', help='Convert a JSON file to YAML, attempting to fix numeric paths.')
    json_to_yaml_parser.add_argument('input_file', type=Path, help='Path to the input JSON file')
    json_to_yaml_parser.add_argument('-o', '--output', type=Path, help='Output YAML file path (defaults to input_file with .yaml extension)')

    yaml_to_json_parser = subparsers.add_parser('yaml-to-json', help='Convert a YAML file to JSON, attempting to fix numeric paths.')
    yaml_to_json_parser.add_argument('input_file', type=Path, help='Path to the input YAML file')
    yaml_to_json_parser.add_argument('-o', '--output', type=Path, help='Output JSON file path (defaults to input_file with .json extension)')
    


    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    setup_logging(args.verbose)

    try:
        if args.command == 'patch':
            output_file = args.output or args.bnk_file.parent / f"patched_{args.bnk_file.name}"
            patch_soundbank(args.bnk_file, args.config_file, output_file,
                            wem_directory=args.wem_dir, big_endian=args.big_endian)

        elif args.command == 'info':
            soundbank = WwiseSoundbank(args.bnk_file)
            catalog = soundbank.get_audio_catalog()
            stats = soundbank.get_statistics()

            print(f"Soundbank: {args.bnk_file}")
            print(f"Audio files: {stats['total_audio_files']}")
            print(f"Total data size: {stats['original_data_size']} bytes")
            print(f"Audio IDs: {sorted(catalog.keys())}")

            if args.export_catalog:
                with open(args.export_catalog, 'w') as f:
                    json.dump(catalog, f, indent=2)
                print(f"Catalog exported to: {args.export_catalog}")

        elif args.command == 'extract':
            soundbank = WwiseSoundbank(args.bnk_file)
            output_path = args.output or Path(f"{args.audio_id}.wem")
            soundbank.export_audio(args.audio_id, output_path)
            print(f"Audio ID {args.audio_id} extracted to: {output_path}")

        elif args.command == 'extract-all':
            soundbank = WwiseSoundbank(args.bnk_file)
            soundbank.export_all_audio(args.output_dir)
            print(f"All audio files extracted to: {args.output_dir}")

        elif args.command == 'replace-one':
            output_file = args.output or args.bnk_file.parent / f"replaced_{args.audio_id}_{args.bnk_file.name}"
            soundbank = WwiseSoundbank(args.bnk_file)
            soundbank.replace_audio(args.audio_id, args.wem_file)
            soundbank.save(output_file)
            print(f"Audio ID {args.audio_id} replaced and saved to: {output_file}")

        
        elif args.command == 'json-to-yaml':
            output_file = args.output or args.input_file.with_suffix('.yaml')
            if not args.input_file.exists():
                raise FileNotFoundError(f"Input file not found: {args.input_file}")
            ConfigurationLoader.convert_json_to_yaml(args.input_file, output_file)

        elif args.command == 'yaml-to-json':
            output_file = args.output or args.input_file.with_suffix('.json')
            if not args.input_file.exists():
                raise FileNotFoundError(f"Input file not found: {args.input_file}")
            ConfigurationLoader.convert_yaml_to_json(args.input_file, output_file)
        

    except FileNotFoundError as e:
        logging.error(f"File not found: {e}. Please check the path and try again.")
        sys.exit(1)
    except KeyError as e:
        logging.error(f"Missing data or invalid ID: {e}")
        sys.exit(1)
    except ValueError as e:
        logging.error(f"Invalid input or data format: {e}")
        sys.exit(1)
    except TypeError as e:
        logging.error(f"Type error in configuration: {e}. Ensure replacement file paths are strings or valid numeric IDs for automatic conversion.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
