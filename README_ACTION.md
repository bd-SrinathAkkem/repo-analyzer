# AI Repository Analyzer GitHub Action

A GitHub Action that uses AI to analyze repositories and detect technologies, architecture patterns, and build commands.

## Usage

### Basic Usage

```yaml
name: Analyze Repository
on: [push]

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: bd-SrinathAkkem/repo-analyzer@v1
        with:
          repo_url: 'https://github.com/facebook/react'
          ai_api_key: ${{ secrets.AI_API_KEY }}
```

### Advanced Usage

```yaml
name: Advanced Repository Analysis
on:
  workflow_dispatch:
    inputs:
      repository_url:
        description: 'Repository URL to analyze'
        required: true

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: bd-SrinathAkkem/repo-analyzer@v1
        id: analyzer
        with:
          repo_url: ${{ inputs.repository_url }}
          model: 'claude-sonnet'
          ai_api_key: ${{ secrets.AI_API_KEY }}
          github_token: ${{ secrets.GITHUB_TOKEN }}

      - name: Use Analysis Results
        run: |
          echo "Architecture: ${{ steps.analyzer.outputs.architecture }}"
          echo "Technologies: ${{ steps.analyzer.outputs.technologies }}"
          echo "Build commands: ${{ steps.analyzer.outputs.build_commands }}"
```

## Inputs

| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `repo_url` | GitHub repository URL to analyze | Yes | - |
| `model` | AI model to use (claude-sonnet, gpt-4, gemini-pro) | No | `claude-sonnet` |
| `config_file` | Path to configuration file | No | - |
| `ai_api_key` | Universal AI API key for all providers (Claude, OpenAI, Gemini) | Yes | - |
| `github_token` | GitHub token for private repositories | No | `${{ github.token }}` |

## Outputs

| Output | Description |
|--------|-------------|
| `analysis_file` | Path to the generated analysis JSON file |
| `technologies` | Comma-separated list of detected technologies |
| `architecture` | Detected architecture type |
| `build_commands` | JSON object containing extracted build commands |

## API Keys

You need one universal AI API key that works with all providers:

### Universal AI API Key
1. Get your API key from your AI provider:
   - Anthropic (Claude): [Anthropic Console](https://console.anthropic.com/)
   - OpenAI (GPT): [OpenAI Platform](https://platform.openai.com/)
   - Google (Gemini): [Google AI Studio](https://makersuite.google.com/)
2. Add as repository secret: `AI_API_KEY`

Note: The same `AI_API_KEY` will work with all supported models (claude-sonnet, gpt-4, gemini-pro, etc.)

## Example Workflow Files

### Simple Analysis
```yaml
name: Analyze Current Repository
on: [push]

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: bd-SrinathAkkem/repo-analyzer@v1
        with:
          repo_url: ${{ github.server_url }}/${{ github.repository }}
          ai_api_key: ${{ secrets.AI_API_KEY }}
```

### Multi-Repository Analysis
```yaml
name: Analyze Multiple Repositories
on: workflow_dispatch

jobs:
  analyze:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        repo:
          - 'https://github.com/facebook/react'
          - 'https://github.com/vuejs/vue'
          - 'https://github.com/angular/angular'
    steps:
      - uses: bd-SrinathAkkem/repo-analyzer@v1
        with:
          repo_url: ${{ matrix.repo }}
          model: 'claude-sonnet'
          ai_api_key: ${{ secrets.AI_API_KEY }}
```

### Analysis with Artifact Upload
```yaml
name: Analyze and Store Results
on: [workflow_dispatch]

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: bd-SrinathAkkem/repo-analyzer@v1
        id: analyzer
        with:
          repo_url: 'https://github.com/facebook/react'
          ai_api_key: ${{ secrets.AI_API_KEY }}

      - name: Upload Results
        uses: actions/upload-artifact@v4
        with:
          name: analysis-results
          path: ${{ steps.analyzer.outputs.analysis_file }}
```

## Publishing Your Action

1. Create a new repository for your action
2. Copy all the files from this directory
3. Create a release with a version tag (e.g., `v1.0.0`)
4. Use in workflows with: `uses: your-username/your-action-name@v1`

## Development

To test the action locally:

```bash
# Build the Docker image
docker build -t repo-analyzer-action .

# Run the action
docker run --rm \
  -e REPO_URL="https://github.com/facebook/react" \
  -e MODEL="claude-sonnet" \
  -e AI_API_KEY="your-api-key" \
  repo-analyzer-action
```