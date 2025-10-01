from common.api import ExtensionAPI
from common.llm import call_llm
from common.utils import extract_code_block
from common.file_type import get_file_type
from common.formatting import markdown_section, markdown_code_block

SYSTEM_PROMPT = """
You are an expert programmer assisting a colleague in adding code to an existing file.

Your colleague will give you:
* Relevant code files if applicable
* Current code file contents
* Insertion point marked by `INSERT_YOUR_CODE` inside the current code file
* If applicable, some contents that should be part of the line/block that should be added (usually a prefix).

Your task:
* Provide a suggestion for the next line or block of code
* Match the file's indentation, style, and conventions
* Wrap your response in triple backticks with the appropriate language identifier.
* Only provide the completion text within the code block, no explanations outside of it
* Do NOT repeat the text that's already before the current line
""".strip()

def make_prompt(api: ExtensionAPI, prefix, suffix, next_line):
    context = []

    current_file_type = get_file_type(api.current_file.path)
    other_files = api.opened_files
    if other_files:
        api.push_meta(f'Relevant files: {", ".join(f.path for f in other_files)}')

        opened_files = [f'Path: `{f.path}`\n\n' + markdown_code_block(f.get_content()) for f in other_files]
        context.append(markdown_section("Relevant files", "\n\n".join(opened_files)))


    prompt = '\n\n'.join(context)

    prompt += '\n\n# Current File\n\n```' + current_file_type + '\n' + prefix + '\n#INSERT_YOUR_CODE'

    if suffix.strip():
        prompt += '\n' + suffix

    prompt += '\n```'

    if next_line.strip():
        prompt += f'\n\nThe next line begins with `{next_line}`.'

    api.log(prompt)

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ]


def extension(api: ExtensionAPI):
    api.notify('Generating inline completion...')

    # Get file content and cursor position
    lines = api.current_file.get_content().splitlines()
    idx = api.cursor_row - 1
    current_line = lines[idx][:api.cursor_column - 1]

    messages = make_prompt(api,
                           '\n'.join(lines[:idx]),
                           '\n'.join(lines[idx+1:]),
                           current_line)

    model = 'qwen'
    api.start_chat()

    content = call_llm(api, model, messages)
    content = extract_code_block(content)

    if content.startswith(current_line):
        content = content[len(current_line):]

    # need to press tab to accept and esc to reject
    api.apply_inline_completion(content)
