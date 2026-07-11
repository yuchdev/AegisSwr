{
  "version": 1,
  "hooks": {
    "SessionStart": [
      {
        "type": "command",
        "command": "python .github/hooks/session_start.py",
        "cwd": ".",
        "timeoutSec": 20
      }
    ],
    "UserPromptSubmit": [
      {
        "type": "command",
        "command": "python .github/hooks/user_prompt_submit.py",
        "cwd": ".",
        "timeoutSec": 5
      }
    ],
    "PreToolUse": [
      {
        "type": "command",
        "matcher": "Bash",
        "command": "python .github/hooks/guard_bash.py",
        "cwd": ".",
        "timeoutSec": 5
      },
      {
        "type": "command",
        "matcher": "Write|Edit",
        "command": "python .github/hooks/secret_scan.py",
        "cwd": ".",
        "timeoutSec": 15
      }
    ],
    "PostToolUse": [
      {
        "type": "command",
        "matcher": "Write|Edit",
        "command": "python .github/hooks/post_edit_format.py",
        "cwd": ".",
        "timeoutSec": 60
      },
      {
        "type": "command",
        "matcher": "Write|Edit",
        "command": "python .github/hooks/doc_link_check.py",
        "cwd": ".",
        "timeoutSec": 60
      }
    ],
    "PostToolUseFailure": [
      {
        "type": "command",
        "matcher": "Bash",
        "command": "python .github/hooks/github_audit.py",
        "cwd": ".",
        "timeoutSec": 10
      }
    ],
    "Stop": [
      {
        "type": "command",
        "command": "python .github/hooks/run_tests.py",
        "cwd": ".",
        "timeoutSec": 900
      },
      {
        "type": "command",
        "command": "python .github/hooks/doc_link_check.py",
        "cwd": ".",
        "timeoutSec": 120
      }
    ],
    "SessionEnd": [
      {
        "type": "command",
        "command": "python .github/hooks/session_end.py",
        "cwd": ".",
        "timeoutSec": 5
      }
    ],
    "ErrorOccurred": [
      {
        "type": "command",
        "command": "python .github/hooks/error_occurred.py",
        "cwd": ".",
        "timeoutSec": 10
      }
    ]
  }
}
