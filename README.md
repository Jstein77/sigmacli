# code-rep-demo
Demo of common workflows with code-based sigma objects.

This script has a dependency on [Sigmoid](https://github.com/sigmacomputing/sigmoid). Clone this repo to your local machine and run the following command to install Sigmoid:
```
pip install sigmoid
```

## GitHub Actions

This repository includes a GitHub Actions workflow that automatically runs the `update_changed_data_models.py` script whenever data model YAML files are modified.

### Setup

To use the GitHub Actions workflow, configure the following secrets in your repository settings:

- `SIGMA_CLIENT_ID` - Your Sigma client ID
- `SIGMA_SECRET` - Your Sigma client secret
- `SIGMA_ORIGIN` - Your Sigma instance URL (e.g., `https://app.sigmacomputing.com`)

The sigmoid package will use these credentials to automatically generate an API key for authentication.

The workflow will:
1. Trigger on pushes to the `main` branch that modify files in `data-models/`
2. Can also be triggered manually via workflow_dispatch
3. Install the sigmoid package from GitHub
4. Run the update script to sync data models with Sigma
5. Commit any changes made by the script (e.g., server-assigned IDs)
