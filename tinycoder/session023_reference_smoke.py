"""Positive-control tester for teacher's changed response envelopes (Docker)."""
from .session023_contract import REFERENCE_INNER, assemble
from .session021_contract import PUBLIC, holdout
from .session022 import docker_test


def main():
    for phase,cases in (('public',PUBLIC),('holdout',holdout())):
        output=docker_test(assemble(REFERENCE_INNER),cases,phase)
        if not output['integrated']:
            raise RuntimeError('Teacher scaffold does not satisfy contract: '+str(output['failure_reasons']))
    print('Teacher scaffold Docker positive control PASS',flush=True)


if __name__=='__main__':main()
