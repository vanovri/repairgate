import argparse
import json
from pathlib import Path
from .demo import demo
from .engine import evaluate, ollama_proposer

def main():
    parser = argparse.ArgumentParser(description='Verify repairs in disposable copies. Originals are never edited.')
    sub = parser.add_subparsers(dest='command', required=True)
    sample = sub.add_parser('demo')
    sample.add_argument('--output', type=Path, default=Path('repair-report.json'))
    repair = sub.add_parser('repair')
    repair.add_argument('repo', type=Path)
    repair.add_argument('--holdout', required=True, type=Path)
    repair.add_argument('--task', required=True)
    provider = repair.add_mutually_exclusive_group(required=True)
    provider.add_argument('--proposals', type=Path)
    provider.add_argument('--ollama', metavar='MODEL')
    repair.add_argument('--trust-local-code', action='store_true')
    repair.add_argument('--attempts', type=int, default=3)
    repair.add_argument('--output', type=Path, default=Path('repair-report.json'))
    args = parser.parse_args()
    if args.command == 'demo':
        result = demo()
    else:
        proposals = ollama_proposer(args.repo.resolve(), args.task, args.ollama) if args.ollama else json.loads(args.proposals.read_text())
        result = evaluate(args.repo, args.holdout, proposals, trust_local_code=args.trust_local_code, max_attempts=args.attempts)
        result['provider'] = 'ollama:' + args.ollama if args.ollama else 'recorded proposals'
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'status': result['status'], 'attempts': len(result['attempts']), 'report': str(args.output)}))

if __name__ == '__main__':
    main()
