"""Pin externally usable source-browser preview URL to an immutable commit."""
from __future__ import annotations

import argparse
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--revision',required=True)
    args=p.parse_args()
    sha=args.revision
    if len(sha)!=40 or any(c not in '0123456789abcdef' for c in sha):
        raise ValueError('Expected full immutable Git SHA')
    url=('https://raw.githack.com/7clan/ai-wieght-optimiization/'+sha+
         '/docs/previews/session022/index.html')
    path=Path('README.md')
    value=path.read_text(encoding='utf-8')
    needle='[View actual model code and static UI snapshot](docs/previews/session022/index.html)'
    if value.count(needle)!=1:raise ValueError('Could not identify Session022 preview link')
    path.write_text(value.replace(needle,'[View actual model code and static UI snapshot]('+url+')'),encoding='utf-8')
    print(url)


if __name__=='__main__':main()
