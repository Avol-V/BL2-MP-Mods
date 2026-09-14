import re
from pathlib import Path
from typing import Any

from mods_base import ENGINE, build_mod, hook, open_in_mod_dir
from unrealsdk.hooks import Block
from unrealsdk.unreal import BoundFunction, UObject, WrappedStruct

__version__: str
__version_info__: tuple[int, ...]

HOTFIX_PATTERN = re.compile(r'^#<hotfix><key>"[^"]*"</key><value>",(.*)"</value><on>$')
TYPED_PATH_PATTERN = re.compile(r"^\w+'(.+)'$")
SKIPPED_PREFIXES = ("say ", "set PlayerInput Bindings", "set Transient.")


def parse_patch(lines: list[str]) -> list[str]:
    commands: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if match := HOTFIX_PATTERN.match(line):
            target, prop, _, value = match.group(1).split(",", 3)
            if typed := TYPED_PATH_PATTERN.match(target):
                target = typed.group(1)
            commands.append(f"set {target} {prop} {value}")
        elif line.lower().startswith("set ") and not line.startswith(SKIPPED_PREFIXES):
            commands.append(line)
    return commands


def load_commands() -> list[str]:
    with open_in_mod_dir(Path(__file__).with_name("cooppatch.txt")) as file:
        return parse_patch(file.readlines())


COMMANDS = load_commands()


def apply_patch() -> None:
    players = ENGINE.GamePlayers
    if not players or players[0] is None or players[0].Actor is None:
        return
    controller = players[0].Actor
    for command in COMMANDS:
        controller.ConsoleCommand(command)


@hook("WillowGame.WillowCoopGameInfo:PickTeam")
def pick_team(
    _obj: UObject,
    args: WrappedStruct,
    _ret: Any,
    _func: BoundFunction,
) -> tuple[type[Block], int]:
    return Block, args.Num


@hook("Engine.GameInfo:PostCommitMapChange")
def map_change(*_: Any) -> None:
    apply_patch()


@hook("WillowGame.FrontendGFxMovie:Start")
def main_menu(*_: Any) -> None:
    apply_patch()


mod = build_mod(
    hooks=[pick_team, map_change, main_menu],
    on_enable=apply_patch,
)
