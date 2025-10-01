from typing import List, Tuple, Dict

from common.api import ExtensionAPI
from common.api import File
from common.utils import add_line_numbers, parse_json
from common.file_type import get_file_type
from common.llm import call_llm


def _format_code_block(content: str) -> str:
    """Wrap content in triple back-tick code-block so the model can read it."""
    return f"```\n{content}\n```"


def get_system_prompt() -> str:
    return """
You are an expert code analyst specializing in static code analysis, symbol resolution, and understanding code structure across programming languages. Your goal is to locate the original declaration or definition of a specific symbol in the provided code, focusing on where it is first introduced or defined, not on subsequent assignments or modifications.

Follow these steps strictly:

1. Analyze file contents to find the declaration or definition of the symbol. This includes variables, functions, classes, properties, attributes, imports, or any other relevant constructs.

2. If the declaration or definition of the symbol is not defined in the current file, check the provided related files' contents one by one.

3. If found in the current file or a related file, output the exact location: filepath, line number(s), and a brief snippet of the definition code. Explain briefly why it matches, emphasizing it's the original definition.

4. If not found in any provided files, analyze imports, references, module structures, or context in the code to infer which files from the project paths list might contain the definition. Suggest the smallest possible list of files (aim for 1-3 if possible, but no more than needed) that are most likely relevant based on import statements, module names, class hierarchies, or symbol patterns. Do not guess randomly—base suggestions on evidence from the code.

5. Output only in JSON format:
* If found: `{"found": true, "location": {"path": "filepath", "line": number, "snippet": "code snippet", "explanation": "explanation"}}`
* If not found: `{"found": false, "suggested_files": ["path1.py", "path2.py"]}` Do not add extra text outside the JSON.

6. Do not make up facts or hallucinate.
""".strip()


def get_prompt(
        current_file: File,
        symbol: str,
        row: int,
        column: int,
        related_files: List[File],
        all_files: List[File],
) -> str:
    related_files = [f'```{get_file_type(f.path)}:{f.path}\n{add_line_numbers(f.get_content())}\n```' for f in related_files]
    all_files = [f'* {f.path}' for f in all_files]
    prompt = f"""
Cursor position: row {row}, column {column}
Symbol at cursor: {symbol}

Current file contents:

```{get_file_type(current_file.path)}:{current_file.path}
{add_line_numbers(current_file.get_content())}
```
""".strip()

    if related_files:
        prompt += '\n\nRelated file contents:\n\n' + '\n\n'.join(related_files)

    if all_files:
        prompt += '\n\nProject file paths:\n\n' + '\n'.join(all_files)

    return prompt


def parse_result(response: str, api: ExtensionAPI, ) -> Tuple[Dict[str, any], List[str]]:
    data = parse_json(api, response)

    if data['found']:
        assert 'suggested_files' not in data, data
        return data['location'], [data['location']['path']]
    else:
        return {}, data['suggested_files']


def extension(api: ExtensionAPI):
    # we allow up to 3 extra passes
    MAX_ITER = 3

    related_files = []  # list(api.opened_files)[:]
    already_seen = {api.current_file.path}
    repo_paths = {f.path: f for f in api.repo_files}

    iteration = 0
    location = None
    while True:
        iteration += 1

        if iteration > MAX_ITER:
            break

        prompt = get_prompt(
            api.current_file,
            api.symbol,
            api.cursor_row,
            api.cursor_column,
            related_files,
            api.repo_files,
        )
        messages = [
            {"role": "system", "content": get_system_prompt()},
            {"role": "user", "content": prompt},
        ]

        api.log(f"Lookup iteration {iteration}: sending {len(related_files)} files")
        raw_response = call_llm(api, 'qwen', messages)
        api.log(raw_response)

        location, suggested_files = parse_result(raw_response, api)

        api.log(
            f"Lookup result {location}, suggested_files: {suggested_files}"
        )

        for f in related_files:
            already_seen.add(f.path)

        suggested_files = [f.strip() for f in suggested_files]
        suggested_files = [f for f in suggested_files if f]
        suggested_files = [f for f in suggested_files if f in repo_paths]
        suggested_files = [f for f in suggested_files if f not in already_seen]

        if suggested_files:
            related_files = [repo_paths[f] for f in suggested_files][:5]
        else:
            break

        if location and location['path'] in already_seen:
            break

    if not location:
        api.log("Could not find")

    api.send_symbol_results('navigation', [
        {
            "file_path": location['path'],
            "line_number": location["line"],
            "excerpt": location['explanation'] + '::' + location['snippet'],
        }])
