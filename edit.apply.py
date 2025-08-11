import re
import time
from typing import List, Dict

from openai import OpenAI

from common.api import ExtensionAPI
from common.diff_lines import get_matches
from common.secrets import OPEN_ROUTER_TOKEN, OPEN_ROUTER_URL

META_TAG = 'metadata'


def call_llm(api: ExtensionAPI, model: str, messages: List[Dict[str, str]], content: str):
    start_time = time.time()

    client = OpenAI(api_key=OPEN_ROUTER_TOKEN, base_url=OPEN_ROUTER_URL)

    response = client.chat.completions.create(
        model=model,
        messages=messages,
    )
    merged_code = response.choices[0].message.content
    matches, cleaned_patch = get_matches(content, merged_code)

    api.apply_diff(cleaned_patch, matches)

    elapsed = time.time() - start_time
    meta_data = f'time: {elapsed:.2f}s'
    api.log(f'patch apply completed {meta_data}')


def extension(api: ExtensionAPI):
    prompt = api.prompt.rstrip()  # no left strip for indentation

    if api.edit_file.path == api.current_file.path:
        content = api.current_file.get_content()
    else:
        try:
            content = api.edit_file.get_content()
        except FileNotFoundError:
            content = ''
    api.log(f'patch generation started ...')
    api.log(f'{api.edit_file.path}/{api.current_file.path}')

    model = 'morph/morph-v3-fast'
    instruction = ''

    messages = [
        {
            "role": "user",
            "content": f"<instructions>{instruction}</instructions>\n<code>f{content}</code>\n<update>{prompt}</update>"
        }
    ]

    call_llm(api, model, messages, content)
