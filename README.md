# Sigma CLI
A CLI tool for managing Sigma data models with Git. It provides a simple interface for interacting with Sigma's data model APIs
and provides an easy workflow to write, review and deploy Sigma data models as code.

## Quick Start
1. To authenticate, add your Client ID, client secret, and base URL to credentials.yml in the .sigma directory.

``` yaml
profiles:
  default:
    base_url: https://api.staging.us.aws.sigmacomputing.io
    client_id: your_client_id
    client_secret: your_client_secret
```
2. Next install sigma-sdlc
```bash
pip install sigma-sdlc
```
3. Sync your data models:
```bash
sigma sync
```
You're ready to go!

## Features
* Authentication: A simple way to generate an auth token using a client and secret from Sigma
* Sync data models from Sigma to your Git repo: Sigma is the source of truth for data model code. The sync command makes sure your remote repo incorporates all changes made in Sigma
* Deploy data models to Sigma: Deploy all changes made locally to Sigma


## Essential Commands
* `sigma login`: Authenticates with Sigma and stores credentials
* `sigma sync`: Syncs data models from Sigma to your local repo
* `sigma deploy`: Deploys data models to Sigma

## Example Workflow
1. Make sure you have authenticated with `sigma login`
2. Sync data models from Sigma to your local repo with `sigma sync`
3. Make changes to the data models in your local repo
4. Deploy the changes to Sigma with `sigma deploy`
