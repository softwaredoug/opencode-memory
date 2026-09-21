import pandas as pd
from pathlib import Path
from pydantic import BaseModel
from collections.abc import Mapping, Sequence
from typing import Any, Iterator
from datetime import datetime, timedelta, timezone


TELEMETRY_PATH = Path.home() / ".local" / "share" / "opencode"

MIN_UTC_TIMESTAMP = datetime(1970, 6, 1, tzinfo=timezone.utc)


class ChatEvent(BaseModel):
    """A single user interaction and subsequent tool calls, etc."""

    system_prompt: str
    user_prompt: str
    tool_calls: list[dict]

    session_id: str
    prompt_id: str


def _get_nested(data: Mapping[str, Any], path: tuple[str | int, ...]) -> Any:
    current: Any = data

    for key in path:
        if isinstance(key, int) and isinstance(current, Sequence):
            if key < 0 or key >= len(current):
                return None
            current = current[key]
        elif isinstance(key, str) and isinstance(current, Mapping):
            if key not in current:
                return None
            current = current[key]
        else:
            return None
    return current


def _extract_session_id(event_dict: dict) -> str | None:
    """Extract the session ID from a telemetry event dictionary."""
    paths = (
        ("session_id",),
        ("event", "properties", "sessionID"),
        ("input", "sessionID"),
    )
    for path in paths:
        value = _get_nested(event_dict, path)
        if value is not None:
            return value
    return None


def _extract_prompt_id(event_dict: dict) -> str:
    return _get_nested(event_dict, ("output", "message", "id"))


def _text_payload(event_dict: dict) -> str | None:
    paths = (
        ("output", "parts", "text"),  # For prompts
        ("output", "parts", 0, "text"),  # For tool calls
        ("event", "properties", "part", "text"),  # For assistant text
        ("output", "output"),  # For tool calls
    )
    for path in paths:
        value = _get_nested(event_dict, path)
        if value is not None:
            return value
    return None


def _tool_names(event_dict: dict) -> str | None:
    """For anything with tool name, extract it as a series."""
    return _get_nested(event_dict, ('input', 'tool'))


def _command(event_dict: dict) -> str | None:
    """For anything with a command, extract it as a series."""
    paths = (
        ("input", "args", "command"),
        ("output", "args", "command")
    )

    for path in paths:
        value = _get_nested(event_dict, path)
        if value is not None:
            return value


def _agent_md_text(event_dict: dict | float) -> str | None:
    if not isinstance(event_dict, dict):
        return None
    try:
        return f"""Project: {event_dict['path']},
AGENTS.md:\n
{event_dict['agents_md']}"""
    except KeyError:
        return None


def _hydrate_system_prompts(telemetry: pd.DataFrame) -> pd.DataFrame:
    """Extract system prompts from telemetry."""
    mask = telemetry['event_type'] == 'system_prompt'
    project_metadata = telemetry.get('project_metadata', pd.Series(index=telemetry.index))
    telemetry.loc[mask, 'text'] = project_metadata[mask].fillna({}).apply(_agent_md_text)
    return telemetry


def _session_id_project_paths(telemetry: pd.DataFrame) -> pd.Series:
    """Get a dict from session id -> project path for all sessions in the telemetry."""
    mask = telemetry['event_type'] == 'system_prompt'
    system_metadata = telemetry[mask].groupby('session_id')['project_metadata'].first()

    def extract_path(project_metadata: dict | float) -> Path | None:
        if not isinstance(project_metadata, dict):
            return None
        path_str = project_metadata.get('path')
        if path_str is None:
            return None
        return Path(path_str)

    system_meta_to_path = system_metadata.map(extract_path)
    return system_meta_to_path


def _hydrate(telemetry: pd.DataFrame) -> pd.DataFrame:
    """Fill in missing session IDs by propagating the last known session ID."""
    telemetry = telemetry.sort_values(by='timestamp').reset_index(drop=True)
    telemetry['session_id'] = telemetry['payload'].apply(_extract_session_id)
    telemetry['prompt_id'] = telemetry['payload'].apply(_extract_prompt_id)
    telemetry['tool_name'] = telemetry['payload'].apply(_tool_names)
    telemetry['command'] = telemetry['payload'].apply(_command)
    telemetry['text'] = telemetry['payload'].apply(_text_payload)
    telemetry['text'] = telemetry['text'].fillna(telemetry['command'])

    sess_id_to_path = _session_id_project_paths(telemetry)
    telemetry['project_path'] = telemetry['session_id'].map(sess_id_to_path)

    # Forward fill prompt_id down
    telemetry['prompt_id'] = telemetry.groupby("session_id")['prompt_id'].ffill()
    telemetry = _hydrate_system_prompts(telemetry)

    # But system prompt starts a session, that is its own prompt_id
    return telemetry


def _parse_telemetry(telemetry: pd.DataFrame,
                     events=['system_prompt', 'prompt', 'tool_result', 'assistant_text']) -> pd.DataFrame:
    """Parse the telemetry JSONL file into a DataFrame."""
    telemetry = _hydrate(telemetry)
    telemetry = telemetry[telemetry['event_type'].isin(events)]
    assert isinstance(telemetry, pd.DataFrame)

    return telemetry


def _load_telemetry(path: Path,
                    last_index_time: datetime = MIN_UTC_TIMESTAMP) -> pd.DataFrame | None:
    """Load telemetry that we care to process."""
    # Go back a day to get any overtlaps
    if not path.exists():
        raise FileNotFoundError(f"Telemetry file not found at {path}")

    last_index_time = last_index_time - timedelta(days=1)
    first_day_formatted = last_index_time.strftime("%Y-%m-%d")
    dataframes = []
    last_index_time = last_index_time.astimezone(timezone.utc)
    for telemetry_path in path.glob("*.jsonl"):
        basename = telemetry_path.stem
        timestamp_yyyymmdd = basename.replace('-telemetry', '')
        try:
            timestamp = datetime.strptime(timestamp_yyyymmdd, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if timestamp_yyyymmdd == first_day_formatted:
            df = pd.read_json(telemetry_path, lines=True)
            dataframes.append(df)
        elif timestamp >= last_index_time:
            df = pd.read_json(telemetry_path, lines=True)
            dataframes.append(df)
    return pd.concat(dataframes, ignore_index=True) if dataframes else None


def last_modified_time(path: Path | str = TELEMETRY_PATH) -> datetime | None:
    """Get the last modified time of the latest telemetry file."""
    path = Path(path)
    latest_file = None
    latest_timestamp = None

    for telemetry_path in path.glob("*.jsonl"):
        basename = telemetry_path.stem
        timestamp_yyyymmdd = basename.replace('-telemetry', '')
        try:
            timestamp = datetime.strptime(timestamp_yyyymmdd, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        if latest_timestamp is None or timestamp > latest_timestamp:
            latest_timestamp = timestamp
            latest_file = telemetry_path

    if latest_file is not None:
        return datetime.fromtimestamp(latest_file.stat().st_mtime,
                                      tz=timezone.utc)
    return None


def prompt_docs(path:
                Path | str = TELEMETRY_PATH,
                last_index_time: datetime | None = None) -> Iterator[dict]:
    """Flattened prompt text as a single search document."""
    path = Path(path)
    if last_index_time is None:
        last_index_time = MIN_UTC_TIMESTAMP
    telemetry = _load_telemetry(path=path, last_index_time=last_index_time)
    if telemetry is None or telemetry.empty:
        return []
    telemetry = _parse_telemetry(telemetry,
                                 events=['system_prompt', 'prompt', 'assistant_text', 'tool_result', 'tool_call'])

    # System prompts give metadata about the repo, task etc through AGENTS.md files
    # and what-not
    # Even though the system repeats them, I logically make one per session
    system_prompts = telemetry[telemetry['event_type'] == 'system_prompt'].groupby('session_id').first()
    for session_id, row in system_prompts.iterrows():
        yield {
            "id": f"{session_id}_system_prompt",
            "transcript": row['text'] if pd.notna(row['text']) else "",
            "prompt_id": f"{session_id}_system_prompt",  # intentional
            "session_id": session_id,
            "prompt_timestamp": row['timestamp'],
            "project_path": row['project_path'] if pd.notna(row['project_path']) else None,
            "is_system_prompt": True
        }

    telemetry = telemetry[telemetry['event_type'] != 'system_prompt']
    prompt_ids = telemetry['prompt_id'].unique()
    for prompt_id in prompt_ids:
        prompt_telemetry = telemetry[telemetry['prompt_id'] == prompt_id]
        if len(prompt_telemetry) == 0:
            continue
        session_id = prompt_telemetry['session_id'].iloc[0]
        # Concat all text to get text for the prompt document
        docs_to_index = prompt_telemetry['text'].drop_duplicates().dropna().index
        prefix_pre_event_type = {
            "prompt": "User:\n",
            "assistant_text": "Assistant:\n",
            "tool_result": "Tool result:\n",
            "tool_call": "Tool call:\n"
        }

        text = ""
        for _, row in prompt_telemetry.loc[docs_to_index].iterrows():
            event_text = row['text'].replace("\n", " ").strip()
            if event_text:
                text += prefix_pre_event_type.get(row['event_type'], "") + row['text'] + "\n\n"

        doc = {
            "id": f"{session_id}_{prompt_id}",
            "transcript": text,
            "prompt_id": prompt_id,
            "session_id": session_id,
            "prompt_timestamp": prompt_telemetry['timestamp'].min().to_pydatetime().replace(tzinfo=timezone.utc),
            "project_path": prompt_telemetry['project_path'].iloc[0] if pd.notna(prompt_telemetry['project_path'].iloc[0]) else None,
            "is_system_prompt": False
        }
        yield doc
