import struct
import json
import argparse
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class Event:
    id: int
    actions: List[int]
    
    audio_file_ids: List[int] = field(default_factory=list)


@dataclass
class Action:
    action_id: int
    target_id: Optional[int]
    action_type: Optional[int]


@dataclass
class Sound:
    sound_id: int
    source_id: Optional[int]


@dataclass
class Container:
    id: int
    children: List[int]
    playlist: List[Dict[str, int]]
    loop_count: Optional[int]
    transition_time: Optional[float]
    transition_mods: Optional[tuple]
    avoid_repeat_count: Optional[int]
    mode: Optional[int]
    flags: Optional[Dict[str, int]]


class BankParser:
    def __init__(self, filename):
        self.filename = filename
        self.events: List[Event] = []
        self.actions: Dict[int, Action] = {}
        self.sounds: Dict[int, Sound] = {}
        self.containers: Dict[int, Container] = {}
        self.audio_files: set[int] = set()
        self.version: int = 0
        
        self.event_audio_map: Dict[str, List[int]] = {}

    def parse(self):
        with open(self.filename, "rb") as f:
            data = f.read()

        pos = self._parse_bkhd(data, 0)

        while pos < len(data):
            chunk_id, chunk_size, pos = self._read_chunk_header(data, pos)

            if chunk_id == b"HIRC":
                pos = self._parse_hirc(data, pos, chunk_size)
            elif chunk_id == b"DIDX":
                pos = self._parse_didx(data, pos, chunk_size)
            else:
                pos += chunk_size

    def _parse_didx(self, data, pos, size):
        end_pos = pos + size
        num_files = size // 12

        for _ in range(num_files):
            if pos + 12 > end_pos:
                break
            file_id = struct.unpack_from("<I", data, pos)[0]
            self.audio_files.add(file_id)
            pos += 12

        return end_pos

    def _read_chunk_header(self, data, pos):
        if pos + 8 > len(data):
            return None, 0, len(data)
        chunk_id = data[pos : pos + 4]
        chunk_size = struct.unpack_from("<I", data, pos + 4)[0]
        return chunk_id, chunk_size, pos + 8

    def _parse_bkhd(self, data, pos):
        if data[pos : pos + 4] == b"AKBK":
            pos += 12
        if data[pos : pos + 4] != b"BKHD":
            raise ValueError("Invalid bank header")
        chunk_size = struct.unpack_from("<I", data, pos + 4)[0]
        self.version = struct.unpack_from("<I", data, pos + 8)[0]
        return pos + 8 + chunk_size

    def _read_object_header(self, data, pos):
        if self.version <= 48:
            obj_type = struct.unpack_from("<I", data, pos)[0]
            obj_size = struct.unpack_from("<I", data, pos + 4)[0]
            return obj_type, obj_size, pos + 8
        else:
            obj_type = data[pos]
            obj_size = struct.unpack_from("<I", data, pos + 1)[0]
            return obj_type, obj_size, pos + 5

    def _parse_hirc(self, data, pos, size):
        end_pos = pos + size
        num_objects = struct.unpack_from("<I", data, pos)[0]
        pos += 4

        for _ in range(num_objects):
            obj_type, obj_data_size, current_obj_data_pos = self._read_object_header(
                data, pos
            )

            if obj_type == 0x04:
                event = self._parse_event(data, current_obj_data_pos, obj_data_size)
                self.events.append(event)
            elif obj_type == 0x03:
                action = self._parse_action(data, current_obj_data_pos, obj_data_size)
                if action is not None:
                    self.actions[action.action_id] = action
            elif obj_type == 0x02:
                sound = self._parse_sound(data, current_obj_data_pos, obj_data_size)
                if sound is not None:
                    self.sounds[sound.sound_id] = sound
            elif obj_type == 0x05:
                container = self._parse_container(
                    data, current_obj_data_pos, obj_data_size
                )
                if container is not None:
                    self.containers[container.id] = container

            pos = current_obj_data_pos + obj_data_size
            if pos > end_pos:
                pos = end_pos
                break

        return end_pos

    def _parse_event(self, data, pos, size) -> Event:
        event_id = struct.unpack_from("<I", data, pos)[0]
        current_pos = pos + 4

        if self.version <= 122:
            action_count = struct.unpack_from("<I", data, current_pos)[0]
            current_pos += 4
        else:
            action_count, bytes_read = self._read_varint(data, current_pos)
            current_pos += bytes_read

        actions = [
            struct.unpack_from("<I", data, current_pos + i * 4)[0]
            for i in range(action_count)
        ]

        return Event(id=event_id, actions=actions)

    def _parse_action(self, data, pos, size) -> Optional[Action]:
        if pos + 4 > len(data):
            return None
        action_id = struct.unpack_from("<I", data, pos)[0]
        current_pos = pos + 4
        action_type = None
        target_id = None

        if current_pos + 2 <= pos + size:
            action_type = struct.unpack_from("<H", data, current_pos)[0]
            current_pos += 2

        if current_pos + 4 <= pos + size:
            target_id = struct.unpack_from("<I", data, current_pos)[0]
            current_pos += 4

        return Action(action_id=action_id, target_id=target_id, action_type=action_type)

    def _parse_sound(self, data, pos, size) -> Optional[Sound]:
        if pos + 4 > len(data):
            return None
        sound_id = struct.unpack_from("<I", data, pos)[0]
        current_pos = pos + 4

        if current_pos + 8 > pos + size:
            return Sound(sound_id=sound_id, source_id=None)

        current_pos += 4
        current_pos += 1

        if current_pos + 4 > pos + size:
            return Sound(sound_id=sound_id, source_id=None)

        source_id = struct.unpack_from("<I", data, current_pos)[0]

        return Sound(sound_id=sound_id, source_id=source_id)

    def _parse_container(self, data, pos, size) -> Optional[Container]:
        if pos + 4 > len(data):
            return None
        container_id = struct.unpack_from("<I", data, pos)[0]
        current_pos = pos + 4

        current_pos = self._parse_node_base_params(data, current_pos, pos + size)

        current_pos, loop_count = self._parse_loop_counts(data, current_pos, pos + size)
        current_pos, transition_time, transition_mods = self._parse_transition_times(
            data, current_pos, pos + size
        )
        current_pos, avoid_repeat_count = self._parse_avoid_repeat_count(
            data, current_pos, pos + size
        )
        current_pos, mode_flags = self._parse_modes_and_flags(
            data, current_pos, pos + size
        )

        if size > 84:
            current_pos += size - 84

        print(
            f"Container ID {container_id} parsing at pos {current_pos} with size {size}"
        )

        children = self._parse_children(data, current_pos, pos + size)
        current_pos += 8 + (4 * len(children))

        playlist = self._parse_playlist(data, current_pos, pos + size)

        return Container(
            id=container_id,
            children=children,
            playlist=playlist,
            loop_count=loop_count,
            transition_time=transition_time,
            transition_mods=transition_mods,
            avoid_repeat_count=avoid_repeat_count,
            mode=mode_flags.get("mode"),
            flags=mode_flags.get("flags"),
        )

    def _parse_loop_counts(self, data, pos, end_pos):
        if pos + 2 > end_pos:
            return pos, None
        loop_count = struct.unpack_from("<h", data, pos)[0]
        pos += 2

        if self.version <= 72:
            return pos, loop_count

        if pos + 4 > end_pos:
            return pos, loop_count

        pos += 4
        return pos, loop_count

    def _parse_transition_times(self, data, pos, end_pos):
        if self.version <= 38:
            if pos + 12 > end_pos:
                return pos, None, None
            transition_time = struct.unpack_from("<i", data, pos)[0]
            pos += 4
            trans_mod_min = struct.unpack_from("<i", data, pos)[0]
            pos += 4
            trans_mod_max = struct.unpack_from("<i", data, pos)[0]
            pos += 4
        else:
            if pos + 12 > end_pos:
                return pos, None, None
            transition_time = struct.unpack_from("<f", data, pos)[0]
            pos += 4
            trans_mod_min = struct.unpack_from("<f", data, pos)[0]
            pos += 4
            trans_mod_max = struct.unpack_from("<f", data, pos)[0]
            pos += 4

        return pos, transition_time, (trans_mod_min, trans_mod_max)

    def _parse_avoid_repeat_count(self, data, pos, end_pos):
        if pos + 2 > end_pos:
            return pos, None
        count = struct.unpack_from("<H", data, pos)[0]
        pos += 2
        return pos, count

    def _parse_modes_and_flags(self, data, pos, end_pos):
        if pos + 3 > end_pos:
            return pos, {"mode": None, "flags": None}

        transition_mode = data[pos]
        pos += 1
        random_mode = data[pos]
        pos += 1
        mode = data[pos]
        pos += 1

        flags = None
        if self.version <= 89:
            if pos + 5 <= end_pos:
                flags = {
                    "_bIsUsingWeight": data[pos],
                    "bResetPlayListAtEachPlay": data[pos + 1],
                    "bIsRestartBackward": data[pos + 2],
                    "bIsContinuous": data[pos + 3],
                    "bIsGlobal": data[pos + 4],
                }
                pos += 5
        else:
            if pos + 1 > end_pos:
                flags = None
            else:
                bitvector = data[pos]
                pos += 1
                flags = {
                    "_bIsUsingWeight": (bitvector >> 0) & 1,
                    "bResetPlayListAtEachPlay": (bitvector >> 1) & 1,
                    "bIsRestartBackward": (bitvector >> 2) & 1,
                    "bIsContinuous": (bitvector >> 3) & 1,
                    "bIsGlobal": (bitvector >> 4) & 1,
                }

        return pos, {"mode": mode, "flags": flags}

    def _parse_node_base_params(self, data, pos, end_pos):
        return pos

    def _parse_children(self, data, pos, end_pos):
        if pos + 4 > end_pos:
            return []
        num_children = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        children = []
        for _ in range(num_children):
            if pos + 4 > end_pos:
                break
            child_id = struct.unpack_from("<I", data, pos)[0]
            children.append(child_id)
            pos += 4
        return children

    def _parse_playlist(self, data, pos, end_pos):
        if self.version <= 38:
            if pos + 4 > end_pos:
                return []
            playlist_count = struct.unpack_from("<I", data, pos)[0]
            pos += 4
        else:
            if pos + 2 > end_pos:
                return []
            playlist_count = struct.unpack_from("<H", data, pos)[0]
            pos += 2

        playlist_items = []
        for _ in range(playlist_count):
            if pos + 4 > end_pos:
                break
            item_id = struct.unpack_from("<I", data, pos)[0]
            pos += 4
            if self.version <= 56:
                if pos + 1 > end_pos:
                    break
                weight = data[pos]
                pos += 1
            else:
                if pos + 4 > end_pos:
                    break
                weight = struct.unpack_from("<i", data, pos)[0]
                pos += 4

            playlist_items.append({"id": item_id, "weight": weight})

        return playlist_items

    def _read_varint(self, data, pos):
        value = 0
        bytes_read = 0
        while True:
            byte = data[pos]
            pos += 1
            bytes_read += 1
            value = (value << 7) | (byte & 0x7F)
            if not (byte & 0x80):
                break
        return value, bytes_read

    def link_audio_to_events(self):
        for event in self.events:
            linked_audio_ids = set()
            for target_id in event.actions:
                self._process_event_reference(target_id, linked_audio_ids)
            
            event.audio_file_ids = list(linked_audio_ids)
            
            if event.audio_file_ids:
                
                self.event_audio_map[str(event.id)] = event.audio_file_ids
            else:
                
                self.event_audio_map[str(event.id)] = []

    def _process_event_reference(self, target_id, linked_audio_ids):
        if target_id in self.actions:
            action = self.actions[target_id]
            if action.action_type == 1027 and action.target_id is not None:
                if action.target_id in self.containers:
                    self._link_container_children(action.target_id, linked_audio_ids)
                elif action.target_id in self.sounds:
                    self._link_sound_to_audio(action.target_id, linked_audio_ids)

        elif target_id in self.containers:
            self._link_container_children(target_id, linked_audio_ids)
        elif target_id in self.sounds:
            self._link_sound_to_audio(target_id, linked_audio_ids)
        else:
            self._link_sound_to_audio(target_id, linked_audio_ids)

    def _link_container_children(self, container_id, linked_audio_ids):
        playlist_children = [
            item["id"] for item in self.containers[container_id].playlist
        ]
        if not playlist_children:
            playlist_children = self.containers[container_id].children
        for child_id in playlist_children:
            self._link_recursive(child_id, linked_audio_ids)

    def _link_recursive(self, obj_id, audio_set):
        if obj_id in self.sounds:
            self._link_sound_to_audio(obj_id, audio_set)
        elif obj_id in self.containers:
            playlist_children = [
                item["id"] for item in self.containers[obj_id].playlist
            ]
            if not playlist_children:
                playlist_children = self.containers[obj_id].children
            for child_id in playlist_children:
                self._link_recursive(child_id, audio_set)

    def _link_sound_to_audio(self, sound_id, audio_set):
        if sound_id in self.sounds:
            source_id = self.sounds[sound_id].source_id
            if source_id in self.audio_files:
                audio_set.add(source_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wwise Soundbank Event Parser")
    parser.add_argument("bank_file", help="Path to .bnk soundbank file")
    parser.add_argument(
        "--format",
        choices=["dec", "hex"],
        default="hex",
        help="Output format for IDs (decimal or hexadecimal)",
    )
    parser.add_argument(
        "--json_output", help="Path to output JSON file (e.g., output.json)"
    )
    args = parser.parse_args()

    parser = BankParser(args.bank_file)
    parser.parse()
    parser.link_audio_to_events()

    print(f"\n{'='*30} PARSING RESULTS {'='*30}\n")
    print(f"Found {len(parser.events)} events:")
    for event in parser.events:
        id_str = str(event.id) if args.format == "dec" else f"0x{event.id:08X}"
        actions_str = (
            ", ".join(str(i) for i in event.actions)
            if args.format == "dec"
            else ", ".join(f"0x{i:08X}" for i in event.actions)
        )

        if not event.audio_file_ids:
            audio_files_str = "No Audio Linked"
        else:
            
            audio_files_str = (
                ", ".join(str(i) for i in event.audio_file_ids)
                if args.format == "dec"
                else ", ".join(f"0x{i:08X}" for i in event.audio_file_ids)
            )

        print(f"Event ID: {id_str}")
        print(f"Action IDs: [{actions_str}]")
        print(f"Associated Audio File IDs: [{audio_files_str}]")
        print("-" * 60)

    if args.json_output:
        
        with open(args.json_output, "w") as f:
            json.dump(parser.event_audio_map, f, indent=4)
