from typing import List
import typing

from common.api import ExtensionAPI, File
from common.llm import call_llm
from common.prompts import get_system_prompt
from common.terminal import get_terminal_snapshot
from common.utils import parse_prompt
from common.formatting import markdown_section, markdown_code_block, add_line_comment


def build_context(api: 'ExtensionAPI', *,
                  current_file: File,
                  other_files: List['File'] = None,
                  selection: str = None,
                  terminal: str = None,
                  cursor: typing.Tuple[int, int] = None,
                  file_list: List['File'] = None) -> str:
    """Builds the context string from the current file and selection."""
    context = []

    if file_list:
        repo_files = [f'{f.path}`' for f in file_list]
        context.append(markdown_section("List of Files", "\n".join(repo_files)))

    if other_files:
        api.push_meta(f'Relevant files: {", ".join(f.path for f in other_files)}')

        opened_files = [f'Path: `{f.path}`\n\n' + markdown_code_block(f.get_content()) for f in other_files]
        context.append(markdown_section("Relevant files", "\n\n".join(opened_files)))

    if current_file:
        api.push_meta(f'Current file: {current_file.path}')
        context.append(
            markdown_section("Current File",
                            f"Path: `{current_file.path}`\n\n" +
                            markdown_code_block(current_file.get_content()))
        )


    if terminal:
        if len(terminal) > 40_000:
            pre_text = f'Terminal output is {len(terminal)} chars long, and here is the last 40k chars of it.\n\n'
        else:
            pre_text = f'Terminal output is {len(terminal)} chars long.'

        context.append(
            markdown_section("Terminal output",
                            f"{pre_text}\n\n" + markdown_code_block(terminal[-40000:]))
        )

    if selection and selection.strip():
        context.append(
            markdown_section("Selection",
                            "This is the code snippet that I'm referring to\n\n" +
                            markdown_code_block(selection))
        )

    if cursor:
        block = current_file.get_content().split('\n')
        assert len(block) > cursor[0], f'Cursor row {cursor[0]} block of length {len(block)}'
        prefix = block[cursor[0] - 3: cursor[0]]
        line = block[cursor[0]]
        line = add_line_comment(current_file, line, f'Cursor is here: `{line[:cursor[1]].strip()}`')
        suffix = block[cursor[0] + 1:cursor[0] + 4]

        block = prefix + [line] + suffix

        context.append(markdown_section("Cursor position",
                                            markdown_code_block('\n'.join(block))))

    return "\n\n".join(context)


def extension(api: ExtensionAPI):
    """Main extension function that handles chat interactions with the AI assistant."""

    command, model, prompt = parse_prompt(api)
    
    api.push_meta(f'model: {model}, command: {command}')

    if command == '':
        api.push_block('meta', f'Without context')
        messages = [
            {'role': 'system', 'content': get_system_prompt(model)},
            *[m.to_dict() for m in api.chat_history],
            {'role': 'user', 'content': prompt},
        ]
    elif command == 'here':
        context = build_context(api,
                                other_files=api.opened_files,
                                selection=api.selection,
                                file_list=api.repo_files,
                                current_file=api.current_file,
                                terminal=get_terminal_snapshot(api),
                                cursor=(api.cursor_row, api.cursor_column),
                                )

        api.push_block('meta', f'With context: {len(context) :,},'
                               f' selection: {bool(api.selection)}')
        api.log(context)
        messages = [
            {'role': 'system', 'content': get_system_prompt(model)},
            {'role': 'user', 'content': context},
            *[m.to_dict() for m in api.chat_history],
            {'role': 'user', 'content': prompt},
        ]
    elif command == 'context':
        context = build_context(api,
                                other_files=api.opened_files,
                                selection=api.selection,
                                file_list=api.repo_files,
                                current_file=api.current_file,
                                terminal=get_terminal_snapshot(api),
                                cursor=(api.cursor_row - 1, api.cursor_column - 1),
                                )
        api.push_block('meta', f'With context: {len(context) :,},'
                               f' selection: {bool(api.selection)}')
        messages = [
            {'role': 'system', 'content': get_system_prompt(model)},
            {'role': 'user', 'content': context},
            *[m.to_dict() for m in api.chat_history],
            {'role': 'user', 'content': prompt},
        ]
    else:
        raise ValueError(f'Unknown command: {command}')

    # api.log(f'messages {len(messages)}')
    api.log(f'prompt {api.prompt}')

    call_llm(api, model, messages)