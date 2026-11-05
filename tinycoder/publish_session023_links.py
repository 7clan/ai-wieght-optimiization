"""Publish immutable mentor diary + actual code preview links."""
import argparse
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--revision',required=True)
    sha=p.parse_args().revision
    if len(sha)!=40 or any(x not in '0123456789abcdef' for x in sha):
        raise ValueError('Expected immutable 40-character Git SHA')
    root='https://raw.githack.com/7clan/ai-wieght-optimiization/'+sha+'/docs/previews/session023/'
    readme=Path('README.md')
    data=readme.read_text(encoding='utf-8')
    for file in ('mentor.html','index.html'):
        old='(docs/previews/session023/'+file+')'
        if data.count(old)!=1:raise ValueError('Missing exact preview placeholder '+file)
        data=data.replace(old,'('+root+file+')')
    readme.write_text(data,encoding='utf-8')
    print(root+'mentor.html',flush=True)


if __name__=='__main__':main()
