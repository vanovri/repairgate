import argparse
import json
from pathlib import Path
from .lab import CASES, run_case, run_lab
from .engine import evaluate, ollama_proposer

def main():
    parser = argparse.ArgumentParser(description='Verify repairs in disposable copies. Originals are never edited.')
    sub = parser.add_subparsers(dest='command', required=True)
    sample = sub.add_parser('demo')
    sample.add_argument('--case', choices=tuple(CASES), default='bill-splitter')
    sample.add_argument('--output', type=Path, default=Path('repair-report.json'))
    lab = sub.add_parser('lab', help='Replay all bundled synthetic regression cases')
    lab.add_argument('--output', type=Path, default=Path('regression-lab-report.json'))
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
        result = run_case(args.case)
    elif args.command == 'lab':
        result = run_lab()
    else:
        proposals = ollama_proposer(args.repo.resolve(), args.task, args.ollama) if args.ollama else json.loads(args.proposals.read_text())
        result = evaluate(args.repo, args.holdout, proposals, trust_local_code=args.trust_local_code, max_attempts=args.attempts)
        result['provider'] = 'ollama:' + args.ollama if args.ollama else 'recorded proposals'
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    summary = result['summary'] if args.command == 'lab' else {'attempts': len(result['attempts'])}
    print(json.dumps({'status': result['status'], **summary, 'report': str(args.output)}))
    if args.command == 'lab' and result['status'] != 'passed':
        raise SystemExit(1)

if __name__ == '__main__':
    main()
