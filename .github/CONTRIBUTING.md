# Contributing to Satellite Controller

Everybody is invited and welcome to contribute to Satellite Controller. Even if you are not a developer, perhaps you would like to help with the documentation? If you are a developer and have a feature that isn't supported yet, why not spend some time and help to integrate it?

The process is straight-forward.

- Fork the repository.
- Write the code for your feature or fix.
- Set up the test environment: `uv venv -p 3.14 && uv pip install -r requirements_lint.txt`.
- Ensure tests pass and linting succeeds (`./script/tests` and `./script/lint`, `./script/lint --auto` formats the code).
- Describe user-visible changes in [docs/behavior.md](../docs/behavior.md) and keep it in line with the code.
- Write docstrings in Sphinx style with `:param:`.
- Create a Pull Request against the `main` branch and tick exactly one type of change in the template.

## Feature suggestions

If you want to suggest a new feature, please open an issue and describe what you would like to happen in which situation.

## Issue Tracker

If you want to report an issue, please create an issue on the repository. Please add the debug log of `custom_components.satellite_controller` (see the README).

## AI Policy

Please read the [AI policy](AI_POLICY.md) before submitting AI-assisted contributions. The TLDR: AI tools are allowed, but a human is responsible and must review and understand every change. Autonomous agents and unreviewed AI output will be rejected.
