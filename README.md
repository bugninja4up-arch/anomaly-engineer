# Anomaly-Engineer

An early-stage, evidence-driven security research assistant with an interactive command-line interface. It supports OpenAI-compatible providers, stores research notes in SQLite, and can load local Markdown skills.

**Current status:** this is a prototype. The request-mutation tool is a mock: it does not send requests or perform fuzzing. The browser, reconnaissance, differential-testing, and JavaScript-analysis modules are placeholders. Do not treat the assistant's hypotheses as confirmed findings.

## Requirements

- Python 3.10 or newer
- An API key for the chosen hosted provider, or a locally running Ollama instance with a suitable model

## Install and run

```bash
git clone https://github.com/bugninja4up-arch/anomaly-engineer.git
cd anomaly-engineer
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
export OPENAI_API_KEY="your-api-key"  # Windows PowerShell: $env:OPENAI_API_KEY="your-api-key"
python main.py
```

Configure the provider, model, scope, and database path in `config.yaml`. For DeepSeek use `DEEPSEEK_API_KEY`; for Ollama configure the local endpoint and model. Never commit real keys, private research notes, or the generated database.

The program stores interactions in `evidence.db` by default. Use only with explicitly authorized targets and follow the applicable program rules. The current testing tool requires explicit approval and is mock-only even after approval.

## License

MIT. See [LICENSE](LICENSE).
