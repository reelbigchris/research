#!/usr/bin/env python3
"""
Parse research-plan.md into tasks.json
"""

import sys
import json
import re


def parse_research_plan(plan_file):
    """Parse research plan markdown into structured tasks"""

    with open(plan_file, 'r') as f:
        content = f.read()

    tasks = []

    # Find all task blocks
    # Pattern: ### Task N: Title
    #          **Agent:** agent-name
    #          **Sources:** ...
    #          **Output:** research/filename.md
    #          **Questions:**
    #          - Question 1
    #          - Question 2

    task_pattern = re.compile(
        r'### Task \d+: (.+?)\n'
        r'\*\*Agent:\*\* (.+?)\n'
        r'\*\*Sources:\*\* (.+?)\n'
        r'\*\*Output:\*\* (.+?)\n'
        r'\*\*Questions:\*\*\n'
        r'((?:- .+?\n)+)',
        re.DOTALL
    )

    for match in task_pattern.finditer(content):
        title = match.group(1).strip()
        agent = match.group(2).strip()
        sources = match.group(3).strip()
        output = match.group(4).strip()
        questions_text = match.group(5).strip()

        # Parse questions
        questions = [
            q.strip('- ').strip()
            for q in questions_text.split('\n')
            if q.strip().startswith('-')
        ]

        tasks.append({
            'title': title,
            'agent': agent,
            'sources': sources,
            'output': output,
            'questions': questions,
            'status': 'pending'
        })

    return tasks


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <research-plan.md> <output.json>")
        sys.exit(1)

    plan_file = sys.argv[1]
    output_file = sys.argv[2]

    try:
        tasks = parse_research_plan(plan_file)

        with open(output_file, 'w') as f:
            json.dump(tasks, f, indent=2)

        print(f"Parsed {len(tasks)} tasks")

    except Exception as e:
        print(f"Error parsing research plan: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
