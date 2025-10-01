from common.api import ExtensionAPI
from common.llm import call_llm
from common.utils import extract_code_block
from common.file_type import get_file_type
from common.formatting import markdown_section, markdown_code_block

SYSTEM_PROMPT = """
You are an expert programmer assisting a colleague in updating code in an existing file.

Your colleague will give you:
* Relevant code files if applicable
* Current code file contents
* A segment of code marked by `UPDATE_START` and `UPDATE_END`.
* The start of the segment usually will contain a comment describing the update he wants.

Your task:
* Suggest an update for the code block
* Match the file's indentation, style, and conventions
* Wrap your response in triple backticks with the appropriate language identifier.
* Only provide the code within the code block, no explanations outside of it
* If the segment started with a instructive comment about the code change, do not include the same comment in your suggestion. If applicable, suggest new descriptive comment(s) about the suggested code.
""".strip()

def make_prompt(api: ExtensionAPI, prefix, suffix, block):
    context = []

    current_file_type = get_file_type(api.current_file.path)
    other_files = api.opened_files
    if other_files:
        api.push_meta(f'Relevant files: {", ".join(f.path for f in other_files)}')

        opened_files = [f'Path: `{f.path}`\n\n' + markdown_code_block(f.get_content()) for f in other_files]
        context.append(markdown_section("Relevant files", "\n\n".join(opened_files)))


    prompt = '\n\n'.join(context)

    prompt += '\n\n# Current File\n\n```' + current_file_type + '\n' + prefix + f'\n#UPDATE_START\n{block}\n#UPDATE_END'

    if suffix.strip():
        prompt += '\n' + suffix

    prompt += '\n```'

    api.log(prompt)

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ]


def extension(api: ExtensionAPI):
    api.notify('Generating inline completion...')

    # Get file content and cursor position
    lines = api.current_file.get_content().splitlines()
    selection_lines = api.selection.splitlines()

    if not selection_lines:
        api.notify('', 'No selection')
        return

    idx = None
    for i in range(len(lines) - len(selection_lines)):
        found = True
        for j in range(len(selection_lines)):
            if lines[i + j] != selection_lines[j]:
                found = False
                break
        if found:
            idx = i
            break

    if idx is None:
        api.notify(api.selection, 'Could not find selection')
        return

    messages = make_prompt(api,
                           '\n'.join(lines[:idx]),
                           '\n'.join(lines[idx+len(selection_lines):]),
                           '\n'.join(selection_lines))

    model = 'qwen'
    api.start_chat()

    content = call_llm(api, model, messages)
    content = extract_code_block(content)

    # need to press tab to accept and esc to reject
    api.apply_inline_completion(content)
