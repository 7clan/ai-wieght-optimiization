"""Execute one Qwen-produced Python function for the Session032 evaluator.

Identical to the Session031 Docker py worker except for the disclosed local
mode: the recycled sandbox has no Docker daemon, so generated Python runs in
an isolated `python3 -I -B` subprocess (no site imports, no bytecode writes)
instead of a container. Nothing else changed.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import sys


def main():
    if not Path('/.dockerenv').is_file() and __import__('os').environ.get(
            'SESSION032_LOCAL_EVAL') != '1':
        raise RuntimeError('Generated Python must run in Docker or disclosed local mode')
    request = json.load(sys.stdin)
    source, payload = request['source'], request['payload']
    if not isinstance(source, str) or len(source) > 40000:
        raise ValueError('Invalid code length')
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError) as exc:
        print(json.dumps({'ok': False, 'syntax_valid': False, 'error': str(exc)}))
        return
    try:
        namespace = {'__name__': '__qwen_generated__'}
        exec(compile(tree, '<generated-python>', 'exec'), namespace)
        result = namespace['summarize'](payload)
        output = json.dumps(result, allow_nan=False)
        print(json.dumps({'ok': True, 'syntax_valid': True, 'value': json.loads(output)}))
    except BaseException as exc:
        print(json.dumps({'ok': False, 'syntax_valid': True,
                          'error': f'{type(exc).__name__}: {exc}'}))


if __name__ == '__main__':
    main()
