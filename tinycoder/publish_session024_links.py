"""Pin actual Qwen repair preview links to an immutable commit."""
import argparse
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--revision',required=True)
    sha=p.parse_args().revision
    if len(sha)!=40 or any(c not in '0123456789abcdef' for c in sha):
        raise ValueError('Expected exact immutable Git SHA')
    url='https://raw.githack.com/7clan/ai-wieght-optimiization/'+sha+'/docs/previews/session024/'
    target=Path('README.md')
    content=target.read_text(encoding='utf-8')
    for file in ('index.html','mentor.html'):
        old='(docs/previews/session024/'+file+')'
        if content.count(old)!=1:raise ValueError('Cannot locate Session024 preview')
        content=content.replace(old,'('+url+file+')')
    target.write_text(content,encoding='utf-8')


if __name__=='__main__':main()
