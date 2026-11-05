"""Pin the model-generated app preview to the real git commit containing it."""
from __future__ import annotations

import argparse
from pathlib import Path
import re


def publish(path, revision):
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Full commit SHA required')
    contents=path.read_text(encoding='utf-8')
    old='[View Qwen\'s actual UI preview and generated source](docs/previews/session021/index.html)'
    new=("[View Qwen's actual UI preview and generated source]"
         f"(https://raw.githack.com/7clan/ai-wieght-optimiization/{revision}/docs/previews/session021/index.html)")
    if contents.count(old)!=1:
        raise ValueError('Expected one unpinned preview link')
    path.write_text(contents.replace(old,new),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--revision',required=True)
    parser.add_argument('--readme',type=Path,default=Path('README.md'))
    args=parser.parse_args()
    publish(args.readme,args.revision)


if __name__=='__main__':
    main()
